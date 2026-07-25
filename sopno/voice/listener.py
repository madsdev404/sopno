"""
sopno/voice/listener.py
━━━━━━━━━━━━━━━━━━━━━━━
Microphone capture and ambient-noise calibration.

Default capture path uses SpeechRecognition's Microphone (device-native
sample rate). The custom Silero/PyAudio VAD path is optional because
forcing 16 kHz on a 44.1 kHz Linux mic was corrupting audio and making
Whisper invent garbage for both Bangla and English.
"""

from __future__ import annotations

import audioop
import sys
import time
from typing import Callable, Optional

import speech_recognition as sr

from sopno.config.settings import settings
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

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log = log_callback or (lambda m: print(f"[Listener] {m}"))
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = settings.dynamic_energy_threshold
        self.recognizer.pause_threshold = settings.pause_threshold
        self.recognizer.phrase_threshold = settings.phrase_threshold
        self.recognizer.energy_threshold = float(settings.energy_threshold_floor)
        self.recognizer.non_speaking_duration = min(0.5, settings.pause_threshold * 0.4)
        self.turn_taker = TurnTaker(log_callback=self.log)
        self._mic: Optional[sr.Microphone] = None

    def _clamp_energy(self) -> None:
        """Keep threshold low enough that normal speech always starts a phrase."""
        lo = float(settings.energy_threshold_floor)
        hi = float(settings.energy_threshold_ceiling)
        if hi < lo:
            hi = lo
        val = float(self.recognizer.energy_threshold)
        self.recognizer.energy_threshold = max(lo, min(val, hi))

    def _get_mic(self) -> sr.Microphone:
        """Reuse one Microphone so sample rate stays consistent."""
        if self._mic is None:
            # sample_rate=None → hardware default (usually 44100). Never force 16000 here.
            self._mic = sr.Microphone()
            self.log(
                f"Mic device ready "
                f"(sample_rate={self._mic.SAMPLE_RATE} Hz, width={self._mic.SAMPLE_WIDTH})."
            )
        return self._mic

    def calibrate(self, duration: float = 0.8) -> None:
        """Light ambient calibration, then clamp — heavy cal made the mic deaf."""
        try:
            mic = self._get_mic()
            with mic as source:
                self.log("Calibrating microphone for background noise…")
                self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                self._clamp_energy()
                self.log(
                    f"Microphone ready "
                    f"(energy_threshold={self.recognizer.energy_threshold:.0f}, "
                    f"pause={self.recognizer.pause_threshold:.1f}s)."
                )
        except Exception as e:
            print(f"[Listener] ERROR: Could not access microphone — {e}")
            print("  Check your microphone connection and PyAudio installation.")
            sys.exit(1)

    def listen(self, phrase_time_limit: int = 10) -> sr.AudioData:
        """Record until a pause (SpeechRecognition)."""
        mic = self._get_mic()
        with mic as source:
            return self.recognizer.listen(
                source,
                timeout=None,
                phrase_time_limit=phrase_time_limit,
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

        Default: classic SpeechRecognition (reliable audio).
        Optional: Silero VAD if settings.stt_capture == \"vad\".
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

        self._clamp_energy()
        need = float(self.recognizer.energy_threshold)
        self.log(
            "Capture mode: classic mic (device-native rate) "
            f"[need energy > {need:.0f}]"
        )

        timeout = None if max_wait_s <= 0 else float(max_wait_s)
        limit = int(max_utterance_s) if max_utterance_s else phrase_time_limit

        try:
            mic = self._get_mic()
            with mic as source:
                if getattr(source, "stream", None) is None:
                    raise RuntimeError(
                        "Microphone stream failed to open "
                        "(check mic permissions / device)."
                    )
                audio = self._listen_with_level_logs(
                    source,
                    running_check=running_check,
                    timeout=timeout,
                    phrase_time_limit=limit,
                )
            if audio is None:
                return None
            duration = len(audio.frame_data) / float(
                audio.sample_rate * audio.sample_width or 1
            )
            self.log(f"Turn captured (~{duration:.1f}s @ {audio.sample_rate} Hz).")
            if on_speech_start:
                on_speech_start()
            return audio
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            self.log(f"Classic listen failed: {e}")
            return None

    def _listen_with_level_logs(
        self,
        source: sr.AudioSource,
        *,
        running_check: Optional[Callable[[], bool]],
        timeout: Optional[float],
        phrase_time_limit: int,
    ) -> Optional[sr.AudioData]:
        """
        Like Recognizer.listen, but periodically logs mic RMS so a deaf
        threshold / silent device is obvious in the HUD.
        """
        assert source.stream is not None, "Microphone stream failed to open"

        seconds_per_buffer = float(source.CHUNK) / float(source.SAMPLE_RATE)
        elapsed = 0.0
        last_log = 0.0
        peak = 0
        frames: list[bytes] = []

        # ── wait for speech start ─────────────────────────────────────
        while True:
            if running_check is not None and not running_check():
                return None
            if timeout is not None and elapsed > timeout:
                raise sr.WaitTimeoutError("listening timed out while waiting for phrase to start")

            buffer = source.stream.read(source.CHUNK)
            if len(buffer) == 0:
                break
            elapsed += seconds_per_buffer
            energy = audioop.rms(buffer, source.SAMPLE_WIDTH)
            if energy > peak:
                peak = energy

            if elapsed - last_log >= 2.0:
                self.log(
                    f"Waiting for speech… mic={energy} peak={peak} "
                    f"(need > {self.recognizer.energy_threshold:.0f})"
                )
                last_log = elapsed

            if energy > self.recognizer.energy_threshold:
                frames.append(buffer)
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

            buffer = source.stream.read(source.CHUNK)
            if len(buffer) == 0:
                break
            frames.append(buffer)
            phrase_elapsed += seconds_per_buffer
            phrase_count += 1

            energy = audioop.rms(buffer, source.SAMPLE_WIDTH)
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
        if spoken < phrase_limit and len(buffer) != 0:
            # Too short — treat as no speech (caller keeps listening)
            self.log(f"Ignored short blip ({spoken} buffers, need ≥ {phrase_limit}).")
            return None

        return sr.AudioData(b"".join(frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH)
