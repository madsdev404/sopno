import sys
import re
import concurrent.futures
import speech_recognition as sr
from gtts import gTTS
import os
import subprocess
import ollama

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
MODEL_NAME = "gemma3:4b"

SYSTEM_PROMPT = """You are "Sopno" (Dream), a friendly, highly intelligent, and helpful AI voice assistant.
You are bilingual, fluent in both Bangla and English.
Guidelines:
1. Respond in the same language the user spoke. If they speak in Bangla or a mix (Benglish), respond in sweet, natural Bangla. If they speak in English, respond in clear English.
2. Keep your responses concise, engaging, and friendly (ideally 2-4 sentences). Avoid long bullet lists, complex tables, markdown code blocks, or heavy punctuation, as your responses will be read aloud.
3. If the user asks for code or long explanations, you can provide a brief summary first and ask if they want you to display the full code/text.
"""

# Maximum messages allowed in context before triggering summarization
# 1 system prompt + 6 complete conversation turns (12 messages) = 13
MAX_HISTORY_LENGTH = 13 

# ==============================================================================
# TTS HELPER FUNCTION
# ==============================================================================
def speak_text(text):
    """
    Intelligently detects the language of the response and vocalizes it
    using Google Text-to-Speech (gTTS) played via system ffplay.
    """
    # Detect if text contains any Bangla Unicode characters
    is_bn = bool(re.search(r'[\u0980-\u09FF]', text))
    target_lang = "bn" if is_bn else "en"
    
    temp_file = "temp_speech.mp3"
    try:
        # Generate speech
        tts = gTTS(text=text, lang=target_lang, slow=False)
        tts.save(temp_file)
        # Play the audio using system ffplay (fully silent and auto-exit)
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", temp_file])
    except Exception as e:
        print(f"\n[Warning: Speech synthesis/playback failed: {e}]")
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

# ==============================================================================
# STT BILINGUAL RECOGNIZER
# ==============================================================================
def recognize_bilingual(r, audio):
    """
    Recognizes the spoken utterance in parallel using Google Speech Recognition
    for both English and Bangla. Selects the most coherent transcription.
    """
    def recognize_lang(lang):
        try:
            return lang, r.recognize_google(audio, language=lang)
        except Exception as e:
            return lang, e

    # Execute English and Bangla recognition in parallel threads to minimize latency
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(recognize_lang, "bn-BD"),
            executor.submit(recognize_lang, "en-US")
        ]
        results = {}
        for future in concurrent.futures.as_completed(futures):
            lang, result = future.result()
            results[lang] = result
            
    bn_res = results.get("bn-BD")
    en_res = results.get("en-US")
    
    # If both failed, raise the first error
    if isinstance(bn_res, Exception) and isinstance(en_res, Exception):
        raise bn_res
        
    # If only one succeeded, return it
    if isinstance(bn_res, Exception):
        return en_res
    if isinstance(en_res, Exception):
        return bn_res
        
    # If both succeeded, check for Bangla characters to decide
    # If Bangla result contains actual Bangla letters, the user likely spoke Bangla
    bn_char_count = len(re.findall(r'[\u0980-\u09FF]', bn_res))
    if bn_char_count > 0:
        return bn_res
    else:
        return en_res

# ==============================================================================
# CONVERSATION MEMORY SUMMARIZATION
# ==============================================================================
def summarize_history(messages):
    """
    Summarizes older conversation history using Gemma-3 to prevent context bloat,
    while preserving the main system prompt and the last 2 conversation turns.
    """
    print("\n[System: Compressing older conversation history to save memory...]")
    
    # Keep the system prompt (idx 0) and the last 4 messages (2 turns) untouched
    preserved_system = messages[0]
    history_to_summarize = messages[1:-4]
    preserved_recent = messages[-4:]
    
    # Format the history to be summarized
    chat_text = ""
    for msg in history_to_summarize:
        role = "User" if msg["role"] == "user" else "Sopno"
        chat_text += f"{role}: {msg['content']}\n"
        
    summary_prompt = (
        "Summarize the following conversation history in 2-3 concise sentences. "
        "Keep key facts, user preferences, or topics discussed so we can preserve context:\n\n"
        f"{chat_text}"
    )
    
    try:
        # Call Ollama for quick summarization
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": summary_prompt}]
        )
        summary = response['message']['content'].strip()
        
        # Rebuild the message list with system prompt, summary context, and recent messages
        new_messages = [
            preserved_system,
            {"role": "system", "content": f"Summary of previous conversation context:\n{summary}"}
        ]
        new_messages.extend(preserved_recent)
        
        print("[System: Memory compressed successfully!]")
        return new_messages
    except Exception as e:
        print(f"[Warning: Memory compression failed ({e}). Keeping full history.]")
        return messages

# ==============================================================================
# MAIN VOICE ASSISTANT LOOP
# ==============================================================================
def main():
    print("=" * 60)
    print("           SOPNO (DREAM) VOICE ASSISTANT          ")
    print("=" * 60)
    print(f"Status:   Initializing Speech engines...")
        
    r = sr.Recognizer()
    
    print(f"Model:    {MODEL_NAME}")
    print(f"Language: Bilingual (English / Bangla)")
    print(f"Memory:   Dynamic Summarization enabled")
    print(f"Control:  Push-to-Talk (Press Enter to speak, type 'exit' to quit)")
    print("=" * 60)
    
    # Pre-adjust for ambient noise once at startup
    try:
        with sr.Microphone() as source:
            print("Adjusting microphone for background noise, please stand by...")
            r.adjust_for_ambient_noise(source, duration=1.5)
            print("Microphone adjusted successfully!\n")
    except Exception as e:
        print(f"Error accessing microphone: {e}")
        print("Please verify your microphone connection and PyAudio status.")
        sys.exit(1)
        
    # Initial greeting
    welcome_text = "Hello! Sopno voice assistant is ready. Press Enter to start speaking."
    print(f"Sopno: {welcome_text}")
    speak_text(welcome_text)
    
    # Initialize messages history with system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    while True:
        try:
            print("\n" + "-" * 40)
            user_input = input(">>> [Press Enter to speak, or type 'exit' to quit]: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'exit()']:
                farewell = "Goodbye! Have a great day."
                print(f"\nSopno: {farewell}")
                speak_text(farewell)
                break
                
            # Perform Voice Input capturing
            with sr.Microphone() as source:
                print("Listening... (Speak now)")
                try:
                    # Capture audio with robust timeouts to prevent freezing
                    audio = r.listen(source, timeout=6, phrase_time_limit=10)
                    print("Processing speech...")
                except sr.WaitTimeoutError:
                    print("Listening timed out. No speech detected. Please press Enter and try again.")
                    continue
                    
            # Recognize text using bilingual parallel recognition
            try:
                text = recognize_bilingual(r, audio)
                print(f"You said: {text}")
            except sr.UnknownValueError:
                err_text = "Sorry, I couldn't understand that. Please speak clearly."
                print(f"Sopno: {err_text}")
                speak_text(err_text)
                continue
            except sr.RequestError as e:
                err_text = "I encountered an issue connecting to the speech service."
                print(f"Sopno: {err_text} ({e})")
                speak_text(err_text)
                continue
                
            # Append user utterance to conversation history
            messages.append({"role": "user", "content": text})
            
            # Check context length and compress older context if needed
            if len(messages) >= MAX_HISTORY_LENGTH:
                messages = summarize_history(messages)
                
            # Get response from Gemma-3 via Ollama (Streaming response)
            print("\nSopno: ", end="", flush=True)
            try:
                stream = ollama.chat(
                    model=MODEL_NAME,
                    messages=messages,
                    stream=True
                )
                
                full_response = ""
                for chunk in stream:
                    chunk_text = chunk['message']['content']
                    print(chunk_text, end="", flush=True)
                    full_response += chunk_text
                print() # Newline after streaming complete
                
            except Exception as e:
                print(f"\nError communicating with Ollama: {e}")
                speak_text("Sorry, I had trouble processing that with the AI model.")
                # Rollback last user input if it failed to process
                messages.pop()
                continue
                
            # Speak the complete response
            speak_text(full_response)
            
            # Save the assistant's reply to the message history
            messages.append({"role": "assistant", "content": full_response})
            
        except KeyboardInterrupt:
            print("\nExiting voice assistant. Goodbye!")
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            break

if __name__ == "__main__":
    main()
