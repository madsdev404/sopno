# "sopno" (Dream) - A to Z Installation Guide

Eikhane "sopno" voice assistant project-er jonno ja ja system dependency and Python libraries install kora lagbe, tar prottekta step details-e deya holo.

---

## Step 1: System Dependencies (Linux Specific)
Linux-e audio input (Microphone) and output (Speaker) thikmoto kaj korar jonno system-level packages install kora dorkar. 

Terminal open kore nicher command-gulo run korun:

```bash
# System packages package manager update korun
sudo apt update

# PyAudio installation-er jonno PortAudio utility install korun
sudo apt install -y python3-dev portaudio19-dev

# TTS rendering playback and helper tools (Mandatory for playing audio)
sudo apt install -y ffmpeg flac
```

---

## Step 2: Python Virtual Environment (venv) Setup
Project dependencies clean and isolated rakhar jonno virtual environment generate kora unique standard practice.

```bash
# Project root directory-te virtual environment toiri korun
python3 -m venv venv

# Virtual environment active korun
source venv/bin/activate
```
*(Proti bar new terminal open korle project folder-e giye `source venv/bin/activate` command run korte hobe)*

---

## Step 3: Python Libraries Installation
Virtual environment active thaka obosthay pip-er maddhome nicher python libraries gulo install korun:

```bash
# Upgrade pip first
pip install --upgrade pip

# Install official Ollama client
pip install ollama

# Install Edge-TTS and gTTS (Voice output)
pip install edge-tts gTTS

# Install Speech Recognition and Whisper (Voice transcription)
pip install SpeechRecognition faster-whisper

# Install PyAudio (Mic inputs record)
pip install pyaudio

# Install sherpa-onnx and pvrecorder (Wake word detection)
pip install sherpa-onnx pvrecorder numpy
```

---

## Step 3.5: Download Wake Word Model (sherpa-onnx)
Sopno uses a local, offline `sherpa-onnx` model for wake-word detection. Download and extract it inside the `models/` directory:

```bash
# Create models directory
mkdir -p models
cd models

# Download Zipformer Gigaspeech model
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.gz

# Extract it
tar -xzf sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.gz

# Remove compressed file
rm sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.gz
```

---

## Step 4: Verification (Kaj korche kina check kora)
Sob install sesh hole system-er configuration properly setup hoyeche kina ta check korte hobe:

### Check Speakers (TTS):
```python
from gtts import gTTS
import subprocess
import os

tts = gTTS(text="Hello. Sopno assistant system is successfully configured.", lang="en")
tts.save("test.mp3")
subprocess.run(["ffplay", "-nodisp", "-autoexit", "test.mp3"])
os.remove("test.mp3")
```

### Check Microphone (STT):
```python
import speech_recognition as sr
r = sr.Recognizer()
with sr.Microphone() as source:
    print("Kichu bolun...")
    audio = r.listen(source)
    print("Shona sesh! Process korchi...")
```

---

## Step 5: Ready for Coding!
Sob successfully install and run hole, amra amader main `sopno.py` code e jabo jekhane Gemma-3 model run hobe memory logic soho.
