from gtts import gTTS
import subprocess
import os

print("TTS initializing... Speaker test start.")
try:
    text = "Hello! Sopno assistant system is successfully configured with natural voice."
    tts = gTTS(text=text, lang="en", slow=False)
    output_file = "test_out.mp3"
    tts.save(output_file)
    subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", output_file])
    if os.path.exists(output_file):
        os.remove(output_file)
    print("Speaker check completed successfully with Google TTS!")
except Exception as e:
    print(f"Error occurred: {e}")
    print("Tip: Make sure you have 'ffmpeg' installed on your Linux system (sudo apt install ffmpeg) and internet access.")
