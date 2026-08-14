"""
tests/test_tts.py
━━━━━━━━━━━━━━━━━
Automated unit tests for the Text-to-Speech (TTS) module.
"""

import unittest
from unittest.mock import patch

from sopno.voice.tts import speak, _is_bangla, engine_name


class TestTTS(unittest.TestCase):
    """Verifies Text-to-Speech language detection and dispatch logic."""

    def test_is_bangla_detection(self) -> None:
        """Test unicode range classification for Bangla characters."""
        self.assertTrue(_is_bangla("আমার সোনার বাংলা"))
        self.assertTrue(_is_bangla("হ্যালো Sopno"))  # Mixed, but contains Bangla
        self.assertFalse(_is_bangla("Hello, how are you?"))
        self.assertFalse(_is_bangla("12345 @#$%"))

    @patch("sopno.voice.tts._speak_gtts")
    @patch("sopno.voice.tts._speak_coqui")
    def test_speak_routing(self, mock_coqui, mock_gtts) -> None:
        """Verify fallback or primary speak dispatch routing."""
        # Speak empty string does nothing
        speak("")
        mock_coqui.assert_not_called()
        mock_gtts.assert_not_called()

        speak("   ")
        mock_coqui.assert_not_called()
        mock_gtts.assert_not_called()

        # Test routing based on active engine
        engine = engine_name()
        if engine == "coqui":
            speak("Hello Test")
            mock_coqui.assert_called_once_with("Hello Test", should_stop=None, on_play_start=None)
            mock_gtts.assert_not_called()
        else:
            speak("Hello Test")
            mock_gtts.assert_called_once_with("Hello Test", should_stop=None, on_play_start=None)
            mock_coqui.assert_not_called()


if __name__ == "__main__":
    unittest.main()
