"""
sopno/core/assistant.py
━━━━━━━━━━━━━━━━━━━━━━━
Main pipeline orchestrator.

Defines the SopnoAssistant class, which runs the continuous listening loop:
  Standby (wake-word) → Listening (command capture) → Thinking (LLM/dispatcher) → Speaking (TTS reply).
Uses a callback-driven design so it can run seamlessly in headless CLI mode
or within a glassmorphic PyQt5 HUD.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

import speech_recognition as sr
import ollama

from sopno.config.settings import settings
from sopno.core.context import ConversationContext
from sopno.core.dispatcher import CommandDispatcher
from sopno.tools.schema import TOOLS_SCHEMA
from sopno.tools.registry import execute_tool
from sopno.voice.listener import Listener
from sopno.voice.stt import transcribe
from sopno.voice.tts import speak
from sopno.voice.wakeword import WakeWordDetector


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
        self.listener = Listener()
        self.wakeword_detector = WakeWordDetector(log_callback=self.on_log_message)

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
        self.on_status_changed("standby")

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
        else:
            # Text mode: brief "speaking" flash for avatar, no TTS
            self.on_status_changed(status)
            time.sleep(0.35)

    def _await_command(self) -> Optional[str]:
        """
        Block until we have a user command.
        Voice: wake word → mic capture → STT.
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

            # ── Voice path ────────────────────────────────────────────────────
            self.on_status_changed("standby")
            triggered = self.wakeword_detector.wait_for_wakeword(
                recognizer=self.listener.recognizer,
                running_check=self._voice_active,
            )
            if not self.running:
                return None
            if self.interaction_mode != "voice":
                continue
            if not triggered:
                continue

            self.on_log_message("Wake word detected! Listening for command…")
            self.on_status_changed("listening")

            try:
                audio = self.listener.listen(phrase_time_limit=10)
            except Exception as e:
                self.on_log_message(f"Microphone capturing failed: {e}")
                continue

            if self.interaction_mode != "voice" or not self.running:
                continue

            self.on_log_message("Transcribing speech…")
            try:
                cmd_text = transcribe(self.listener.recognizer, audio)
                self.on_log_message(f"User command: '{cmd_text}'")
                self.on_speech_detected(cmd_text)
                return cmd_text
            except sr.UnknownValueError:
                self.on_log_message("Could not understand audio.")
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

        # D. LLM Processing with dynamic tool-calling fallback
        self.on_log_message("Querying Ollama with tool calling schema…")
        self.context.add_user_message(cmd_text)
        chat_messages = self.context.get_messages_for_llm()

        try:
            response = ollama.chat(
                model=settings.model_name,
                messages=chat_messages,
                tools=TOOLS_SCHEMA,
            )

            response_msg = response.get("message", {})
            tool_calls = response_msg.get("tool_calls", [])

            if tool_calls:
                chat_messages.append(response_msg)

                for tool in tool_calls:
                    name = tool["function"]["name"]
                    args = tool["function"]["arguments"]
                    self.on_log_message(f"LLM request tool: '{name}' with args {args}")

                    tool_result = execute_tool(name, args)
                    self.on_log_message(f"Tool output: '{tool_result}'")

                    chat_messages.append({
                        "role": "tool",
                        "content": tool_result,
                    })

                self.on_log_message("Requesting conversational response from Ollama…")
                final_response = ollama.chat(
                    model=settings.model_name,
                    messages=chat_messages,
                )
                assistant_reply = final_response["message"]["content"]
            else:
                assistant_reply = response_msg.get("content", "")

            assistant_reply_clean = re.sub(r"[*_`#\-]", " ", assistant_reply)
            assistant_reply_clean = re.sub(r"\s+", " ", assistant_reply_clean).strip()

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
        """Boots the sound system and starts the continuous listening loop."""
        self.on_log_message("Initializing sound system…")

        self.listener.calibrate()
        self.on_log_message("Sound system initialized successfully!")

        welcome_text = "Hello! Sopno voice assistant is ready."
        self._deliver_reply(welcome_text)
        self.on_status_changed("standby")

        self.on_log_message(f"Using LLM Model: {settings.model_name}")
        self.on_log_message(f"Wake words configured: {settings.wake_words}")

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
