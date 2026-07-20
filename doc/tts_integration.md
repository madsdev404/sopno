# Offline TTS Integration for Sopno

## What we are doing
We replaced the original **Microsoft Edge TTS** (which required an internet connection) with an **offline neural speech synthesis** implementation based on **Coqui TTS** (the open‑source continuation of Mozilla‑TTS).  The new `speak_text()` function loads a multilingual model once, synthesises the assistant’s response to a temporary WAV file, and plays it back with `ffplay`.

## Why we made this change
| Reason | Details |
|--------|---------|
| **Offline‑only** | No network calls are needed; the assistant works behind firewalls or on isolated machines. |
| **Privacy** | Audio data never leaves the device, satisfying strict privacy requirements. |
| **High‑quality neural voice** | Coqui TTS provides natural‑sounding neural voices (much better than `espeak`‑based solutions). |
| **Multilingual support** | A single multilingual model can speak both English and Bangla, keeping the existing language‑switch logic intact. |
| **Future‑proof** | The same library can be used to fine‑tune or replace the model with a custom Bangla voice later. |

## How it works (implementation steps)
1. **Import** the library:
   ```python
   from TTS.api import TTS
   ```
2. **Lazy‑load a global TTS engine** the first time `speak_text()` is called, using a multilingual model (e.g., `tts_models/multilingual/multi-dataset/your_tts`).  The model is downloaded automatically (~200 MB) to `~/.local/share/tts/`.
3. **Detect Bangla characters** with a regular expression to preserve the existing language‑switch behaviour (the model itself already handles both languages).
4. **Synthesize** the text to `temp_speech.wav` via `tts.tts_to_file(...)`.
5. **Play** the file with `ffplay` (the same playback method used elsewhere in the project).
6. **Clean up** the temporary file after playback.

## Usage notes
* The first run will take a few seconds to download the model; subsequent runs are instantaneous.
* The code works on CPU only (`gpu=False`). If a GPU is available and you install the appropriate PyTorch build, you can set `gpu=True` for faster synthesis.
* To change the voice or language, replace the model name in the `TTS()` constructor with any model listed on the Coqui TTS model hub.

## Next steps for the project
* **Python version** – Coqui TTS currently supports Python 3.9‑3.11. Create a virtual environment with one of those versions before installing the `TTS` package.
* **Testing** – Run `python3 sopno.py` after installing the package and verify that the assistant speaks both English and Bangla without falling back to online services.
* **Optional** – If you later want an even higher‑quality Bangla‑only model, you can fine‑tune a custom model and point `model_name` to its path.

---
*Document created by Antigravity AI coding assistant to record the offline TTS integration.*
