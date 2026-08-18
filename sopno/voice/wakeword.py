"""
sopno/voice/wakeword.py
━━━━━━━━━━━━━━━━━━━━━━
Wake-word detection engine.

Leverages 'sherpa-onnx' for fast, offline, low-latency wake-word spotting (KWS).
If sherpa-onnx is unavailable, it falls back to a continuous STT-based approach.

Both paths read from the shared MicStream (sounddevice) — no PvRecorder,
no PyAudio, no device conflicts.
"""

import re
import time
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.mic import MicStream
from sopno.voice.stt import transcribe


def dynamic_greeting() -> str:
    """Return a short, time-appropriate greeting."""
    hour = datetime.now().hour
    if hour < 6:
        period = "night"
        msg = "Up late?"
    elif hour < 12:
        period = "morning"
        msg = "Hope you slept well"
    elif hour < 17:
        period = "afternoon"
        msg = "Good afternoon"
    elif hour < 21:
        period = "evening"
        msg = "Good evening"
    else:
        period = "night"
        msg = "Working late?"

    greetings = {
        "morning": [
            f"Good morning! {msg}. Sopno here, what's on your mind?",
            f"Morning! {msg}. What can I help with?",
            f"Hey, good morning. {msg}. What do you need?",
        ],
        "afternoon": [
            f"{msg}. Sopno here, what's up?",
            f"Hey! {msg}. What can I do for you?",
            f"Afternoon! What's on your mind?",
        ],
        "evening": [
            f"{msg}. Sopno here, what do you need?",
            f"Hey, {msg.lower()}. What can I help with?",
            f"{msg}. What's on your mind?",
        ],
        "night": [
            f"Hey, {msg.lower()}. What do you need?",
            f"Night owl? Sopno here. What's up?",
            f"{msg}. What can I help with?",
        ],
    }
    import random
    return random.choice(greetings[period])


class WakeWordDetector:
    """Detects when the user says the wake word."""

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log = log_callback or (lambda msg: print(f"[WakeWord] {msg}"))
        self.use_sherpa = False
        self.kws = None
        self._init_sherpa()

    def _init_sherpa(self) -> None:
        """Attempt to initialize sherpa-onnx keyword spotter."""
        model_dir = settings.models_dir / "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
        tokens_path = model_dir / "tokens.txt"
        encoder_path = model_dir / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
        decoder_path = model_dir / "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
        joiner_path = model_dir / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"

        if tokens_path.exists() and encoder_path.exists():
            try:
                import sherpa_onnx

                tokens = {}
                with open(tokens_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) == 2:
                            tokens[parts[0]] = int(parts[1])

                def tokenize_word(word: str) -> str:
                    word_to_match = "▁" + word.upper().replace(" ", "▁")
                    sorted_tokens = sorted(tokens.keys(), key=len, reverse=True)
                    result_tokens = []
                    i = 0
                    while i < len(word_to_match):
                        matched = False
                        for t in sorted_tokens:
                            if word_to_match[i:].startswith(t):
                                result_tokens.append(t)
                                i += len(t)
                                matched = True
                                break
                        if not matched:
                            result_tokens.append(word_to_match[i])
                            i += 1
                    return " ".join(result_tokens)

                keywords_to_register = []
                for kw in settings.wake_words:
                    kw_clean = kw.lower().strip()
                    kw_clean = re.sub(r'[^a-zA-Z\s]', '', kw_clean)
                    if kw_clean:
                        token_seq = tokenize_word(kw_clean)
                        if token_seq:
                            keywords_to_register.append(f"{token_seq} :1.5")

                if not keywords_to_register:
                    keywords_to_register = ["▁DR E A M :1.5"]

                temp_keywords_path = model_dir / "active_keywords.txt"
                with open(temp_keywords_path, "w", encoding="utf-8") as f:
                    for kw_line in keywords_to_register:
                        f.write(kw_line + "\n")

                self.kws = sherpa_onnx.KeywordSpotter(
                    tokens=str(tokens_path),
                    encoder=str(encoder_path),
                    decoder=str(decoder_path),
                    joiner=str(joiner_path),
                    num_threads=1,
                    keywords_file=str(temp_keywords_path),
                    provider="cpu",
                )
                self.use_sherpa = True
                self.log(f"sherpa-onnx KWS active. Wake words: {settings.wake_words}")
            except Exception as e:
                self.log(f"Failed to load sherpa-onnx ({e}). Falling back to STT-based wake word.")
                self.use_sherpa = False
        else:
            self.log("sherpa-onnx model files not found. Using STT-based wake word detection.")

    def wait_for_wakeword(self, recognizer: sr.Recognizer, running_check: Callable[[], bool],
                          mic_stream: Optional[MicStream] = None) -> bool:
        """
        Blocks until the wake word is spoken.

        Reads from the shared MicStream — no PvRecorder, no PyAudio.
        """
        if mic_stream is None:
            self.log("No MicStream — cannot detect wake word.")
            return False

        try:
            if self.use_sherpa and self.kws is not None:
                return self._detect_sherpa(mic_stream, running_check)
            else:
                return self._detect_stt(mic_stream, recognizer, running_check)
        finally:
            pass

    def _detect_sherpa(self, mic_stream: MicStream,
                       running_check: Callable[[], bool]) -> bool:
        """sherpa-onnx KWS detection using the shared MicStream."""
        import sherpa_onnx

        self.log("Listening for wake word (sherpa-onnx)…")
        stream = self.kws.create_stream()
        chunk_frames = 512  # sherpa-onnx expects 512-sample windows

        try:
            while running_check():
                chunk = mic_stream.read(chunk_frames, timeout_s=0.5)
                if not chunk:
                    continue
                # MicStream is 16kHz int16 — perfect for sherpa-onnx
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                stream.accept_waveform(mic_stream.rate, samples)

                while self.kws.is_ready(stream):
                    self.kws.decode_stream(stream)

                result = self.kws.get_result(stream)
                if result != "":
                    self.kws.reset_stream(stream)
                    self.log("Wake word detected!")
                    return True
        except Exception as e:
            self.log(f"sherpa-onnx error: {e}. Falling back to STT-based detection.")
            return self._detect_stt(mic_stream, None, running_check)

        return False

    def _detect_stt(self, mic_stream: MicStream,
                    recognizer: Optional[sr.Recognizer],
                    running_check: Callable[[], bool]) -> bool:
        """STT-based wake word detection using the shared MicStream."""
        self.log("Listening for wake word (STT fallback)…")

        while running_check():
            try:
                chunk_size = 1024
                frames: list[bytes] = []
                total_frames = 0
                target_frames = int(mic_stream.rate * 3.0)

                while total_frames < target_frames and running_check():
                    chunk = mic_stream.read(chunk_size, timeout_s=0.5)
                    if not chunk:
                        continue
                    frames.append(chunk)
                    total_frames += len(chunk) // (mic_stream.channels * mic_stream.sample_width)

                if not frames:
                    continue

                audio = sr.AudioData(b"".join(frames), mic_stream.rate, mic_stream.sample_width)
                text = transcribe(recognizer, audio)
                self.log(f"Heard: '{text}'")
                text_lower = text.lower().strip()

                if any(ww.lower().strip() in text_lower for ww in settings.wake_words):
                    self.log("Wake word detected!")
                    return True

            except sr.UnknownValueError:
                self._ww_fail_count = getattr(self, "_ww_fail_count", 0) + 1
                if self._ww_fail_count % 5 == 1:
                    self.log(
                        f"Wake word not recognized "
                        f"({self._ww_fail_count} attempts). "
                        f"Speak clearly after the prompt."
                    )
                continue
            except Exception as e:
                time.sleep(0.5)
                continue

        return False
