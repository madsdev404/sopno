"""
tests/test_barge.py
━━━━━━━━━━━━━━━━━━━
Unit tests for barge-in — the mic monitor that stops Sopno when you interrupt.
"""

import unittest
from unittest.mock import MagicMock, patch

from sopno.core.assistant import SopnoAssistant
from sopno.voice import tts
from sopno.voice.barge import BargeDetector


class TestBargeDetector(unittest.TestCase):
    """Verifies the pure energy-gate decision logic (no audio I/O)."""

    def test_baseline_learns_own_voice_threshold(self) -> None:
        """User speech above own-voice baseline triggers barge-in."""
        d = BargeDetector(floor=100, multiplier=2.0, margin=10,
                          confirm_frames=3, baseline_frames=4)
        # Sopno's own voice measures ~400 → threshold = 400*2 + 10 = 810
        for _ in range(4):
            d.feed(400)
        self.assertFalse(d.interrupted)
        d.feed(700)  # below threshold — Sopno's own loud syllable
        self.assertFalse(d.interrupted)
        # User speaks over her for 3 sustained frames
        d.feed(900)
        self.assertFalse(d.interrupted)
        d.feed(900)
        self.assertFalse(d.interrupted)
        d.feed(900)
        self.assertTrue(d.interrupted)

    def test_floor_applies_when_own_voice_not_heard(self) -> None:
        """Headphone setup: baseline near zero, threshold falls back to floor."""
        d = BargeDetector(floor=100, multiplier=1.5, margin=20,
                          confirm_frames=2, baseline_frames=2)
        d.feed(5)
        d.feed(5)  # baseline ~5 → max(100, 5*1.5+20) = 100
        d.feed(250)  # normal speech
        self.assertFalse(d.interrupted)
        d.feed(250)
        self.assertTrue(d.interrupted)

    def test_quiet_frames_never_trigger(self) -> None:
        """Sustained energy below the threshold must never interrupt."""
        d = BargeDetector(floor=100, multiplier=2.0, margin=10,
                          confirm_frames=1000, baseline_frames=2)
        d.feed(500)
        d.feed(500)
        for _ in range(500):
            d.feed(400)
        self.assertFalse(d.interrupted)


class TestPlaybackInterrupt(unittest.TestCase):
    """Verifies tts playback stops early when should_stop() turns True."""

    def test_should_stop_terminates_playback(self) -> None:
        proc = MagicMock()
        proc.poll.return_value = None  # still running
        with patch("subprocess.Popen", return_value=proc) as popen:
            tts._play_audio("/tmp/x.wav", should_stop=lambda: True, on_play_start=lambda: None)
        popen.assert_called_once()
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()

    def test_on_play_start_fires(self) -> None:
        proc = MagicMock()
        proc.poll.side_effect = [None, 0]  # running once, then finished
        called = []
        with patch("subprocess.Popen", return_value=proc):
            tts._play_audio("/tmp/x.wav", should_stop=lambda: False, on_play_start=lambda: called.append(1))
        self.assertEqual(called, [1])

    def test_no_should_stop_plays_to_end(self) -> None:
        proc = MagicMock()
        proc.poll.return_value = 0  # already finished
        with patch("subprocess.Popen", return_value=proc) as popen:
            tts._play_audio("/tmp/x.wav")
        popen.assert_called_once()
        proc.terminate.assert_not_called()


class _FakeBargeMonitor:
    """Stand-in for BargeInMonitor in assistant tests (no mic)."""

    def __init__(self, log_callback=None) -> None:
        self.log = log_callback or (lambda m: None)
        self.interrupted = False

    def start(self) -> None:
        pass

    def start_measurement(self) -> None:
        pass

    def stop(self) -> None:
        pass


class TestBargeInAssistant(unittest.TestCase):
    """Verifies the assistant orchestrates barge-in around TTS."""

    def _make_assistant(self) -> SopnoAssistant:
        with patch("sopno.core.assistant.MemoryStore"), patch(
            "sopno.core.assistant.Listener"
        ), patch("sopno.core.assistant.MicStream"):
            asst = SopnoAssistant()
            return asst

    def test_barge_in_stops_speech_and_skips_settle(self) -> None:
        asst = self._make_assistant()
        monitor = _FakeBargeMonitor()
        monitor.interrupted = True
        statuses = []
        asst.on_status_changed = lambda s: statuses.append(s)

        with patch("sopno.core.assistant.BargeInMonitor", return_value=monitor) as mon_cls, patch(
            "sopno.core.assistant.speak"
        ) as mock_speak, patch("sopno.core.assistant.time.sleep") as mock_sleep, patch(
            "sopno.core.assistant.settings.barge_in_enabled", True, create=True
        ):
            asst._deliver_reply("hello there")

        mon_cls.assert_called_once()
        # TTS got the interrupt hook and the baseline trigger
        self.assertTrue(callable(mock_speak.call_args.kwargs["should_stop"]))
        self.assertTrue(callable(mock_speak.call_args.kwargs["on_play_start"]))
        # No PulseAudio settle sleep needed — shared MicStream eliminates device race.
        # Only the post-speech settle (_POST_SPEAK_SETTLE_S) should fire.
        self.assertEqual(statuses[-1], "listening")

    def test_no_barge_in_keeps_normal_settle(self) -> None:
        asst = self._make_assistant()
        monitor = _FakeBargeMonitor()
        statuses = []
        asst.on_status_changed = lambda s: statuses.append(s)

        with patch("sopno.core.assistant.BargeInMonitor", return_value=monitor), patch(
            "sopno.core.assistant.speak"
        ), patch("sopno.core.assistant.time.sleep") as mock_sleep, patch(
            "sopno.core.assistant.settings.barge_in_enabled", True, create=True
        ):
            asst._deliver_reply("hi")

        # Only the post-speech settle (_POST_SPEAK_SETTLE_S) should fire.
        self.assertGreaterEqual(mock_sleep.call_count, 1)
        self.assertEqual(statuses[-1], "speaking")

    def test_barge_in_disabled_speaks_plain(self) -> None:
        asst = self._make_assistant()
        statuses = []
        asst.on_status_changed = lambda s: statuses.append(s)

        with patch("sopno.core.assistant.BargeInMonitor") as mon_cls, patch(
            "sopno.core.assistant.speak"
        ) as mock_speak, patch("sopno.core.assistant.time.sleep") as mock_sleep, patch(
            "sopno.core.assistant.settings.barge_in_enabled", False, create=True
        ):
            asst._deliver_reply("hello")

        mon_cls.assert_not_called()
        mock_speak.assert_called_once_with("hello")
        mock_sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
