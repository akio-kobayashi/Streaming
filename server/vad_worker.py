from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps

from .config import VadConfig


@dataclass(frozen=True)
class SpeechSegment:
    start: int
    end: int


class SileroVadWorker:
    def __init__(self, config: VadConfig) -> None:
        if config.backend != "silero":
            raise ValueError(f"unsupported VAD backend: {config.backend}")
        self.config = config

    def get_speech_segments(self, data: bytes, *, sample_rate: int) -> list[SpeechSegment]:
        if not data:
            return []
        if sample_rate != 16000:
            raise ValueError(f"Silero VAD input must be 16000 Hz PCM, got {sample_rate}")

        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return []

        options = VadOptions(
            threshold=self.config.threshold,
            min_speech_duration_ms=self.config.min_speech_ms,
            min_silence_duration_ms=self.config.min_silence_ms,
            speech_pad_ms=self.config.speech_pad_ms,
        )
        timestamps = get_speech_timestamps(audio, vad_options=options, sampling_rate=sample_rate)
        return [SpeechSegment(start=item["start"], end=item["end"]) for item in timestamps]
