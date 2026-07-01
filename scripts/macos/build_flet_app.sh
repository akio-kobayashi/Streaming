#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv-flet-macos}"
FLET_VERSION="${FLET_VERSION:-0.85.3}"
FLET_ARCHIVE_DIR="vendor/flet-desktop"
FLET_ARCHIVE="$FLET_ARCHIVE_DIR/flet-macos.tar.gz"
FLET_ARCHIVE_VERSIONED="$FLET_ARCHIVE_DIR/flet-macos-$FLET_VERSION.tar.gz"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3 and retry." >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r requirements-flet.txt pyinstaller

mkdir -p "$FLET_ARCHIVE_DIR"
if [ ! -f "$FLET_ARCHIVE_VERSIONED" ]; then
  curl -L --fail --retry 3 \
    -o "$FLET_ARCHIVE_VERSIONED" \
    "https://github.com/flet-dev/flet/releases/download/v$FLET_VERSION/flet-macos.tar.gz"
fi
cp "$FLET_ARCHIVE_VERSIONED" "$FLET_ARCHIVE"

PYINSTALLER_CONFIG_DIR=.pyinstaller-cache "$VENV_DIR/bin/pyinstaller" \
  --name StreamingASRClient \
  --noconfirm \
  --windowed \
  --icon assets/app-icon.icns \
  --collect-all flet \
  --collect-all flet_desktop \
  --collect-all websockets \
  --collect-all sounddevice \
  --add-data "$FLET_ARCHIVE:flet_desktop/app" \
  client/flet/app.py

plutil -replace NSMicrophoneUsageDescription \
  -string "Streaming ASR Client uses the microphone to stream speech audio to the configured ASR server." \
  dist/StreamingASRClient.app/Contents/Info.plist

codesign --force --deep --sign - dist/StreamingASRClient.app
codesign --verify --deep --verbose=2 dist/StreamingASRClient.app
echo "Built dist/StreamingASRClient.app"
