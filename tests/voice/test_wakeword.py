"""
tests/test_wakeword.py
━━━━━━━━━━━━━━━━━━━━━━
Unit tests for WakeWordDetector and listening mode integration.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.voice.wakeword import WakeWordDetector


class TestWakeWordDetector(unittest.TestCase):
    """Verifies wake word detection initialization and fallback behavior."""

    @patch("sopno.voice.wakeword.settings")
    def test_init_fallback_when_model_files_missing(self, mock_settings) -> None:
        """sherpa-onnx falls back gracefully when model files don't exist."""
        mock_settings.wake_words = ["sopno", "dream"]
        mock_settings.models_dir = MagicMock()
        mock_settings.models_dir.__truediv__ = MagicMock(
            return_value=MagicMock(exists=MagicMock(return_value=False))
        )

        detector = WakeWordDetector(log_callback=MagicMock())
        self.assertFalse(detector.use_sherpa)

    @patch("sopno.voice.wakeword.settings")
    def test_wait_for_wakeword_returns_false_on_exit(self, mock_settings) -> None:
        """wait_for_wakeword returns False when running_check returns False."""
        mock_settings.wake_words = ["sopno", "dream"]
        mock_settings.models_dir = MagicMock()
        mock_settings.models_dir.__truediv__ = MagicMock(
            return_value=MagicMock(exists=MagicMock(return_value=False))
        )

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()
        running_check = MagicMock(return_value=False)

        result = detector.wait_for_wakeword(mock_recognizer, running_check)
        self.assertFalse(result)

    @patch("sopno.voice.wakeword.sr")
    @patch("sopno.voice.wakeword.settings")
    def test_fallback_detects_wake_word(self, mock_settings, mock_sr) -> None:
        """SpeechRecognition fallback detects wake word in transcribed text."""
        mock_settings.wake_words = ["sopno", "dream"]
        mock_settings.models_dir = MagicMock()
        mock_settings.models_dir.__truediv__ = MagicMock(
            return_value=MagicMock(exists=MagicMock(return_value=False))
        )

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()

        # running_check returns True once, then False to exit
        call_count = [0]

        def running_side_effect():
            call_count[0] += 1
            return call_count[0] <= 1

        mock_audio = MagicMock()
        mock_recognizer.listen.return_value = mock_audio
        mock_sr.Microphone.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sr.Microphone.return_value.__exit__ = MagicMock(return_value=False)

        with patch("sopno.voice.wakeword.transcribe", return_value="hey sopno how are you"):
            result = detector.wait_for_wakeword(mock_recognizer, running_side_effect)

        self.assertTrue(result)

    @patch("sopno.voice.wakeword.sr")
    @patch("sopno.voice.wakeword.settings")
    def test_fallback_ignores_non_wake_word(self, mock_settings, mock_sr) -> None:
        """SpeechRecognition fallback ignores audio without wake word."""
        mock_settings.wake_words = ["sopno", "dream"]
        mock_settings.models_dir = MagicMock()
        mock_settings.models_dir.__truediv__ = MagicMock(
            return_value=MagicMock(exists=MagicMock(return_value=False))
        )

        detector = WakeWordDetector(log_callback=MagicMock())
        mock_recognizer = MagicMock()

        call_count = [0]

        def running_side_effect():
            call_count[0] += 1
            return call_count[0] <= 2

        mock_audio = MagicMock()
        mock_recognizer.listen.return_value = mock_audio
        mock_sr.Microphone.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sr.Microphone.return_value.__exit__ = MagicMock(return_value=False)

        with patch("sopno.voice.wakeword.transcribe", return_value="what time is it"):
            result = detector.wait_for_wakeword(mock_recognizer, running_side_effect)

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
