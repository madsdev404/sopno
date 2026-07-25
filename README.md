# 🌙 Sopno (স্বপ্ন) — Bilingual Offline AI Voice Assistant

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-linux-lightgrey.svg)](https://www.kernel.org/)
[![AI Engine](https://img.shields.io/badge/brain-Ollama%20%7C%20Gemma3-purple.svg)](https://ollama.com/)
[![Local & Private](https://img.shields.io/badge/privacy-100%25%20offline-success.svg)](#)
[![Code Style](https://img.shields.io/badge/code%20style-pep8-green.svg)](https://pep8.org/)

**Sopno** (Bengali: স্বপ্ন, meaning *Dream*) is a local, privacy-respecting, Jarvis-like AI voice assistant designed specifically for Linux desktops. It runs entirely on your machine—no internet connection required. It seamlessly listens in the background, transcribes dual-language speech (English and Bangla), leverages high-fidelity offline models for reasoning, acts via customized local system tools, and responds with expressively synthesized voice audio synced with a gorgeous glassmorphic HUD.

---

## 🎨 Architectural Overview

```
                 ┌──────────────────────────────────────┐
                 │             YOU (User)               │
                 └──────┬────────────────────────┬──────┘
                        │ Speak                  ▲ Hear Response
                        ▼                        │
          ┌───────────────────────────┐    ┌─────┴─────────────────────┐
          │  🎤 sopno/voice/listener  │    │   🔊 sopno/voice/tts      │
          │    Audio Stream Capture   │    │     Coqui TTS Engine      │
          └─────────────┬─────────────┘    └─────────────▲─────────────┘
                        │ Waveform                       │ Audio Sync
                        ▼                                │
          ┌───────────────────────────┐    ┌─────────────┴─────────────┐
          │ 📡 sopno/voice/wakeword   │    │     📺 sopno/ui/hud       │
          │   sherpa-onnx (Offline)   │    │  Glassmorphic PyQt5 HUD   │
          └─────────────┬─────────────┘    └─────────────▲─────────────┘
                        │ Triggered                      │ text
                        ▼                                │
          ┌───────────────────────────┐    ┌─────────────┴─────────────┐
          │     🗣️ sopno/voice/stt    │    │   💾 sopno/core/context   │
          │   faster-whisper (Local)  │    │  Conversation Context     │
          └─────────────┬─────────────┘    └─────────────▲─────────────┘
                        │ Transcription Text             │ Response Text
                        ▼                                │
          ┌───────────────────────────┐    ┌─────────────┴─────────────┐
          │ 🧠 sopno/core/dispatcher  ├─►  │     🤖 sopno/llm/client   │
          │  Command/Intent Router    │    │  Ollama Local Gemma3 Model│
          └─────────────┬─────────────┘    └───────────────────────────┘
                        │ Intent Match
                        ▼
          ┌───────────────────────────┐
          │     🛠️ sopno/tools        │
          │   Local Desktop Controls  │
          └───────────────────────────┘
```

---

## ✨ Features

*   **🔒 100% Offline-First Privacy:** All speech processing and model inference occur locally on your hardware. Zero metrics or voice waveforms are ever uploaded to cloud APIs.
*   **📡 Custom Local Wake Word:** Zero Picovoice licenses or API keys. Driven by a fast, offline `sherpa-onnx` Keyword Spotter with active boosting.
*   **🗣️ Bilingual Speech-to-Text (STT):** High-speed transcribing powered by `faster-whisper` (CTranslate2) with native bilingual recognition for English and Bengali.
*   **🔊 Expressive Neural Text-to-Speech (TTS):** True offline speech generation using Coqui TTS (with high-quality dual-language voices) and lightweight fallback systems.
*   **🧠 Local LLM Brain:** Integrated with `Ollama` running `qwen3:8b` (or any compatible model) supporting contextual, dynamic conversation history summarization.
*   **📺 Elegant Glassmorphic UI:** A floating, transparent PyQt5 HUD that sits beautifully on top of your windows to show live assistant states (Standby, Listening, Thinking, Speaking).
*   **🛠️ Full OS Desktop Integration:** Voice-controlled tools to adjust system volume, control media streams (Play/Pause/Skip), unlock/lock screens, retrieve exact time/date, search the web, and run custom applications.
*   **⚙️ Background System Daemon:** Comes pre-packaged with user systemd service files to boot automatically and run robustly as an always-on background service.

---

## 📁 Repository Structure

```text
sopno/
├── 📄 main.py                      # Starts the voice assistant (headless CLI or HUD GUI)
├── 📄 requirements.txt             # Unified Python dependencies
├── 📄 config.json                  # Centralized system configurations & user settings
├── 📁 sopno/                       # Core python package
│   ├── 📁 core/                    # Orchestrator pipeline, dispatcher, and context engines
│   ├── 📁 voice/                   # Audio stream recorders, wake word, STT, and TTS engines
│   ├── 📁 llm/                     # Ollama API connectors and summarizers
│   ├── 📁 tools/                   # Extensible action registry (volume, apps, media controls)
│   ├── 📁 ui/                      # PyQt5 overlay HUD and CLI terminals
│   └── 📁 config/                  # Safe system loader and prompt manager
├── 📁 prompts/                     # Editable plain text prompt templates (system personality)
├── 📁 scripts/                     # Daemon registrars and installation tools
└── 📁 tests/                       # Complete unit tests mapping each feature module
```

---

## 🚀 Getting Started

### 📋 Prerequisites

To run Sopno, you'll need standard system packages for handling audio and python building tools on Linux:

**Debian/Ubuntu/Pop!_OS:**
```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev ffmpeg flac libnotify-bin wmctrl xdotool
```

### 🧠 Step 1: Install Ollama

Sopno uses Ollama to run high-performance offline models:

1. Install Ollama:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. Pull the default highly optimized Gemma3 model:
   ```bash
   ollama pull qwen3:8b
   ```

### 🛠️ Step 2: Clone and Setup Virtual Environment

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/sopno.git
   ```
2. Create and activate a clean virtual environment:
   ```bash
   cd sopno
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install the unified python dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## 💻 Usage

### 🚀 Running the Assistant

Run the main orchestrator in **GUI mode** (brings up the gorgeous overlay HUD):
```bash
python3 main.py --gui
```

Alternatively, run in **headless Terminal mode**:
```bash
python3 main.py --cli
```

### 🗣️ Conversing & Voice Commands

1. Say the configured wake word: **"Sopno"** or **"Dream"**.
2. Wait for the HUD/terminal status to update to **🎤 Listening...**.
3. Speak your prompt in English or Bangla. Example command ideas:
   * *"What's the weather like in Dhaka?"* (Ollama response)
   * *"আজকের আবহাওয়া কেমন?"* (Ollama Bangla response)
   * *"Set volume to 80 percent."* (OS tool command execution)
   * *"কোড এডিটর খোলো"* (Opens VS Code)
   * *"Mute the audio."* (Mutes sound card)
   * *"Exit/বিদায়"* (Closes the assistant gracefully)

---

## ⚙️ Running as a Persistent Background Daemon

Sopno can be configured as a **systemd user service** so that it always runs in the background from boot and launches its interactive HUD right when you log into your graphical desktop interface.

1. **Install and enable the background daemon:**
   ```bash
   ./scripts/install_daemon.sh
   ```
2. **Control the service:**
   ```bash
   # Check background service status
   systemctl --user status sopno

   # Watch real-time running logs
   journalctl --user -u sopno -f

   # Start or stop the daemon
   systemctl --user start sopno
   systemctl --user stop sopno
   ```

---

## 🧪 Running Tests

Ensure system consistency by executing the standard test suite:

```bash
python3 -m unittest discover -s tests
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

*Made with ❤️ by Md. Abduss Sobhan.*
