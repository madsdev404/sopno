"""
sopno/voice/vad.py
━━━━━━━━━━━━━━━━━━
Offline Voice Activity Detection (turn-taking) for natural conversation.

Uses Silero VAD via sherpa-onnx to detect when the user starts and finishes
speaking. Captures from the shared MicStream (sounddevice) — no PyAudio,
no device races with barge-in.
"""

from __future__ import annotations

import audioop
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.mic import MicStream

_SAMPLE_RATE = 16000
_SILERO_URLS = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
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


def _to_16k_float(pcm16: bytes, in_rate: int, resample_state) -> Tuple[np.ndarray, object]:
    """Resample int16 PCM to 16 kHz float32 mono in [-1, 1]."""
    if in_rate != _SAMPLE_RATE:
        pcm16, resample_state = audioop.ratecv(pcm16, 2, 1, in_rate, _SAMPLE_RATE, resample_state)
    samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, resample_state


class TurnTaker:
    """
    Capture one complete user utterance using offline Silero VAD.

    Flow:
      idle listen → speech starts → collect → silence after speech → end turn

    Uses the shared MicStream for audio capture — no PyAudio.
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None,
                 mic_stream: Optional[MicStream] = None):
        self.log = log_callback or (lambda m: print(f"[VAD] {m}"))
        self._vad = None
        self._window_size = 512
        self._available = False
        self._mic_stream = mic_stream
        self._init_vad()

    def set_mic_stream(self, stream: MicStream) -> None:
        """Attach the shared mic stream."""
        self._mic_stream = stream

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
            config.silero_vad.threshold = 0.45
            config.silero_vad.min_silence_duration = 0.85
            config.silero_vad.min_speech_duration = 0.25
            config.silero_vad.max_speech_duration = 15.0
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
        Wait for the user to speak, then return one full utterance at 16 kHz.

        Uses the shared MicStream for audio capture.
        """
        if not self._available or self._vad is None:
            return None

        if self._mic_stream is None:
            self.log("No MicStream — VAD capture unavailable.")
            return None

        is_running = running_check or (lambda: True)
        speech_started = False
        speech_notified = False
        started_at = time.time()
        speech_started_at = 0.0
        leftover = np.array([], dtype=np.float32)
        resample_state = None
        # ~250ms pre-roll at 16 kHz
        pre_roll_max = int(0.25 * _SAMPLE_RATE)
        pre_roll = np.array([], dtype=np.float32)

        try:
            self._vad.reset()
        except Exception:
            pass

        try:
            capture_rate = self._mic_stream.rate
            self.log(f"Mic capture @ {capture_rate} Hz → resample → {_SAMPLE_RATE} Hz for VAD/STT.")

            # Read enough int16 frames so that after resample we keep up with VAD windows
            read_frames = 1024

            while is_running():
                raw = self._mic_stream.read(read_frames, timeout_s=0.5)
                if not raw:
                    continue
                chunk_f, resample_state = _to_16k_float(raw, capture_rate, resample_state)
                leftover = np.concatenate([leftover, chunk_f])

                while len(leftover) >= self._window_size:
                    window = leftover[: self._window_size]
                    leftover = leftover[self._window_size :]

                    if not speech_started:
                        pre_roll = np.concatenate([pre_roll, window])
                        if len(pre_roll) > pre_roll_max:
                            pre_roll = pre_roll[-pre_roll_max:]

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

                while not self._vad.empty():
                    seg = self._vad.front.samples
                    self._vad.pop()
                    if seg is None or len(seg) < int(0.25 * _SAMPLE_RATE):
                        continue
                    samples = np.asarray(seg, dtype=np.float32)
                    if len(pre_roll):
                        lead = pre_roll[-int(0.15 * _SAMPLE_RATE) :]
                        samples = np.concatenate([lead, samples])
                    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
                    if peak > 1e-3:
                        samples = samples * min(0.95 / peak, 3.0)
                    audio = _float_to_audio_data(samples)
                    self.log(f"Turn captured ({len(samples) / _SAMPLE_RATE:.1f}s).")
                    return audio

                now = time.time()
                if not speech_started and max_wait_s > 0 and (now - started_at) >= max_wait_s:
                    self.log("No speech started — turn wait timed out.")
                    return None

                if speech_started and (now - speech_started_at) >= max_utterance_s:
                    self.log("Utterance hit max length — finalizing.")
                    try:
                        self._vad.flush()
                    except Exception:
                        pass
                    while not self._vad.empty():
                        seg = self._vad.front.samples
                        self._vad.pop()
                        if seg is not None and len(seg) >= int(0.25 * _SAMPLE_RATE):
                            return _float_to_audio_data(np.asarray(seg, dtype=np.float32))
                    return None

            return None
        except Exception as e:
            self.log(f"VAD capture error: {e}")
            return None
