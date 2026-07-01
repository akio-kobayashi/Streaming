#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv-qt}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3 and retry." >&2
  exit 1
fi

if [ "${RESET_QT_VENV:-0}" = "1" ]; then
  rm -rf "$VENV_DIR"
fi

if [ -d "$VENV_DIR" ] && ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
  echo "$VENV_DIR is incomplete. Recreating it." >&2
  rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m ensurepip --upgrade >/dev/null
if ! "$VENV_DIR/bin/python" -c "import PySide6, certifi, numpy, sounddevice, websockets" >/dev/null 2>&1; then
  "$VENV_DIR/bin/python" -m pip --disable-pip-version-check install -r requirements-qt.txt
fi

if "$VENV_DIR/bin/python" -m pip show PyQt6 >/dev/null 2>&1; then
  echo "PyQt6 is installed in $VENV_DIR. Recreate the venv with RESET_QT_VENV=1." >&2
  exit 1
fi

if "$VENV_DIR/bin/python" -m pip show pyqtgraph >/dev/null 2>&1; then
  echo "pyqtgraph is installed in $VENV_DIR. Recreate the venv with RESET_QT_VENV=1." >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m py_compile client/qt/app.py
"$VENV_DIR/bin/python" --version
"$VENV_DIR/bin/python" -c "from PySide6.QtCore import QLibraryInfo, qVersion; print('Qt', qVersion()); print('plugins', QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))"
QT_QPA_PLATFORM=offscreen "$VENV_DIR/bin/python" -c "from PySide6 import QtWidgets; app = QtWidgets.QApplication([]); print('offscreen ok')"
"$VENV_DIR/bin/python" -c "import PySide6, certifi, numpy, sounddevice, websockets; print('deps ok')"

echo "Qt client setup ok: $VENV_DIR"
