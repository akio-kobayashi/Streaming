from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .config import AppConfig, load_config
from .schemas import MessageError, parse_client_message, server_event
from .session import SessionState, create_session
from .vad_worker import SileroVadWorker, SpeechSegment
from .whisper_worker import FasterWhisperWorker, TranscriptionResult


logger = logging.getLogger("uvicorn.error")


def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or AppConfig()
    app = FastAPI(title="Streaming Multilingual ASR")
    app.state.config = app_config
    app.state.asr_worker = FasterWhisperWorker(app_config.whisper)
    app.state.vad_worker = SileroVadWorker(app_config.vad)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        session: SessionState | None = None
        logger.info("websocket connected client=%s", websocket.client)
        await websocket.send_json(server_event("ready"))

        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    logger.info(
                        "websocket disconnected client=%s session_id=%s",
                        websocket.client,
                        session.session_id if session else None,
                    )
                    return
                if message["type"] == "websocket.receive" and "text" in message:
                    session = await _handle_text_message(
                        websocket,
                        message["text"],
                        session,
                        app_config,
                        app.state.asr_worker,
                    )
                elif message["type"] == "websocket.receive" and "bytes" in message:
                    await _handle_audio_message(
                        websocket,
                        message["bytes"],
                        session,
                        app_config,
                        app.state.asr_worker,
                        app.state.vad_worker,
                    )
        except WebSocketDisconnect:
            logger.info(
                "websocket disconnected client=%s session_id=%s",
                websocket.client,
                session.session_id if session else None,
            )
            return

    return app


async def _handle_text_message(
    websocket: WebSocket,
    raw_text: str,
    session: SessionState | None,
    app_config: AppConfig,
    asr_worker: FasterWhisperWorker,
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
            await _send_final(websocket, session, app_config, asr_worker)
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
    app_config: AppConfig,
    asr_worker: FasterWhisperWorker,
    vad_worker: SileroVadWorker,
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
    if session.vad_mode == "server":
        await _handle_vad_audio(websocket, session, app_config, asr_worker, vad_worker)
    else:
        await _send_partial_if_due(websocket, session, app_config, asr_worker)


async def _handle_vad_audio(
    websocket: WebSocket,
    session: SessionState,
    app_config: AppConfig,
    asr_worker: FasterWhisperWorker,
    vad_worker: SileroVadWorker,
) -> None:
    if session.audio_ms_received - session.last_vad_audio_ms < app_config.streaming.decode_interval_ms:
        return
    session.last_vad_audio_ms = session.audio_ms_received

    segment = await _first_unfinalized_speech_segment(session, vad_worker)
    if segment is None:
        return

    utterance_id = await _ensure_utterance_started(websocket, session, segment)
    total_samples = len(session.audio_buffer) // 2
    silence_samples = total_samples - segment.end
    min_silence_samples = int(session.sample_rate * app_config.vad.min_silence_ms / 1000)

    if silence_samples >= min_silence_samples:
        await _send_segment_final(websocket, session, asr_worker, segment, utterance_id)
        await websocket.send_json(
            server_event(
                "utterance_end",
                session_id=session.session_id,
                utterance_id=utterance_id,
                start_ms=int(segment.start / session.sample_rate * 1000),
                end_ms=int(segment.end / session.sample_rate * 1000),
            )
        )
        session.finalized_sample = max(session.finalized_sample, segment.end)
        session.active_utterance_id = None
        session.last_partial_text = ""
        return

    await _send_segment_partial_if_due(websocket, session, asr_worker, segment, utterance_id)


async def _first_unfinalized_speech_segment(
    session: SessionState,
    vad_worker: SileroVadWorker,
) -> SpeechSegment | None:
    segments = await asyncio.to_thread(
        vad_worker.get_speech_segments,
        bytes(session.audio_buffer),
        sample_rate=session.sample_rate,
    )
    for segment in segments:
        if segment.end > session.finalized_sample:
            return segment
    return None


async def _ensure_utterance_started(
    websocket: WebSocket,
    session: SessionState,
    segment: SpeechSegment,
) -> str:
    if session.active_utterance_id is not None:
        return session.active_utterance_id

    session.utterance_index += 1
    session.active_utterance_id = f"u-{session.utterance_index:04d}"
    session.last_partial_text = ""
    await websocket.send_json(
        server_event(
            "utterance_start",
            session_id=session.session_id,
            utterance_id=session.active_utterance_id,
            start_ms=int(segment.start / session.sample_rate * 1000),
        )
    )
    return session.active_utterance_id


async def _send_partial_if_due(
    websocket: WebSocket,
    session: SessionState,
    app_config: AppConfig,
    asr_worker: FasterWhisperWorker,
) -> None:
    if session.audio_ms_received < max(500, app_config.streaming.decode_interval_ms):
        return
    if session.audio_ms_received - session.last_decode_audio_ms < app_config.streaming.decode_interval_ms:
        return

    session.last_decode_audio_ms = session.audio_ms_received
    result = await _transcribe_bytes(session, asr_worker, bytes(session.audio_buffer))
    if not result.text or result.text == session.last_partial_text:
        return

    stable_text, unstable_text = _split_stable_unstable(session.last_partial_text, result.text)
    session.last_partial_text = result.text
    await websocket.send_json(
        server_event(
            "partial",
            session_id=session.session_id,
            utterance_id="u-0001",
            language=result.language,
            text=result.text,
            stable_text=stable_text,
            unstable_text=unstable_text,
        )
    )


async def _send_segment_partial_if_due(
    websocket: WebSocket,
    session: SessionState,
    asr_worker: FasterWhisperWorker,
    segment: SpeechSegment,
    utterance_id: str,
) -> None:
    if session.audio_ms_received - session.last_decode_audio_ms < 1:
        return

    session.last_decode_audio_ms = session.audio_ms_received
    data = _slice_pcm_s16le(session, segment.start, len(session.audio_buffer) // 2)
    result = await _transcribe_bytes(session, asr_worker, data)
    if not result.text or result.text == session.last_partial_text:
        return

    stable_text, unstable_text = _split_stable_unstable(session.last_partial_text, result.text)
    session.last_partial_text = result.text
    await websocket.send_json(
        server_event(
            "partial",
            session_id=session.session_id,
            utterance_id=utterance_id,
            language=result.language,
            text=result.text,
            stable_text=stable_text,
            unstable_text=unstable_text,
        )
    )


async def _send_final(
    websocket: WebSocket,
    session: SessionState,
    app_config: AppConfig,
    asr_worker: FasterWhisperWorker,
) -> None:
    if not session.audio_buffer:
        return

    if session.vad_mode == "server":
        if session.active_utterance_id is None:
            return
        segment = SpeechSegment(session.finalized_sample, len(session.audio_buffer) // 2)
        await _send_segment_final(websocket, session, asr_worker, segment, session.active_utterance_id)
        return

    result = await _transcribe_bytes(session, asr_worker, bytes(session.audio_buffer))
    if not result.text:
        return

    session.last_partial_text = result.text
    await websocket.send_json(
        server_event(
            "final",
            session_id=session.session_id,
            utterance_id="u-0001",
            language=result.language,
            text=result.text,
            stable_text=result.text,
            unstable_text="",
        )
    )


async def _send_segment_final(
    websocket: WebSocket,
    session: SessionState,
    asr_worker: FasterWhisperWorker,
    segment: SpeechSegment,
    utterance_id: str,
) -> None:
    data = _slice_pcm_s16le(session, segment.start, segment.end)
    result = await _transcribe_bytes(session, asr_worker, data)
    if not result.text:
        return

    session.last_partial_text = result.text
    await websocket.send_json(
        server_event(
            "final",
            session_id=session.session_id,
            utterance_id=utterance_id,
            language=result.language,
            text=result.text,
            stable_text=result.text,
            unstable_text="",
        )
    )


async def _transcribe_bytes(
    session: SessionState,
    asr_worker: FasterWhisperWorker,
    data: bytes,
) -> TranscriptionResult:
    logger.info(
        "transcribing session_id=%s audio_ms=%s bytes=%s",
        session.session_id,
        session.audio_ms_received,
        len(data),
    )
    return await asyncio.to_thread(
        asr_worker.transcribe_pcm_s16le,
        data,
        sample_rate=session.sample_rate,
        language=session.language,
        task=session.task,
    )


def _slice_pcm_s16le(session: SessionState, start_sample: int, end_sample: int) -> bytes:
    start_byte = max(0, start_sample) * 2
    end_byte = max(start_sample, end_sample) * 2
    return bytes(session.audio_buffer[start_byte:end_byte])


def _split_stable_unstable(previous: str, current: str) -> tuple[str, str]:
    prefix_len = 0
    max_len = min(len(previous), len(current))
    while prefix_len < max_len and previous[prefix_len] == current[prefix_len]:
        prefix_len += 1
    return current[:prefix_len], current[prefix_len:]


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
