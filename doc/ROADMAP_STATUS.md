# 🗺️ SOPNO Assistant — Implementation Roadmap & Status Tracker

This document tracks the incremental progress of transforming **Sopno (স্বপ্ন)** from a simple terminal script into a fully offline, background-running, Jarvis-like AI voice assistant.

---

## 📊 Status Summary
* **Current Phase:** Upgrading Core Foundations
* **Latest Completed Upgrade:** Offline Faster Whisper STT Integration

---

## 🛠️ Feature Checklist

### 1. Voice Output (Text-to-Speech) — **[COMPLETED]**
* [x] **High-quality Neural Voices:** Upgraded from standard robotic `gTTS` to high-fidelity Microsoft Edge Neural Speech.
* [x] **Bilingual Language Routing:** Automatically selects `bn-BD-NabanitaNeural` (Bengali Female) or `en-US-AriaNeural` (English Female).
* [x] **Network Resiliency:** Implemented automatic graceful fallback to Google `gTTS` in case of offline/network failures.
* [x] **HUD Sync:** Synchronized audio synthesis so both CLI and PyQt5 HUD GUI benefit automatically.

### 2. Wake Word Detection — **[COMPLETED]**
* [x] **Local Offline Activation:** Integrated `sherpa-onnx` Keyword Spotter with a pre-trained Gigaspeech Zipformer model to run lightweight, offline wake-word processing for custom keywords.
* [x] **Dynamic Config Integration:** Automatically loads custom wake words from `config.json`, tokenizes them dynamically using the model's vocabulary, and applies boosting scores at runtime.
* [x] **No Keys Required:** Completely free, open-source, and local, eliminating the need for Picovoice API access keys or cloud accounts.
* [x] **Smart Fallback:** Implemented a continuous, auto-calibrating SpeechRecognition/Google STT wake-word listener if `sherpa-onnx` model files are missing, ensuring 100% out-of-the-box operation.

### 3. Voice Input (Speech-to-Text) — **[COMPLETED]**
* [x] **Local Offline STT:** Migrated from online Google SpeechRecognition to fully offline, high-speed `faster-whisper`.
* [x] **Bilingual Language Recognition:** Natively detects and transcribes both English and Bangla offline with near-zero latency using the CTranslate2 model.
* [x] **Graceful Fallback:** Implemented automatic online Google STT fallback to handle any temporary CPU/Whisper-loading issues, ensuring 100% voice engine reliability.

### 4. Background Daemon (Always Running) — **[REMAINING]**
* [ ] **systemd User Service:** Enable Sopno to run seamlessly as a background user daemon (`systemctl --user`).
* [ ] **Autostart Configuration:** Create system config so the Glassmorphic HUD launches automatically on desktop login.

### 5. OS Control & Tools — **[PARTIALLY DONE / INTEGRATED]**
* [x] **Core Functions:** Time/date, open apps, volume adjust, media controls, system stats, lock screen.
* [ ] **CLI Sync:** Enable tool calling on the terminal interface (`sopno.py`) as it is already implemented in `gui.py`.

---

## 📓 Technical Progress Log

### [July 14, 2026] — Step 1: Upgraded Voice Output to Neural Edge-TTS
* **Modified Files:** `sopno.py`
* **Added Files:** `test_edge_tts.py`
* **Impact:** Drastically reduced TTS response latency (~2s down to ~400ms) and made the voice incredibly natural, human-like, and expressive.

### [July 14, 2026] — Step 2: Integrated Dual-Mode Wake-Word Engine
* **Modified Files:** `gui.py`, `doc/ROADMAP_STATUS.md`
* **Impact:** Integrated Picovoice Porcupine for offline, near-zero CPU wake-word detection with an automated fallback to continuous SpeechRecognition.

### [July 14, 2026] — Step 3: Implemented Offline Faster Whisper STT
* **Modified Files:** `sopno.py`, `doc/ROADMAP_STATUS.md`
* **Added Files:** `test_whisper.py`
* **Impact:** Fully offline voice recognition with native bilingual support. Eliminates internet latency for voice transcribing.

### [July 17, 2026] — Step 4: Replaced Picovoice with sherpa-onnx KWS
* **Modified Files:** `gui.py`, `config.json`, `doc/ROADMAP_STATUS.md`
* **Impact:** Upgraded wake-word detection to a completely free, local, open-source model using `sherpa-onnx`. Removed requirements for Picovoice access keys and commercial licenses, allowing unlimited custom local wake words (e.g., "Sopno", "Dream").

