"""
sopno/ui/cli.py
━━━━━━━━━━━━━━━
Terminal-mode CLI interface.

Initializes the SopnoAssistant with stdout/logging callbacks to display
assistant status and transcription outputs directly in the console.
"""

import sys
from sopno.config.settings import settings
from sopno.core.assistant import SopnoAssistant


def run_cli() -> None:
    """Run Sopno in full CLI console mode."""
    wake_words_str = ", ".join(f"'{w}'" for w in getattr(settings, "wake_words", ["dream"]))
    mode = getattr(settings, "listening_mode", "wake_word")
    control = f"Offline wake-word (say {wake_words_str})" if mode == "wake_word" else "Always-on listening (speak anytime)"

    print("=" * 60)
    print("🌙  SOPNO AI — TERMINAL CLI MODE")
    print("  Language: Bilingual (English / Bangla)")
    print("  Memory:   Dynamic Summarization enabled")
    print(f"  Control:  {control}")
    print("=" * 60)

    def on_status_changed(status: str) -> None:
        color_map = {
            "standby":   "\033[90m💤 STANDBY\033[0m",
            "listening": "\033[96m🎤 LISTENING…\033[0m",
            "thinking":  "\033[95m🧠 THINKING…\033[0m",
            "speaking":  "\033[92m🔊 SPEAKING…\033[0m",
            "error":     "\033[91m⚠️ ERROR\033[0m",
        }
        display = color_map.get(status.lower(), f"[{status.upper()}]")
        print(f"\n{display}")

    def on_speech_detected(text: str) -> None:
        print(f"\033[1;33mYou said:\033[0m “{text}”")

    def on_reply_generated(text: str) -> None:
        print(f"\033[1;32mAssistant:\033[0m {text}")

    def on_log_message(msg: str) -> None:
        print(f"\033[2m[System] {msg}\033[0m")

    # Initialize assistant with CLI stdout handlers
    assistant = SopnoAssistant(
        status_callback=on_status_changed,
        speech_callback=on_speech_detected,
        reply_callback=on_reply_generated,
        log_callback=on_log_message
    )

    try:
        assistant.run()
    except KeyboardInterrupt:
        print("\n\n\033[1;31mExiting Sopno voice assistant. Goodbye!\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    run_cli()
