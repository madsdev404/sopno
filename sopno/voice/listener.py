"""
sopno/voice/listener.py
━━━━━━━━━━━━━━━━━━━━━━
Microphone capture and ambient-noise calibration.

Uses the shared MicStream (sounddevice) for audio capture — no PyAudio.
This eliminates the device open/close race that caused segfaults when
PyAudio (listener) and sounddevice (barge-in) competed for the mic.
"""

from __future__ import annotations

import audioop
import struct
import sys
import time
from typing import Callable, Optional

import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.mic import MicStream
from sopno.voice.vad import TurnTaker


def _install_alsa_error_handler() -> None:
    """Silence libasound callback spam (JACK/ALSA probe noise)."""
    try:
        import ctypes

        ERROR_HANDLER = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
        )

        def _noop(filename, line, function, err, fmt):  # noqa: ANN001
            return None

        handler = ERROR_HANDLER(_noop)
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        asound.snd_lib_error_set_handler(handler)
        _install_alsa_error_handler._handler = handler  # type: ignore[attr-defined]
    except Exception:
        pass


_install_alsa_error_handler()


class Listener:
    """Calibration + one-turn microphone capture for STT."""

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None,
                 mic_stream: Optional[MicStream] = None):
        self.log = log_callback or (lambda m: print(f"[Listener] {m}"))
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = settings.dynamic_energy_threshold
        self.recognizer.pause_threshold = settings.pause_threshold
        self.recognizer.phrase_threshold = settings.phrase_threshold
        self.recognizer.energy_threshold = float(settings.energy_threshold_floor)
        self.recognizer.non_speaking_duration = min(0.5, settings.pause_threshold * 0.4)
        self.turn_taker = TurnTaker(log_callback=self.log, mic_stream=mic_stream)
        self._mic_stream: Optional[MicStream] = mic_stream
        self._last_barge_close: float = 0.0  # set by assistant after barge-in

    def set_mic_stream(self, stream: MicStream) -> None:
        """Attach the shared mic stream (called by assistant before calibrate)."""
        self._mic_stream = stream
        self.turn_taker.set_mic_stream(stream)

    def _clamp_energy(self) -> None:
        """Keep threshold low enough that normal speech always starts a phrase."""
        lo = float(settings.energy_threshold_floor)
        hi = float(settings.energy_threshold_ceiling)
        if hi < lo:
            hi = lo
        old = float(self.recognizer.energy_threshold)
        clamped = max(lo, min(old, hi))
        if clamped != old:
            self.log(
                f"Energy threshold clamped: {old:.0f} → {clamped:.0f} "
                f"(range {lo:.0f}–{hi:.0f})"
            )
        self.recognizer.energy_threshold = clamped

    def calibrate(self, duration: float = 0.8) -> None:
        """Light ambient calibration using the shared MicStream."""
        if self._mic_stream is None:
            print("[Listener] ERROR: No MicStream attached. Call set_mic_stream() first.")
            sys.exit(1)

        try:
            self.log("Calibrating microphone for background noise…")
            self._mic_stream.start()

            # Read ambient noise for `duration` seconds
            total_frames = int(self._mic_stream.rate * duration)
            chunk_size = 1024
            energies = []

            frames_read = 0
            while frames_read < total_frames:
                chunk = self._mic_stream.read_blocking(chunk_size)
                if not chunk:
                    time.sleep(0.01)
                    continue
                # chunk is int16 mono bytes — compute RMS energy
                energy = audioop.rms(chunk, 2)
                energies.append(energy)
                frames_read += len(chunk) // (self._mic_stream.channels * self._mic_stream.sample_width)

            if energies:
                avg_energy = sum(energies) / len(energies)
                # Set threshold to ~2x ambient noise (standard SR calibration)
                self.recognizer.energy_threshold = max(
                    float(settings.energy_threshold_floor),
                    avg_energy * 2.0,
                )

            self._clamp_energy()
            self.log(
                f"Microphone ready "
                f"(energy_threshold={self.recognizer.energy_threshold:.0f}, "
                f"pause={self.recognizer.pause_threshold:.1f}s, "
                f"sample_rate={self._mic_stream.rate} Hz)."
            )
        except Exception as e:
            print(f"[Listener] ERROR: Could not access microphone — {e}")
            print("  Check your microphone connection and sounddevice installation.")
            sys.exit(1)

    def listen(self, phrase_time_limit: int = 10) -> sr.AudioData:
        """Record until a pause — reads from the shared MicStream."""
        if self._mic_stream is None:
            raise RuntimeError("No MicStream attached")

        frames: list[bytes] = []
        chunk_size = 1024
        seconds_per_buffer = chunk_size / float(self._mic_stream.rate)
        pause_limit = int(self.recognizer.pause_threshold / seconds_per_buffer)
        phrase_limit = int(phrase_time_limit / seconds_per_buffer)
        pause_count = 0
        phrase_count = 0

        while phrase_count < phrase_limit:
            chunk = self._mic_stream.read_blocking(chunk_size)
            if not chunk:
                break
            frames.append(chunk)
            phrase_count += 1

            energy = audioop.rms(chunk, 2)
            if energy > self.recognizer.energy_threshold:
                pause_count = 0
            else:
                pause_count += 1
            if pause_count > pause_limit:
                break

        if not frames:
            raise sr.UnknownValueError("no audio captured")

        return sr.AudioData(
            b"".join(frames),
            self._mic_stream.rate,
            self._mic_stream.sample_width,
        )

    def listen_for_turn(
        self,
        *,
        running_check: Optional[Callable[[], bool]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        max_wait_s: float = 0.0,
        max_utterance_s: float = 12.0,
        phrase_time_limit: int = 10,
    ) -> Optional[sr.AudioData]:
        """
        Wait for the user to speak, then return one full utterance.

        Reads from the shared MicStream — no PyAudio, no device races.
        """
        use_vad = (
            getattr(settings, "stt_capture", "classic") == "vad"
            and self.turn_taker.available
        )

        if use_vad:
            self.log("Capture mode: Silero VAD")
            return self.turn_taker.listen_utterance(
                running_check=running_check,
                on_speech_start=on_speech_start,
                max_wait_s=max_wait_s,
                max_utterance_s=max_utterance_s,
            )

        if running_check is not None and not running_check():
            return None

        if self._mic_stream is None:
            self.log("No MicStream attached — cannot listen.")
            return None

        need = float(self.recognizer.energy_threshold)
        self.log(
            "Capture mode: shared MicStream (sounddevice, no PyAudio) "
            f"[need energy > {need:.0f}]"
        )

        effective_timeout = None if max_wait_s <= 0 else float(max_wait_s)
        _HARD_WAIT_LIMIT = 30.0

        limit = int(max_utterance_s) if max_utterance_s else phrase_time_limit

        audio = self._listen_with_level_logs(
            running_check=running_check,
            timeout=effective_timeout,
            phrase_time_limit=limit,
            on_speech_start=on_speech_start,
            hard_wait_limit=_HARD_WAIT_LIMIT,
        )

        if audio is None:
            return None

        duration = len(audio.frame_data) / float(audio.sample_rate * audio.sample_width or 1)
        self.log(f"Turn captured (~{duration:.1f}s @ {audio.sample_rate} Hz).")
        return audio

    def _listen_with_level_logs(
        self,
        *,
        running_check: Optional[Callable[[], bool]],
        timeout: Optional[float],
        phrase_time_limit: int,
        on_speech_start: Optional[Callable[[], None]] = None,
        hard_wait_limit: float = 30.0,
    ) -> Optional[sr.AudioData]:
        """
        Like Recognizer.listen, but reads from the shared MicStream
        and periodically logs mic RMS.
        """
        if self._mic_stream is None:
            return None

        rate = self._mic_stream.rate
        chunk_size = 1024
        seconds_per_buffer = chunk_size / float(rate)
        elapsed = 0.0
        last_log = 0.0
        peak = 0
        frames: list[bytes] = []
        _speech_fired = False

        # ── wait for speech start ─────────────────────────────────────
        while True:
            if running_check is not None and not running_check():
                return None
            if elapsed > hard_wait_limit:
                self.log(
                    f"No speech detected after {hard_wait_limit:.0f}s — "
                    f"threshold may be too high (>{self.recognizer.energy_threshold:.0f})."
                )
                raise sr.WaitTimeoutError(
                    f"no speech after {hard_wait_limit:.0f}s"
                )
            if timeout is not None and elapsed > timeout:
                raise sr.WaitTimeoutError("listening timed out while waiting for phrase to start")

            chunk = self._mic_stream.read_blocking(chunk_size)
            if not chunk:
                break
            elapsed += seconds_per_buffer
            energy = audioop.rms(chunk, 2)
            if energy > peak:
                peak = energy

            if elapsed - last_log >= 2.0:
                self.log(
                    f"Waiting for speech… mic={energy} peak={peak} "
                    f"(need > {self.recognizer.energy_threshold:.0f})"
                )
                last_log = elapsed

            if energy > self.recognizer.energy_threshold:
                frames.append(chunk)
                if on_speech_start is not None and not _speech_fired:
                    _speech_fired = True
                    on_speech_start()
                break

        if not frames:
            return None

        # ── capture until pause ───────────────────────────────────────
        pause_limit = int(self.recognizer.pause_threshold / seconds_per_buffer)
        phrase_limit = int(self.recognizer.phrase_threshold / seconds_per_buffer)
        non_speak = int(self.recognizer.non_speaking_duration / seconds_per_buffer)
        pause_count = 0
        phrase_count = 1  # already have the starting buffer
        phrase_elapsed = seconds_per_buffer

        while True:
            if running_check is not None and not running_check():
                return None
            if phrase_time_limit and phrase_elapsed > phrase_time_limit:
                break

            chunk = self._mic_stream.read_blocking(chunk_size)
            if not chunk:
                break
            frames.append(chunk)
            phrase_elapsed += seconds_per_buffer
            phrase_count += 1

            energy = audioop.rms(chunk, 2)
            if energy > self.recognizer.energy_threshold:
                pause_count = 0
            else:
                pause_count += 1
            if pause_count > pause_limit:
                break

        # Drop trailing silence, require minimum phrase length
        drop = max(0, pause_count - non_speak)
        if drop:
            frames = frames[: len(frames) - drop]
        spoken = phrase_count - pause_count
        if spoken < phrase_limit and len(frames) > 0:
            self.log(f"Ignored short blip ({spoken} buffers, need ≥ {phrase_limit}).")
            return None

        return sr.AudioData(b"".join(frames), rate, self._mic_stream.sample_width)
