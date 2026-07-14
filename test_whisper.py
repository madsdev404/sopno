import speech_recognition as sr
import os
import tempfile
import time

print("STT initializing... Loading Faster Whisper model...")
try:
    from faster_whisper import WhisperModel
    # Load tiny model on CPU with int8 quantization for ultra-speed and lightweight RAM footprint
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    print("Faster Whisper model loaded successfully!")
    
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n>>> Calibrating background noise, stay silent for 1s...")
        r.adjust_for_ambient_noise(source, duration=1)
        print(">>> Say something clearly in English or Bangla (e.g., 'Hello Sopno' or 'কেমন আছো')...")
        audio = r.listen(source, timeout=5, phrase_time_limit=5)
        print(">>> Recording complete! Transcribing offline...")
        
    # Save the captured audio to a temporary WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
        temp_wav_path = temp_wav.name
        
    try:
        # Write WAV bytes
        with open(temp_wav_path, "wb") as f:
            f.write(audio.get_wav_data())
            
        start_time = time.time()
        # Transcribe WAV file
        segments, info = model.transcribe(temp_wav_path, beam_size=5)
        text = " ".join([segment.text for segment in segments]).strip()
        elapsed = time.time() - start_time
        
        print(f"\nResult: '{text}'")
        print(f"Detected Language: '{info.language}' (Probability: {info.language_probability:.2f})")
        print(f"Time Taken: {elapsed:.2f} seconds")
        print("\nOffline Whisper STT check completed successfully!")
        
    finally:
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)
            
except Exception as e:
    print(f"\nError occurred: {e}")
