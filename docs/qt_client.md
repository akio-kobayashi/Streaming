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

The macOS setup script uses `python3 -m venv` by default. The Qt venv must
contain PySide6 only. Do not install PyQt6 or pyqtgraph into the same
environment.

npm helper:

```bash
npm run dev:qt -- --server-url wss://<public-host>/ws
```

## macOS App Bundle

Build a double-clickable `.app` with PyInstaller:

```bash
scripts/macos/build_qt_app.sh
open dist/StreamingASRQt.app
```

Build a distributable drag-install `.dmg`:

```bash
scripts/macos/build_qt_dmg.sh
open dist/StreamingASRQt-0.1.0-mac.dmg
```

The DMG contains `StreamingASRQt.app` and an `Applications` shortcut. Drag the
app onto `Applications` to install it.

The build script adds the microphone permission text. The icon file itself is
not required for the build. If `assets/app-icon.icns` exists locally, enable it
explicitly:

```bash
USE_ICON=1 scripts/macos/build_qt_app.sh
```

The script first builds a normal PyInstaller `onedir` payload, then wraps it in
`dist/StreamingASRQt.app`. This avoids depending on PyInstaller's macOS bundle
step, which can be slow and opaque for Qt applications.

Optional local cleanup/signing can be enabled when needed:

```bash
STRIP_XATTR=1 CODESIGN_APP=1 scripts/macos/build_qt_app.sh
```

DMG build options:

```bash
VERSION=0.1.1 scripts/macos/build_qt_dmg.sh
BUILD_APP=0 scripts/macos/build_qt_dmg.sh
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
