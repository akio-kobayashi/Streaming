from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from uuid import uuid4

from .config import AppConfig


@dataclass
class SessionState:
    session_id: str
    sample_rate: int
    channels: int
    audio_format: str
    language: str
    task: str
    latency_ms: int
    vad_mode: str
    started_at: float
    bytes_received: int = 0
    chunks_received: int = 0
    pending_language: str | None = None
    audio_buffer: bytearray = field(default_factory=bytearray)
    last_decode_audio_ms: int = 0
    last_vad_audio_ms: int = 0
    last_partial_text: str = ""
    finalized_sample: int = 0
    utterance_index: int = 0
    active_utterance_id: str | None = None

    @property
    def audio_ms_received(self) -> int:
        if self.audio_format != "pcm_s16le" or self.channels <= 0 or self.sample_rate <= 0:
            return 0
        bytes_per_sample = 2
        samples = self.bytes_received / bytes_per_sample / self.channels
        return int(samples / self.sample_rate * 1000)

    def add_audio(self, data: bytes) -> None:
        self.bytes_received += len(data)
        self.chunks_received += 1
        self.audio_buffer.extend(data)

    def apply_config(self, message: dict) -> dict:
        changed: dict = {}
        if "latency_ms" in message:
            self.latency_ms = int(message["latency_ms"])
            changed["latency_ms"] = self.latency_ms
        if "language" in message:
            language = str(message["language"])
            language_apply = message.get("language_apply", "immediate")
            if language_apply == "next_utterance":
                self.pending_language = language
                changed["pending_language"] = language
            else:
                self.language = language
                self.pending_language = None
                changed["language"] = language
        return changed


def create_session(start_message: dict, app_config: AppConfig) -> SessionState:
    return SessionState(
        session_id=f"s-{uuid4().hex[:12]}",
        sample_rate=start_message.get("sample_rate", app_config.audio.sample_rate),
        channels=start_message.get("channels", app_config.audio.channels),
        audio_format=start_message.get("format", app_config.audio.format),
        language=start_message.get("language", app_config.whisper.language),
        task=start_message.get("task", "transcribe"),
        latency_ms=start_message.get("latency_ms", app_config.streaming.latency_ms),
        vad_mode=start_message.get("vad_mode", app_config.vad.mode),
        started_at=monotonic(),
    )
