"""
sopno/voice/mic.py
━━━━━━━━━━━━━━━━━━
Single shared microphone stream for both listener and barge-in.

Uses sounddevice (sd.InputStream) — eliminates the PyAudio/sounddevice
conflict that caused segfaults when both tried to open the same
PulseAudio device.

Both the listener (STT capture) and barge-in monitor read from the
same ring buffer, so there is never a device open/close race.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

from sopno.config.settings import settings


class MicStream:
    """
    Thread-safe shared microphone stream.

    Opens one sd.InputStream and stores incoming audio in a ring buffer.
    Multiple readers (listener, barge-in) can call read() to get frames.
    The stream runs continuously once started — no open/close races.
    """

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda m: print(f"[Mic] {m}"))
        self._sd = None
        self._stream = None
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._buf_lock = threading.Lock()
        self._rate = 16000
        self._channels = 1
        self._dtype = "int16"
        self._sample_width = 2  # int16 = 2 bytes
        self._started = False

    @property
    def rate(self) -> int:
        return self._rate

    @property
    def sample_width(self) -> int:
        return self._sample_width

    @property
    def channels(self) -> int:
        return self._channels

    def start(self) -> None:
        """Open the mic stream and begin capturing into the ring buffer."""
        if self._started:
            return

        import sounddevice as sd
        self._sd = sd

        # Retry opening — PulseAudio may need a moment after calibration.
        for attempt in range(5):
            try:
                self._stream = sd.InputStream(
                    samplerate=self._rate,
                    channels=self._channels,
                    dtype=self._dtype,
                    blocksize=1024,
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._started = True
                self.log(
                    f"Mic stream opened "
                    f"(rate={self._rate}, device-native, sounddevice)"
                )
                return
            except Exception as e:
                if attempt < 4:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                self.log(f"Mic stream failed after 5 attempts: {e}")
                raise

    def stop(self) -> None:
        """Stop the mic stream."""
        if not self._started:
            return
        with self._lock:
            try:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
            except Exception:
                pass
            self._stream = None
            self._started = False

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """sounddevice callback — append audio data to the ring buffer."""
        if status:
            pass  # overflow/underflow warnings — not critical
        with self._buf_lock:
            self._buf.extend(indata.tobytes())

    def read(self, num_frames: int) -> bytes:
        """
        Read num_frames worth of audio bytes from the ring buffer.

        Returns raw int16 mono audio bytes. If not enough data is
        available yet, returns whatever is in the buffer.
        """
        num_bytes = num_frames * self._channels * self._sample_width
        with self._buf_lock:
            if len(self._buf) >= num_bytes:
                chunk = bytes(self._buf[:num_bytes])
                self._buf = self._buf[num_bytes:]
                return chunk
            # Return whatever we have
            chunk = bytes(self._buf)
            self._buf.clear()
            return chunk

    def read_blocking(self, num_frames: int, timeout_s: float = 2.0) -> bytes:
        """Read exactly num_frames, waiting up to timeout_s if buffer is empty."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            chunk = self.read(num_frames)
            if len(chunk) >= num_frames * self._channels * self._sample_width:
                return chunk
            time.sleep(0.005)  # 5ms — small enough for low latency
        return self.read(num_frames)  # return whatever we got

    def flush(self) -> None:
        """Discard all buffered audio (e.g. after barge-in)."""
        with self._buf_lock:
            self._buf.clear()
