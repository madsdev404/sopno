"""
sopno/core/assistant.py
━━━━━━━━━━━━━━━━━━━━━━━
Main pipeline orchestrator.

Defines the SopnoAssistant class, which runs the continuous listening loop:
  Standby (wake-word) → Listening (command capture) → Thinking (LLM/dispatcher) → Speaking (TTS reply).
Uses a callback-driven design so it can run seamlessly in headless CLI mode
or within a glassmorphic PyQt5 HUD.
"""

import re
import sys
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
        self.on_log_message      = log_callback or (lambda m: print(f"[Log] {m}"))

        self.running = True
        self.context = ConversationContext()
        self.dispatcher = CommandDispatcher()
        self.listener = Listener()
        self.wakeword_detector = WakeWordDetector(log_callback=self.on_log_message)

    def stop(self) -> None:
        """Stop the assistant loop."""
        self.running = False

    def run(self) -> None:
        """Boots the sound system and starts the continuous listening loop."""
        self.on_log_message("Initializing sound system…")
        
        # Calibrate microphone for background noise
        self.listener.calibrate()
        self.on_log_message("Sound system initialized successfully!")

        # Welcome greeting
        welcome_text = "Hello! Sopno voice assistant is ready."
        self.on_reply_generated(welcome_text)
        self.on_status_changed("speaking")
        speak(welcome_text)
        self.on_status_changed("standby")

        # Configuration keywords
        self.on_log_message(f"Using LLM Model: {settings.model_name}")
        self.on_log_message(f"Wake words configured: {settings.wake_words}")

        while self.running:
            try:
                self.on_status_changed("standby")
                
                # ── Step 1: Wait for Wake Word ─────────────────────────────────
                triggered = self.wakeword_detector.wait_for_wakeword(
                    recognizer=self.listener.recognizer,
                    running_check=lambda: self.running
                )

                if not triggered or not self.running:
                    continue

                # ── Step 2: Wake Word Detected, Listen for Command ─────────────
                self.on_log_message("Wake word detected! Listening for command…")
                self.on_status_changed("listening")

                try:
                    audio = self.listener.listen(phrase_time_limit=10)
                except Exception as e:
                    self.on_log_message(f"Microphone capturing failed: {e}")
                    continue

                # ── Step 3: Transcribe Captured Speech ─────────────────────────
                self.on_log_message("Transcribing speech…")
                try:
                    cmd_text = transcribe(self.listener.recognizer, audio)
                    self.on_log_message(f"User command: '{cmd_text}'")
                    self.on_speech_detected(cmd_text)
                except sr.UnknownValueError:
                    self.on_log_message("Could not understand audio.")
                    continue
                except Exception as e:
                    self.on_log_message(f"STT Error: {e}")
                    continue

                # ── Step 4: Process the Command ────────────────────────────────
                self.on_status_changed("thinking")

                # Parse clean input to check for system override actions (exit, lang switch)
                clean_cmd = cmd_text.lower().strip().replace(".", "").replace("?", "").replace("!", "")

                # A. Exit checks
                if clean_cmd in ["exit", "quit", "goodbye", "bye", "exit()", "বিদায়"]:
                    farewell = "Goodbye! Have a great day."
                    self.on_reply_generated(farewell)
                    self.on_status_changed("speaking")
                    speak(farewell)
                    self.on_status_changed("standby")
                    self.running = False
                    break

                # B. Language switches
                bangla_keywords = ["speak in bangla", "change to bangla", "talk in bangla", "banglay kotha bolo", "বাংলায় কথা বলো", "বাংলা করো", "বাংলায় বল"]
                english_keywords = ["speak in english", "change to english", "talk in english", "english-e kotha bolo", "ইংরেজিতে কথা বলো", "english-e bol", "ইংরেজিতে বল"]

                if any(kw in clean_cmd for kw in bangla_keywords):
                    self.context.current_language = "bn"
                    switch_text = "ঠিক আছে, আমি এখন থেকে বাংলায় কথা বলব।"
                    self.on_reply_generated(switch_text)
                    self.on_status_changed("speaking")
                    speak(switch_text)
                    self.context.add_user_message(cmd_text)
                    self.context.add_assistant_message(switch_text)
                    continue

                elif any(kw in clean_cmd for kw in english_keywords):
                    self.context.current_language = "en"
                    switch_text = "Sure, I will speak in English from now on."
                    self.on_reply_generated(switch_text)
                    self.on_status_changed("speaking")
                    speak(switch_text)
                    self.context.add_user_message(cmd_text)
                    self.context.add_assistant_message(switch_text)
                    continue

                # C. Rule-based Dispatcher (Fast path)
                self.on_log_message("Checking local system rules dispatcher…")
                tool_output = self.dispatcher.dispatch(cmd_text)
                if tool_output is not None:
                    self.on_log_message(f"Rule dispatcher executed tool. Output: '{tool_output}'")
                    self.on_reply_generated(tool_output)
                    self.on_status_changed("speaking")
                    speak(tool_output)
                    
                    # Record the action in the history
                    self.context.add_user_message(cmd_text)
                    self.context.add_assistant_message(tool_output)
                    continue

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
                        # Feed the assistant's request to call tools into chat history
                        chat_messages.append(response_msg)

                        for tool in tool_calls:
                            name = tool["function"]["name"]
                            args = tool["function"]["arguments"]
                            self.on_log_message(f"LLM request tool: '{name}' with args {args}")
                            
                            # Execute the tool and capture output
                            tool_result = execute_tool(name, args)
                            self.on_log_message(f"Tool output: '{tool_result}'")

                            # Add tool output as context to model
                            chat_messages.append({
                                "role": "tool",
                                "content": tool_result
                            })

                        # Ask Ollama for final summarized response including tool outputs
                        self.on_log_message("Requesting conversational response from Ollama…")
                        final_response = ollama.chat(
                            model=settings.model_name,
                            messages=chat_messages,
                        )
                        assistant_reply = final_response["message"]["content"]
                    else:
                        assistant_reply = response_msg.get("content", "")

                    # Clean markdown symbols (since output is read aloud)
                    assistant_reply_clean = re.sub(r'[*_`#\-]', ' ', assistant_reply)
                    assistant_reply_clean = re.sub(r'\s+', ' ', assistant_reply_clean).strip()

                    self.on_reply_generated(assistant_reply_clean)
                    self.on_status_changed("speaking")
                    speak(assistant_reply_clean)

                    # Save the response to permanent context memory
                    self.context.add_assistant_message(assistant_reply_clean)

                except Exception as err:
                    self.on_log_message(f"Ollama/Chat error: {err}")
                    error_speech = "Sorry, I had trouble communicating with the AI model."
                    self.on_reply_generated(error_speech)
                    self.on_status_changed("speaking")
                    speak(error_speech)
                    
                    # Pop the failed user utterance to prevent context poison
                    if self.context.raw_messages and self.context.raw_messages[-1]["role"] == "user":
                        self.context.raw_messages.pop()

            except KeyboardInterrupt:
                self.on_log_message("KeyboardInterrupt caught. Shutting down Sopno.")
                self.running = False
                break
            except Exception as e:
                self.on_log_message(f"Unexpected loop exception: {e}")
                time.sleep(1)

        self.on_status_changed("standby")
        self.on_log_message("Sopno pipeline stopped.")
