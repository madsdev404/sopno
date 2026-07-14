import asyncio
import edge_tts
import subprocess
import os

async def main():
    print("Testing Edge TTS...")
    text = "Hello! Sopno assistant system is successfully configured with edge neural voice."
    voice = "en-US-AriaNeural"
    output_file = "test_edge.mp3"
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        print("Audio saved successfully. Playing now...")
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", output_file])
        print("Playback finished!")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(output_file):
            os.remove(output_file)

if __name__ == "__main__":
    asyncio.run(main())
