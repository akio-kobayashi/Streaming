from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import json
import math
import os
import ssl
import struct
import sys
import threading
import time
import zlib
from pathlib import Path
from typing import Any

import flet as ft
import websockets


DEFAULT_SERVER_URL = "ws://127.0.0.1:8000/ws"
TARGET_SAMPLE_RATE = 16000
CHUNK_FRAMES = 1600
LEVEL_FLOOR_DB = -60
LEVEL_SEGMENTS = 30
SPECTROGRAM_WIDTH = 640
SPECTROGRAM_HEIGHT = 220
SPECTROGRAM_FFT_SIZE = 256
SPECTROGRAM_BINS = 96
SPECTROGRAM_UPDATE_INTERVAL_S = 0.08
CLIENT_CONFIG_PATH = Path.home() / ".streaming-asr-client" / "config.json"


def load_client_settings() -> dict[str, Any]:
    try:
        with CLIENT_CONFIG_PATH.open("r", encoding="utf-8") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return settings if isinstance(settings, dict) else {}


def save_client_settings(settings: dict[str, Any]) -> None:
    try:
        CLIENT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CLIENT_CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def png_data_url(width: int, height: int, rgb: bytes) -> str:
    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)

    raw = b"".join(
        b"\x00" + rgb[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )
    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw, 1)),
            chunk(b"IEND", b""),
        ]
    )
    encoded = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


AUDACITY_COLORMAP: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (0, 0, 0)),
    (0.08, (0, 7, 18)),
    (0.18, (0, 28, 61)),
    (0.34, (27, 28, 116)),
    (0.5, (108, 32, 157)),
    (0.66, (206, 31, 169)),
    (0.78, (255, 65, 92)),
    (0.9, (255, 155, 48)),
    (1.0, (255, 244, 176)),
)


def audacity_color(value: float) -> tuple[int, int, int]:
    x = max(0.0, min(1.0, value))
    for index in range(1, len(AUDACITY_COLORMAP)):
        right_stop, right_color = AUDACITY_COLORMAP[index]
        left_stop, left_color = AUDACITY_COLORMAP[index - 1]
        if x <= right_stop:
            t = (x - left_stop) / max(0.0001, right_stop - left_stop)
            return tuple(
                round(left_color[channel] + (right_color[channel] - left_color[channel]) * t)
                for channel in range(3)
            )
    return AUDACITY_COLORMAP[-1][1]


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
    settings = load_client_settings()

    state: dict[str, Any] = {
        "loop": None,
        "websocket": None,
        "audio_queue": None,
        "stream": None,
        "connected": False,
        "recording": False,
        "connecting": False,
        "audio_callbacks": 0,
        "level_update_pending": False,
        "spectrogram_update_pending": False,
        "last_spectrogram_update": 0.0,
    }
    final_lines: list[str] = []
    partial_line = {"stable": "", "unstable": ""}

    server_url = ft.TextField(
        label="WebSocket URL",
        value=os.environ.get("STREAMING_ASR_SERVER_URL") or settings.get("server_url") or DEFAULT_SERVER_URL,
        expand=True,
    )
    insecure_tls = ft.Checkbox(
        label="Insecure TLS",
        value=bool(settings.get("insecure_tls", False)),
        tooltip="Disable WSS certificate verification for private test servers only.",
    )
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
    level_value = ft.Text("-inf dB", width=72, text_align=ft.TextAlign.RIGHT)
    level_segments = [
        ft.Container(width=10, height=18, bgcolor=ft.Colors.BLUE_GREY_900, border_radius=1)
        for _ in range(LEVEL_SEGMENTS)
    ]
    level_meter = ft.Container(
        content=ft.Row(level_segments, spacing=2),
        padding=6,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
        border_radius=6,
        bgcolor=ft.Colors.BLUE_GREY_900,
    )
    level_bar = ft.ProgressBar(value=0, width=220, height=10, color=ft.Colors.GREEN, bgcolor=ft.Colors.BLUE_GREY_900)
    progress_ring = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
    spectrogram_pixels = bytearray(SPECTROGRAM_WIDTH * SPECTROGRAM_HEIGHT * 3)
    spectrogram_image = ft.Image(
        src=png_data_url(SPECTROGRAM_WIDTH, SPECTROGRAM_HEIGHT, bytes(spectrogram_pixels)),
        width=SPECTROGRAM_WIDTH,
        height=SPECTROGRAM_HEIGHT,
        fit=ft.BoxFit.COVER,
        gapless_playback=True,
    )
    spectrogram_stage = ft.Container(
        content=ft.Stack(
            [
                spectrogram_image,
                ft.Container(
                    content=caption_text,
                    bgcolor=ft.Colors.BLACK,
                    opacity=0.75,
                    padding=12,
                    alignment=center_alignment(),
                    border_radius=4,
                    left=28,
                    right=28,
                    bottom=24,
                ),
            ],
            width=SPECTROGRAM_WIDTH,
            height=SPECTROGRAM_HEIGHT,
        ),
        bgcolor=ft.Colors.BLACK,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_800),
        border_radius=8,
        padding=0,
    )
    final_log = ft.Column([], spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
    partial_stable_text = ft.Text("", color=ft.Colors.WHITE)
    partial_unstable_text = ft.Text("", color=ft.Colors.AMBER)
    partial_box = ft.Container(
        visible=False,
        content=ft.Row([partial_stable_text, partial_unstable_text], spacing=0),
        padding=8,
        border=ft.Border.all(1, ft.Colors.AMBER),
        bgcolor=ft.Colors.BLUE_GREY_900,
        border_radius=4,
    )
    transcript_box = ft.Container(
        content=ft.Column([final_log, partial_box], spacing=6, alignment=ft.MainAxisAlignment.END),
        height=180,
        padding=10,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_800),
        border_radius=8,
        bgcolor=ft.Colors.BLACK,
    )

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
        progress_ring.visible = value in {"connecting", "recording"}
        safe_update()

    def set_connected(value: bool) -> None:
        state["connected"] = value
        state["connecting"] = False
        connect_button.disabled = value
        record_button.disabled = not value or state["recording"]
        stop_button.disabled = not value
        safe_update()

    def set_connecting(value: bool) -> None:
        state["connecting"] = value
        connect_button.disabled = value
        record_button.disabled = True
        stop_button.disabled = True
        safe_update()

    def current_server_url() -> str:
        return str(server_url.value or "").strip()

    def connection_ssl_context(url: str) -> ssl.SSLContext | None:
        if not url.startswith("wss://"):
            return None
        if not insecure_tls.value:
            return None
        return ssl._create_unverified_context()

    def websocket_connect_kwargs(url: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "max_size": None,
            "open_timeout": 10,
        }
        ssl_context = connection_ssl_context(url)
        if ssl_context is not None:
            kwargs["ssl"] = ssl_context
        return kwargs

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

    def level_color(index: int) -> str:
        ratio = index / max(1, LEVEL_SEGMENTS - 1)
        if ratio >= 0.84:
            return ft.Colors.RED
        if ratio >= 0.68:
            return ft.Colors.AMBER
        return ft.Colors.GREEN

    def reset_level_meter() -> None:
        for segment in level_segments:
            segment.bgcolor = ft.Colors.BLUE_GREY_900
        level_value.value = "-inf dB"
        safe_update()

    def update_level_meter(chunk: bytes) -> None:
        samples = memoryview(chunk).cast("h")
        if len(samples) == 0:
            reset_level_meter()
            return

        sum_squares = 0.0
        for sample in samples:
            normalized = sample / 32768.0
            sum_squares += normalized * normalized
        rms = math.sqrt(sum_squares / len(samples))
        db = 20 * math.log10(max(rms, 0.000001))
        clamped_db = max(LEVEL_FLOOR_DB, min(0.0, db))
        active_segments = round(((clamped_db - LEVEL_FLOOR_DB) / abs(LEVEL_FLOOR_DB)) * LEVEL_SEGMENTS)
        for index, segment in enumerate(level_segments):
            segment.bgcolor = level_color(index) if index < active_segments else ft.Colors.BLUE_GREY_900
        level_value.value = "-inf dB" if db <= LEVEL_FLOOR_DB else f"{clamped_db:.1f} dB"
        level_ratio = max(0.0, min(1.0, (clamped_db - LEVEL_FLOOR_DB) / abs(LEVEL_FLOOR_DB)))
        level_bar.value = level_ratio
        if level_ratio >= 0.84:
            level_bar.color = ft.Colors.RED
        elif level_ratio >= 0.68:
            level_bar.color = ft.Colors.AMBER
        else:
            level_bar.color = ft.Colors.GREEN
        safe_update()

    def schedule_level_update(chunk: bytes) -> None:
        loop = state.get("loop")
        if not loop:
            return
        if state["level_update_pending"]:
            return
        state["level_update_pending"] = True

        def update() -> None:
            state["level_update_pending"] = False
            update_level_meter(chunk)

        loop.call_soon_threadsafe(update)

    def clear_spectrogram() -> None:
        spectrogram_pixels[:] = b"\x00" * len(spectrogram_pixels)
        spectrogram_image.src = png_data_url(SPECTROGRAM_WIDTH, SPECTROGRAM_HEIGHT, bytes(spectrogram_pixels))
        safe_update()

    def draw_spectrogram_column(samples: list[int]) -> None:
        if len(samples) < SPECTROGRAM_FFT_SIZE:
            samples = [0] * (SPECTROGRAM_FFT_SIZE - len(samples)) + samples
        else:
            samples = samples[-SPECTROGRAM_FFT_SIZE:]

        normalized = [sample / 32768.0 for sample in samples]
        magnitudes: list[float] = []
        for bin_index in range(1, SPECTROGRAM_BINS + 1):
            k = bin_index * (SPECTROGRAM_FFT_SIZE // 2) / SPECTROGRAM_BINS
            real = 0.0
            imag = 0.0
            for n, value in enumerate(normalized):
                angle = 2.0 * math.pi * k * n / SPECTROGRAM_FFT_SIZE
                real += value * math.cos(angle)
                imag -= value * math.sin(angle)
            magnitude = math.sqrt(real * real + imag * imag) / SPECTROGRAM_FFT_SIZE
            db = 20.0 * math.log10(max(magnitude, 0.000001))
            magnitudes.append(max(0.0, min(1.0, (db + 80.0) / 80.0)))

        row_stride = SPECTROGRAM_WIDTH * 3
        for y in range(SPECTROGRAM_HEIGHT):
            row_start = y * row_stride
            row_end = row_start + row_stride
            spectrogram_pixels[row_start : row_end - 3] = spectrogram_pixels[row_start + 3 : row_end]
            bin_pos = int((1.0 - y / max(1, SPECTROGRAM_HEIGHT - 1)) * (SPECTROGRAM_BINS - 1))
            color = audacity_color(magnitudes[bin_pos])
            pixel_index = row_end - 3
            spectrogram_pixels[pixel_index : pixel_index + 3] = bytes(color)

        spectrogram_image.src = png_data_url(SPECTROGRAM_WIDTH, SPECTROGRAM_HEIGHT, bytes(spectrogram_pixels))
        safe_update()

    def schedule_spectrogram_update(chunk: bytes) -> None:
        loop = state.get("loop")
        if not loop:
            return
        now = time.monotonic()
        if now - state["last_spectrogram_update"] < SPECTROGRAM_UPDATE_INTERVAL_S:
            return
        if state["spectrogram_update_pending"]:
            return
        state["last_spectrogram_update"] = now
        state["spectrogram_update_pending"] = True
        samples = list(memoryview(chunk).cast("h"))

        def update() -> None:
            state["spectrogram_update_pending"] = False
            draw_spectrogram_column(samples)

        loop.call_soon_threadsafe(update)

    def render_transcript() -> None:
        final_log.controls = [
            ft.Container(
                content=ft.Text(text, color=ft.Colors.BLACK),
                bgcolor=ft.Colors.WHITE,
                padding=8,
                border_radius=4,
            )
            for text in final_lines[-20:]
        ]
        partial_stable_text.value = partial_line["stable"]
        partial_unstable_text.value = partial_line["unstable"]
        partial_box.visible = bool(partial_line["stable"] or partial_line["unstable"])
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
                render_transcript()
                render_caption()
            elif message["type"] == "final":
                text = message.get("text") or f"{message.get('stable_text', '')}{message.get('unstable_text', '')}"
                if text:
                    final_lines = [*final_lines, text][-20:]
                partial_line = {"stable": "", "unstable": ""}
                render_transcript()
                render_caption()
            elif message["type"] == "stopped":
                set_status("stopped")
                break
            elif message["type"] == "error":
                set_status("error")

    async def client_loop() -> None:
        url = current_server_url()
        if not url:
            append_log("error: WebSocket URL is empty")
            set_status("error")
            return
        save_client_settings({"server_url": url, "insecure_tls": bool(insecure_tls.value)})
        append_log(f"connecting: {url}")
        set_status("connecting")
        set_connecting(True)
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=20)
        state["loop"] = asyncio.get_running_loop()
        state["audio_queue"] = audio_queue
        sender_task = None
        try:
            async with websockets.connect(url, **websocket_connect_kwargs(url)) as websocket:
                state["websocket"] = websocket
                sender_task = asyncio.create_task(send_audio_loop(websocket, audio_queue))
                await receive_loop(websocket)
        except Exception as exc:  # noqa: BLE001 - show UI-visible connection errors.
            append_log(f"connection error: {type(exc).__name__}: {exc}")
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
            append_log("microphone: not connected")
            return
        if state["recording"]:
            return
        try:
            import sounddevice as sd
        except ImportError:
            append_log("error: sounddevice is not installed")
            set_status("microphone unavailable")
            return

        append_log("microphone: opening")
        try:
            default_input = sd.default.device[0]
            append_log(f"microphone default input: {default_input}")
            if default_input is not None and default_input >= 0:
                append_log(str(sd.query_devices(default_input)))
            else:
                append_log("microphone error: no default input device")
                set_status("microphone unavailable")
                return
        except Exception as exc:  # noqa: BLE001 - show UI-visible audio errors.
            append_log(f"microphone device query error: {type(exc).__name__}: {exc}")

        def audio_callback(indata: Any, frames: int, time_info: Any, status_flags: Any) -> None:
            if status_flags:
                append_log(f"audio status: {status_flags}")
            chunk = bytes(indata)
            state["audio_callbacks"] += 1
            if state["audio_callbacks"] == 1:
                append_log(f"microphone: first audio callback frames={frames} bytes={len(chunk)}")
            schedule_level_update(chunk)
            schedule_spectrogram_update(chunk)
            enqueue_audio(chunk)

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
            append_log(f"microphone error: {type(exc).__name__}: {exc}")
            set_status("microphone error")
            return

        state["stream"] = stream
        state["recording"] = True
        state["audio_callbacks"] = 0
        record_button.disabled = True
        stop_button.disabled = False
        append_log("microphone: stream started")
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
        reset_level_meter()
        append_log(f"microphone: stopped callbacks={state['audio_callbacks']}")
        if send_stop:
            send_json({"type": "stop"})
        record_button.disabled = not state["connected"]
        safe_update()

    def connect() -> None:
        if state.get("connected") or state.get("connecting") or state.get("loop"):
            return
        set_status("connecting")
        set_connecting(True)
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
            [server_url, insecure_tls, language, latency_ms, connect_button, record_button, stop_button, progress_ring, status],
            vertical_alignment=ft.CrossAxisAlignment.END,
        ),
        ft.Row([ft.Text("Input level"), level_meter, level_bar, level_value], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        spectrogram_stage,
        ft.Row([font_size, line_count, chars_per_line]),
        transcript_box,
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


def configure_local_flet_runtime() -> None:
    if sys.platform != "darwin" or os.environ.get("FLET_CLIENT_URL"):
        return

    repo_root = Path(__file__).resolve().parents[2]
    archive = repo_root / "vendor" / "flet-desktop" / "flet-macos.tar.gz"
    if archive.is_file():
        os.environ["FLET_CLIENT_URL"] = archive.as_uri()


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
        configure_local_flet_runtime()
        ft.app(target=main)


if __name__ == "__main__":
    run()
