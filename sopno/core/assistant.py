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
from sopno.memory.store import MemoryStore
from sopno.tools.schema import TOOLS_SCHEMA
from sopno.tools.registry import execute_tool
from sopno.voice.listener import Listener
from sopno.voice.stt import transcribe
from sopno.voice.tts import speak
from sopno.voice.wakeword import WakeWordDetector

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


# ── Memory intent patterns (English + Bangla) ────────────────────────────────
# Order of evaluation matters: recall before remember (recall phrases contain
# "remember"), and remember before forget ("don't forget X" must REMEMBER).

_MEMORY_FORGET_ALL_EN = re.compile(
    r"\bforget everything\b|\berase\s+(?:all|your|every)\s+(?:memory|memories)\b|"
    r"\bclear\s+(?:your|all)\s+(?:memory|memories)\b",
    re.IGNORECASE,
)

_MEMORY_RECALL_EN = re.compile(
    r"\bwhat do you remember\b|\bwhat memories\b|\bwhat have you remembered\b|"
    r"\bdo you remember anything\b|\bwhat did i tell you\b|"
    r"\bwhat did you remember\b|\btell me what you remember\b",
    re.IGNORECASE,
)

_MEMORY_REMEMBER_EN = re.compile(
    r"\b(?:remember\s+that|remember\s+this|remember|don'?t\s+forget|"
    r"do\s+not\s+forget|note\s+that|take\s+a\s+note|take\s+note)"
    r"\s+(?:that\s+)?(?:about\s+)?(.+)$",
    re.IGNORECASE,
)

_MEMORY_FORGET_EN = re.compile(
    r"\bforget\s+(?:that\s+|about\s+)?(.+)$",
    re.IGNORECASE,
)

_MEMORY_FORGET_ALL_BN = re.compile(
    r"(?<!\w)সব\s+ভুলে\s+যাও(?!\w)|(?<!\w)সব\s+ভুলে\s+যেও(?!\w)|"
    r"(?<!\w)সব\s+মনে\s+থাকা\s+মুছে\s+দাও(?!\w)|"
    r"(?<!\w)সব\s+মুছে\s+দাও(?!\w)|"
    r"(?<!\w)মনে\s+থাকা\s+সব\s+মুছে\s+দাও(?!\w)",
)

_MEMORY_RECALL_BN = re.compile(
    r"(?<!\w)(?:কী|কি)\s+মনে\s+আছে(?!\w)|(?<!\w)(?:কী|কি)\s+মনে\s+রেখেছ(?!\w)|"
    r"(?<!\w)(?:কী|কি)\s+মনে\s+রেখেছো(?!\w)|(?<!\w)(?:কী|কি)\s+মনে\s+রেখ(?!\w)|"
    r"(?<!\w)তুমি\s+(?:কী|কি)\s+মনে\s+(?:রাখো|রাখ)(?!\w)|"
    r"(?<!\w)(?:কী|কি)\s+জিনিস\s+মনে\s+আছে(?!\w)|"
    r"(?<!\w)আমার\s+সম্পর্কে\s+(?:কী|কি)\s+মনে\s+আছে(?!\w)",
)

_MEMORY_REMEMBER_BN = re.compile(
    r"(?<!\w)(?:মনে\s+রাখো|মনে\s+রাখ|মনে\s+রাখুন|মনে\s+রেখো|মনে\s+রেখ)"
    r"\s+(?:যে\s+)?(.+)$"
    r"|(?<!\w)(?:ভুলো\s+না|ভুলে\s+যেও\s+না)\s+(?:যে\s+)?(.+)$"
)

_MEMORY_FORGET_BN = re.compile(
    r"(?<!\w)(?:ভুলে\s+যাও|ভুলে\s+যেও|মুছে\s+ফেলো|মনে\s+থেকে\s+মুছে\s+দাও)"
    r"\s+(?:যে\s+)?(.+)$",
)

_MEMORY_TOPIC_EN = re.compile(r"\b(?:about|regarding)\s+(.+)$", re.IGNORECASE)
# Bangla puts the topic BEFORE সম্পর্কে/নিয়ে: "ফ্লাস্ক সম্পর্কে কী মনে আছে"
_MEMORY_TOPIC_BN = re.compile(r"(.+?)\s+(?:সম্পর্কে|নিয়ে)\s+(?:কী|কি)\s+মনে")


def _memory_topic(text: str, is_bn: bool) -> str:
    """Extract the recall topic from 'what do you remember about <topic>'."""
    pattern = _MEMORY_TOPIC_BN if is_bn else _MEMORY_TOPIC_EN
    match = pattern.search(text.strip())
    if not match:
        return ""
    return match.group(1).strip().rstrip("?।.!?")


def parse_memory_intent(text: str) -> Optional[tuple[str, str]]:
    """
    Detect explicit memory commands via rules (fast path, no LLM call).

    Returns (action, content):
      ("remember",  fact)    — store this fact
      ("forget",    target)  — forget a specific memory
      ("forget_all", "")     — forget everything
      ("recall",    topic)   — recall memories (topic may be "")
      None                   — not a memory command

    Evaluation order: forget_all → recall → remember → forget.
    """
    if not text:
        return None

    txt = text.strip()
    is_bn = bool(re.search(r"[\u0980-\u09FF]", txt))

    if is_bn:
        if _MEMORY_FORGET_ALL_BN.search(txt):
            return ("forget_all", "")
        if _MEMORY_FORGET_BN.search(txt):
            target = _MEMORY_FORGET_BN.search(txt).group(1).strip().rstrip("?।.!?")
            return ("forget", target) if target else None
        if _MEMORY_RECALL_BN.search(txt):
            return ("recall", _memory_topic(txt, True))
        if (m := _MEMORY_REMEMBER_BN.search(txt)) is not None:
            content = (m.group(1) or m.group(2) or "").strip().rstrip("?।.!?")
            return ("remember", content) if content else None
    else:
        if _MEMORY_FORGET_ALL_EN.search(txt):
            return ("forget_all", "")
        if _MEMORY_RECALL_EN.search(txt):
            return ("recall", _memory_topic(txt, False))
        if (m := _MEMORY_REMEMBER_EN.search(txt)) is not None:
            content = m.group(1).strip().rstrip("?.!")
            return ("remember", content) if content else None
        if (m := _MEMORY_FORGET_EN.search(txt)) is not None:
            target = m.group(1).strip().rstrip("?.!")
            return ("forget", target) if target else None

    return None


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

        # Persistent long-term memory — open once, shared with the context
        self.memory_store = MemoryStore()
        self.context.memory_store = self.memory_store

        # Listening mode: "wake_word" gates on wake word; "always_on" uses continuous VAD
        self.listening_mode = getattr(settings, "listening_mode", "wake_word")
        self._wake_detector: Optional[WakeWordDetector] = None

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

    def set_listening_mode(self, mode: str) -> None:
        """Switch between wake_word and always_on listening."""
        mode = (mode or "").strip().lower()
        if mode not in ("wake_word", "always_on"):
            return
        self.listening_mode = mode
        self._text_event.set()  # unblock wake word wait if active

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

    @property
    def wake_detector(self) -> WakeWordDetector:
        """Lazy-init wake word detector (only created when wake_word mode is active)."""
        if self._wake_detector is None:
            self._wake_detector = WakeWordDetector(log_callback=self.on_log_message)
        return self._wake_detector

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

            # ── Voice path ──────────────────────────────────────────────────
            if self.listening_mode == "wake_word":
                # Gate: wait for wake word before listening for a command
                self.on_status_changed("standby")
                self.on_log_message(f"Waiting for wake word ({', '.join(settings.wake_words)})…")
                if not self.wake_detector.wait_for_wakeword(
                    self.listener.recognizer, running_check=self._voice_active
                ):
                    return None
                self.on_log_message("Wake word detected — listening for command.")

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
                # Config lock wins; else only force Bangla after an explicit language switch.
                # Do NOT lock to default context "en" — that breaks Bangla recognition.
                if settings.stt_language and settings.stt_language != "auto":
                    lang_hint = settings.stt_language
                elif self.context.current_language == "bn":
                    lang_hint = "bn"
                else:
                    lang_hint = None

                cmd_text = transcribe(
                    self.listener.recognizer,
                    audio,
                    language=lang_hint,
                )
                cmd_text = (cmd_text or "").strip()
                if not cmd_text:
                    self.on_log_message("Empty transcript — staying quiet.")
                    continue
                # Match reply language to what was actually spoken
                if re.search(r"[\u0980-\u09FF]", cmd_text):
                    self.context.current_language = "bn"
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

    def _handle_memory_intent(self, cmd_text: str) -> Optional[str]:
        """
        Handle explicit memory commands (remember / forget / recall).

        Returns the spoken reply if this was a memory command, else None so the
        normal dispatcher/LLM pipeline takes over.
        """
        intent = parse_memory_intent(cmd_text)
        if intent is None:
            return None

        action, content = intent
        is_bn = bool(re.search(r"[\u0980-\u09FF]", cmd_text))

        if action == "remember":
            self.memory_store.remember(content)
            self.on_log_message(f"[Memory] Stored: '{content}'")
            return (
                "Got it. I'll remember that."
                if not is_bn
                else "ঠিক আছে, আমি এটা মনে রাখব।"
            )

        if action == "recall":
            memories = self.memory_store.recall(
                content, limit=settings.memory_recall_limit
            )
            if not memories:
                return (
                    "I don't have any memories about that yet."
                    if not is_bn
                    else "এই বিষয়ে আমার এখনো কিছু মনে নেই।"
                )
            facts = [m["content"] for m in memories]
            prefix = "I remember: " if not is_bn else "আমার মনে আছে: "
            return prefix + ", ".join(facts)

        if action == "forget":
            if self.memory_store.forget(text=content):
                self.on_log_message(f"[Memory] Forgot: '{content}'")
                return (
                    "Okay, I've forgotten that."
                    if not is_bn
                    else "ঠিক আছে, আমি সেটা ভুলে গেছি।"
                )
            return (
                "I couldn't find that in my memory."
                if not is_bn
                else "আমি ওটা আমার মনে খুঁজে পাইনি।"
            )

        if action == "forget_all":
            count = self.memory_store.wipe()
            self.on_log_message(f"[Memory] Wiped all memories ({count}).")
            return (
                f"Okay, I've cleared all {count} of my memories."
                if not is_bn
                else f"ঠিক আছে, আমি আমার সব {count}টি মনে থাকা জিনিস মুছে দিয়েছি।"
            )

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

        # C. Memory commands (fast rule path — before tools / LLM)
        memory_reply = self._handle_memory_intent(cmd_text)
        if memory_reply is not None:
            self._deliver_reply(memory_reply)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(memory_reply)
            return True

        # D. Rule-based Dispatcher (Fast path)
        self.on_log_message("Checking local system rules dispatcher…")
        tool_output = self.dispatcher.dispatch(cmd_text)
        if tool_output is not None:
            self.on_log_message(f"Rule dispatcher executed tool. Output: '{tool_output}'")
            self._deliver_reply(tool_output)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(tool_output)
            return True

        # E. LLM Processing — tools only when the phrase looks action-oriented
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
        initial_status = "standby" if self.listening_mode == "wake_word" else "listening"
        self.on_status_changed(initial_status)

        self.on_log_message(f"Using LLM Model: {settings.model_name}")
        self.on_log_message(f"Listening mode: {self.listening_mode}")

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
