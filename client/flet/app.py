from __future__ import annotations

import argparse
import asyncio
import json
import threading
from typing import Any

import flet as ft
import websockets


DEFAULT_SERVER_URL = "ws://127.0.0.1:8000/ws"


def main(page: ft.Page) -> None:
    page.title = "Streaming ASR Flet Client"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16

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
    status = ft.Text("idle")
    event_log = ft.TextField(label="Event log", multiline=True, min_lines=10, max_lines=18, read_only=True)
    caption_text = ft.Text("", size=36, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
    caption_box = ft.Container(
        content=caption_text,
        bgcolor=ft.Colors.BLACK,
        opacity=0.75,
        padding=12,
        alignment=ft.alignment.center,
        border_radius=4,
        expand=True,
    )

    font_size = ft.Slider(label="Font size", min=16, max=96, divisions=80, value=36)
    line_count = ft.Slider(label="Lines", min=1, max=5, divisions=4, value=2)
    chars_per_line = ft.Slider(label="Chars/line", min=8, max=60, divisions=52, value=22)

    def append_log(message: Any) -> None:
        line = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
        event_log.value = f"{line}\n{event_log.value or ''}"[:6000]
        page.update()

    def set_status(value: str) -> None:
        status.value = value
        page.update()

    def render_caption(text: str) -> None:
        limit = int(chars_per_line.value)
        lines = [text[i : i + limit] for i in range(0, len(text), limit)] or [""]
        caption_text.value = "\n".join(lines[-int(line_count.value) :])
        caption_text.size = int(font_size.value)
        page.update()

    async def smoke_test() -> None:
        set_status("connecting")
        audio_received = 0
        stopped = False
        try:
            async with websockets.connect(server_url.value, max_size=None) as websocket:
                set_status("connected")
                async for raw in websocket:
                    message = json.loads(raw)
                    append_log(message)
                    if message["type"] == "ready":
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "start",
                                    "sample_rate": 16000,
                                    "channels": 1,
                                    "format": "pcm_s16le",
                                    "language": language.value,
                                    "task": "transcribe",
                                    "latency_ms": 1000,
                                    "vad_mode": "server",
                                }
                            )
                        )
                    elif message["type"] == "config":
                        await websocket.send(bytes(1600))
                        await websocket.send(bytes(1600))
                        await websocket.send(bytes(1600))
                        await websocket.send(json.dumps({"type": "stop"}))
                    elif message["type"] == "audio_received":
                        audio_received += 1
                        render_caption(f"audio_received: {audio_received}")
                    elif message["type"] == "partial":
                        render_caption(f"{message.get('stable_text', '')}{message.get('unstable_text', '')}")
                    elif message["type"] == "final":
                        render_caption(message.get("text", ""))
                    elif message["type"] == "stopped":
                        stopped = True
                        set_status("stopped")
                        break
        except Exception as exc:  # noqa: BLE001 - show UI-visible connection errors.
            append_log(f"error: {exc}")
            set_status("error")
            return

        if audio_received >= 1 and stopped:
            set_status("ok")
        else:
            set_status("failed")

    def run_async(coro) -> None:
        threading.Thread(target=lambda: asyncio.run(coro), daemon=True).start()

    connect_button = ft.ElevatedButton("Smoke test", on_click=lambda _: run_async(smoke_test()))

    for control in [font_size, line_count, chars_per_line]:
        control.on_change = lambda _: render_caption(caption_text.value)

    page.add(
        ft.Row([server_url, language, connect_button, status], vertical_alignment=ft.CrossAxisAlignment.END),
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
