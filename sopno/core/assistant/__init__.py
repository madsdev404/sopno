"""
sopno/core/assistant/__init__.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Main pipeline orchestrator.

Defines the SopnoAssistant class, which runs the continuous conversation loop:
  Intro (TTS) → Listening (idle VAD) → Thinking → Speaking → Listening again.
Uses offline Silero VAD for natural turn-taking; stays quiet until the user speaks.

Memory intent parsing lives in ``assistant/memory.py``;
confirmation patterns live in ``assistant/confirm.py``.
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
from sopno.core.reminders import ReminderPoller, ReminderStore, set_store as set_reminder_store
from sopno.core.rules import RulePoller, RuleStore, set_store as set_rule_store
from sopno.llm.client import chat as llm_chat, message_as_dict
from sopno.memory.store import MemoryStore
from sopno.tools.schema import get_schema, get_schema_for
from sopno.tools.registry import execute_tool
from sopno.tools.builtins.dev.terminal import _close as close_terminal_shell
from sopno.tools.builtins.files.files import pending_action, resolve_pending
from sopno.voice.listener import Listener
from sopno.voice.mic import MicStream
from sopno.voice.stt import transcribe
from sopno.voice.tts import speak
from sopno.voice.wakeword import WakeWordDetector, dynamic_greeting

from sopno.core.assistant.memory import parse_memory_intent  # noqa: F401 – public re-export
from sopno.core.assistant.confirm import (
    YES_RESPONSES as _YES_RESPONSES,
    YES_RESPONSES_BN as _YES_RESPONSES_BN,
    NO_RESPONSES as _NO_RESPONSES,
    NO_RESPONSES_BN as _NO_RESPONSES_BN,
)

# Only attach the heavy tool schema when the utterance looks action-oriented.
# Pure chat without tools is much faster on CPU (seconds vs tens of seconds).
_TOOLISH = re.compile(
    r"(?:"
    # Multi-word capability queries
    r"what can you do|your tool|your capabilit|what do you know|what are you able|"
    r"what feature|list (your )?feature|tell me what you can|what can sopno|"
    r"can you (?:do|help|handle|use|access)|how can you help"
    r"|(?:"
    # Single-word / short action tokens
    r"\b(?:"
    r"open|launch|start|close|search|google|source|find|look|"
    r"volume|mute|unmute|"
    r"play|pause|resume|next|previous|skip|"
    r"time|date|clock|battery|cpu|ram|memory|stats|status|system|"
    r"media|music|song|spotify|browser|chrome|firefox|vscode|terminal|"
    r"fetch|read|url|web|website|site|page|internet|online|"
    r"research|find out|look up|tell me about|what is|what are|who is|"
    r"latest|news|update|fact|define|explain|"
    r"terminal|command|shell|run|execute|install|apt|pip|sudo|git|bash|"
    r"script|compile|build|ping|curl|wget|kill|process|restart|download|"
    r"service|cron|log|journal|systemctl|ps aux|list processes|"
    r"file|folder|directory|create|edit|delete|rename|overwrite|write|notes|note|"
    r"copy|duplicate|move|grep|search for|read pdf|pdf|docx|xlsx|image|scan|"
    r"remind|reminder|reminders|timer|alert|schedule|remind me|"
    r"browse|navigate|webpage|"
    r"clipboard|copy that|screenshot|screen shot|windows|window|focus|type |typing|"
    r"keyboard|press |keys|key|disk|storage|gpu|graphics|network stats|"
    r"database|sql|query|uninstall|package|pacman|flatpak|"
    r"ping|traceroute|wifi|firewall|public ip|my ip|"
    r"email|mail|inbox|calendar|event|meeting|ocr|vision|describe (?:a )?(?:image|picture|screenshot)|"
    r"rule|rules|automation|automate|if .* then |"
    r"subagent|delegate|researcher|coder|reviewer|code review|review this|"
    r"commit|stage|stash|branch|push|pull|merge|diff|"
    r"code|project|repo|codebase|poem|song|video|recipe|weather"
    r")\b)"
    r")",
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

        # Shared mic stream — one sounddevice InputStream for both listener
        # and barge-in. Eliminates the PyAudio/sounddevice device race.
        self.mic_stream = MicStream(log_callback=self.on_log_message)
        self.listener = Listener(log_callback=self.on_log_message, mic_stream=self.mic_stream)

        # Persistent long-term memory — open once, shared with the context
        self.memory_store = MemoryStore()
        self.context.memory_store = self.memory_store

        # Persistent reminders — one shared store (tools + background poller).
        self.reminder_store = ReminderStore()
        set_reminder_store(self.reminder_store)
        self._reminder_poller: Optional[ReminderPoller] = None
        self._rule_poller: Optional[RulePoller] = None
        self._rule_store: Optional[RuleStore] = None
        self._agent_runtime = None
        # Serializes speech so a fired reminder never overlaps a spoken reply.
        self._speech_lock = threading.Lock()

        # Dynamic tools: plugins + MCP clients, loaded at startup so the LLM
        # schema (get_schema()) includes them from the first turn.
        self._mcp_hub = None
        if getattr(settings, "plugins_enabled", True):
            try:
                from sopno.tools.plugins import load_plugins
                loaded = load_plugins()
                if loaded:
                    self.on_log_message(f"[Plugins] loaded: {', '.join(loaded)}")
            except Exception as e:  # noqa: BLE001
                self.on_log_message(f"[Plugins] failed to load: {e}")
        if getattr(settings, "mcp_enabled", True) and getattr(settings, "mcp_servers", {}):
            try:
                from sopno.tools.mcp_client import McpHub
                self._mcp_hub = McpHub(settings.mcp_servers)
                self.on_log_message(f"[MCP] {self._mcp_hub.refresh()}")
            except Exception as e:  # noqa: BLE001
                self.on_log_message(f"[MCP] failed to connect: {e}")

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
        close_terminal_shell()
        self.mic_stream.stop()
        self.reminder_store.close()
        if self._rule_store is not None:
            try:
                self._rule_store.close()
            except Exception:  # noqa: BLE001
                pass
            self._rule_store = None
        if self._agent_runtime is not None:
            try:
                self._agent_runtime.stop()
            except Exception as e:  # noqa: BLE001
                self.on_log_message(f"[Agents] stop failed: {e}")
            self._agent_runtime = None
        if self._mcp_hub is not None:
            try:
                self._mcp_hub.close()
            except Exception:  # noqa: BLE001
                pass
            self._mcp_hub = None
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

    def _wake_word_active(self) -> bool:
        """True while we should keep listening for the wake word.

        Returns False when the user switches to always_on mode mid-wait,
        so the wake word loop exits immediately and the new mode takes effect.
        """
        return (
            self.running
            and self.interaction_mode == "voice"
            and self.listening_mode == "wake_word"
        )

    @property
    def wake_detector(self) -> WakeWordDetector:
        """Lazy-init wake word detector (only created when wake_word mode is active)."""
        if self._wake_detector is None:
            self._wake_detector = WakeWordDetector(log_callback=self.on_log_message)
        return self._wake_detector

    def _speak_with_barge_in(self, text: str) -> bool:
        """
        Speak while watching the mic; returns True if the user interrupted.

        Barge-in detection runs IN the InputStream callback — no separate
        thread, no frame consumption. The callback learns the TTS audio
        baseline after a short delay (for ffplay startup), then sets a
        threshold. If the user speaks louder than that during TTS,
        barge_in fires.
        """
        if not getattr(settings, "barge_in_enabled", True):
            speak(text)
            return False

        mic = self.mic_stream
        multiplier = float(getattr(settings, "barge_in_multiplier", 2.0))
        margin = float(getattr(settings, "barge_in_margin", 50))
        confirm_blocks = 8
        # ~0.77s of real TTS audio for baseline (12 blocks * 1024 frames @ 16kHz)
        cal_blocks = 12
        # ffplay startup latency — audio isn't audible until after this delay.
        # Calibration MUST happen after this delay so baseline reflects real TTS.
        _FFPLAY_STARTUP_DELAY_S = 0.5
        _MIN_BASELINE = 200.0  # ignore ambient-noise baselines below this

        mic.barge_in.clear()

        def _on_play_start() -> None:
            """Arm barge-in after TTS audio baseline is learned."""
            def _calibrate_and_arm() -> None:
                # Start calibration NOW — after ffplay has started producing audio.
                # The callback will collect energy for cal_blocks (~0.77s).
                mic.start_barge_calibration(cal_blocks)
                threading.Timer(cal_blocks * 1024 / mic.rate + 0.1, _arm).start()

            def _arm() -> None:
                # Read back the baseline energy the callback collected
                avg = mic._barge_baseline_avg
                if avg and avg > _MIN_BASELINE:
                    threshold = avg * multiplier + margin
                    mic.set_barge_threshold(threshold, confirm_blocks=confirm_blocks)
                    self.on_log_message(
                        f"Barge-in armed: baseline={avg:.0f}, "
                        f"threshold={threshold:.0f}"
                    )
                else:
                    # Baseline too low (ambient noise only) — use floor-based threshold
                    threshold = max(float(settings.energy_threshold_ceiling), _MIN_BASELINE * multiplier + margin)
                    mic.set_barge_threshold(threshold, confirm_blocks=confirm_blocks)
                    self.on_log_message(
                        f"Barge-in armed: baseline={avg:.0f} too low, "
                        f"using floor threshold={threshold:.0f}"
                    )

            # Delay calibration until ffplay audio is actually playing
            threading.Timer(_FFPLAY_STARTUP_DELAY_S, _calibrate_and_arm).start()

        try:
            speak(
                text,
                should_stop=lambda: mic.barge_in.is_set(),
                on_play_start=_on_play_start,
            )
        finally:
            mic.clear_barge()
            mic._barge_baseline_avg = 0.0
            self.mic_stream.flush()
        return mic.barge_in.is_set()

    def _deliver_reply(self, text: str, *, status: str = "speaking", barge_in: bool = True) -> None:
        """Show reply in UI; speak aloud only in voice mode."""
        self.on_reply_generated(text)
        with self._speech_lock:
            if self.interaction_mode == "voice":
                self.on_status_changed(status)
                if barge_in and self._speak_with_barge_in(text):
                    self.on_log_message("Barge-in detected — stopped speaking.")
                    self.on_status_changed("listening")
                    return
                if not barge_in:
                    from sopno.voice.tts import speak
                    speak(text)
                    # Flush stale TTS audio captured by mic through speakers
                    self.mic_stream.flush()
                time.sleep(_POST_SPEAK_SETTLE_S)
            else:
                # Text mode: brief "speaking" flash for avatar, no TTS
                self.on_status_changed(status)
                time.sleep(0.35)

    def _deliver_reminder(self, text: str) -> None:
        """Deliver a fired reminder from the background poller thread."""
        if not self.running:
            return
        with self._speech_lock:
            self.on_reply_generated(text)
            if self.interaction_mode == "voice":
                self.on_status_changed("speaking")
                self._speak_with_barge_in(text)
                self.on_status_changed("listening")
            else:
                self.on_status_changed("speaking")
                time.sleep(0.35)
                self.on_status_changed("standby")
        self.on_log_message(f"[Reminder] Delivered: {text}")

    def _deliver_rule(self, text: str) -> None:
        """Deliver a fired automation-rule action from the background poller."""
        if not self.running:
            return
        with self._speech_lock:
            self.on_reply_generated(text)
            if self.interaction_mode == "voice":
                self.on_status_changed("speaking")
                self._speak_with_barge_in(text)
                self.on_status_changed("listening")
            else:
                self.on_status_changed("speaking")
                time.sleep(0.35)
                self.on_status_changed("standby")
        self.on_log_message(f"[Rule] Fired: {text}")

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
                    self.listener.recognizer, running_check=self._wake_word_active,
                    mic_stream=self.mic_stream,
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
                    max_wait_s=0.0,
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
                continue

            self.on_log_message("Transcribing speech…")
            try:
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
                if re.search(r"[\u0980-\u09FF]", cmd_text):
                    self.context.current_language = "bn"
                self.on_log_message(f"User: '{cmd_text}'")
                self.on_speech_detected(cmd_text)
                return cmd_text
            except sr.UnknownValueError:
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
            "banglay kotha bolo", "বাংলায় কথা বলো", "বাংলা করো", "বাংলায় বল",
        ]
        english_keywords = [
            "speak in english", "change to english", "talk in english",
            "english-e kotha bolo", "ইংরেজিতে কথা বলো", "english-e bol", "ইংরেজিতে বল",
        ]

        if any(kw in clean_cmd for kw in bangla_keywords):
            self.context.current_language = "bn"
            switch_text = "ঠিক আছে, আমি এখন থেকে বাংলায় কথা বলব।"
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

        # C. Pending file-action confirmation (write / edit / delete / rename)
        pending = pending_action()
        if pending is not None:
            is_yes = bool(_YES_RESPONSES.search(cmd_text)
                          or _YES_RESPONSES_BN.search(cmd_text))
            is_no = bool(_NO_RESPONSES.search(cmd_text)
                         or _NO_RESPONSES_BN.search(cmd_text))
            if is_yes and not is_no:
                result = resolve_pending(pending["id"], "yes") or "Done."
                self.on_log_message(f"[File] Confirmed → {result}")
                self._deliver_reply(result)
                self.context.add_user_message(cmd_text)
                self.context.add_assistant_message(result)
                return True
            if is_no and not is_yes:
                result = resolve_pending(pending["id"], "no") or "Cancelled."
                self.on_log_message(f"[File] Declined → {result}")
                self._deliver_reply(result)
                self.context.add_user_message(cmd_text)
                self.context.add_assistant_message(result)
                return True

        # D. Memory commands (fast rule path — before tools / LLM)
        memory_reply = self._handle_memory_intent(cmd_text)
        if memory_reply is not None:
            self._deliver_reply(memory_reply)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(memory_reply)
            return True

        # E. Rule-based Dispatcher (Fast path)
        self.on_log_message("Checking local system rules dispatcher…")
        tool_output = self.dispatcher.dispatch(cmd_text)
        if tool_output is not None:
            self.on_log_message(f"Rule dispatcher executed tool. Output: '{tool_output}'")
            self._deliver_reply(tool_output)
            self.context.add_user_message(cmd_text)
            self.context.add_assistant_message(tool_output)
            return True

        # F. LLM Processing — tools only when the phrase looks action-oriented
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
                tools=get_schema_for(cmd_text) if use_tools else None,
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

        # Start the shared mic stream first, then calibrate.
        self.mic_stream.start()
        self.listener.calibrate()
        vad_note = "Silero VAD" if self.listener.turn_taker.available else "classic listen"
        self.on_log_message(f"Sound system ready ({vad_note} turn-taking).")

        # Welcome message — dynamic, time-based greeting.
        welcome_text = dynamic_greeting()
        self.on_log_message(f"Intro: '{welcome_text}'")
        self._deliver_reply(welcome_text, barge_in=False)
        initial_status = "standby" if self.listening_mode == "wake_word" else "listening"
        self.on_status_changed(initial_status)

        self.on_log_message(f"Using LLM Model: {settings.model_name}")
        self.on_log_message(f"Listening mode: {self.listening_mode}")

        # Background reminder poller — fires due reminders into the reply flow.
        if getattr(settings, "reminders_enabled", True):
            self._reminder_poller = ReminderPoller(
                deliver=self._deliver_reminder,
                run_check=lambda: self.running,
            )
            self._reminder_poller.start()
            self.on_log_message(
                f"Reminders enabled (poll every {settings.reminders_poll_seconds}s)."
            )

        # Background automation-rule poller — fires "if X then Y" rules.
        if getattr(settings, "rules_enabled", True):
            self._rule_store = RuleStore()
            set_rule_store(self._rule_store)
            self._rule_poller = RulePoller(
                store=self._rule_store,
                deliver=self._deliver_rule,
                run_check=lambda: self.running,
            )
            self._rule_poller.start()
            self.on_log_message(
                f"Automation rules enabled (poll every {settings.rules_poll_seconds}s)."
            )

        # Background long-running agents — workers + scheduler + watchdog.
        if getattr(settings, "agents_enabled", True):
            from sopno.core.agents.runtime import AgentRuntime
            self._agent_runtime = AgentRuntime(run_check=lambda: self.running)
            self._agent_runtime.start()
            self.on_log_message(
                f"Background agents enabled "
                f"({settings.agents_concurrency} worker(s))."
            )

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
                self.on_status_changed("listening")
                time.sleep(1)

        self.on_status_changed("standby")
        self.on_log_message("Sopno pipeline stopped.")
