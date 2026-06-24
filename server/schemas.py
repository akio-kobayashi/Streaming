from __future__ import annotations

from typing import Any, Literal

SUPPORTED_TASKS = {"transcribe", "translate"}
SUPPORTED_AUDIO_FORMATS = {"pcm_s16le"}
SUPPORTED_LANGUAGE_APPLY = {"immediate", "next_utterance"}


class MessageError(ValueError):
    pass


def require_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MessageError("message must be a JSON object")
    return value


def parse_client_message(value: Any) -> dict[str, Any]:
    message = require_mapping(value)
    message_type = message.get("type")
    if message_type == "start":
        return _parse_start(message)
    if message_type == "config":
        return _parse_config(message)
    if message_type == "stop":
        return {"type": "stop"}
    raise MessageError(f"unsupported message type: {message_type}")


def _parse_start(message: dict[str, Any]) -> dict[str, Any]:
    sample_rate = int(message.get("sample_rate", 16000))
    channels = int(message.get("channels", 1))
    audio_format = str(message.get("format", "pcm_s16le"))
    language = str(message.get("language", "auto"))
    task = str(message.get("task", "transcribe"))
    latency_ms = int(message.get("latency_ms", 1000))
    vad_mode = str(message.get("vad_mode", "server"))

    if sample_rate <= 0:
        raise MessageError("sample_rate must be positive")
    if channels != 1:
        raise MessageError("only mono audio is supported in the initial implementation")
    if audio_format not in SUPPORTED_AUDIO_FORMATS:
        raise MessageError(f"unsupported audio format: {audio_format}")
    if task not in SUPPORTED_TASKS:
        raise MessageError(f"unsupported task: {task}")
    if latency_ms < 0:
        raise MessageError("latency_ms must be non-negative")

    return {
        "type": "start",
        "sample_rate": sample_rate,
        "channels": channels,
        "format": audio_format,
        "language": language,
        "task": task,
        "latency_ms": latency_ms,
        "vad_mode": vad_mode,
    }


def _parse_config(message: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {"type": "config"}
    if "latency_ms" in message:
        parsed["latency_ms"] = int(message["latency_ms"])
        if parsed["latency_ms"] < 0:
            raise MessageError("latency_ms must be non-negative")
    if "vad_silence_ms" in message:
        parsed["vad_silence_ms"] = int(message["vad_silence_ms"])
        if parsed["vad_silence_ms"] < 0:
            raise MessageError("vad_silence_ms must be non-negative")
    if "min_utterance_ms" in message:
        parsed["min_utterance_ms"] = int(message["min_utterance_ms"])
        if parsed["min_utterance_ms"] < 0:
            raise MessageError("min_utterance_ms must be non-negative")
    if "language" in message:
        parsed["language"] = str(message["language"])
    if "language_apply" in message:
        language_apply = str(message["language_apply"])
        if language_apply not in SUPPORTED_LANGUAGE_APPLY:
            raise MessageError(f"unsupported language_apply: {language_apply}")
        parsed["language_apply"] = language_apply
    return parsed


def server_event(
    event_type: Literal["ready", "config", "audio_received", "utterance_start", "partial", "final", "utterance_end", "stopped", "error"],
    **payload: Any,
) -> dict[str, Any]:
    return {"type": event_type, **payload}
