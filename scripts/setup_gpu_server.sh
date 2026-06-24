#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
MODEL="${ASR_WHISPER_MODEL:-large-v3}"
DEVICE="${ASR_WHISPER_DEVICE:-cuda}"
COMPUTE_TYPE="${ASR_WHISPER_COMPUTE_TYPE:-float16}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python command not found: $PYTHON_BIN" >&2
  exit 1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
  echo "nvidia-smi not found; continuing, but GPU availability is unverified." >&2
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
fi

"$VENV_DIR/bin/python" - <<PY
from pathlib import Path

import yaml

path = Path("config.yaml")
config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
whisper = config.setdefault("whisper", {})
whisper["backend"] = "faster-whisper"
whisper["model"] = "$MODEL"
whisper["device"] = "$DEVICE"
whisper["compute_type"] = "$COMPUTE_TYPE"
vad = config.setdefault("vad", {})
vad.setdefault("mode", "server")
vad.setdefault("backend", "silero")
path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
PY

"$VENV_DIR/bin/python" - <<'PY'
import nvidia.cublas.lib
import nvidia.cudnn.lib

print("CUDA library path:")
print(next(iter(nvidia.cublas.lib.__path__)) + ":" + next(iter(nvidia.cudnn.lib.__path__)))
PY

echo "Setup complete. Start the server with: scripts/run_gpu_server.sh"
