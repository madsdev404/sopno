"""
sopno/voice/vad.py
━━━━━━━━━━━━━━━━━
Offline Voice Activity Detection (turn-taking) for natural conversation.

Uses Silero VAD via sherpa-onnx (already a project dependency) to detect
when the user starts and finishes speaking — closer to human turn-taking
than fixed timeouts.

Falls back to SpeechRecognition listen() if the VAD model is unavailable.
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import speech_recognition as sr

from sopno.config.settings import settings

_SAMPLE_RATE = 16000
_SILERO_URLS = (
    # Official sherpa-onnx release asset
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
    # Upstream Silero package data (fallback)
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
)


def ensure_silero_model(log: Optional[Callable[[str], None]] = None) -> Optional[Path]:
    """Return path to silero_vad.onnx, downloading once if missing."""
    _log = log or (lambda m: None)
    path = settings.models_dir / "silero_vad.onnx"
    if path.is_file() and path.stat().st_size > 10_000:
        return path

    settings.models_dir.mkdir(parents=True, exist_ok=True)
    for url in _SILERO_URLS:
        try:
            _log(f"Downloading Silero VAD model…\n  {url}")
            urllib.request.urlretrieve(url, path)
            if path.is_file() and path.stat().st_size > 10_000:
                _log(f"Silero VAD ready: {path}")
                return path
        except Exception as e:
            _log(f"VAD download failed ({e})")
    return None


def _float_to_audio_data(samples: np.ndarray, sample_rate: int = _SAMPLE_RATE) -> sr.AudioData:
    """Convert float32 mono [-1, 1] to SpeechRecognition AudioData."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    return sr.AudioData(pcm.tobytes(), sample_rate, 2)


class TurnTaker:
    """
    Capture one complete user utterance using offline Silero VAD.

    Flow:
      idle listen → speech starts → collect → silence after speech → end turn
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log = log_callback or (lambda m: print(f"[VAD] {m}"))
        self._vad = None
        self._window_size = 512
        self._available = False
        self._init_vad()

    @property
    def available(self) -> bool:
        return self._available

    def _init_vad(self) -> None:
        model_path = ensure_silero_model(self.log)
        if model_path is None:
            self.log("Silero VAD model missing — using classic mic listen fallback.")
            return
        try:
            import sherpa_onnx

            config = sherpa_onnx.VadModelConfig()
            config.silero_vad.model = str(model_path)
            config.silero_vad.threshold = 0.5
            # End turn shortly after the user stops (natural pause)
            config.silero_vad.min_silence_duration = 0.55
            config.silero_vad.min_speech_duration = 0.2
            config.silero_vad.max_speech_duration = 12.0
            config.sample_rate = _SAMPLE_RATE

            self._window_size = int(config.silero_vad.window_size)
            self._vad = sherpa_onnx.VoiceActivityDetector(
                config, buffer_size_in_seconds=60
            )
            self._available = True
            self.log("Silero VAD (sherpa-onnx) active for turn-taking.")
        except Exception as e:
            self.log(f"Could not init Silero VAD ({e}) — fallback listen.")
            self._vad = None
            self._available = False

    def listen_utterance(
        self,
        *,
        running_check: Optional[Callable[[], bool]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        max_wait_s: float = 10.0,
        max_utterance_s: float = 12.0,
    ) -> Optional[sr.AudioData]:
        """
        Wait for the user to speak, then return one full utterance.

        Args:
            running_check: return False to abort
            on_speech_start: fired once when VAD first detects speech
            max_wait_s: how long to wait for speech to begin (0 = forever)
            max_utterance_s: hard cap on utterance length
        """
        if not self._available or self._vad is None:
            return None

        try:
            import pyaudio
        except ImportError:
            self.log("PyAudio missing — cannot run VAD capture.")
            return None

        is_running = running_check or (lambda: True)
        pa = pyaudio.PyAudio()
        stream = None
        speech_started = False
        speech_notified = False
        started_at = time.time()
        speech_started_at = 0.0
        leftover = np.array([], dtype=np.float32)

        # Reset VAD internal state between turns
        try:
            self._vad.reset()
        except Exception:
            # Older sherpa builds may not expose reset — recreate is heavy; ignore
            pass

        try:
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=_SAMPLE_RATE,
                input=True,
                frames_per_buffer=max(self._window_size, 1024),
            )

            while is_running():
                raw = stream.read(self._window_size, exception_on_overflow=False)
                chunk = np.frombuffer(raw, dtype=np.float32)
                leftover = np.concatenate([leftover, chunk])

                while len(leftover) >= self._window_size:
                    window = leftover[: self._window_size]
                    leftover = leftover[self._window_size :]
                    self._vad.accept_waveform(window)

                    if not speech_started:
                        try:
                            if self._vad.is_speech_detected():
                                speech_started = True
                                speech_started_at = time.time()
                                if not speech_notified and on_speech_start:
                                    on_speech_start()
                                    speech_notified = True
                        except Exception:
                            pass

                # Completed speech segment(s)
                while not self._vad.empty():
                    seg = self._vad.front.samples
                    self._vad.pop()
                    if seg is None or len(seg) < int(0.2 * _SAMPLE_RATE):
                        continue
                    audio = _float_to_audio_data(np.asarray(seg, dtype=np.float32))
                    self.log(f"Turn captured ({len(seg) / _SAMPLE_RATE:.1f}s).")
                    return audio

                now = time.time()
                if not speech_started and max_wait_s > 0 and (now - started_at) >= max_wait_s:
                    self.log("No speech started — turn wait timed out.")
                    return None

                if speech_started and (now - speech_started_at) >= max_utterance_s:
                    self.log("Utterance hit max length — finalizing.")
                    # Force flush if possible
                    try:
                        self._vad.flush()
                    except Exception:
                        pass
                    while not self._vad.empty():
                        seg = self._vad.front.samples
                        self._vad.pop()
                        if seg is not None and len(seg) >= int(0.2 * _SAMPLE_RATE):
                            return _float_to_audio_data(np.asarray(seg, dtype=np.float32))
                    return None

            return None
        except Exception as e:
            self.log(f"VAD capture error: {e}")
            return None
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            try:
                pa.terminate()
            except Exception:
                pass
