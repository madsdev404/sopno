"""
sopno/voice/mic.py
━━━━━━━━━━━━━━━━━━━
Single shared microphone stream with one InputStream callback.

Opens ONE sounddevice InputStream and feeds audio into a single
thread-safe bytearray buffer. All consumers (wake word, listener)
read sequentially from the same buffer — no fan-out, no stale audio.

Barge-in detection happens IN the callback itself — no separate thread,
no frame consumption. The callback computes RMS energy per block and
sets a threading.Event when energy exceeds the barge-in threshold.
"""

from __future__ import annotations

import audioop
import struct
import threading
import time
from typing import Optional


class MicStream:
    """
    Thread-safe shared microphone stream.

    Opens one sd.InputStream and writes all captured audio into a
    single bytearray buffer. Consumers call read() to get audio —
    reading CONSUMES from the buffer (FIFO).

    Barge-in: call set_barge_threshold(energy) to arm detection.
    When energy exceeds the threshold for enough consecutive blocks,
    the barge_in Event is set. Check barge_in.is_set() from the
    main thread — no separate monitoring thread needed.
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

        # ── Barge-in detection (runs in the audio callback) ──────────
        self._barge_threshold: Optional[float] = None  # None = disabled
        self._barge_consecutive = 0
        self._barge_need = 0  # consecutive blocks needed
        self.barge_in = threading.Event()
        # Calibration: collect energy for N blocks, then compute average
        self._barge_cal_collecting = False
        self._barge_cal_remaining = 0
        self._barge_cal_sum = 0.0
        self._barge_cal_count = 0
        self._barge_baseline_avg = 0.0

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

    # ── Barge-in API ────────────────────────────────────────────────

    def set_barge_threshold(self, energy: float, confirm_blocks: int = 8) -> None:
        """
        Arm barge-in detection. When RMS energy exceeds ``energy``
        for ``confirm_blocks`` consecutive callback blocks (~64ms each),
        ``self.barge_in`` is set.

        Pass energy=0 or call clear_barge() to disarm.
        """
        if energy <= 0:
            self.clear_barge()
            return
        with self._lock:
            self._barge_threshold = energy
            self._barge_consecutive = 0
            self._barge_need = confirm_blocks
            self.barge_in.clear()

    def clear_barge(self) -> None:
        """Disarm barge-in detection and clear the flag."""
        with self._lock:
            self._barge_threshold = None
            self._barge_consecutive = 0
            self._barge_cal_collecting = False
            self.barge_in.clear()

    def start_barge_calibration(self, num_blocks: int = 8) -> None:
        """Start collecting energy samples in the callback to learn the
        TTS audio baseline. After ``num_blocks`` blocks, the average
        energy is stored in ``_barge_baseline_avg``."""
        with self._lock:
            self._barge_cal_collecting = True
            self._barge_cal_remaining = num_blocks
            self._barge_cal_sum = 0.0
            self._barge_cal_count = 0

    # ── Callback ────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """sounddevice callback — append audio + inline barge-in check."""
        raw = indata.tobytes()
        energy = float(audioop.rms(raw, 2))

        with self._lock:
            # Barge-in calibration: collect energy for N blocks
            if self._barge_cal_collecting and self._barge_cal_remaining > 0:
                self._barge_cal_sum += energy
                self._barge_cal_count += 1
                self._barge_cal_remaining -= 1
                if self._barge_cal_remaining <= 0:
                    self._barge_baseline_avg = (
                        self._barge_cal_sum / self._barge_cal_count
                        if self._barge_cal_count > 0 else 0.0
                    )
                    self._barge_cal_collecting = False

            # Barge-in detection: check against threshold
            if self._barge_threshold is not None:
                if energy > self._barge_threshold:
                    self._barge_consecutive += 1
                    if self._barge_consecutive >= self._barge_need:
                        self.barge_in.set()
                        self._barge_threshold = None  # one-shot
                else:
                    self._barge_consecutive = max(0, self._barge_consecutive - 1)

        with self._cond:
            self._buf.extend(raw)
            self._cond.notify_all()
