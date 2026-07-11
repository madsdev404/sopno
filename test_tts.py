import pyttsx3

print("TTS initializing... Speaker test start.")
try:
    engine = pyttsx3.init()
    engine.say("Hello. Sopno assistant system is successfully configured.")
    engine.runAndWait()
    print("Speaker check completed successfully!")
except Exception as e:
    print(f"Error occurred: {e}")
    print("Tip: Linux system-e espeak install kora thaka lagbe (sudo apt install espeak).")
