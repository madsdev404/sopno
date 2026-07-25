"""
sopno/core/assistant.py
━━━━━━━━━━━━━━━━━━━━━━━
Main pipeline orchestrator.

Defines the SopnoAssistant class, which runs the continuous conversation loop:
  Intro (TTS) → Listening (idle VAD) → Thinking → Speaking → Listening again.
Uses offline Silero VAD for natural turn-taking; stays quiet until the user speaks.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

import speech_recognition as sr

from sopno.config.settings import settings
from sopno.core.context import ConversationContext
from sopno.core.dispatcher import CommandDispatcher
from sopno.llm.client import chat as llm_chat, message_as_dict
from sopno.tools.schema import TOOLS_SCHEMA
from sopno.tools.registry import execute_tool
from sopno.voice.listener import Listener
from sopno.voice.stt import transcribe
from sopno.voice.tts import speak

# Only attach the heavy tool schema when the utterance looks action-oriented.
# Pure chat without tools is much faster on CPU (seconds vs tens of seconds).
_TOOLISH = re.compile(
    r"\b("
    r"open|launch|start|close|search|google|volume|mute|unmute|"
    r"play|pause|resume|next|previous|skip|"
    r"time|date|clock|battery|cpu|ram|memory|stats|status|system|"
    r"media|music|song|spotify|browser|chrome|firefox|vscode|terminal|"
    r"খোল|সার্চ|ভলিউম|সময়|তারিখ|প্লে|পজ"
    r")\b",
    re.IGNORECASE,
)


# Brief pause after TTS so the mic does not hear Sopno's own voice as a turn.
_POST_SPEAK_SETTLE_S = 0.45


class SopnoAssistant:
    """The central brain that coordinates the Speech-to-Text-to-LLM-to-TTS pipeline."""

    def __init__(
        self,
        status_callback: Optional[Callable[[str], None]] = None,
        speech_callback: Optional[Callable[[str], None]] = None,
        reply_callback: Optional[Callable[[str], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        # Callback bindings for UI state synchronization
        self.on_status_changed  = status_callback or (lambda s: None)
        self.on_speech_detected = speech_callback or (lambda t: None)
        self.on_reply_generated = reply_callback or (lambda r: None)
        self.on_log_message     = log_callback or (lambda m: print(f"[Log] {m}"))

        self.running = True
        self.context = ConversationContext()
        self.dispatcher = CommandDispatcher()
        self.listener = Listener(log_callback=self.on_log_message)

        # voice = mic + TTS; text = typed input + silent replies
        self.interaction_mode = "voice"
        self._pending_text: Optional[str] = None
        self._text_event = threading.Event()
        self._mode_lock = threading.Lock()

    def stop(self) -> None:
        """Stop the assistant loop."""
        self.running = False
        self._text_event.set()

    def set_interaction_mode(self, mode: str) -> None:
        """Switch between voice and text interaction."""
        mode = (mode or "").strip().lower()
        if mode not in ("voice", "text"):
            return
        with self._mode_lock:
            if self.interaction_mode == mode:
                return
            self.interaction_mode = mode
        self._pending_text = None
        self._text_event.set()  # unblock whichever wait is active
        self.on_log_message(f"Mode → {mode}")
        # Voice resumes idle listening; text sits quiet until typed input
        self.on_status_changed("listening" if mode == "voice" else "standby")

    def submit_text(self, text: str) -> None:
        """Queue a typed message (text mode)."""
        cleaned = (text or "").strip()
        if not cleaned:
            return
        if self.interaction_mode != "text":
            self.on_log_message("Switch to Text mode to type messages.")
            return
        self._pending_text = cleaned
        self._text_event.set()

    def _voice_active(self) -> bool:
        return self.running and self.interaction_mode == "voice"

    def _deliver_reply(self, text: str, *, status: str = "speaking") -> None:
        """Show reply in UI; speak aloud only in voice mode."""
        self.on_reply_generated(text)
        if self.interaction_mode == "voice":
            self.on_status_changed(status)
            speak(text)
            time.sleep(_POST_SPEAK_SETTLE_S)
        else:
            # Text mode: brief "speaking" flash for avatar, no TTS
            self.on_status_changed(status)
            time.sleep(0.35)

    def _await_command(self) -> Optional[str]:
        """
        Block until we have a user command.
        Voice: idle listen (VAD) → capture turn → STT. Stays quiet until speech.
        Text: wait for submit_text().
        """
        while self.running:
            mode = self.interaction_mode

            if mode == "text":
                self.on_status_changed("standby")
                self.on_log_message("Text mode — type a message.")
                self._text_event.clear()

                while self.running and self.interaction_mode == "text":
                    if self._text_event.wait(timeout=0.2):
                        self._text_event.clear()
                        if self.interaction_mode != "text":
                            break
                        text = self._pending_text
                        self._pending_text = None
                        if text:
                            self.on_speech_detected(text)
                            self.on_log_message(f"User (text): '{text}'")
                            return text
                continue

            # ── Voice path: continuous conversation (no wake-word gate) ───────
            self.on_status_changed("listening")
            self.on_log_message("Listening… say something when you're ready.")

            def _on_speech_start() -> None:
                self.on_log_message("Speech detected — capturing turn…")
                self.on_status_changed("listening")

            try:
                audio = self.listener.listen_for_turn(
                    running_check=self._voice_active,
                    on_speech_start=_on_speech_start,
                    max_wait_s=0.0,  # wait forever while idle-listening
                    max_utterance_s=12.0,
                )
            except Exception as e:
                self.on_log_message(f"Microphone capturing failed: {e}")
                time.sleep(0.3)
                continue

            if not self.running:
                return None
            if self.interaction_mode != "voice":
                continue
            if audio is None:
                # Aborted (mode switch / stop) or empty — keep listening quietly
                continue

            self.on_log_message("Transcribing speech…")
            try:
                cmd_text = transcribe(self.listener.recognizer, audio)
                cmd_text = (cmd_text or "").strip()
                if not cmd_text:
                    self.on_log_message("Empty transcript — staying quiet.")
                    continue
                self.on_log_message(f"User: '{cmd_text}'")
                self.on_speech_detected(cmd_text)
                return cmd_text
            except sr.UnknownValueError:
                # Noise / cough / unclear — do not invent an answer
                self.on_log_message("Could not understand audio — still listening.")
                continue
            except Exception as e:
                self.on_log_message(f"STT Error: {e}")
                continue

        return None

    def _process_command(self, cmd_text: str) -> bool:
        """
        Run dispatcher / LLM for one command.
        Returns False if the assistant should exit.
        """
        self.on_status_changed("thinking")
        clean_cmd = cmd_text.lower().strip().replace(".", "").replace("?", "").replace("!", "")

        # A. Exit checks
        if clean_cmd in ["exit", "quit", "goodbye", "bye", "exit()", "বিদায়"]:
            farewell = "Goodbye! Have a great day."
            self._deliver_reply(farewell)
            self.on_status_changed("standby")
            self.running = False
            return False

        # B. Language switches
        bangla_keywords = [
            "speak in bangla", "change to bangla", "talk in bangla",
            "banglay kotha bolo", "বাংলায় কথা বলো", "বাংলা করো", "বাংলায় বল",
        ]
        english_keywords = [
            "speak in english", "change to english", "talk in english",
            "english-e kotha bolo", "ইংরেজিতে কথা বলো", "english-e bol", "ইংরেজিতে বল",
        ]

        if any(kw in clean_cmd for kw in bangla_keywords):
            self.context.current_language = "bn"
            switch_text = "ঠিক আছে, আমি এখন থেকে বাংলায় কথা বলব।"
            self._deliver_reply(switch_text)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(switch_text)
            return True

        if any(kw in clean_cmd for kw in english_keywords):
            self.context.current_language = "en"
            switch_text = "Sure, I will speak in English from now on."
            self._deliver_reply(switch_text)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(switch_text)
            return True

        # C. Rule-based Dispatcher (Fast path)
        self.on_log_message("Checking local system rules dispatcher…")
        tool_output = self.dispatcher.dispatch(cmd_text)
        if tool_output is not None:
            self.on_log_message(f"Rule dispatcher executed tool. Output: '{tool_output}'")
            self._deliver_reply(tool_output)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(tool_output)
            return True

        # D. LLM Processing — tools only when the phrase looks action-oriented
        use_tools = bool(_TOOLISH.search(cmd_text))
        if use_tools:
            self.on_log_message("Querying Ollama with tools…")
        else:
            self.on_log_message("Querying Ollama (fast chat, no tools)…")

        self.context.add_user_message(cmd_text)
        chat_messages = self.context.get_messages_for_llm()

        try:
            response = llm_chat(
                chat_messages,
                tools=TOOLS_SCHEMA if use_tools else None,
            )

            response_msg = message_as_dict(response["message"])
            tool_calls = response_msg.get("tool_calls") or []

            if tool_calls:
                chat_messages.append(response_msg)

                for tool in tool_calls:
                    # Ollama may return dicts or objects
                    fn = tool["function"] if isinstance(tool, dict) else tool.function
                    name = fn["name"] if isinstance(fn, dict) else fn.name
                    args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
                    if not isinstance(args, dict):
                        args = {}
                    self.on_log_message(f"LLM request tool: '{name}' with args {args}")

                    tool_result = execute_tool(name, args)
                    self.on_log_message(f"Tool output: '{tool_result}'")

                    chat_messages.append({
                        "role": "tool",
                        "content": tool_result,
                    })

                self.on_log_message("Requesting conversational response from Ollama…")
                final_response = llm_chat(chat_messages)
                final_msg = message_as_dict(final_response["message"])
                assistant_reply = final_msg.get("content", "")
            else:
                assistant_reply = response_msg.get("content", "")

            assistant_reply_clean = re.sub(r"[*_`#\-]", " ", assistant_reply or "")
            assistant_reply_clean = re.sub(r"\s+", " ", assistant_reply_clean).strip()

            if not assistant_reply_clean:
                assistant_reply_clean = "Sorry, I didn't catch that. Could you say it again?"

            self._deliver_reply(assistant_reply_clean)
            self.context.add_assistant_message(assistant_reply_clean)

        except Exception as err:
            self.on_log_message(f"Ollama/Chat error: {err}")
            error_speech = "Sorry, I had trouble communicating with the AI model."
            self._deliver_reply(error_speech)
            if self.context.raw_messages and self.context.raw_messages[-1]["role"] == "user":
                self.context.raw_messages.pop()

        return True

    def run(self) -> None:
        """Intro → idle listen → answer only when the user speaks."""
        self.on_log_message("Initializing sound system…")

        self.listener.calibrate()
        vad_note = "Silero VAD" if self.listener.turn_taker.available else "classic listen"
        self.on_log_message(f"Sound system ready ({vad_note} turn-taking).")

        welcome_text = "Hello! I'm Sopno. I'm listening whenever you're ready."
        self._deliver_reply(welcome_text)
        self.on_status_changed("listening")

        self.on_log_message(f"Using LLM Model: {settings.model_name}")

        while self.running:
            try:
                cmd_text = self._await_command()
                if not cmd_text or not self.running:
                    continue
                if not self._process_command(cmd_text):
                    break
            except KeyboardInterrupt:
                self.on_log_message("KeyboardInterrupt caught. Shutting down Sopno.")
                self.running = False
                break
            except Exception as e:
                self.on_log_message(f"Unexpected loop exception: {e}")
                time.sleep(1)

        self.on_status_changed("standby")
        self.on_log_message("Sopno pipeline stopped.")
