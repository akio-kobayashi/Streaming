from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .config import GestureConfig


class GestureEventType(str, Enum):
    NOOP = "NOOP"
    MOVE_FRAME = "MOVE_FRAME"
    RESIZE_FRAME = "RESIZE_FRAME"
    PLACE_FRAME = "PLACE_FRAME"
    HIDE_FRAME = "HIDE_FRAME"


class GestureState(str, Enum):
    IDLE = "Idle"
    RESIZING_FRAME = "ResizingFrame"
    MOVING_FRAME = "MovingFrame"
    PLACED = "Placed"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass
class HandObservation:
    landmarks: list[Point]
    handedness: str = "unknown"


@dataclass
class GestureEvent:
    type: GestureEventType
    points: tuple[Point, ...] = ()
    state: GestureState = GestureState.IDLE


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def is_finger_extended(landmarks: list[Point], tip_index: int, pip_index: int) -> bool:
    return landmarks[tip_index].y < landmarks[pip_index].y


def palm_width(landmarks: list[Point]) -> float:
    return max(1.0, distance(landmarks[5], landmarks[17]))


def is_pinching(hand: HandObservation, threshold: float) -> bool:
    landmarks = hand.landmarks
    return distance(landmarks[4], landmarks[8]) / palm_width(landmarks) < threshold


def pinch_point(hand: HandObservation) -> Point:
    thumb = hand.landmarks[4]
    index = hand.landmarks[8]
    return Point((thumb.x + index.x) // 2, (thumb.y + index.y) // 2)


def is_open_palm(hand: HandObservation) -> bool:
    landmarks = hand.landmarks
    extended = [
        is_finger_extended(landmarks, 8, 6),
        is_finger_extended(landmarks, 12, 10),
        is_finger_extended(landmarks, 16, 14),
        is_finger_extended(landmarks, 20, 18),
    ]
    return sum(extended) >= 4


class GestureStateMachine:
    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self.state = GestureState.PLACED
        self._open_since: float | None = None
        self._candidate_type: GestureEventType | None = None
        self._candidate_frames = 0
        self._no_pinch_frames = 0

    def update(self, hands: Iterable[HandObservation]) -> GestureEvent:
        observations = list(hands)
        now = time.monotonic()
        open_detected = any(is_open_palm(hand) for hand in observations)
        pinch_points = tuple(
            pinch_point(hand)
            for hand in observations
            if is_pinching(hand, self.config.pinch_threshold)
        )

        self._open_since = self._update_timer(self._open_since, open_detected, now)
        raw_type = self._raw_event_type(len(pinch_points))
        if raw_type is not None:
            if raw_type == self._candidate_type:
                self._candidate_frames += 1
            else:
                self._candidate_type = raw_type
                self._candidate_frames = 1
            self._no_pinch_frames = 0
        else:
            self._candidate_type = None
            self._candidate_frames = 0
            self._no_pinch_frames += 1

        if self.state == GestureState.IDLE:
            if self._sustained(self._open_since, now, self.config.open_sustain_sec):
                self.state = GestureState.PLACED
                return GestureEvent(GestureEventType.PLACE_FRAME, state=self.state)
            return GestureEvent(GestureEventType.NOOP, state=self.state)

        if self.state == GestureState.RESIZING_FRAME:
            if raw_type == GestureEventType.RESIZE_FRAME:
                return GestureEvent(GestureEventType.RESIZE_FRAME, pinch_points[:2], self.state)
            if self._no_pinch_frames >= self.config.sustain_frames:
                self.state = GestureState.PLACED
                return GestureEvent(GestureEventType.PLACE_FRAME, state=self.state)

        if self.state == GestureState.MOVING_FRAME:
            if raw_type == GestureEventType.MOVE_FRAME:
                return GestureEvent(GestureEventType.MOVE_FRAME, pinch_points, self.state)
            if self._no_pinch_frames >= self.config.sustain_frames:
                self.state = GestureState.PLACED
                return GestureEvent(GestureEventType.PLACE_FRAME, state=self.state)

        if (
            raw_type == GestureEventType.RESIZE_FRAME
            and self._candidate_frames >= self.config.sustain_frames
        ):
            self.state = GestureState.RESIZING_FRAME
            return GestureEvent(GestureEventType.RESIZE_FRAME, pinch_points[:2], self.state)

        if (
            raw_type == GestureEventType.MOVE_FRAME
            and self._candidate_frames >= self.config.sustain_frames
        ):
            self.state = GestureState.MOVING_FRAME
            return GestureEvent(GestureEventType.MOVE_FRAME, pinch_points, self.state)

        return GestureEvent(GestureEventType.NOOP, state=self.state)

    @staticmethod
    def _raw_event_type(pinch_count: int) -> GestureEventType | None:
        if pinch_count >= 2:
            return GestureEventType.RESIZE_FRAME
        if pinch_count == 1:
            return GestureEventType.MOVE_FRAME
        return None

    @staticmethod
    def _update_timer(started_at: float | None, detected: bool, now: float) -> float | None:
        if detected:
            return now if started_at is None else started_at
        return None

    @staticmethod
    def _sustained(started_at: float | None, now: float, duration: float) -> bool:
        return started_at is not None and now - started_at >= duration
