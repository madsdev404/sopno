"""
sopno/voice/barge.py
━━━━━━━━━━━━━━━━━━━━
Barge-in detection — Sopno stops talking the moment you start talking.

While TTS plays, a small background thread watches the microphone. It first
measures Sopno's *own* voice (so she doesn't interrupt herself through the
speakers), then flags an interrupt as soon as the user speaks over her.

The pure decision logic lives in ``BargeDetector`` (no audio I/O, easy to
unit-test); ``BargeInMonitor`` feeds it real mic frames in a thread.

Graceful degradation: if PyAudio or the mic is unavailable, barge-in is simply
disabled and playback runs to completion.
"""

from __future__ import annotations

import audioop
import threading
import time
from typing import Callable, Optional

from sopno.config.settings import settings


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

    Usage:
        monitor = BargeInMonitor(log_callback=log)
        monitor.start()                          # open the mic
        speak(text, should_stop=monitor.interrupt,
              on_play_start=monitor.start_measurement)
        monitor.stop()                           # close the mic
        if monitor.interrupted: ...              # the user barged in
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None,
                 listener=None) -> None:
        self.log = log_callback or (lambda m: print(f"[Barge] {m}"))
        self._listener = listener  # shared mic source
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._measuring = threading.Event()
        self._interrupt = threading.Event()
        # Direct refs to PyAudio objects so stop() can close them even if
        # the thread is orphaned (stream.read blocked on some ALSA drivers).
        self._stream = None
        self._pa = None
        self._stream_lock = threading.Lock()

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
        self._thread = threading.Thread(target=self._run, daemon=True, name="barge-in")
        self._thread.start()

    def start_measurement(self) -> None:
        """Start learning the own-voice baseline (call once playback starts)."""
        self._measuring.set()

    def stop(self) -> None:
        """Stop the mic watcher and close the audio stream directly."""
        self._stop.set()
        # Close the stream directly — don't rely on thread join which can
        # hang if stream.read() is blocked on some ALSA drivers.
        with self._stream_lock:
            try:
                if self._stream is not None:
                    self._stream.stop_stream()
                    self._stream.close()
            except Exception:
                pass
            try:
                if self._pa is not None:
                    self._pa.terminate()
            except Exception:
                pass
            self._stream = None
            self._pa = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _open_stream(self, pa):
        """Open the default mic at a supported rate; returns (stream, rate)."""
        info = pa.get_default_input_device_info()
        device_index = int(info["index"])
        native = int(info.get("defaultSampleRate") or 44100)
        for rate in (native, 44100, 48000, 16000):
            try:
                stream = pa.open(
                    format=pa.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=1024,
                )
                return stream, rate
            except Exception:
                continue
        raise RuntimeError("Could not open microphone input stream.")

    def _run(self) -> None:
        # Try shared mic from listener first (PulseAudio-friendly).
        if self._listener is not None:
            stream, rate = self._listener.open_shared_mic()
            if stream is not None:
                with self._stream_lock:
                    self._stream = stream
                try:
                    self._run_loop(stream, rate)
                finally:
                    self._listener.close_shared_mic()
                    with self._stream_lock:
                        self._stream = None
                return

        # Fallback: open our own mic (works on ALSA, fails on PulseAudio).
        try:
            import pyaudio
        except ImportError:
            self.log("PyAudio missing — barge-in disabled.")
            return

        pa = None
        stream = None
        time.sleep(0.5)
        for attempt in range(4):
            try:
                pa = pyaudio.PyAudio()
                stream, rate = self._open_stream(pa)
                with self._stream_lock:
                    self._pa = pa
                    self._stream = stream
                break
            except Exception as e:
                try:
                    if pa is not None:
                        pa.terminate()
                except Exception:
                    pass
                pa = None
                stream = None
                if attempt < 3:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                self.log(f"Mic unavailable — barge-in disabled ({e}).")
                return

        try:
            self._run_loop(stream, rate)
        finally:
            with self._stream_lock:
                self._stream = None
                self._pa = None
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            try:
                pa.terminate()
            except Exception:
                pass

    def _run_loop(self, stream, rate: int) -> None:
        """Core barge-in detection loop — reads from the given stream."""
        frames_per_sec = rate / float(1024)
        detector = BargeDetector(
            floor=self._floor,
            multiplier=self._multiplier,
            margin=self._margin,
            confirm_frames=max(1, int(self._confirm_s * frames_per_sec)),
            baseline_frames=max(1, int(self._baseline_sec * frames_per_sec)),
        )

        try:
            while not self._stop.is_set():
                try:
                    frame = stream.read(1024, exception_on_overflow=False)
                except Exception:
                    break
                if not self._measuring.is_set():
                    continue
                energy = audioop.rms(frame, 2)
                if detector.feed(energy):
                    self._interrupt.set()
                    break
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
