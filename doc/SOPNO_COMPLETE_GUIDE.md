# 🌙 SOPNO (স্বপ্ন) — Complete Technical Guide
> **"Making Your PC Alive — A Bilingual Jarvis-like AI Voice Assistant"**

---

## Table of Contents

1. [What is Sopno?](#1-what-is-sopno)
2. [Architecture Overview](#2-architecture-overview)
3. [Current System — Deep Dive](#3-current-system--deep-dive)
4. [Installation on Any PC](#4-installation-on-any-pc)
5. [Running & Using Sopno](#5-running--using-sopno)
6. [What is Missing — Jarvis Roadmap](#6-what-is-missing--jarvis-roadmap)
7. [Upgrading Each Component](#7-upgrading-each-component)
8. [Making it Always Alive (Daemon)](#8-making-it-always-alive-daemon)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. What is Sopno?

**Sopno** (Bengali: স্বপ্ন, meaning *Dream*) is a local, bilingual AI voice assistant that runs entirely on your PC. It listens to your voice, understands Bengali and English, thinks using a local LLM (Large Language Model), and speaks back to you.

### Goals
- **Private** — No cloud AI. Your conversations stay on your machine.
- **Bilingual** — Speaks Bengali and English naturally.
- **Always Alive** — (Target state) Runs in the background like Jarvis from Iron Man.
- **Extensible** — Can be given tools to control apps, search the web, and more.

### Current State vs Target State

| Feature | Current | Target (Jarvis) |
|---|---|---|
| Voice Input | ✅ Google STT (online) | ✅ Whisper (offline) |
| LLM Brain | ✅ Gemma3 via Ollama | ✅ Same + Tools |
| Voice Output | ✅ gTTS (online, slow) | ✅ Edge-TTS / Piper (fast) |
| Wake Word | ❌ Not yet | ✅ "Hey Sopno" |
| Always Running | ❌ Terminal only | ✅ systemd daemon |
| Desktop HUD | ❌ Not yet | ✅ Floating overlay |
| OS Control | ❌ Not yet | ✅ Open apps, music, etc. |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                     YOU (Human)                     │
└──────────────────────┬──────────────────────────────┘
                       │ Voice
                       ▼
┌─────────────────────────────────────────────────────┐
│              🎤 EARS — Speech-to-Text (STT)         │
│   Microphone → Audio → Text                         │
│   Library: SpeechRecognition + Google / Whisper     │
└──────────────────────┬──────────────────────────────┘
                       │ Text
                       ▼
┌─────────────────────────────────────────────────────┐
│              🧠 BRAIN — LLM via Ollama              │
│   Text → Reasoning → Response Text                  │
│   Model: gemma3:4b (local, private)                 │
│   Memory: Dynamic summarization                     │
└──────────────────────┬──────────────────────────────┘
                       │ Response Text
                       ▼
┌─────────────────────────────────────────────────────┐
│              🔊 MOUTH — Text-to-Speech (TTS)        │
│   Text → Audio → Speaker                           │
│   Library: gTTS + ffplay / Edge-TTS / Piper         │
└─────────────────────────────────────────────────────┘
```

---

## 3. Current System — Deep Dive

### 3.1 File Structure

```
sopno/
├── sopno.py            ← Main voice assistant script
├── test_stt.py         ← Microphone test script
├── test_tts.py         ← Speaker/TTS test script
├── venv/               ← Python virtual environment
├── doc/
│   ├── 01_installation.md
│   └── SOPNO_COMPLETE_GUIDE.md  ← This file
└── .gitignore
```

### 3.2 Configuration Block

```python
# File: sopno.py — Lines 10–25
MODEL_NAME = "gemma3:4b"          # Which Ollama model to use
MAX_HISTORY_LENGTH = 13           # Max messages before memory compression
                                  # = 1 system prompt + 6 full turns
```

**Why `gemma3:4b`?**
It's a small, fast model that runs on consumer hardware (4–8 GB RAM). You can change this to any model you have pulled via Ollama (e.g., `llama3.2`, `mistral`, `phi3`).

### 3.3 The System Prompt

```python
SYSTEM_PROMPT = """You are "Sopno" (Dream), a friendly, highly intelligent,
and helpful AI voice assistant. You are bilingual, fluent in both Bangla and English.
Guidelines:
1. Respond in the same language the user spoke.
2. Keep responses concise (2-4 sentences). No bullet lists or markdown.
3. For code/long text, give a brief summary first.
"""
```

**Why these constraints?**
Because TTS reads text aloud — markdown symbols like `**bold**` or `- bullet` sound terrible when spoken. The prompt instructs the model to speak naturally.

### 3.4 TTS — The Mouth (`speak_text`)

```python
def speak_text(text):
    is_bn = bool(re.search(r'[\u0980-\u09FF]', text))  # Detect Bengali chars
    target_lang = "bn" if is_bn else "en"
    
    tts = gTTS(text=text, lang=target_lang, slow=False)
    tts.save("temp_speech.mp3")
    subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "temp_speech.mp3"])
    os.remove("temp_speech.mp3")
```

**What it does:** Detects if the response is Bengali or English by checking for Bengali Unicode characters (`\u0980–\u09FF`), generates an MP3 using Google TTS, and plays it with `ffplay`.

**Why `ffplay`?** It's part of `ffmpeg` (already installed), works headlessly, and auto-exits when audio finishes. No extra library needed.

**Current Limitation:** Requires internet. Has ~1–2s delay from API call.

### 3.5 STT — The Ears (`recognize_bilingual`)

```python
def recognize_bilingual(r, audio):
    def recognize_lang(lang):
        try:
            return lang, r.recognize_google(audio, language=lang)
        except Exception as e:
            return lang, e

    # Run Bengali and English recognition in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(recognize_lang, "bn-BD"),
            executor.submit(recognize_lang, "en-US")
        ]
        results = {}
        for future in concurrent.futures.as_completed(futures):
            lang, result = future.result()
            results[lang] = result

    bn_res = results.get("bn-BD")
    en_res = results.get("en-US")

    # If Bengali result has actual Bengali characters → user spoke Bengali
    bn_char_count = len(re.findall(r'[\u0980-\u09FF]', bn_res))
    if bn_char_count > 0:
        return bn_res
    else:
        return en_res
```

**Why parallel?** Google STT processes audio differently per language. Instead of sequential attempts (doubling latency), we fire both simultaneously and pick the best result.

**Why check Bengali characters?** When Google processes English speech in Bengali mode, it returns transliterated text (no actual Bengali characters). So if the result has Bengali unicode → user actually spoke Bengali.

### 3.6 Memory Summarization (`summarize_history`)

```python
def summarize_history(messages):
    preserved_system = messages[0]       # Keep system prompt
    history_to_summarize = messages[1:-4] # Middle history → summarize
    preserved_recent = messages[-4:]      # Last 2 turns → keep raw

    # Ask the LLM to summarize old history in 2-3 sentences
    summary = ollama.chat(model=MODEL_NAME, messages=[...])

    return [preserved_system, {"role": "system", "content": f"Summary: {summary}"}, *preserved_recent]
```

**Why?** LLMs have a context window limit. If you chat for an hour, the message list grows huge, slowing responses and eventually crashing. This keeps the list lean while preserving memory of what you talked about.

**When triggered?** When `len(messages) >= 13` (configurable via `MAX_HISTORY_LENGTH`).

### 3.7 Main Loop (`main`)

```
Start → Adjust microphone for noise → Greet user
  ↓
Loop:
  Listen → Transcribe → Check exit/language commands
  → Send to LLM → Stream response → Speak response
  → Save to history → Check if memory needs compression
  → Repeat
```

---

## 4. Installation on Any PC

### 4.1 Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04+ |
| Python | 3.9+ | 3.11+ |
| RAM | 8 GB | 16 GB |
| Storage | 5 GB free | 10 GB free |
| Microphone | Any USB/built-in mic | Noise-cancelling USB |
| Internet | Yes (for gTTS + Google STT) | Optional (after upgrade) |

### 4.2 Step 1 — Install System Dependencies

```bash
# Update package lists
sudo apt update

# Audio libraries (required for microphone input)
sudo apt install -y python3-dev portaudio19-dev

# FFmpeg for audio playback
sudo apt install -y ffmpeg flac

# Git (if not already installed)
sudo apt install -y git
```

**For Fedora/RHEL:**
```bash
sudo dnf install python3-devel portaudio-devel ffmpeg git
```

**For Arch Linux:**
```bash
sudo pacman -S python portaudio ffmpeg git
```

### 4.3 Step 2 — Install Ollama

Ollama runs the local AI model on your machine.

```bash
# Official one-line installer
curl -fsSL https://ollama.com/install.sh | sh

# Verify it's running
ollama --version

# Pull the Gemma3 4B model (~2.5 GB download)
ollama pull gemma3:4b

# Test the model
ollama run gemma3:4b "Say hello in one sentence."
```

**Alternative models (if RAM is limited):**
```bash
ollama pull phi3         # ~2.3 GB — very fast, good for low RAM
ollama pull llama3.2:1b  # ~1.3 GB — ultra lightweight
ollama pull mistral      # ~4.1 GB — great quality
```

### 4.4 Step 3 — Clone & Setup Sopno

```bash
# Clone the repository
git clone https://github.com/yourusername/sopno.git
cd sopno

# Create a virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### 4.5 Step 4 — Install Python Libraries

```bash
pip install ollama gTTS SpeechRecognition pyaudio
```

**If `pyaudio` fails to install:**
```bash
# Try this alternative approach
sudo apt install -y python3-pyaudio
# OR build from source:
pip install --global-option='build_ext' --global-option='-I/usr/include' pyaudio
```

### 4.6 Step 5 — Verify Everything Works

**Test microphone:**
```bash
python3 test_stt.py
```

**Test speaker/TTS:**
```bash
python3 test_tts.py
```

**Test Ollama:**
```bash
ollama run gemma3:4b "Are you working?"
```

---

## 5. Running & Using Sopno

### 5.1 Start the Assistant

```bash
# Always activate venv first
cd /path/to/sopno
source venv/bin/activate

# Run
python3 sopno.py
```

### 5.2 Voice Commands

| What you say | What happens |
|---|---|
| Anything in English | Sopno replies in English |
| যেকোনো বাংলা কথা | সোপনো বাংলায় উত্তর দেয় |
| "Speak in Bangla" | Forces Bengali response mode |
| "Speak in English" | Forces English response mode |
| "exit" / "quit" / "bye" / "বিদায়" | Closes the assistant |

### 5.3 Changing the AI Model

Edit `sopno.py` line 13:
```python
MODEL_NAME = "gemma3:4b"   # Change to any ollama model name
```

Available models you can use after pulling:
```
gemma3:4b        — Default. Good balance of speed and quality.
mistral          — Better reasoning, slightly slower.
phi3             — Very fast, good for weak hardware.
llama3.2         — Latest Meta model, excellent quality.
qwen2.5:7b       — Strong multilingual support.
```

---

## 6. What is Missing — Jarvis Roadmap

To go from "terminal script" to "always-alive Jarvis", here are the missing pieces in priority order:

### Priority 1 — Wake Word (So It Listens Without You Doing Anything)

**What:** Instead of running a script manually, Sopno should always be listening in the background and wake up when you say **"Hey Sopno"**.

**Why:** This is the core of "always alive". Without it, you have to switch to a terminal and press run — that's not Jarvis.

**How:** Use `sherpa-onnx` Keyword Spotter with a pre-trained Gigaspeech Zipformer model — it is 100% free, runs offline, requires no API access keys, and allows custom wake words to be defined on the fly.

```bash
# Install libraries
pip install sherpa-onnx pvrecorder numpy
```

```python
import os
import numpy as np
import sherpa_onnx
from pvrecorder import PvRecorder

# Initialize Keyword Spotter with a local model
kws = sherpa_onnx.KeywordSpotter(
    tokens="models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/tokens.txt",
    encoder="models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    decoder="models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    joiner="models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    num_threads=1,
    keywords_file="models/active_keywords.txt",  # Contains custom BPE-tokenized keywords (e.g. ▁SO P N O :1.5)
    provider="cpu",
)

recorder = PvRecorder(device_index=-1, frame_length=512)
recorder.start()

stream = kws.create_stream()
print("Listening for wake word...")

while True:
    pcm = recorder.read()
    # Normalize PCM samples to float32 [-1, 1]
    samples = np.array(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    stream.accept_waveform(16000, samples)
    
    while kws.is_ready(stream):
        kws.decode_stream(stream)
        
    result = kws.get_result(stream)
    if result != "":
        print(f"Wake word detected: {result}")
        kws.reset_stream(stream)
        # → Trigger STT here
```

---

### Priority 2 — Offline STT with faster-whisper

**What:** Replace Google STT with OpenAI Whisper running locally.

**Why:** Google STT needs internet. Whisper is faster, more accurate, works offline, and supports Bengali natively.

```bash
pip install faster-whisper
```

```python
from faster_whisper import WhisperModel

# Options: "tiny", "base", "small", "medium", "large-v3"
# tiny = fastest (low accuracy), large-v3 = best (needs more RAM)
model = WhisperModel("small", device="cpu", compute_type="int8")

def transcribe(audio_file_path):
    segments, info = model.transcribe(audio_file_path, beam_size=5)
    text = " ".join([s.text for s in segments])
    detected_lang = info.language  # Automatically detects Bengali/English
    return text, detected_lang
```

**Model size vs RAM guide:**
| Model | Size | RAM Needed | Speed |
|---|---|---|---|
| tiny | 75 MB | 1 GB | Very fast |
| base | 145 MB | 1 GB | Fast |
| small | 466 MB | 2 GB | Good |
| medium | 1.5 GB | 5 GB | Very good |
| large-v3 | 3 GB | 10 GB | Best |

---

### Priority 3 — Fast Offline TTS with Edge-TTS or Piper

**What:** Replace gTTS (slow, online) with a fast, natural, offline voice.

**Option A — Edge-TTS (Free, Natural, Microsoft voices, needs internet once):**
```bash
pip install edge-tts
```

```python
import asyncio
import edge_tts

async def speak(text, lang="en"):
    voice = "bn-BD-NabanitaNeural" if lang == "bn" else "en-US-AriaNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save("speech.mp3")
    # Play with ffplay as before

asyncio.run(speak("Hello, I am Sopno.", lang="en"))
```

**Available Bengali voices:**
- `bn-BD-NabanitaNeural` — Female Bengali
- `bn-BD-PradeepNeural` — Male Bengali
- `bn-IN-BashkarNeural` — Male (India Bengali)

**Option B — Piper TTS (100% Offline, very fast):**
```bash
pip install piper-tts
# Download a voice model from: https://huggingface.co/rhasspy/piper-voices
```

```python
import subprocess

def speak_piper(text):
    # Piper reads from stdin and outputs a WAV file
    process = subprocess.run(
        ["piper", "--model", "en_US-amy-medium.onnx", "--output_file", "speech.wav"],
        input=text.encode(),
        capture_output=True
    )
    subprocess.run(["aplay", "speech.wav"])
```

---

### Priority 4 — systemd Daemon (Always Running, Survives Reboots)

**What:** Turn Sopno into a background system service that starts on boot and never dies.

**Why:** Currently if you close the terminal, Sopno dies. A daemon keeps it alive forever.

**Create the service file:**

```bash
sudo nano /etc/systemd/system/sopno.service
```

```ini
[Unit]
Description=Sopno AI Voice Assistant
After=network.target sound.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/Projects/sopno
ExecStart=/home/YOUR_USERNAME/Projects/sopno/venv/bin/python3 sopno.py
Restart=always
RestartSec=5
Environment="PULSE_RUNTIME_PATH=/run/user/1000/pulse"
Environment="DISPLAY=:0"

[Install]
WantedBy=default.target
```

```bash
# Replace YOUR_USERNAME with your actual username
sudo systemctl daemon-reload
sudo systemctl enable sopno      # Start on boot
sudo systemctl start sopno       # Start now
sudo systemctl status sopno      # Check if running
sudo journalctl -u sopno -f      # Watch live logs
```

---

### Priority 5 — OS Control / Tools

**What:** Give Sopno the ability to actually *do* things on your PC.

**Why:** Right now it only talks. Jarvis opens apps, plays music, searches the web, etc.

```python
import subprocess
import webbrowser
import datetime

# Tool definitions
def open_app(app_name):
    apps = {
        "chrome": "google-chrome",
        "firefox": "firefox",
        "files": "nautilus",
        "terminal": "gnome-terminal",
        "vscode": "code",
        "spotify": "spotify",
    }
    cmd = apps.get(app_name.lower())
    if cmd:
        subprocess.Popen([cmd])
        return f"Opening {app_name}."
    return f"I don't know how to open {app_name}."

def search_web(query):
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Searching Google for {query}."

def get_time():
    now = datetime.datetime.now()
    return f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d')}."

def control_volume(direction):
    if direction == "up":
        subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%+"])
        return "Volume increased."
    elif direction == "down":
        subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%-"])
        return "Volume decreased."
    elif direction == "mute":
        subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "toggle"])
        return "Volume toggled."
```

**Integrating tools with the LLM using function calling:**
```python
# Let the LLM decide which tool to call
import json

TOOLS = [
    {"name": "open_app", "description": "Open an application", "parameters": {"app_name": "string"}},
    {"name": "search_web", "description": "Search Google", "parameters": {"query": "string"}},
    {"name": "get_time", "description": "Get current time and date", "parameters": {}},
]

# Add tool descriptions to system prompt, parse LLM output for tool calls
```

---

### Priority 6 — Desktop HUD (Floating Overlay)

**What:** A small, always-visible floating window on your screen showing Sopno's state.

**Why:** Visual feedback makes it feel *alive* — you can see "Listening...", "Thinking...", "Speaking..." at all times.

```bash
pip install PyQt5
```

```python
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

class SopnoHUD(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sopno")
        self.setGeometry(50, 50, 300, 80)  # Position: top-left corner
        
        # Make window transparent and always on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.label = QLabel("💤 Sopno — Standby", self)
        self.label.setFont(QFont("Inter", 12))
        self.label.setStyleSheet("color: #00FF88; background: rgba(0,0,0,150); padding: 10px; border-radius: 8px;")
        self.label.resize(280, 60)

    def set_state(self, state):
        states = {
            "listening": "🎤 Listening...",
            "thinking":  "🧠 Thinking...",
            "speaking":  "🔊 Speaking...",
            "standby":   "💤 Standby",
        }
        self.label.setText(f"Sopno — {states.get(state, state)}")
```

---

## 7. Upgrading Each Component

### Complete Upgraded Stack

```
Current:  Google STT → gemma3:4b → gTTS
Upgraded: faster-whisper → gemma3:4b + tools → edge-tts/piper
Daemon:   systemd service
HUD:      PyQt5 floating overlay
Wake:     sherpa-onnx KWS
```

### Full Upgraded Dependencies

```bash
# Offline STT
pip install faster-whisper

# Better TTS
pip install edge-tts

# Wake word (offline, no key needed)
pip install sherpa-onnx pvrecorder numpy

# Desktop HUD
pip install PyQt5

# OS control helpers
sudo apt install -y wmctrl xdotool

# Notifications
sudo apt install -y libnotify-bin
```

---

## 8. Making it Always Alive (Daemon)

### Full Daemon Setup Flow

```
1. Install Ollama as a service (it does this automatically)
2. Create sopno.service file
3. Enable and start it
4. (Optional) Add auto-start for HUD via ~/.config/autostart/
```

### Auto-start HUD on Desktop Login

```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/sopno-hud.desktop
```

```ini
[Desktop Entry]
Type=Application
Name=Sopno HUD
Exec=/home/YOUR_USERNAME/Projects/sopno/venv/bin/python3 /home/YOUR_USERNAME/Projects/sopno/hud.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
```

### Check Ollama is Running as a Service

```bash
# Ollama installs itself as a systemd service automatically
systemctl status ollama

# If not running:
sudo systemctl start ollama
sudo systemctl enable ollama
```

---

## 9. Troubleshooting

### "No module named 'pyaudio'"
```bash
sudo apt install -y python3-pyaudio
# OR
pip install pyaudio --global-option="build_ext" --global-option="-I/usr/include"
```

### "ffplay: command not found"
```bash
sudo apt install -y ffmpeg
```

### "Ollama connection refused"
```bash
# Make sure Ollama is running
ollama serve &
# OR check service
sudo systemctl start ollama
```

### "Could not get audio device"
```bash
# Check if microphone is detected
arecord -l

# Check PulseAudio
pulseaudio --check && echo "Running" || pulseaudio --start
```

### STT gives wrong language
- Speak more clearly and pause after finishing
- Adjust `r.pause_threshold` (default `0.8` seconds) in `sopno.py`
- Try `r.energy_threshold = 4000` (higher = less sensitive to noise)

### Model is too slow
- Switch to a lighter model: `ollama pull phi3`
- Change `MODEL_NAME = "phi3"` in `sopno.py`
- Ensure no other heavy apps are running

### Wake word not triggering
- Ensure the model files are located inside `models/`
- Try increasing microphone sensitivity in system settings
- Make sure you're not in a loud environment

---

## Quick Reference Card

```bash
# Start Sopno (manual)
cd ~/Projects/sopno && source venv/bin/activate && python3 sopno.py

# Start as daemon
sudo systemctl start sopno

# Watch daemon logs
sudo journalctl -u sopno -f

# Stop daemon  
sudo systemctl stop sopno

# Pull a new AI model
ollama pull llama3.2

# Update Python packages
source venv/bin/activate && pip install --upgrade ollama gTTS SpeechRecognition

# Test mic only
python3 test_stt.py

# Test speaker only
python3 test_tts.py
```

---

*Document maintained for Sopno v1.x | Last updated: July 2026*
*Author: Sopno Development*
