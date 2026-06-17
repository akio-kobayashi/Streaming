from __future__ import annotations

import argparse
import json
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .config import AppConfig, load_config
from .schemas import MessageError, parse_client_message, server_event
from .session import SessionState, create_session


def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or AppConfig()
    app = FastAPI(title="Streaming Multilingual ASR")
    app.state.config = app_config

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        session: SessionState | None = None
        await websocket.send_json(server_event("ready"))

        try:
            while True:
                message = await websocket.receive()
                if "text" in message:
                    session = await _handle_text_message(websocket, message["text"], session, app_config)
                elif "bytes" in message:
                    await _handle_audio_message(websocket, message["bytes"], session)
        except WebSocketDisconnect:
            return

    return app


async def _handle_text_message(
    websocket: WebSocket,
    raw_text: str,
    session: SessionState | None,
    app_config: AppConfig,
) -> SessionState | None:
    try:
        parsed_json: Any = json.loads(raw_text)
        message = parse_client_message(parsed_json)
    except (json.JSONDecodeError, MessageError, TypeError, ValueError) as exc:
        await websocket.send_json(server_event("error", message=str(exc)))
        return session

    if message["type"] == "start":
        session = create_session(message, app_config)
        await websocket.send_json(
            server_event(
                "config",
                session_id=session.session_id,
                sample_rate=session.sample_rate,
                channels=session.channels,
                format=session.audio_format,
                language=session.language,
                task=session.task,
                latency_ms=session.latency_ms,
                vad_mode=session.vad_mode,
            )
        )
        return session

    if message["type"] == "config":
        if session is None:
            await websocket.send_json(server_event("error", message="start message required before config"))
            return session
        changed = session.apply_config(message)
        await websocket.send_json(server_event("config", session_id=session.session_id, **changed))
        return session

    if message["type"] == "stop":
        if session is not None:
            await websocket.send_json(
                server_event(
                    "stopped",
                    session_id=session.session_id,
                    chunks_received=session.chunks_received,
                    bytes_received=session.bytes_received,
                    audio_ms_received=session.audio_ms_received,
                )
            )
        await websocket.close()
        return session

    await websocket.send_json(server_event("error", message=f"unhandled message: {message['type']}"))
    return session


async def _handle_audio_message(
    websocket: WebSocket,
    data: bytes,
    session: SessionState | None,
) -> None:
    if session is None:
        await websocket.send_json(server_event("error", message="start message required before audio"))
        return
    session.add_audio(data)
    await websocket.send_json(
        server_event(
            "audio_received",
            session_id=session.session_id,
            chunks_received=session.chunks_received,
            bytes_received=session.bytes_received,
            audio_ms_received=session.audio_ms_received,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Streaming Multilingual ASR server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    app = create_app(load_config(args.config))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
