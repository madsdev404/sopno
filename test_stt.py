import speech_recognition as sr

print("STT initializing... Microphone test start.")
r = sr.Recognizer()

try:
    with sr.Microphone() as source:
        print("\n>>> System noise adjust korchi, 1 second nirbof thakun...")
        r.adjust_for_ambient_noise(source, duration=1)
        print(">>> Ekhon microphone-e sposto vabe English-e kichu bolun (e.g. 'Hello computer')...")
        audio = r.listen(source, timeout=5, phrase_time_limit=5)
        print(">>> Recording complete! Speech processing cholche...")

    # Google Free Speech API use kore test korchi
    text = r.recognize_google(audio)
    print(f"\nResult: You said: '{text}'")
    print("\nMicrophone and STT check completed successfully!")

except sr.UnknownValueError:
    print("\nError: Audio thikmoto bujha jayni. Micer kache sposto kore bolun.")
except sr.RequestError as e:
    print(f"\nError: API network problem; {e}")
except Exception as e:
    print(f"\nError occurred: {e}")
    print("Tip: PyAudio/Microphone input connection active ache kina check korun.")
