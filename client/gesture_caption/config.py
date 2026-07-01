from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CameraConfig:
    device_index: int = 0
    width: int = 1280
    height: int = 720
    mirror: bool = True


@dataclass
class GestureConfig:
    pinch_threshold: float = 0.35
    sustain_frames: int = 4
    open_sustain_sec: float = 0.3


@dataclass
class CaptionConfig:
    x: int = 120
    y: int = 420
    width: int = 760
    height: int = 180
    min_width: int = 160
    min_height: int = 70
    alpha: float = 0.72
    font_scale: float = 0.9
    line_height: int = 34
    max_history: int = 6


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_sec: float = 0.1


@dataclass
class AsrConfig:
    server_url: str = "ws://127.0.0.1:8000/ws"
    language: str = "ja"
    latency_ms: int = 1000


@dataclass
class AppConfig:
    camera: CameraConfig
    gesture: GestureConfig
    caption: CaptionConfig
    audio: AudioConfig
    asr: AsrConfig

    @classmethod
    def defaults(cls) -> "AppConfig":
        return cls(
            camera=CameraConfig(),
            gesture=GestureConfig(),
            caption=CaptionConfig(),
            audio=AudioConfig(),
            asr=AsrConfig(),
        )
