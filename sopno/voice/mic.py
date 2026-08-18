"""
sopno/voice/mic.py
━━━━━━━━━━━━━━━━━━
Single shared microphone stream with one InputStream callback.

Opens ONE sounddevice InputStream and feeds audio into a single
thread-safe bytearray buffer. All consumers (wake word, listener,
barge-in) read sequentially from the same buffer — no fan-out,
no stale audio, no frame consumption races.

Based on the voice-core pattern: single InputStream callback,
Condition-based read, no ring buffer duplication.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class MicStream:
    """
    Thread-safe shared microphone stream.

    Opens one sd.InputStream and writes all captured audio into a
    single bytearray buffer. Consumers call read() to get audio —
    reading CONSUMES from the buffer (FIFO). This means callers
    must coordinate access (wake word → listener → barge-in are
    sequential in the assistant pipeline, so no locking needed).
    """

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda m: print(f"[Mic] {m}"))
        self._sd = None
        self._stream = None
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
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
        """Open the mic stream and begin capturing into the shared buffer."""
        if self._started:
            return

        import sounddevice as sd
        self._sd = sd

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
                    f"(rate={self._rate}, sounddevice, shared buffer)"
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
            self._cond.notify_all()

    def read(self, num_frames: int, timeout_s: float = 2.0) -> bytes:
        """
        Read exactly num_frames from the shared buffer (blocking).

        Returns up to num_frames of audio data. If the buffer has less
        than requested, waits up to timeout_s for more data to arrive.
        Returns whatever is available after the timeout (may be empty).
        """
        num_bytes = num_frames * self._channels * self._sample_width
        deadline = time.monotonic() + timeout_s

        with self._cond:
            while len(self._buf) < num_bytes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=min(remaining, 0.05))

            # Take what's available (up to num_bytes)
            take = min(len(self._buf), num_bytes)
            if take == 0:
                return b""
            chunk = bytes(self._buf[:take])
            self._buf = self._buf[take:]
            return chunk

    def flush(self) -> None:
        """Discard all buffered audio (e.g. between conversation turns)."""
        with self._lock:
            self._buf.clear()

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """sounddevice callback — append audio to the shared buffer."""
        with self._cond:
            self._buf.extend(indata.tobytes())
            self._cond.notify_all()
