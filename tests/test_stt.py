"""
tests/test_stt.py
━━━━━━━━━━━━━━━━━
Automated unit tests for the Speech-to-Text (STT) module.
"""

import unittest
from unittest.mock import patch, MagicMock

import speech_recognition as sr
from sopno.voice.stt import transcribe


class TestSTT(unittest.TestCase):
    """Verifies Whisper transcription and Google STT fallback routing."""

    @patch("sopno.voice.stt._transcribe_whisper")
    def test_transcribe_whisper_primary(self, mock_whisper) -> None:
        """Verify Whisper is prioritized and called."""
        mock_whisper.return_value = "Mocked Whisper Transcript"

        recognizer = MagicMock(spec=sr.Recognizer)
        audio_data = MagicMock(spec=sr.AudioData)

        result = transcribe(recognizer, audio_data)
        
        self.assertEqual(result, "Mocked Whisper Transcript")
        mock_whisper.assert_called_once_with(audio_data)

    @patch("sopno.voice.stt._transcribe_google")
    @patch("sopno.voice.stt._transcribe_whisper")
    def test_transcribe_whisper_fallback_to_google(self, mock_whisper, mock_google) -> None:
        """Verify fallback to Google STT when Whisper raises an unexpected error."""
        # Whisper fails with general exception, triggers Google fallback
        mock_whisper.side_effect = Exception("Whisper loading error")
        mock_google.return_value = "Mocked Google Transcript"

        recognizer = MagicMock(spec=sr.Recognizer)
        audio_data = MagicMock(spec=sr.AudioData)

        result = transcribe(recognizer, audio_data)

        self.assertEqual(result, "Mocked Google Transcript")
        mock_whisper.assert_called_once_with(audio_data)
        mock_google.assert_called_once_with(recognizer, audio_data)


if __name__ == "__main__":
    unittest.main()
