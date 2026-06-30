from __future__ import annotations

import argparse
import asyncio
import html
import json
import math
import ssl
import sys
import threading
from typing import Any

import certifi
import numpy as np
import sounddevice as sd
import websockets
from PySide6 import QtCore, QtGui, QtWidgets


TARGET_SAMPLE_RATE = 16000
CHUNK_FRAMES = 1600
SPEC_ROWS = 256
SPEC_COLS = 640
LEVEL_FLOOR_DB = -60.0


def build_colormap() -> np.ndarray:
    stops = np.array([0.0, 0.08, 0.18, 0.34, 0.5, 0.66, 0.78, 0.9, 1.0], dtype=np.float32)
    colors = np.array(
        [
            [0, 0, 0],
            [0, 7, 18],
            [0, 28, 61],
            [27, 28, 116],
            [108, 32, 157],
            [206, 31, 169],
            [255, 65, 92],
            [255, 155, 48],
            [255, 244, 176],
        ],
        dtype=np.float32,
    )
    scale = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    table = np.empty((256, 3), dtype=np.uint8)
    for channel in range(3):
        table[:, channel] = np.interp(scale, stops, colors[:, channel]).astype(np.uint8)
    return table


def pcm_dbfs(chunk: bytes) -> float:
    samples = np.frombuffer(chunk, dtype=np.int16)
    if samples.size == 0:
        return LEVEL_FLOOR_DB
    audio = samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(audio * audio)))
    return 20.0 * math.log10(max(rms, 1.0e-6))


def synthetic_chunk(index: int) -> bytes:
    t = (np.arange(CHUNK_FRAMES, dtype=np.float32) + index * CHUNK_FRAMES) / TARGET_SAMPLE_RATE
    signal = np.sin(2.0 * np.pi * (220.0 + index * 14.0) * t)
    signal += 0.45 * np.sin(2.0 * np.pi * (440.0 + index * 8.0) * t)
    env = np.linspace(0.15, 0.85, CHUNK_FRAMES, dtype=np.float32)
    return (np.clip(signal * env * 0.28, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


class Bridge(QtCore.QObject):
    log = QtCore.Signal(str)
    status = QtCore.Signal(str)
    connected = QtCore.Signal(bool)
    message = QtCore.Signal(dict)
    audio = QtCore.Signal(bytes)
    level = QtCore.Signal(float)


class StreamingQtClient(QtWidgets.QMainWindow):
    def __init__(self, server_url: str, insecure_tls: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Streaming ASR Qt Client")
        self.resize(1180, 820)
        self.insecure_tls_default = insecure_tls

        self.bridge = Bridge()
        self.bridge.log.connect(self.append_log)
        self.bridge.status.connect(self.set_status)
        self.bridge.connected.connect(self.set_connected)
        self.bridge.message.connect(self.handle_message)
        self.bridge.audio.connect(self.update_spectrogram)
        self.bridge.level.connect(self.update_level)

        self.websocket: Any | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.audio_queue: asyncio.Queue[bytes] | None = None
        self.worker: threading.Thread | None = None
        self.audio_stream: sd.RawInputStream | None = None
        self.final_lines: list[str] = []
        self.stable_text = ""
        self.unstable_text = ""
        self.spec = np.zeros((SPEC_ROWS, SPEC_COLS), dtype=np.float32)
        self.colors = build_colormap()

        self.server_url = QtWidgets.QLineEdit(server_url)
        self.device_box = QtWidgets.QComboBox()
        self.language = QtWidgets.QComboBox()
        self.language.addItems(["ja", "en", "zh", "ko", "auto"])
        self.latency_ms = QtWidgets.QSpinBox()
        self.latency_ms.setRange(0, 10000)
        self.latency_ms.setSingleStep(100)
        self.latency_ms.setValue(1000)
        self.insecure_tls = QtWidgets.QCheckBox("Insecure TLS")
        self.insecure_tls.setChecked(insecure_tls)

        self.connect_button = QtWidgets.QPushButton("Connect")
        self.record_button = QtWidgets.QPushButton("Record")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.record_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.status_label = QtWidgets.QLabel("idle")

        self.level_bar = QtWidgets.QProgressBar()
        self.level_bar.setRange(0, 1000)
        self.level_bar.setTextVisible(False)
        self.level_bar.setStyleSheet(
            "QProgressBar { background: #111; border: 1px solid #333; height: 14px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #18b957, stop:0.68 #18b957, stop:0.82 #f3d23b, stop:1 #d93434); }"
        )
        self.level_label = QtWidgets.QLabel("-inf dB")

        self.spec_view = QtWidgets.QLabel()
        self.spec_view.setMinimumHeight(360)
        self.spec_view.setStyleSheet("background: #050608;")
        self.spec_view.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self.caption = QtWidgets.QLabel("Streaming ASR")
        self.caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet(
            "QLabel { background: rgba(0,0,0,190); color: white; "
            "font-size: 18px; font-weight: 700; padding: 8px; }"
        )

        self.transcript = QtWidgets.QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setStyleSheet("QTextEdit { background: white; color: black; font-size: 18px; }")
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)

        self.build_layout()
        self.connect_signals()
        self.refresh_devices()
        self.render_spectrogram()

    def build_layout(self) -> None:
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(QtWidgets.QLabel("WebSocket"))
        toolbar.addWidget(self.server_url, 1)
        toolbar.addWidget(QtWidgets.QLabel("Mic"))
        toolbar.addWidget(self.device_box)
        toolbar.addWidget(QtWidgets.QLabel("Language"))
        toolbar.addWidget(self.language)
        toolbar.addWidget(QtWidgets.QLabel("Latency"))
        toolbar.addWidget(self.latency_ms)
        toolbar.addWidget(self.insecure_tls)
        toolbar.addWidget(self.connect_button)
        toolbar.addWidget(self.record_button)
        toolbar.addWidget(self.stop_button)
        toolbar.addWidget(self.status_label)

        level = QtWidgets.QHBoxLayout()
        level.addWidget(QtWidgets.QLabel("Input level"))
        level.addWidget(self.level_bar, 1)
        level.addWidget(self.level_label)

        stage = QtWidgets.QWidget()
        stage_layout = QtWidgets.QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.addWidget(self.spec_view, 1)
        stage_layout.addWidget(self.caption)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(stage)
        splitter.addWidget(self.transcript)
        splitter.addWidget(self.log)
        splitter.setSizes([420, 180, 180])

        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)
        layout.addLayout(toolbar)
        layout.addLayout(level)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

    def connect_signals(self) -> None:
        self.connect_button.clicked.connect(self.connect_server)
        self.record_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.language.currentTextChanged.connect(self.send_language_config)
        self.latency_ms.valueChanged.connect(self.send_latency_config)

    def refresh_devices(self) -> None:
        self.device_box.clear()
        self.device_box.addItem("System default", None)
        try:
            devices = sd.query_devices()
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"audio devices error: {type(exc).__name__}: {exc}")
            return
        count = 0
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) > 0:
                count += 1
                self.device_box.addItem(f"{index}: {device.get('name')} ({device.get('max_input_channels')} ch)", index)
        self.append_log(f"audio devices: {count} input device(s)")

    def append_log(self, text: str) -> None:
        self.log.insertPlainText(f"{text}\n")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_connected(self, connected: bool) -> None:
        self.connect_button.setEnabled(not connected)
        self.record_button.setEnabled(connected)
        self.stop_button.setEnabled(connected)

    def connect_server(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.set_status("connecting")
        self.connect_button.setEnabled(False)
        self.worker = threading.Thread(target=lambda: asyncio.run(self.client_loop()), daemon=True)
        self.worker.start()

    async def client_loop(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.audio_queue = asyncio.Queue(maxsize=32)
        url = self.server_url.text().strip()
        self.bridge.log.emit(f"connecting: {url}")
        try:
            async with websockets.connect(
                url,
                max_size=None,
                open_timeout=10,
                ssl=self.ssl_context(url),
            ) as websocket:
                self.websocket = websocket
                async for raw in websocket:
                    data = json.loads(raw)
                    self.bridge.log.emit(json.dumps(data, ensure_ascii=False))
                    self.bridge.message.emit(data)
                    if data.get("type") == "ready":
                        await websocket.send(json.dumps(self.start_message()))
                        asyncio.create_task(self.send_audio_loop(websocket))
        except Exception as exc:  # noqa: BLE001
            self.bridge.log.emit(f"connection error: {type(exc).__name__}: {exc}")
            self.bridge.status.emit("error")
            self.bridge.connected.emit(False)
        finally:
            self.websocket = None
            self.loop = None
            self.audio_queue = None

    def ssl_context(self, url: str) -> ssl.SSLContext | None:
        if not url.startswith("wss://"):
            return None
        if self.insecure_tls.isChecked():
            self.bridge.log.emit("tls: certificate verification disabled")
            return ssl._create_unverified_context()
        self.bridge.log.emit(f"tls: using certifi CA bundle {certifi.where()}")
        return ssl.create_default_context(cafile=certifi.where())

    async def send_audio_loop(self, websocket: Any) -> None:
        assert self.audio_queue is not None
        while True:
            await websocket.send(await self.audio_queue.get())

    def start_message(self) -> dict[str, Any]:
        return {
            "type": "start",
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 1,
            "format": "pcm_s16le",
            "language": self.language.currentText(),
            "task": "transcribe",
            "latency_ms": self.latency_ms.value(),
            "vad_mode": "server",
        }

    def handle_message(self, data: dict) -> None:
        msg_type = data.get("type")
        if msg_type == "config":
            self.set_status(f"connected {data.get('session_id', '')}")
            self.set_connected(True)
        elif msg_type == "partial":
            self.stable_text = data.get("stable_text", "")
            self.unstable_text = data.get("unstable_text", "")
            self.render_text()
        elif msg_type == "final":
            text = data.get("text") or f"{data.get('stable_text', '')}{data.get('unstable_text', '')}"
            if text:
                self.final_lines = [*self.final_lines, text][-20:]
            self.stable_text = ""
            self.unstable_text = ""
            self.render_text()
        elif msg_type == "audio_received":
            self.set_status("recording")
        elif msg_type == "stopped":
            self.set_status("stopped")

    def render_text(self) -> None:
        rows = [f"<div style='color:#000'>{html.escape(line)}</div>" for line in self.final_lines]
        pending = f"{self.stable_text}{self.unstable_text}".strip()
        if pending:
            rows.append(
                "<div>"
                f"<span style='color:#333'>{html.escape(self.stable_text)}</span>"
                f"<span style='color:#c47a00'>{html.escape(self.unstable_text)}</span>"
                "</div>"
            )
        self.transcript.setHtml("<br>".join(rows))
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def send_json(self, data: dict[str, Any]) -> None:
        if self.loop and self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.send(json.dumps(data)), self.loop)

    def send_language_config(self) -> None:
        self.send_json({"type": "config", "language": self.language.currentText(), "language_apply": "next_utterance"})

    def send_latency_config(self) -> None:
        self.send_json({"type": "config", "latency_ms": self.latency_ms.value()})

    def start_recording(self) -> None:
        if self.audio_stream:
            return
        try:
            self.audio_stream = sd.RawInputStream(
                samplerate=TARGET_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=CHUNK_FRAMES,
                device=self.device_box.currentData(),
                callback=self.audio_callback,
            )
            self.audio_stream.start()
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"microphone error: {type(exc).__name__}: {exc}")
            self.audio_stream = None
            self.set_status("microphone error")
            return
        self.record_button.setEnabled(False)
        self.set_status("recording")

    def stop_recording(self) -> None:
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            self.audio_stream = None
        self.send_json({"type": "stop"})
        self.record_button.setEnabled(True)
        self.set_status("stopped")

    def audio_callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        chunk = bytes(indata)
        if status:
            self.bridge.log.emit(f"audio status: {status}")
        if self.loop and self.audio_queue:
            self.loop.call_soon_threadsafe(self.enqueue_audio, chunk)
        self.bridge.audio.emit(chunk)
        self.bridge.level.emit(pcm_dbfs(chunk))

    def enqueue_audio(self, chunk: bytes) -> None:
        if not self.audio_queue:
            return
        try:
            self.audio_queue.put_nowait(chunk)
        except asyncio.QueueFull:
            pass

    def update_level(self, db: float) -> None:
        clamped = max(LEVEL_FLOOR_DB, min(0.0, db))
        ratio = (clamped - LEVEL_FLOOR_DB) / abs(LEVEL_FLOOR_DB)
        self.level_bar.setValue(round(ratio * 1000))
        self.level_label.setText("-inf dB" if db <= LEVEL_FLOOR_DB else f"{clamped:.1f} dB")

    def update_spectrogram(self, chunk: bytes) -> None:
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size < 256:
            return
        window = samples[-1024:] if samples.size >= 1024 else np.pad(samples, (1024 - samples.size, 0))
        spectrum = np.abs(np.fft.rfft(window * np.hanning(window.size)))[:SPEC_ROWS]
        values = np.clip((20.0 * np.log10(np.maximum(spectrum, 1.0e-6)) + 80.0) / 80.0, 0.0, 1.0)
        self.spec[:, :-1] = self.spec[:, 1:]
        self.spec[:, -1] = values[::-1]
        self.render_spectrogram()

    def render_spectrogram(self) -> None:
        indices = np.clip(self.spec * 255.0, 0, 255).astype(np.uint8)
        rgb = np.ascontiguousarray(self.colors[indices])
        height, width, _ = rgb.shape
        image = QtGui.QImage(rgb.data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888).copy()
        pixmap = QtGui.QPixmap.fromImage(image)
        self.spec_view.setPixmap(
            pixmap.scaled(
                self.spec_view.size(),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.render_spectrogram()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self.stop_recording()
        super().closeEvent(event)

    def run_self_test(self) -> None:
        self.append_log("self-test: starting")
        self.handle_message({"type": "partial", "stable_text": "これはQt版の", "unstable_text": "動作確認です"})
        for index in range(24):
            chunk = synthetic_chunk(index)
            self.update_spectrogram(chunk)
            self.update_level(pcm_dbfs(chunk))
        self.handle_message({"type": "final", "text": "これはQt版の動作確認です。"})
        self.append_log("self-test: ok")
        self.set_status("self-test ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Streaming ASR Qt client")
    parser.add_argument("--server-url", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--insecure-tls", action="store_true", help="Disable TLS certificate verification for testing")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(f"starting Streaming ASR Qt Client: {args.server_url}", file=sys.stderr, flush=True)
    app = QtWidgets.QApplication([])
    window = StreamingQtClient(args.server_url, insecure_tls=args.insecure_tls)
    window.show()
    window.raise_()
    window.activateWindow()
    if args.self_test:
        QtCore.QTimer.singleShot(100, window.run_self_test)
        QtCore.QTimer.singleShot(2500, app.quit)
    app.exec()
    print("Streaming ASR Qt Client exited", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
