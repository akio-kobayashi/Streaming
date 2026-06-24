from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .config import WhisperConfig


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str


class FasterWhisperWorker:
    def __init__(self, config: WhisperConfig) -> None:
        if config.backend != "faster-whisper":
            raise ValueError(f"unsupported whisper backend: {config.backend}")

        from faster_whisper import WhisperModel

        self.config = config
        logger.info(
            "loading faster-whisper model=%s device=%s compute_type=%s",
            config.model,
            config.device,
            config.compute_type,
        )
        self.model = WhisperModel(
            config.model,
            device=config.device,
            compute_type=config.compute_type,
        )
        logger.info("faster-whisper model loaded")

    def transcribe_pcm_s16le(
        self,
        data: bytes,
        *,
        sample_rate: int,
        language: str,
        task: str,
    ) -> TranscriptionResult:
        if not data:
            return TranscriptionResult(text="", language=language)
        if sample_rate != 16000:
            raise ValueError(f"Whisper input must be 16000 Hz PCM, got {sample_rate}")

        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return TranscriptionResult(text="", language=language)

        requested_language = None if language == "auto" else language
        segments, info = self.model.transcribe(
            audio,
            language=requested_language,
            task=task,
            beam_size=1,
            vad_filter=False,
        )
        text = "".join(segment.text for segment in segments).strip()
        detected_language = getattr(info, "language", None) or language
        return TranscriptionResult(text=text, language=detected_language)
