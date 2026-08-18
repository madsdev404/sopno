"""
sopno/voice/barge.py
━━━━━━━━━━━━━━━━━━━━━
Barge-in detection — Sopno stops talking the moment you start talking.

While TTS plays, a small background thread watches the microphone. It first
measures Sopno's *own* voice (so she doesn't interrupt herself through the
speakers), then flags an interrupt as soon as the user speaks over her.

The pure decision logic lives in ``BargeDetector`` (no audio I/O, easy to
unit-test); ``BargeInMonitor`` feeds it real mic frames in a thread.

Uses the shared ``MicStream`` (sounddevice) — no separate mic open/close,
no device race, no segfaults.
"""

from __future__ import annotations

import audioop
import threading
import time
from typing import Callable, Optional

from sopno.config.settings import settings
from sopno.voice.mic import MicStream


class BargeDetector:
    """
    Pure energy-gate detector: learns the assistant's own voice, then flags
    when the user speaks over it.

    Feed it one energy sample per mic frame via ``feed()``. Once the baseline
    (the assistant's own voice) is learned, any energy sustained above
    ``max(floor, baseline * multiplier + margin)`` for ``confirm_frames``
    consecutive samples confirms a barge-in.

    Energy scale matches SpeechRecognition: ``audioop.rms(frame, width)``,
    so ``floor`` maps directly to ``energy_threshold_floor``.
    """

    def __init__(
        self,
        *,
        floor: float,
        multiplier: float,
        margin: float,
        confirm_frames: int,
        baseline_frames: int,
    ) -> None:
        self._floor = floor
        self._multiplier = multiplier
        self._margin = margin
        self._confirm_frames = max(2, confirm_frames)
        self._baseline_frames = max(1, baseline_frames)

        self._baseline_sum = 0.0
        self._baseline_count = 0
        self._threshold: Optional[float] = None
        self._exceed = 0
        self.interrupted = False

    def feed(self, energy: float) -> bool:
        """
        Process one energy sample. Returns True once barge-in is confirmed.

        The first ``baseline_frames`` samples learn the own-voice baseline;
        afterwards each sample is compared against the computed threshold.
        """
        if self._threshold is None:
            self._baseline_sum += energy
            self._baseline_count += 1
            if self._baseline_count >= self._baseline_frames:
                baseline = self._baseline_sum / self._baseline_count
                self._threshold = max(
                    self._floor,
                    baseline * self._multiplier + self._margin,
                )
            return False

        if energy > self._threshold:
            self._exceed += 1
            if self._exceed >= self._confirm_frames:
                self.interrupted = True
                return True
        else:
            # Gentle decay — a single quiet frame doesn't reset the count
            self._exceed = max(0, self._exceed - 1)
        return False


class BargeInMonitor:
    """
    Watches the mic in a background thread while Sopno speaks.

    Uses the shared MicStream — no separate mic open/close, no device race.

    Usage:
        monitor = BargeInMonitor(mic_stream=mic, log_callback=log)
        monitor.start()                          # start watching
        speak(text, should_stop=monitor.interrupted,
              on_play_start=monitor.start_measurement)
        monitor.stop()                           # stop watching
        if monitor.interrupted: ...              # the user barged in
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None,
                 mic_stream: Optional[MicStream] = None) -> None:
        self.log = log_callback or (lambda m: print(f"[Barge] {m}"))
        self._mic_stream = mic_stream
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._measuring = threading.Event()
        self._interrupt = threading.Event()

        self._baseline_sec = float(getattr(settings, "barge_in_baseline_s", 0.4))
        self._multiplier = float(getattr(settings, "barge_in_multiplier", 1.7))
        self._margin = float(getattr(settings, "barge_in_margin", 30))
        self._confirm_s = float(getattr(settings, "barge_in_confirm_ms", 180)) / 1000.0
        self._floor = float(settings.energy_threshold_floor)

    @property
    def interrupted(self) -> bool:
        """Thread-safe flag: True once the user's voice is confirmed."""
        return self._interrupt.is_set()

    def start(self) -> None:
        """Begin listening for barge-in in a background thread."""
        self._stop.clear()
        self._interrupt.clear()
        self._measuring.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="barge-in")
        self._thread.start()

    def start_measurement(self) -> None:
        """Start learning the own-voice baseline (call once playback starts).

        Flushes stale pre-playback audio from the shared buffer so the baseline
        is learned from actual TTS output, not old ambient noise.
        """
        if self._mic_stream is not None:
            self._mic_stream.flush()
        self._measuring.set()

    def stop(self) -> None:
        """Stop the mic watcher."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _run(self) -> None:
        """Read frames from the shared mic stream and detect barge-in."""
        if self._mic_stream is None:
            self.log("No MicStream attached — barge-in disabled.")
            return

        rate = self._mic_stream.rate
        frames_per_sec = rate / 1024.0
        detector = BargeDetector(
            floor=self._floor,
            multiplier=self._multiplier,
            margin=self._margin,
            confirm_frames=max(1, int(self._confirm_s * frames_per_sec)),
            baseline_frames=max(1, int(self._baseline_sec * frames_per_sec)),
        )

        while not self._stop.is_set():
            try:
                chunk = self._mic_stream.read(1024, timeout_s=0.5)
            except Exception:
                break
            if not chunk:
                continue
            if not self._measuring.is_set():
                continue
            energy = audioop.rms(chunk, 2)
            if detector.feed(energy):
                self._interrupt.set()
                break
