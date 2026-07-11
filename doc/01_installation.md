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

# TTS (Text-to-Speech) offline rendering-er jonno espeak install korun
sudo apt install -y espeak

# Audio processing & Speech Recognition helper tools (optional but recommended)
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

# Install Offline Text-to-Speech library (Mouth)
pip install pyttsx3

# Install Speech Recognition library (Ears)
pip install SpeechRecognition

# Install PyAudio (Mic inputs record korar jonno dependency)
pip install pyaudio
```

---

## Step 4: Verification (Kaj korche kina check kora)
Sob install sesh hole system-er configuration properly setup hoyeche kina ta check korte hobe:

### Check Speakers (TTS):
```python
import pyttsx3
engine = pyttsx3.init()
engine.say("Hello. Sopno assistant system is successfully configured.")
engine.runAndWait()
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
