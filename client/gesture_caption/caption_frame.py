from __future__ import annotations

import cv2
import numpy as np

from .config import CaptionConfig
from .gesture import GestureEvent, GestureEventType, Point


class DragStart:
    def __init__(self, point: Point, x: int, y: int) -> None:
        self.offset_x = point.x - x
        self.offset_y = point.y - y


class ResizeStart:
    def __init__(self, a: Point, b: Point, x: int, y: int, width: int, height: int) -> None:
        x1, x2 = sorted((a.x, b.x))
        y1, y2 = sorted((a.y, b.y))
        self.left_offset = x1 - x
        self.right_offset = x + width - x2
        self.top_offset = y1 - y
        self.bottom_offset = y + height - y2
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class CaptionFrame:
    def __init__(self, config: CaptionConfig) -> None:
        self.config = config
        self.x = config.x
        self.y = config.y
        self.width = config.width
        self.height = config.height
        self.visible = False
        self.final_lines: list[str] = []
        self.partial_text = ""
        self._drag_start: DragStart | None = None
        self._resize_start: ResizeStart | None = None

    def apply_event(self, event: GestureEvent) -> None:
        if event.type == GestureEventType.HIDE_FRAME:
            self._reset_interaction()
            self.hide()
        elif event.type == GestureEventType.MOVE_FRAME and event.points:
            if self.visible:
                self.drag_to(event.points[0])
        elif event.type == GestureEventType.RESIZE_FRAME and len(event.points) >= 2:
            if self.visible:
                self.resize_from_pinch(event.points[0], event.points[1])
        elif event.type == GestureEventType.PLACE_FRAME:
            self._reset_interaction()
        elif event.type == GestureEventType.NOOP:
            pass

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def move_center(self, point: Point) -> None:
        self.x = int(point.x - self.width / 2)
        self.y = int(point.y - self.height / 2)

    def drag_to(self, point: Point) -> None:
        self._resize_start = None
        if self._drag_start is None:
            if not self.contains(point):
                return
            self._drag_start = DragStart(point, self.x, self.y)
        self.x = point.x - self._drag_start.offset_x
        self.y = point.y - self._drag_start.offset_y

    def move_by(self, dx: int, dy: int) -> None:
        self._reset_interaction()
        self.x += dx
        self.y += dy
        self.visible = True

    def resize_by(self, dw: int, dh: int) -> None:
        self._reset_interaction()
        self.width = max(self.config.min_width, self.width + dw)
        self.height = max(self.config.min_height, self.height + dh)
        self.visible = True

    def scale_font(self, factor: float) -> None:
        self.config.font_scale = max(0.45, min(2.0, self.config.font_scale * factor))

    def set_from_diagonal(self, a: Point, b: Point) -> None:
        x1, x2 = sorted((a.x, b.x))
        y1, y2 = sorted((a.y, b.y))
        self.x = x1
        self.y = y1
        self.width = max(self.config.min_width, x2 - x1)
        self.height = max(self.config.min_height, y2 - y1)

    def resize_from_pinch(self, a: Point, b: Point) -> None:
        self._drag_start = None
        if self._resize_start is None:
            if not (self.contains(a) and self.contains(b)):
                return
            self._resize_start = ResizeStart(a, b, self.x, self.y, self.width, self.height)

        x1, x2 = sorted((a.x, b.x))
        y1, y2 = sorted((a.y, b.y))
        left = x1 - self._resize_start.left_offset
        right = x2 + self._resize_start.right_offset
        top = y1 - self._resize_start.top_offset
        bottom = y2 + self._resize_start.bottom_offset

        if right - left < self.config.min_width:
            center_x = (left + right) / 2
            left = int(center_x - self.config.min_width / 2)
            right = left + self.config.min_width
        if bottom - top < self.config.min_height:
            center_y = (top + bottom) / 2
            top = int(center_y - self.config.min_height / 2)
            bottom = top + self.config.min_height

        self.x = int(left)
        self.y = int(top)
        self.width = int(right - left)
        self.height = int(bottom - top)

    def clamp(self, frame_width: int, frame_height: int) -> None:
        self.width = min(self.width, frame_width)
        self.height = min(self.height, frame_height)
        self.x = max(0, min(self.x, frame_width - self.width))
        self.y = max(0, min(self.y, frame_height - self.height))

    def set_partial(self, text: str) -> None:
        self.partial_text = text

    def clear(self) -> None:
        self.final_lines = []
        self.partial_text = ""

    def add_final(self, text: str) -> None:
        if not text:
            return
        self.final_lines = [*self.final_lines, text][-self.config.max_history :]
        self.partial_text = ""

    def draw(self, frame: np.ndarray) -> None:
        if not self.visible:
            return
        height, width = frame.shape[:2]
        self.clamp(width, height)
        x1, y1 = self.x, self.y
        x2, y2 = self.x + self.width, self.y + self.height

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), -1)
        cv2.addWeighted(overlay, self.config.alpha, frame, 1 - self.config.alpha, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 1)

        lines = self._visible_text_lines()
        baseline = y2 - 16
        for text, color in reversed(lines):
            for wrapped in reversed(self.wrap_text(text)):
                cv2.putText(
                    frame,
                    wrapped,
                    (x1 + 14, baseline),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    self.config.font_scale,
                    color,
                    2,
                    cv2.LINE_AA,
                )
                baseline -= self.config.line_height
                if baseline < y1 + self.config.line_height:
                    return

    def _visible_text_lines(self) -> list[tuple[str, tuple[int, int, int]]]:
        final = [(line, (255, 255, 255)) for line in self.final_lines]
        partial = [(self.partial_text, (0, 210, 255))] if self.partial_text else []
        return [*final, *partial]

    def wrap_text(self, text: str) -> list[str]:
        max_chars = max(1, int(self.width / max(1, self.config.font_scale * 22)))
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)] or [""]

    def contains(self, point: Point) -> bool:
        return self.x <= point.x <= self.x + self.width and self.y <= point.y <= self.y + self.height

    def _reset_interaction(self) -> None:
        self._drag_start = None
        self._resize_start = None

