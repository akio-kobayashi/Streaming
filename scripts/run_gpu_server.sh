#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
HOST="${ASR_SERVER_HOST:-0.0.0.0}"
PORT="${ASR_SERVER_PORT:-8000}"
CONFIG="${ASR_CONFIG:-config.yaml}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Virtualenv not found at $VENV_DIR. Run scripts/setup_gpu_server.sh first." >&2
  exit 1
fi

if [ ! -f "$CONFIG" ]; then
  echo "Config file not found: $CONFIG. Run scripts/setup_gpu_server.sh first." >&2
  exit 1
fi

CUDA_LIB_PATH="$("$VENV_DIR/bin/python" - <<'PY'
import nvidia.cublas.lib
import nvidia.cudnn.lib

print(next(iter(nvidia.cublas.lib.__path__)) + ":" + next(iter(nvidia.cudnn.lib.__path__)))
PY
)"

export LD_LIBRARY_PATH="${CUDA_LIB_PATH}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec "$VENV_DIR/bin/python" -m server.app --host "$HOST" --port "$PORT" --config "$CONFIG"
