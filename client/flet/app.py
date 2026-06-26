from __future__ import annotations

import argparse
import asyncio
import json
import threading
from typing import Any

import flet as ft
import websockets


DEFAULT_SERVER_URL = "ws://127.0.0.1:8000/ws"
TARGET_SAMPLE_RATE = 16000
CHUNK_FRAMES = 1600


def center_alignment() -> Any:
    if hasattr(ft, "Alignment"):
        return ft.Alignment(0, 0)

    alignment_module = getattr(ft, "alignment", None)
    center = getattr(alignment_module, "center", None)
    if center is not None:
        return center

    return None


def main(page: ft.Page) -> None:
    page.title = "Streaming ASR Flet Client"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16

    state: dict[str, Any] = {
        "loop": None,
        "websocket": None,
        "audio_queue": None,
        "stream": None,
        "connected": False,
        "recording": False,
    }
    final_lines: list[str] = []
    partial_line = {"stable": "", "unstable": ""}

    server_url = ft.TextField(label="WebSocket URL", value=DEFAULT_SERVER_URL, expand=True)
    language = ft.Dropdown(
        label="Language",
        width=120,
        value="ja",
        options=[
            ft.dropdown.Option("ja"),
            ft.dropdown.Option("en"),
            ft.dropdown.Option("zh"),
            ft.dropdown.Option("ko"),
            ft.dropdown.Option("auto"),
        ],
    )
    latency_ms = ft.TextField(label="Latency ms", value="1000", width=120)
    status = ft.Text("idle")
    event_log = ft.TextField(label="Event log", multiline=True, min_lines=10, max_lines=18, read_only=True)
    caption_text = ft.Text("", size=36, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
    caption_box = ft.Container(
        content=caption_text,
        bgcolor=ft.Colors.BLACK,
        opacity=0.75,
        padding=12,
        alignment=center_alignment(),
        border_radius=4,
        expand=True,
    )

    font_size = ft.Slider(label="Font size", min=16, max=96, divisions=80, value=36)
    line_count = ft.Slider(label="Lines", min=1, max=5, divisions=4, value=2)
    chars_per_line = ft.Slider(label="Chars/line", min=8, max=60, divisions=52, value=22)

    def safe_update() -> None:
        try:
            page.update()
        except Exception:
            pass

    def append_log(message: Any) -> None:
        line = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
        event_log.value = f"{line}\n{event_log.value or ''}"[:6000]
        safe_update()

    def set_status(value: str) -> None:
        status.value = value
        safe_update()

    def set_connected(value: bool) -> None:
        state["connected"] = value
        connect_button.disabled = value
        record_button.disabled = not value or state["recording"]
        stop_button.disabled = not value
        safe_update()

    def wrap_text(text: str, limit: int) -> list[str]:
        return [text[i : i + limit] for i in range(0, len(text), limit)] or [""]

    def render_caption() -> None:
        limit = int(chars_per_line.value)
        max_lines = int(line_count.value)
        stable_lines = [line for text in final_lines for line in wrap_text(text, limit)]
        partial_text = f"{partial_line['stable']}{partial_line['unstable']}"
        partial_lines = wrap_text(partial_text, limit) if partial_text else []
        caption_text.value = "\n".join([*stable_lines, *partial_lines][-max_lines:])
        caption_text.size = int(font_size.value)
        safe_update()

    def current_latency_ms() -> int:
        try:
            return max(0, int(latency_ms.value))
        except ValueError:
            return 1000

    def start_message() -> dict[str, Any]:
        return {
            "type": "start",
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 1,
            "format": "pcm_s16le",
            "language": language.value,
            "task": "transcribe",
            "latency_ms": current_latency_ms(),
            "vad_mode": "server",
        }

    def send_json(payload: dict[str, Any]) -> None:
        loop = state.get("loop")
        websocket = state.get("websocket")
        if not loop or not websocket:
            return
        asyncio.run_coroutine_threadsafe(websocket.send(json.dumps(payload)), loop)

    async def send_audio_loop(websocket: Any, audio_queue: asyncio.Queue[bytes]) -> None:
        while True:
            chunk = await audio_queue.get()
            await websocket.send(chunk)

    async def receive_loop(websocket: Any) -> None:
        nonlocal final_lines, partial_line
        async for raw in websocket:
            message = json.loads(raw)
            append_log(message)

            if message["type"] == "ready":
                await websocket.send(json.dumps(start_message()))
            elif message["type"] == "config":
                set_status(f"connected {message.get('session_id', '')}")
                set_connected(True)
            elif message["type"] == "audio_received":
                set_status("recording")
            elif message["type"] == "partial":
                partial_line = {
                    "stable": message.get("stable_text", ""),
                    "unstable": message.get("unstable_text", ""),
                }
                render_caption()
            elif message["type"] == "final":
                text = message.get("text") or f"{message.get('stable_text', '')}{message.get('unstable_text', '')}"
                if text:
                    final_lines = [*final_lines, text][-20:]
                partial_line = {"stable": "", "unstable": ""}
                render_caption()
            elif message["type"] == "stopped":
                set_status("stopped")
                break
            elif message["type"] == "error":
                set_status("error")

    async def client_loop() -> None:
        set_status("connecting")
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=20)
        state["loop"] = asyncio.get_running_loop()
        state["audio_queue"] = audio_queue
        sender_task = None
        try:
            async with websockets.connect(server_url.value, max_size=None) as websocket:
                state["websocket"] = websocket
                sender_task = asyncio.create_task(send_audio_loop(websocket, audio_queue))
                await receive_loop(websocket)
        except Exception as exc:  # noqa: BLE001 - show UI-visible connection errors.
            append_log(f"error: {exc}")
            set_status("error")
        finally:
            if sender_task:
                sender_task.cancel()
            stop_microphone(send_stop=False)
            state["websocket"] = None
            state["audio_queue"] = None
            state["loop"] = None
            set_connected(False)

    def enqueue_audio(chunk: bytes) -> None:
        loop = state.get("loop")
        audio_queue = state.get("audio_queue")
        if not loop or not audio_queue:
            return

        def put_chunk() -> None:
            try:
                audio_queue.put_nowait(chunk)
            except asyncio.QueueFull:
                pass

        loop.call_soon_threadsafe(put_chunk)

    def start_microphone() -> None:
        if not state["connected"]:
            set_status("not connected")
            return
        if state["recording"]:
            return
        try:
            import sounddevice as sd
        except ImportError:
            append_log("error: sounddevice is not installed")
            set_status("microphone unavailable")
            return

        def audio_callback(indata: Any, frames: int, time_info: Any, status_flags: Any) -> None:
            if status_flags:
                append_log(f"audio status: {status_flags}")
            enqueue_audio(bytes(indata))

        try:
            stream = sd.RawInputStream(
                samplerate=TARGET_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=CHUNK_FRAMES,
                callback=audio_callback,
            )
            stream.start()
        except Exception as exc:  # noqa: BLE001 - show UI-visible audio errors.
            append_log(f"microphone error: {exc}")
            set_status("microphone error")
            return

        state["stream"] = stream
        state["recording"] = True
        record_button.disabled = True
        stop_button.disabled = False
        set_status("recording")
        safe_update()

    def stop_microphone(send_stop: bool = True) -> None:
        stream = state.get("stream")
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:  # noqa: BLE001 - show UI-visible audio errors.
                append_log(f"microphone close error: {exc}")
        state["stream"] = None
        state["recording"] = False
        if send_stop:
            send_json({"type": "stop"})
        record_button.disabled = not state["connected"]
        safe_update()

    def connect() -> None:
        if state.get("connected") or state.get("loop"):
            return
        threading.Thread(target=lambda: asyncio.run(client_loop()), daemon=True).start()

    connect_button = ft.ElevatedButton("Connect", on_click=lambda _: connect())
    record_button = ft.ElevatedButton("Record", disabled=True, on_click=lambda _: start_microphone())
    stop_button = ft.ElevatedButton("Stop", disabled=True, on_click=lambda _: stop_microphone())

    def update_language(_: Any) -> None:
        send_json({"type": "config", "language": language.value, "language_apply": "next_utterance"})

    def update_latency(_: Any) -> None:
        send_json({"type": "config", "latency_ms": current_latency_ms()})

    language.on_change = update_language
    latency_ms.on_change = update_latency

    for control in [font_size, line_count, chars_per_line]:
        control.on_change = lambda _: render_caption()

    page.add(
        ft.Row(
            [server_url, language, latency_ms, connect_button, record_button, stop_button, status],
            vertical_alignment=ft.CrossAxisAlignment.END,
        ),
        caption_box,
        ft.Row([font_size, line_count, chars_per_line]),
        event_log,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Streaming ASR Flet client")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8550)
    parser.add_argument(
        "--web",
        action="store_true",
        help="Run as a standalone Flet web app in the browser",
    )
    return parser


def run() -> None:
    args = build_parser().parse_args()
    global DEFAULT_SERVER_URL
    DEFAULT_SERVER_URL = args.server_url

    if args.web:
        ft.app(
            target=main,
            view=ft.AppView.WEB_BROWSER,
            host=args.host,
            port=args.port,
        )
    else:
        ft.app(target=main)


if __name__ == "__main__":
    run()
