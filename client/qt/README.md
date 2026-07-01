# Qt Client

PC desktop client based on PySide6, numpy, sounddevice, and websockets.

This is the primary desktop-client direction. The Flet client is retained only
as an experimental prototype.

## Run

```bash
python3 -m venv .venv-qt
source .venv-qt/bin/activate
pip install -r requirements-qt.txt
python -m client.qt.app --server-url wss://<public-host>/ws
```

macOS helper:

```bash
RESET_QT_VENV=1 scripts/macos/setup_qt_client.sh
scripts/macos/run_qt_client.sh --server-url wss://<public-host>/ws
```

The macOS helper uses uv and Python 3.12 by default.

## Intended UI

- WebSocket URL, language, latency, connect, record, stop, and status controls.
- Audacity-style live spectrogram rendered directly with Qt.
- Monophonic dB level meter.
- Broadcast-caption style overlay on the spectrogram.
- Bottom-anchored transcript pane with unstable partial text coloring.
- Event log for connection, audio, and server messages.
