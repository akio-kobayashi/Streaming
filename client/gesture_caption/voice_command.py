from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .caption_frame import CaptionFrame


class VoiceCommandType(str, Enum):
    SHOW = "SHOW"
    HIDE = "HIDE"
    CLEAR = "CLEAR"
    FONT_UP = "FONT_UP"
    FONT_DOWN = "FONT_DOWN"
    MOVE_UP = "MOVE_UP"
    MOVE_DOWN = "MOVE_DOWN"
    MOVE_LEFT = "MOVE_LEFT"
    MOVE_RIGHT = "MOVE_RIGHT"
    WIDER = "WIDER"
    NARROWER = "NARROWER"
    TALLER = "TALLER"
    SHORTER = "SHORTER"


@dataclass(frozen=True)
class VoiceCommand:
    type: VoiceCommandType
    source_text: str


CONTROL_WORDS = ("字幕", "フレーム", "枠")


def normalize_text(text: str) -> str:
    return re.sub(r"[\s　、。,.!！?？「」『』（）()]", "", text)


def parse_voice_command(text: str) -> VoiceCommand | None:
    normalized = normalize_text(text)
    if not normalized:
        return None
    if not any(word in normalized for word in CONTROL_WORDS):
        return None

    if any(word in normalized for word in ("表示", "出して", "出す", "見せて", "オン")):
        return VoiceCommand(VoiceCommandType.SHOW, text)
    if any(word in normalized for word in ("非表示", "消して", "隠して", "オフ")):
        return VoiceCommand(VoiceCommandType.HIDE, text)
    if any(word in normalized for word in ("クリア", "消去", "リセット")):
        return VoiceCommand(VoiceCommandType.CLEAR, text)

    if any(word in normalized for word in ("文字大きく", "文字を大きく", "大きい文字", "フォント大きく")):
        return VoiceCommand(VoiceCommandType.FONT_UP, text)
    if any(word in normalized for word in ("文字小さく", "文字を小さく", "小さい文字", "フォント小さく")):
        return VoiceCommand(VoiceCommandType.FONT_DOWN, text)

    if any(word in normalized for word in ("上へ", "上に", "上げて")):
        return VoiceCommand(VoiceCommandType.MOVE_UP, text)
    if any(word in normalized for word in ("下へ", "下に", "下げて")):
        return VoiceCommand(VoiceCommandType.MOVE_DOWN, text)
    if any(word in normalized for word in ("左へ", "左に", "左寄せ", "左")):
        return VoiceCommand(VoiceCommandType.MOVE_LEFT, text)
    if any(word in normalized for word in ("右へ", "右に", "右寄せ", "右")):
        return VoiceCommand(VoiceCommandType.MOVE_RIGHT, text)

    if any(word in normalized for word in ("横広げて", "広げて", "幅広く", "大きく")):
        return VoiceCommand(VoiceCommandType.WIDER, text)
    if any(word in normalized for word in ("横狭く", "狭く", "幅狭く")):
        return VoiceCommand(VoiceCommandType.NARROWER, text)
    if any(word in normalized for word in ("縦広げて", "高さ大きく", "高く")):
        return VoiceCommand(VoiceCommandType.TALLER, text)
    if any(word in normalized for word in ("縦狭く", "高さ小さく", "低く")):
        return VoiceCommand(VoiceCommandType.SHORTER, text)

    return None


def apply_voice_command(caption: "CaptionFrame", command: VoiceCommand) -> str:
    if command.type == VoiceCommandType.SHOW:
        caption.show()
    elif command.type == VoiceCommandType.HIDE:
        caption.hide()
    elif command.type == VoiceCommandType.CLEAR:
        caption.clear()
    elif command.type == VoiceCommandType.FONT_UP:
        caption.scale_font(1.15)
    elif command.type == VoiceCommandType.FONT_DOWN:
        caption.scale_font(1 / 1.15)
    elif command.type == VoiceCommandType.MOVE_UP:
        caption.move_by(0, -40)
    elif command.type == VoiceCommandType.MOVE_DOWN:
        caption.move_by(0, 40)
    elif command.type == VoiceCommandType.MOVE_LEFT:
        caption.move_by(-40, 0)
    elif command.type == VoiceCommandType.MOVE_RIGHT:
        caption.move_by(40, 0)
    elif command.type == VoiceCommandType.WIDER:
        caption.resize_by(80, 0)
    elif command.type == VoiceCommandType.NARROWER:
        caption.resize_by(-80, 0)
    elif command.type == VoiceCommandType.TALLER:
        caption.resize_by(0, 40)
    elif command.type == VoiceCommandType.SHORTER:
        caption.resize_by(0, -40)
    return command.type.value
