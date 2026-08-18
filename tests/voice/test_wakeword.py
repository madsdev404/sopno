"""
tests/test_wakeword.py
━━━━━━━━━━━━━━━━━━━━━━━
Unit tests for WakeWordDetector and listening mode integration.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.voice.wakeword import WakeWordDetector, dynamic_greeting


def _make_mock_mic_stream(rate=16000):
    """Create a mock MicStream that returns silence from read()."""
    mock_stream = MagicMock()
    mock_stream.rate = rate
    mock_stream.channels = 1
    mock_stream.sample_width = 2
    # Return 3 seconds of silence (16000 * 3 * 2 = 96000 bytes), then empty
    silence = b'\x00' * (rate * 3 * 2)
    mock_stream.read = MagicMock(return_value=silence)
    return mock_stream


class TestDynamicGreeting(unittest.TestCase):
    """Verifies time-based greeting generation."""

    def test_returns_string(self) -> None:
        result = dynamic_greeting()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 10)

    def test_mentions_sopno(self) -> None:
        # Run multiple times — at least one should mention Sopno
        results = [dynamic_greeting() for _ in range(20)]
        self.assertTrue(any("Sopno" in r or "sopno" in r.lower() for r in results))


class TestWakeWordDetector(unittest.TestCase):
    """Verifies wake word detection initialization and fallback behavior."""

    @patch("sopno.voice.wakeword.settings")
    def test_init_fallback_when_model_files_missing(self, mock_settings) -> None:
        """sherpa-onnx falls back gracefully when model files don't exist."""
        mock_settings.wake_words = ["sopno", "dream"]
        # All path operations return a mock whose .exists() is False
        fake_path = MagicMock()
        fake_path.exists = MagicMock(return_value=False)
        fake_path.__truediv__ = MagicMock(return_value=fake_path)
        fake_path.__str__ = MagicMock(return_value="/fake/path")
        mock_settings.models_dir = fake_path

        detector = WakeWordDetector(log_callback=MagicMock())
        self.assertFalse(detector.use_sherpa)

    @patch("sopno.voice.wakeword.settings")
    def test_wait_for_wakeword_returns_false_when_no_stream(self, mock_settings) -> None:
        """wait_for_wakeword returns False when no mic_stream is provided."""
        mock_settings.wake_words = ["sopno", "dream"]
        fake_path = MagicMock()
        fake_path.exists = MagicMock(return_value=False)
        fake_path.__truediv__ = MagicMock(return_value=fake_path)
        fake_path.__str__ = MagicMock(return_value="/fake/path")
        mock_settings.models_dir = fake_path

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()
        running_check = MagicMock(return_value=True)

        result = detector.wait_for_wakeword(mock_recognizer, running_check, mic_stream=None)
        self.assertFalse(result)

    @patch("sopno.voice.wakeword.settings")
    def test_wait_for_wakeword_returns_false_on_exit(self, mock_settings) -> None:
        """wait_for_wakeword returns False when running_check returns False."""
        mock_settings.wake_words = ["sopno", "dream"]
        fake_path = MagicMock()
        fake_path.exists = MagicMock(return_value=False)
        fake_path.__truediv__ = MagicMock(return_value=fake_path)
        fake_path.__str__ = MagicMock(return_value="/fake/path")
        mock_settings.models_dir = fake_path

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()
        running_check = MagicMock(return_value=False)
        mock_stream = _make_mock_mic_stream()

        result = detector.wait_for_wakeword(mock_recognizer, running_check, mic_stream=mock_stream)
        self.assertFalse(result)

    @patch("sopno.voice.wakeword.settings")
    def test_fallback_detects_wake_word(self, mock_settings) -> None:
        """STT fallback detects wake word in transcribed text."""
        mock_settings.wake_words = ["sopno", "dream"]
        fake_path = MagicMock()
        fake_path.exists = MagicMock(return_value=False)
        fake_path.__truediv__ = MagicMock(return_value=fake_path)
        fake_path.__str__ = MagicMock(return_value="/fake/path")
        mock_settings.models_dir = fake_path

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()
        mock_stream = _make_mock_mic_stream()

        call_count = [0]

        def running_side_effect():
            call_count[0] += 1
            return call_count[0] <= 3

        with patch("sopno.voice.wakeword.transcribe", return_value="hey sopno how are you"):
            result = detector.wait_for_wakeword(
                mock_recognizer, running_side_effect, mic_stream=mock_stream
            )

        self.assertTrue(result)

    @patch("sopno.voice.wakeword.settings")
    def test_fallback_ignores_non_wake_word(self, mock_settings) -> None:
        """STT fallback ignores audio without wake word."""
        mock_settings.wake_words = ["sopno", "dream"]
        fake_path = MagicMock()
        fake_path.exists = MagicMock(return_value=False)
        fake_path.__truediv__ = MagicMock(return_value=fake_path)
        fake_path.__str__ = MagicMock(return_value="/fake/path")
        mock_settings.models_dir = fake_path

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()
        mock_stream = _make_mock_mic_stream()

        call_count = [0]

        def running_side_effect():
            call_count[0] += 1
            return call_count[0] <= 4

        with patch("sopno.voice.wakeword.transcribe", return_value="what time is it"):
            result = detector.wait_for_wakeword(
                mock_recognizer, running_side_effect, mic_stream=mock_stream
            )

        self.assertFalse(result)


class TestListeningModeIntegration(unittest.TestCase):
    """Verifies SopnoAssistant respects listening_mode config."""

    @patch("sopno.voice.wakeword.settings")
    def test_assistant_default_mode_is_wake_word(self, mock_settings) -> None:
        """Assistant defaults to wake_word listening mode."""
        mock_settings.wake_words = ["sopno", "dream"]
        mock_settings.models_dir = MagicMock()
        mock_settings.models_dir.__truediv__ = MagicMock(
            return_value=MagicMock(exists=MagicMock(return_value=False))
        )

        with patch("sopno.core.assistant.settings") as mock_asst_settings:
            mock_asst_settings.listening_mode = "wake_word"
            mock_asst_settings.wake_words = ["sopno", "dream"]
            mock_asst_settings.stt_language = "auto"
            mock_asst_settings.current_language = "en"

            from sopno.core.assistant import SopnoAssistant
            assistant = SopnoAssistant()
            self.assertEqual(assistant.listening_mode, "wake_word")
            self.assertIsNone(assistant._wake_detector)

    @patch("sopno.voice.wakeword.settings")
    def test_wake_detector_is_lazy(self, mock_settings) -> None:
        """WakeWordDetector is not created until first accessed."""
        mock_settings.wake_words = ["sopno", "dream"]
        mock_settings.models_dir = MagicMock()
        mock_settings.models_dir.__truediv__ = MagicMock(
            return_value=MagicMock(exists=MagicMock(return_value=False))
        )

        with patch("sopno.core.assistant.settings") as mock_asst_settings:
            mock_asst_settings.listening_mode = "wake_word"
            mock_asst_settings.wake_words = ["sopno", "dream"]
            mock_asst_settings.stt_language = "auto"
            mock_asst_settings.current_language = "en"

            from sopno.core.assistant import SopnoAssistant
            assistant = SopnoAssistant()
            self.assertIsNone(assistant._wake_detector)

            with patch("sopno.core.assistant.WakeWordDetector") as MockWWD:
                MockWWD.return_value = MagicMock()
                _ = assistant.wake_detector
                self.assertIsNotNone(assistant._wake_detector)
                MockWWD.assert_called_once()


if __name__ == "__main__":
    unittest.main()
