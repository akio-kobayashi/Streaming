from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm_s16le"


@dataclass
class StreamingConfig:
    chunk_ms: int = 50
    decode_interval_ms: int = 500
    latency_ms: int = 1000
    window_ms: int = 15000
    overlap_ms: int = 1500


@dataclass
class VadConfig:
    mode: str = "server"
    backend: str = "silero"
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 700
    speech_pad_ms: int = 200


@dataclass
class WhisperConfig:
    backend: str = "faster-whisper"
    model: str = "small"
    language: str = "ja"
    device: str = "auto"
    compute_type: str = "auto"


@dataclass
class CaptionConfig:
    position: str = "bottom"
    background_color: str = "#000000"
    background_opacity: float = 0.75
    text_color: str = "#ffffff"
    unstable_text_color: str = "#d0d0d0"
    font_size_px: int = 36
    line_count: int = 2
    chars_per_line: int = 22
    scroll_mode: str = "push_up"
    text_align: str = "center"


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    caption: CaptionConfig = field(default_factory=CaptionConfig)


def _merge_dataclass(instance: Any, values: dict[str, Any]) -> Any:
    for key, value in values.items():
        if not hasattr(instance, key):
            continue
        current = getattr(instance, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, value)
    return instance


def load_config(path: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    if path is None:
        return config

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    return _merge_dataclass(config, raw)
