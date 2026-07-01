#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv-gesture"
MODEL_DIR="${REPO_ROOT}/client/gesture_caption/models"
HAND_MODEL="${MODEL_DIR}/hand_landmarker.task"
HAND_MODEL_URL="${HAND_MODEL_URL:-https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task}"
PYTHON_BIN="${PYTHON_BIN:-}"

cd "${REPO_ROOT}"
mkdir -p "${REPO_ROOT}/.cache/gesture-caption/matplotlib" "${REPO_ROOT}/.cache/gesture-caption/xdg"
export MPLCONFIGDIR="${MPLCONFIGDIR:-${REPO_ROOT}/.cache/gesture-caption/matplotlib}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${REPO_ROOT}/.cache/gesture-caption/xdg}"

if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "Python 3 is required." >&2
    exit 1
  fi
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating Python virtual environment: ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")
print(f"Using Python {sys.version.split()[0]}")
PY

missing="$("${VENV_DIR}/bin/python" - <<'PY'
missing = []
for name in ("cv2", "mediapipe", "numpy"):
    try:
        __import__(name)
    except Exception:
        missing.append(name)
print(" ".join(missing))
PY
)"

if [[ -n "${missing}" ]]; then
  echo "Installing gesture client dependencies..."
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/python" -m pip install -r client/gesture_caption/requirements.txt
fi

if [[ ! -f "${HAND_MODEL}" ]]; then
  if command -v curl >/dev/null 2>&1; then
    echo "Downloading MediaPipe hand landmarker model..."
    mkdir -p "${MODEL_DIR}"
    curl -L "${HAND_MODEL_URL}" -o "${HAND_MODEL}"
  else
    echo "curl is required to download ${HAND_MODEL_URL}" >&2
    exit 1
  fi
fi

exec "${VENV_DIR}/bin/python" -m client.gesture_caption.main "$@"
