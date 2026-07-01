#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv-qt}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "$VENV_DIR is missing. Running scripts/macos/setup_qt_client.sh ..." >&2
  scripts/macos/setup_qt_client.sh
fi

if ! "$VENV_DIR/bin/python" -c "import PySide6, certifi, numpy, sounddevice, websockets" >/dev/null 2>&1; then
  echo "Qt dependencies are missing. Running scripts/macos/setup_qt_client.sh ..." >&2
  scripts/macos/setup_qt_client.sh
fi

"$VENV_DIR/bin/python" -c "import PySide6, certifi, numpy, sounddevice, websockets" >/dev/null
exec "$VENV_DIR/bin/python" client/qt/app.py "$@"
