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
    """Verifies Whisper transcription and offline / online fallback routing."""

    @patch("sopno.voice.stt._transcribe_whisper")
    def test_transcribe_whisper_primary(self, mock_whisper) -> None:
        """Verify Whisper is prioritized and called."""
        mock_whisper.return_value = "Mocked Whisper Transcript"

        recognizer = MagicMock(spec=sr.Recognizer)
        audio_data = MagicMock(spec=sr.AudioData)

        result = transcribe(recognizer, audio_data)

        self.assertEqual(result, "Mocked Whisper Transcript")
        mock_whisper.assert_called_once()

    @patch("sopno.voice.stt.settings")
    @patch("sopno.voice.stt._transcribe_google")
    @patch("sopno.voice.stt._transcribe_whisper")
    def test_online_fallback_opt_in(self, mock_whisper, mock_google, mock_settings) -> None:
        """Google is used only when stt_online_fallback is True."""
        mock_settings.stt_language = "auto"
        mock_settings.stt_online_fallback = True
        mock_whisper.side_effect = Exception("Whisper loading error")
        mock_google.return_value = "Mocked Google Transcript"

        result = transcribe(MagicMock(spec=sr.Recognizer), MagicMock(spec=sr.AudioData))
        self.assertEqual(result, "Mocked Google Transcript")
        mock_google.assert_called_once()

    @patch("sopno.voice.stt.settings")
    @patch("sopno.voice.stt._transcribe_google")
    @patch("sopno.voice.stt._transcribe_whisper")
    def test_offline_default_no_google(self, mock_whisper, mock_google, mock_settings) -> None:
        """Default path stays offline — no Google call."""
        mock_settings.stt_language = "auto"
        mock_settings.stt_online_fallback = False
        mock_whisper.side_effect = Exception("Whisper loading error")

        with self.assertRaises(sr.UnknownValueError):
            transcribe(MagicMock(spec=sr.Recognizer), MagicMock(spec=sr.AudioData))
        mock_google.assert_not_called()


if __name__ == "__main__":
    unittest.main()
