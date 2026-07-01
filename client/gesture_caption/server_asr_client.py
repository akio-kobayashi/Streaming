from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class AsrResult:
    text: str
    stable_text: str = ""
    unstable_text: str = ""
    is_final: bool = False
    received_at: float = 0.0


class ServerAsrClient:
    def __init__(
        self,
        server_url: str,
        audio_queue: queue.Queue[bytes],
        *,
        sample_rate: int,
        channels: int,
        language: str,
        latency_ms: int,
    ) -> None:
        self.server_url = server_url
        self.audio_queue = audio_queue
        self.sample_rate = sample_rate
        self.channels = channels
        self.language = language
        self.latency_ms = latency_ms
        self.results: queue.Queue[AsrResult] = queue.Queue()
        self.events: queue.Queue[str] = queue.Queue(maxsize=50)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._websocket: Any = None
        self._configured_event: asyncio.Event | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop and self._websocket:
            asyncio.run_coroutine_threadsafe(self._send_stop(), self._loop)
        if self._thread:
            self._thread.join(timeout=3)

    async def _send_stop(self) -> None:
        try:
            await self._websocket.send(json.dumps({"type": "stop"}))
        except Exception:
            pass

    async def _run(self) -> None:
        import websockets

        self._loop = asyncio.get_running_loop()
        self._configured_event = asyncio.Event()
        try:
            async with websockets.connect(self.server_url, max_size=None) as websocket:
                self._websocket = websocket
                sender = asyncio.create_task(self._send_audio_loop(websocket))
                receiver = asyncio.create_task(self._receive_loop(websocket))
                done, pending = await asyncio.wait(
                    {sender, receiver},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    task.result()
        except Exception as exc:  # noqa: BLE001 - visible client status.
            self._put_event(f"asr error: {exc}")
        finally:
            self._websocket = None
            self._loop = None
            self._configured_event = None

    async def _send_audio_loop(self, websocket: Any) -> None:
        while not self._stop_event.is_set():
            if self._configured_event is None or not self._configured_event.is_set():
                await asyncio.sleep(0.02)
                continue
            try:
                chunk = await asyncio.to_thread(self.audio_queue.get, True, 0.1)
            except queue.Empty:
                continue
            await websocket.send(chunk)

    async def _receive_loop(self, websocket: Any) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            message_type = message.get("type")
            if message_type == "ready":
                await websocket.send(json.dumps(self._start_message()))
            elif message_type == "config":
                if self._configured_event is not None:
                    self._configured_event.set()
                self._put_event("asr connected")
            elif message_type == "partial":
                stable = message.get("stable_text", "")
                unstable = message.get("unstable_text", "")
                self.results.put(
                    AsrResult(
                        text=f"{stable}{unstable}",
                        stable_text=stable,
                        unstable_text=unstable,
                        is_final=False,
                        received_at=time.time(),
                    )
                )
            elif message_type == "final":
                text = message.get("text") or f"{message.get('stable_text', '')}{message.get('unstable_text', '')}"
                self.results.put(AsrResult(text=text, is_final=True, received_at=time.time()))
            elif message_type == "stopped":
                self._put_event("asr stopped")
                return
            elif message_type == "error":
                self._put_event(f"asr server error: {message.get('message', '')}")

    def _start_message(self) -> dict[str, Any]:
        return {
            "type": "start",
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": "pcm_s16le",
            "language": self.language,
            "task": "transcribe",
            "latency_ms": self.latency_ms,
            "vad_mode": "server",
        }

    def _put_event(self, text: str) -> None:
        try:
            self.events.put_nowait(text)
        except queue.Full:
            pass
