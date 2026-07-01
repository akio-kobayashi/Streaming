from __future__ import annotations

import queue

from .config import AudioConfig


class PcmMicrophoneStream:
    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self.queue: queue.Queue[bytes] = queue.Queue(maxsize=40)
        self._stream = None
        self._blocksize = int(config.sample_rate * config.chunk_sec)

    def start(self) -> None:
        import sounddevice as sd

        def callback(indata, frames, time_info, status) -> None:
            try:
                self.queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        self._stream = sd.RawInputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            blocksize=self._blocksize,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
