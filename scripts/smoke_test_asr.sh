#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
SERVER_URL="${1:-${ASR_TEST_SERVER_URL:-ws://127.0.0.1:8000/ws}}"
TEST_WAV="${ASR_TEST_WAV:-/tmp/streaming_asr_smoke.wav}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Virtualenv not found at $VENV_DIR. Run scripts/setup_gpu_server.sh first." >&2
  exit 1
fi

if command -v ffmpeg >/dev/null 2>&1 && ffmpeg -y -hide_banner -loglevel error -f lavfi -i "flite=text='test'" -t 0.1 -ar 16000 -ac 1 -sample_fmt s16 /tmp/streaming_flite_probe.wav; then
  ffmpeg -y -hide_banner -loglevel error \
    -f lavfi -t 0.8 -i anullsrc=r=16000:cl=mono \
    -f lavfi -i "flite=text='hello world this is a streaming speech recognition test'" \
    -f lavfi -t 1.4 -i anullsrc=r=16000:cl=mono \
    -filter_complex '[0:a][1:a][2:a]concat=n=3:v=0:a=1' \
    -ar 16000 -ac 1 -sample_fmt s16 "$TEST_WAV"
else
  "$VENV_DIR/bin/python" - <<PY
import wave
from pathlib import Path

path = Path("$TEST_WAV")
with wave.open(str(path), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(b"\\x00\\x00" * 16000)
PY
  echo "ffmpeg flite is unavailable; generated silence-only WAV, so ASR text may be empty." >&2
fi

"$VENV_DIR/bin/python" -m client.cli.send_wav \
  --server "$SERVER_URL" \
  --file "$TEST_WAV" \
  --language en \
  --task transcribe \
  --chunk-ms 200 \
  --no-realtime
