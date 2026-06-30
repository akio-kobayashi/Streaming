# Qt Client

PC desktop client development moves to Qt.

Flet is retained as an experimental prototype only. The browser client remains
the reference for spectrogram, caption layout, and transcript behavior.

## Stack

- PySide6 for the desktop UI.
- PySide6 `QImage` / `QPixmap` for the live Audacity-style spectrogram.
- sounddevice for microphone capture.
- websockets for the ASR WebSocket protocol.
- numpy for level meter and FFT processing.

## Run

```bash
python3 -m venv .venv-qt
source .venv-qt/bin/activate
pip install -r requirements-qt.txt
python -m client.qt.app --server-url wss://<public-host>/ws
```

macOS setup helper:

```bash
RESET_QT_VENV=1 scripts/macos/setup_qt_client.sh
scripts/macos/run_qt_client.sh --server-url wss://<public-host>/ws
```

The macOS setup script uses uv and Python 3.12 by default. The Qt venv must
contain PySide6 only. Do not install PyQt6 or pyqtgraph into the same
environment.

npm helper:

```bash
npm run dev:qt -- --server-url wss://<public-host>/ws
```

## UI Requirements

- The first screen is the usable desktop client, not a landing page.
- Top toolbar: WebSocket URL, language, latency, connect, record, stop, and status.
- Main stage: live spectrogram rendered directly with Qt, with broadcast-caption overlay.
- Level meter: mono dBFS meter updated from local microphone input.
- Transcript pane: bottom-anchored partial and final text display.
- Event log: connection, audio, and server protocol diagnostics.

## Validation Order

1. Start Qt client and connect to a known WebSocket URL.
2. Confirm `ready` then `config` in the event log.
3. Press `Record`.
4. Confirm the level meter and spectrogram move before evaluating ASR text.
5. Confirm `audio_received` events from the server.
6. Compare partial/final rendering against the browser client.
