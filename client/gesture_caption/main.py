from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from .audio_stream import PcmMicrophoneStream
from .caption_frame import CaptionFrame
from .config import AppConfig
from .gesture import GestureStateMachine, HandObservation, Point
from .server_asr_client import ServerAsrClient
from .voice_command import apply_voice_command, parse_voice_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gesture controlled Whisper caption frame")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--server-url", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--language", default="ja")
    parser.add_argument("--latency-ms", type=int, default=1000)
    parser.add_argument(
        "--gesture-only",
        action="store_true",
        help="Test camera, MediaPipe hand tracking, and gesture frame control without audio or ASR",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Alias for --gesture-only",
    )
    parser.add_argument(
        "--hand-landmarker-model",
        default="",
        help="Optional MediaPipe Tasks hand_landmarker.task path. Falls back to mp.solutions.hands if omitted.",
    )
    return parser


class HandTracker:
    def __init__(self, model_asset_path: str = "") -> None:
        self.model_asset_path = model_asset_path
        self._tasks_landmarker = None
        self._solutions_hands = None
        self._mp = None
        if model_asset_path:
            self._init_tasks(model_asset_path)
        elif self._has_solutions_api():
            self._init_solutions()
        elif self._default_task_model_path().exists():
            self._init_tasks(str(self._default_task_model_path()))
        else:
            raise RuntimeError(
                "This MediaPipe installation does not provide mp.solutions.hands. "
                "Download hand_landmarker.task to client/gesture_caption/models/ "
                "or run scripts/macos/run_gesture_caption.sh."
            )

    @staticmethod
    def _default_task_model_path() -> Path:
        return Path(__file__).resolve().parent / "models" / "hand_landmarker.task"

    @staticmethod
    def _has_solutions_api() -> bool:
        import mediapipe as mp

        return hasattr(mp, "solutions") and hasattr(mp.solutions, "hands")

    def _init_tasks(self, model_asset_path: str) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        if not Path(model_asset_path).exists():
            raise FileNotFoundError(model_asset_path)

        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_asset_path),
            num_hands=2,
            running_mode=vision.RunningMode.VIDEO,
        )
        self._tasks_landmarker = vision.HandLandmarker.create_from_options(options)
        self._mp = mp

    def _init_solutions(self) -> None:
        import mediapipe as mp

        if not self._has_solutions_api():
            raise RuntimeError("Installed MediaPipe does not provide mp.solutions.hands.")

        self._mp = mp
        self._solutions_hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

    def close(self) -> None:
        if self._tasks_landmarker is not None:
            self._tasks_landmarker.close()
        if self._solutions_hands is not None:
            self._solutions_hands.close()

    def detect(self, frame_bgr, timestamp_ms: int) -> list[HandObservation]:
        height, width = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if self._tasks_landmarker is not None:
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=frame_rgb)
            result = self._tasks_landmarker.detect_for_video(image, timestamp_ms)
            observations: list[HandObservation] = []
            for index, landmarks in enumerate(result.hand_landmarks):
                handedness = "unknown"
                if index < len(result.handedness) and result.handedness[index]:
                    handedness = result.handedness[index][0].category_name
                observations.append(
                    HandObservation(
                        [Point(int(lm.x * width), int(lm.y * height)) for lm in landmarks],
                        handedness,
                    )
                )
            return observations

        result = self._solutions_hands.process(frame_rgb)
        if not result.multi_hand_landmarks:
            return []
        observations = []
        handedness_values = result.multi_handedness or []
        for index, landmarks in enumerate(result.multi_hand_landmarks):
            handedness = "unknown"
            if index < len(handedness_values):
                handedness = handedness_values[index].classification[0].label
            observations.append(
                HandObservation(
                    [Point(int(lm.x * width), int(lm.y * height)) for lm in landmarks.landmark],
                    handedness,
                )
            )
        return observations


def draw_hand_landmarks(frame, hands: list[HandObservation]) -> None:
    for hand in hands:
        for point in hand.landmarks:
            cv2.circle(frame, (point.x, point.y), 3, (80, 220, 255), -1)
        if len(hand.landmarks) > 8:
            cv2.circle(frame, (hand.landmarks[8].x, hand.landmarks[8].y), 7, (0, 255, 0), 2)
            cv2.circle(frame, (hand.landmarks[4].x, hand.landmarks[4].y), 7, (0, 255, 255), 2)


def main() -> None:
    args = build_parser().parse_args()
    config = AppConfig.defaults()
    config.camera.device_index = args.camera
    config.camera.width = args.width
    config.camera.height = args.height
    config.asr.server_url = args.server_url
    config.asr.language = args.language
    config.asr.latency_ms = args.latency_ms

    cap = cv2.VideoCapture(config.camera.device_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera.height)
    if not cap.isOpened():
        raise RuntimeError(
            "Failed to open camera. On macOS, allow Camera access for the terminal app "
            "running this command in System Settings > Privacy & Security > Camera. "
            "If permission is already granted, try another device with --camera 1."
        )

    tracker = HandTracker(args.hand_landmarker_model)
    gestures = GestureStateMachine(config.gesture)
    caption = CaptionFrame(config.caption)
    audio = None
    asr = None
    if args.gesture_only or args.no_server:
        caption.visible = True
        caption.add_final("固定字幕フレームのテストです。")
        caption.set_partial("ピンチで移動、両手ピンチでリサイズできます。")
    else:
        audio = PcmMicrophoneStream(config.audio)
        audio.start()
        asr = ServerAsrClient(
            config.asr.server_url,
            audio.queue,
            sample_rate=config.audio.sample_rate,
            channels=config.audio.channels,
            language=config.asr.language,
            latency_ms=config.asr.latency_ms,
        )
        asr.start()

    started_at = time.monotonic()
    last_voice_command = ""
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if config.camera.mirror:
                frame = cv2.flip(frame, 1)

            timestamp_ms = int((time.monotonic() - started_at) * 1000)
            hands = tracker.detect(frame, timestamp_ms)
            event = gestures.update(hands)
            caption.apply_event(event)

            if asr is not None:
                while not asr.results.empty():
                    result = asr.results.get_nowait()
                    command = parse_voice_command(result.text) if result.is_final else None
                    if command is not None:
                        last_voice_command = apply_voice_command(caption, command)
                    elif result.is_final:
                        caption.add_final(result.text)
                    else:
                        caption.set_partial(result.text)
                while not asr.events.empty():
                    last_voice_command = asr.events.get_nowait()

            draw_hand_landmarks(frame, hands)
            caption.draw(frame)
            cv2.putText(
                frame,
                f"state={event.state.value} event={event.type.value}",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            if last_voice_command:
                cv2.putText(
                    frame,
                    f"voice_command={last_voice_command}",
                    (12, 58),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 220, 255),
                    2,
                    cv2.LINE_AA,
                )
            cv2.imshow("Gesture Caption", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in {27, ord("q")}:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if asr is not None:
            asr.stop()
        if audio is not None:
            audio.stop()
        tracker.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
