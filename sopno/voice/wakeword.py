"""
sopno/voice/wakeword.py
━━━━━━━━━━━━━━━━━━━━━━━
Wake-word detection engine.

Leverages 'sherpa-onnx' for fast, offline, low-latency wake-word spotting (KWS).
If sherpa-onnx or pvrecorder are unavailable, it falls back gracefully to a
continuous SpeechRecognition-based pattern matching approach.
"""

import os
import re
import sys
import time
from typing import Callable, Optional

import speech_recognition as sr

from sopno.config.settings import settings
from sopno.voice.stt import transcribe


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
                
                # Load tokens to perform greedy BPE tokenization
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
                self.log(f"Failed to load sherpa-onnx ({e}). Falling back to continuous SpeechRecognition.")
                self.use_sherpa = False
        else:
            self.log("sherpa-onnx model files not found. Using continuous SpeechRecognition for wake words.")

    def wait_for_wakeword(self, recognizer: sr.Recognizer, running_check: Callable[[], bool]) -> bool:
        """
        Blocks until the wake word is spoken.

        Args:
            recognizer: Shared SpeechRecognition Recognizer instance (for fallback)
            running_check: A zero-argument function returning False if the assistant should exit

        Returns:
            True if the wake word was successfully detected, False if exiting.
        """
        if self.use_sherpa and self.kws is not None:
            try:
                from pvrecorder import PvRecorder
                import numpy as np

                self.log("Listening for wake word (sherpa-onnx)…")
                recorder = PvRecorder(device_index=-1, frame_length=512)
                recorder.start()
                stream = self.kws.create_stream()

                try:
                    while running_check():
                        pcm = recorder.read()
                        samples = np.array(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                        stream.accept_waveform(16000, samples)

                        while self.kws.is_ready(stream):
                            self.kws.decode_stream(stream)

                        result = self.kws.get_result(stream)
                        if result != "":
                            self.kws.reset_stream(stream)
                            self.log("Wake word detected!")
                            return True
                finally:
                    try:
                        recorder.stop()
                        recorder.delete()
                    except Exception:
                        pass
            except Exception as e:
                self.log(f"Error in sherpa-onnx stream: {e}. Falling back to SpeechRecognition.")
                self.use_sherpa = False

        # ── Fallback: Continuous SpeechRecognition check ───────────────────────
        self.log("Listening for wake word (SpeechRecognition fallback)…")
        while running_check():
            try:
                with sr.Microphone() as source:
                    try:
                        audio = recognizer.listen(source, timeout=3.0, phrase_time_limit=3.0)
                    except sr.WaitTimeoutError:
                        continue

                text = transcribe(recognizer, audio)
                self.log(f"Heard: '{text}'")
                text_lower = text.lower().strip()

                # Match wake words from config
                if any(ww.lower().strip() in text_lower for ww in settings.wake_words):
                    self.log("Wake word detected!")
                    return True

            except sr.UnknownValueError:
                # Silently ignore un-decodable audio / background noise
                continue
            except Exception as e:
                time.sleep(0.5)
                continue

        return False
