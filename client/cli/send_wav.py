from __future__ import annotations

import argparse
import asyncio
import json
import wave
from pathlib import Path
from typing import Any

import websockets


def read_wav_chunks(path: Path, chunk_ms: int) -> tuple[dict[str, Any], list[bytes]]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()

        if channels != 1:
            raise ValueError("Only mono WAV files are supported by the initial CLI client")
        if sample_width != 2:
            raise ValueError("Only 16-bit PCM WAV files are supported by the initial CLI client")

        frames_per_chunk = max(1, int(sample_rate * chunk_ms / 1000))
        chunks: list[bytes] = []
        frames_read = 0
        while frames_read < frames:
            data = wav.readframes(frames_per_chunk)
            if not data:
                break
            chunks.append(data)
            frames_read += frames_per_chunk

    metadata = {
        "sample_rate": sample_rate,
        "channels": channels,
        "format": "pcm_s16le",
        "duration_ms": int(frames / sample_rate * 1000),
    }
    return metadata, chunks


async def receive_messages(websocket: websockets.WebSocketClientProtocol) -> None:
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                print(f"< binary {len(message)} bytes")
                continue
            try:
                parsed = json.loads(message)
            except json.JSONDecodeError:
                print(f"< {message}")
            else:
                print("< " + json.dumps(parsed, ensure_ascii=False))
    except websockets.ConnectionClosed:
        return


async def send_wav(args: argparse.Namespace) -> None:
    metadata, chunks = read_wav_chunks(Path(args.file), args.chunk_ms)

    start_message = {
        "type": "start",
        "sample_rate": metadata["sample_rate"],
        "channels": metadata["channels"],
        "format": metadata["format"],
        "language": args.language,
        "task": args.task,
        "latency_ms": args.latency_ms,
        "vad_mode": args.vad_mode,
    }

    async with websockets.connect(args.server, max_size=None) as websocket:
        receiver = asyncio.create_task(receive_messages(websocket))
        await websocket.send(json.dumps(start_message))

        delay = args.chunk_ms / 1000 if args.realtime else 0
        for chunk in chunks:
            await websocket.send(chunk)
            if delay:
                await asyncio.sleep(delay)

        await websocket.send(json.dumps({"type": "stop"}))
        await receiver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a WAV file as PCM chunks over WebSocket")
    parser.add_argument("--server", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--file", required=True)
    parser.add_argument("--language", default="ja")
    parser.add_argument("--task", choices=["transcribe", "translate"], default="transcribe")
    parser.add_argument("--latency-ms", type=int, default=1000)
    parser.add_argument("--vad-mode", default="server")
    parser.add_argument("--chunk-ms", type=int, default=50)
    parser.add_argument("--realtime", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(send_wav(args))


if __name__ == "__main__":
    main()
