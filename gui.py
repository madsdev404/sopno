import sys
import os
import json
import time
import re
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QTextEdit, QPushButton, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QPoint, QSize
from PyQt5.QtGui import QFont, QColor, QIcon, QMovie

# Load Configuration
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "model_name": "gemma3:4b",
        "picovoice_access_key": "",
        "wake_words": ["sopno", "সোপনো", "dream"],
        "voice_lang_bn": "bn",
        "voice_lang_en": "en"
    }

class AssistantWorker(QObject):
    # Signals to communicate with GUI
    status_changed = pyqtSignal(str) # standby, listening, thinking, speaking, error
    speech_detected = pyqtSignal(str) # What user said
    reply_generated = pyqtSignal(str) # What Sopno said
    log_message = pyqtSignal(str) # Internal log messages
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = True
        self.is_listening = False
        
    def start_loop(self):
        # We import here to prevent blocking PyQt5 import
        import speech_recognition as sr
        import ollama
        from tools import execute_tool
        from sopno import speak_text, recognize_bilingual, SYSTEM_PROMPT, MAX_HISTORY_LENGTH, summarize_history
        
        self.log_message.emit("Initializing Sound System...")
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.pause_threshold = self.config.get("pause_threshold", 0.8)
        
        # Pull model first or ensure it exists
        model_name = self.config.get("model_name", "gemma3:4b")
        self.log_message.emit(f"Using Model: {model_name}")
        
        # Setup tools schema
        from tools import get_current_time # verify imports
        
        # We define tools for Ollama chat
        from tools_schema import TOOLS_SCHEMA
        
        # Test microphone once
        try:
            with sr.Microphone() as source:
                self.log_message.emit("Calibrating microphone...")
                r.adjust_for_ambient_noise(source, duration=1.5)
                self.log_message.emit("Microphone calibrated successfully!")
        except Exception as e:
            self.status_changed.emit("error")
            self.log_message.emit(f"Microphone Error: {e}")
            return
            
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        current_language = "en"
        
        self.status_changed.emit("standby")
        self.log_message.emit("Sopno is ready and listening...")
        
        # Play startup welcome chime or voice
        welcome = "Hello, Sopno is active."
        self.reply_generated.emit(welcome)
        self.status_changed.emit("speaking")
        speak_text(welcome)
        self.status_changed.emit("standby")
        
        # Determine if we should use Picovoice Porcupine or fallback SpeechRecognition
        access_key = self.config.get("picovoice_access_key", "").strip()
        use_porcupine = False
        porcupine = None
        
        if access_key:
            try:
                import pvporcupine
                
                # Porcupine supports: 'alexa', 'americano', 'blueberry', 'bumblebee', 'computer', 'grapefruit', 'grasshopper', 'hey google', 'hey siri', 'jarvis', 'ok google', 'picovoice', 'porcupine', 'terminator'
                config_keywords = self.config.get("wake_words", ["sopno", "সোপনো", "dream"])
                supported_keywords = [
                    "alexa", "americano", "blueberry", "bumblebee", "computer", "grapefruit", 
                    "grasshopper", "hey google", "hey siri", "jarvis", "ok google", "picovoice", 
                    "porcupine", "terminator"
                ]
                
                porcupine_keywords = [kw.lower() for kw in config_keywords if kw.lower() in supported_keywords]
                if not porcupine_keywords:
                    porcupine_keywords = ["computer"]
                    
                porcupine = pvporcupine.create(access_key=access_key, keywords=porcupine_keywords)
                use_porcupine = True
                self.log_message.emit(f"Picovoice Porcupine active. Wake words: {porcupine_keywords}")
            except Exception as e:
                self.log_message.emit(f"Failed to load Picovoice Porcupine ({e}). Falling back to continuous SpeechRecognition.")
                use_porcupine = False
        else:
            self.log_message.emit("No Picovoice Access Key. Using continuous SpeechRecognition for wake words.")
            
        # Local wake word implementation or continuous listening
        while self.running:
            try:
                triggered = False
                
                if use_porcupine and porcupine is not None:
                    from pvrecorder import PvRecorder
                    self.status_changed.emit("standby")
                    self.log_message.emit("Listening for wake word (Picovoice)...")
                    
                    recorder = PvRecorder(device_index=-1, frame_length=porcupine.frame_length)
                    recorder.start()
                    
                    try:
                        while self.running:
                            pcm = recorder.read()
                            result = porcupine.process(pcm)
                            if result >= 0:
                                triggered = True
                                break
                    finally:
                        try:
                            recorder.stop()
                            recorder.delete()
                        except Exception:
                            pass
                            
                    if not triggered:
                        continue
                else:
                    with sr.Microphone() as source:
                        self.status_changed.emit("standby")
                        self.log_message.emit("Listening for wake word (SpeechRecognition)...")
                        try:
                            # Short capture to check for wake words
                            audio = r.listen(source, timeout=5, phrase_time_limit=4)
                        except sr.WaitTimeoutError:
                            continue
                        except Exception as e:
                            time.sleep(0.5)
                            continue
                            
                    # Transcribe speech
                    try:
                        self.log_message.emit("Checking transcription...")
                        text = recognize_bilingual(r, audio)
                        self.log_message.emit(f"Heard: {text}")
                    except Exception:
                        # Ignore unrecognized sounds
                        continue
                    
                    # Check wake word
                    text_lower = text.lower().strip()
                    wake_words = self.config.get("wake_words", ["sopno", "সোপনো", "dream"])
                    triggered = any(ww in text_lower for ww in wake_words) or "sopno" in text_lower or "সোপন" in text_lower
                
                if triggered:
                    self.log_message.emit("Wake word detected!")
                    # Speak a quick acknowledging sound or greeting
                    self.status_changed.emit("listening")
                    
                    # Capture the actual command
                    with sr.Microphone() as cmd_source:
                        self.log_message.emit("Capturing command...")
                        try:
                            cmd_audio = r.listen(cmd_source, timeout=7, phrase_time_limit=10)
                        except sr.WaitTimeoutError:
                            self.log_message.emit("Command timeout.")
                            continue
                            
                    try:
                        cmd_text = recognize_bilingual(r, cmd_audio)
                        self.log_message.emit(f"User command: {cmd_text}")
                        self.speech_detected.emit(cmd_text)
                    except Exception as e:
                        self.log_message.emit(f"STT Error: {e}")
                        continue
                        
                    # Process Command
                    self.status_changed.emit("thinking")
                    
                    # Check exit
                    clean_cmd = cmd_text.lower().strip().replace(".", "").replace("?", "")
                    if clean_cmd in ['exit', 'quit', 'goodbye', 'bye', 'বিদায়']:
                        farewell = "Goodbye!"
                        self.reply_generated.emit(farewell)
                        self.status_changed.emit("speaking")
                        speak_text(farewell)
                        self.status_changed.emit("standby")
                        self.running = False
                        break
                        
                    # Handle language switch commands
                    if any(kw in clean_cmd for kw in ["speak in bangla", "change to bangla", "banglay kotha bolo", "বাংলায় কথা বলো"]):
                        current_language = "bn"
                        switch_text = "ঠিক আছে, আমি এখন থেকে বাংলায় কথা বলব।"
                        self.reply_generated.emit(switch_text)
                        self.status_changed.emit("speaking")
                        speak_text(switch_text)
                        messages.append({"role": "user", "content": cmd_text})
                        messages.append({"role": "assistant", "content": switch_text})
                        continue
                    elif any(kw in clean_cmd for kw in ["speak in english", "change to english", "english-e kotha bolo", "ইংরেজিতে কথা বলো"]):
                        current_language = "en"
                        switch_text = "Sure, I will speak in English from now on."
                        self.reply_generated.emit(switch_text)
                        self.status_changed.emit("speaking")
                        speak_text(switch_text)
                        messages.append({"role": "user", "content": cmd_text})
                        messages.append({"role": "assistant", "content": switch_text})
                        continue
                        
                    # Append User Message
                    messages.append({"role": "user", "content": cmd_text})
                    
                    if len(messages) >= MAX_HISTORY_LENGTH:
                        messages = summarize_history(messages)
                        
                    chat_messages = messages.copy()
                    if current_language == "bn":
                        chat_messages.append({"role": "system", "content": "IMPORTANT: You MUST respond in Bangla (বাংলা) only."})
                    else:
                        chat_messages.append({"role": "system", "content": "IMPORTANT: You MUST respond in English only."})
                        
                    # Query Ollama with Tool Calling
                    try:
                        self.log_message.emit("Querying Ollama with tools...")
                        response = ollama.chat(
                            model=model_name,
                            messages=chat_messages,
                            tools=TOOLS_SCHEMA
                        )
                        
                        response_msg = response.get('message', {})
                        tool_calls = response_msg.get('tool_calls', [])
                        
                        if tool_calls:
                            # Execute the tools
                            for tool in tool_calls:
                                name = tool['function']['name']
                                args = tool['function']['arguments']
                                self.log_message.emit(f"Executing tool: {name} with args {args}")
                                tool_result = execute_tool(name, args)
                                self.log_message.emit(f"Tool output: {tool_result}")
                                
                                # Feed back tool results to assistant
                                chat_messages.append(response_msg)
                                chat_messages.append({
                                    "role": "tool",
                                    "content": tool_result
                                })
                                
                            # Query again for conversation response
                            self.log_message.emit("Querying Ollama for conversational reply...")
                            final_response = ollama.chat(
                                model=model_name,
                                messages=chat_messages
                            )
                            assistant_reply = final_response['message']['content']
                        else:
                            assistant_reply = response_msg.get('content', '')
                            
                        # Clean reply formatting
                        assistant_reply = re.sub(r'[*_`#\-\n]', ' ', assistant_reply).strip()
                        self.reply_generated.emit(assistant_reply)
                        
                        # Synthesize and speak
                        self.status_changed.emit("speaking")
                        speak_text(assistant_reply)
                        
                        # Add response to memory
                        messages.append({"role": "assistant", "content": assistant_reply})
                        
                    except Exception as err:
                        self.log_message.emit(f"Ollama/Chat Error: {err}")
                        error_speech = "Sorry, I encountered an issue while processing your request."
                        self.reply_generated.emit(error_speech)
                        self.status_changed.emit("speaking")
                        speak_text(error_speech)
                        if len(messages) > 0 and messages[-1]["role"] == "user":
                            messages.pop()
                            
            except Exception as e:
                self.log_message.emit(f"Main loop error: {e}")
                time.sleep(1)

        # Cleanup Picovoice Resources
        if porcupine is not None:
            try:
                porcupine.delete()
            except Exception:
                pass


class SopnoHUDWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.old_pos = None
        
        # Load HUD UI
        self.init_ui()
        
        # Start background worker
        self.worker = AssistantWorker(config)
        self.thread = threading.Thread(target=self.worker.start_loop)
        self.thread.daemon = True
        
        # Connect signals
        self.worker.status_changed.connect(self.update_status)
        self.worker.speech_detected.connect(self.update_user_speech)
        self.worker.reply_generated.connect(self.update_sopno_reply)
        self.worker.log_message.connect(self.update_log)
        
        self.thread.start()

    def init_ui(self):
        # Configure frameless, translucent, always on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Premium Modern Glassmorphism Styling
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setStyleSheet("""
            QWidget#CentralWidget {
                background-color: rgba(15, 23, 42, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
            }
        """)
        
        # Window Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 229, 255, 100)) # Neon cyan shadow glow
        shadow.setOffset(0, 0)
        self.central_widget.setGraphicsEffect(shadow)
        
        # Main Layout
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title and Close button header
        header = QHBoxLayout()
        title = QLabel("🌙 SOPNO AI")
        title.setFont(QFont("Outfit", 12, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: 2px;")
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8892B0;
                border: none;
                font-size: 14px;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 76, 76, 0.2);
                color: #FF4C4C;
            }
        """)
        self.close_btn.clicked.connect(self.close_app)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.close_btn)
        layout.addLayout(header)
        
        # Status Glow Circle & Label
        status_layout = QHBoxLayout()
        self.status_glow = QLabel()
        self.status_glow.setFixedSize(14, 14)
        self.status_glow.setStyleSheet("background-color: #888888; border-radius: 7px;")
        
        self.status_label = QLabel("💤 STANDBY")
        self.status_label.setFont(QFont("Inter", 10, QFont.Bold))
        self.status_label.setStyleSheet("color: #8892B0;")
        
        status_layout.addWidget(self.status_glow)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Transcription Output Area
        self.speech_display = QLabel("Waiting for voice...")
        self.speech_display.setFont(QFont("Inter", 10))
        self.speech_display.setWordWrap(True)
        self.speech_display.setStyleSheet("color: rgba(255,255,255,0.7); background-color: rgba(255,255,255,0.05); padding: 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05);")
        self.speech_display.setMinimumHeight(55)
        layout.addWidget(self.speech_display)
        
        # Sopno Reply Display
        self.reply_display = QTextEdit()
        self.reply_display.setReadOnly(True)
        self.reply_display.setFont(QFont("Inter", 10))
        self.reply_display.setPlaceholderText("Responses will appear here...")
        self.reply_display.setStyleSheet("""
            QTextEdit {
                color: #00FFCC; 
                background-color: rgba(0,0,0,0.2); 
                border: 1px solid rgba(0,255,204,0.1); 
                padding: 10px; 
                border-radius: 12px;
            }
        """)
        self.reply_display.setMinimumHeight(90)
        self.reply_display.setMaximumHeight(150)
        layout.addWidget(self.reply_display)
        
        # Debug Logs (very small, subtle text)
        self.log_display = QLabel("Sopno System active.")
        self.log_display.setFont(QFont("Inter", 8))
        self.log_display.setStyleSheet("color: #4B5563; padding-top: 5px;")
        layout.addWidget(self.log_display)
        
        self.setCentralWidget(self.central_widget)
        self.resize(380, 420)
        
        # Center/position HUD on screen
        self.position_hud()
        
    def position_hud(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 40
        y = 60 # Sits nicely near top right
        self.move(x, y)
        
    # Drag window handlers
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    # Slot updates
    def update_status(self, status):
        # Color codes:
        # standby: #888888 (Gray)
        # listening: #00E5FF (Neon Cyan)
        # thinking: #FF007F (Neon Pink)
        # speaking: #00FF66 (Neon Green)
        # error: #FF3333 (Neon Red)
        
        shadow = self.central_widget.graphicsEffect()
        
        if status == "standby":
            self.status_glow.setStyleSheet("background-color: #888888; border-radius: 7px;")
            self.status_label.setText("💤 STANDBY")
            self.status_label.setStyleSheet("color: #8892B0;")
            if shadow: shadow.setColor(QColor(136, 136, 136, 60))
        elif status == "listening":
            self.status_glow.setStyleSheet("background-color: #00E5FF; border-radius: 7px; border: 1px solid #FFFFFF;")
            self.status_label.setText("🎤 LISTENING...")
            self.status_label.setStyleSheet("color: #00E5FF;")
            if shadow: shadow.setColor(QColor(0, 229, 255, 180))
        elif status == "thinking":
            self.status_glow.setStyleSheet("background-color: #FF007F; border-radius: 7px; border: 1px solid #FFFFFF;")
            self.status_label.setText("🧠 THINKING...")
            self.status_label.setStyleSheet("color: #FF007F;")
            if shadow: shadow.setColor(QColor(255, 0, 127, 180))
        elif status == "speaking":
            self.status_glow.setStyleSheet("background-color: #00FF66; border-radius: 7px; border: 1px solid #FFFFFF;")
            self.status_label.setText("🔊 SPEAKING...")
            self.status_label.setStyleSheet("color: #00FF66;")
            if shadow: shadow.setColor(QColor(0, 255, 102, 180))
        elif status == "error":
            self.status_glow.setStyleSheet("background-color: #FF3333; border-radius: 7px;")
            self.status_label.setText("⚠️ SYSTEM ERROR")
            self.status_label.setStyleSheet("color: #FF3333;")
            if shadow: shadow.setColor(QColor(255, 51, 51, 150))

    def update_user_speech(self, text):
        self.speech_display.setText(f'“ {text} ”')
        
    def update_sopno_reply(self, text):
        self.reply_display.setText(text)
        
    def update_log(self, log):
        self.log_display.setText(log)
        print(f"[HUD Log] {log}")
        
    def close_app(self):
        self.worker.running = False
        self.close()
        sys.exit(0)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set app style
    app.setStyle("Fusion")
    
    config = load_config()
    window = SopnoHUDWindow(config)
    window.show()
    sys.exit(app.exec_())
