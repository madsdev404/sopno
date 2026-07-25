"""
sopno/llm/summarizer.py
━━━━━━━━━━━━━━━━━━━━━━━
Conversation history compressor.

When the message history grows too long (> settings.max_history_length),
this module summarizes the older portion using the LLM itself, keeping
the context window lean without losing important information.

Usage:
    from sopno.llm.summarizer import compress_history
    messages = compress_history(messages)
"""

from sopno.config.settings import settings
from sopno.config.prompts import SUMMARIZE_PROMPT
from sopno.llm.client import single_reply


def compress_history(messages: list[dict]) -> list[dict]:
    """
    Summarize older conversation turns to reduce context length.

    Strategy:
      - Always keep: messages[0] (system prompt) + last 4 messages (2 full turns)
      - Summarize: everything in between using the LLM
      - Inject: the summary as a single system message after the system prompt

    Args:
        messages: Full current conversation history

    Returns:
        Compressed message list with summary injected
    """
    if len(messages) < settings.max_history_length:
        return messages  # nothing to compress yet

    print("\n[Memory] Compressing older conversation history…")

    system_prompt   = messages[0]          # always preserved
    to_summarize    = messages[1:-4]       # older turns
    recent_turns    = messages[-4:]        # last 2 complete turns, always preserved

    # Build a readable text block from the turns to summarize
    chat_text = ""
    for msg in to_summarize:
        speaker = "User" if msg["role"] == "user" else "Sopno"
        chat_text += f"{speaker}: {msg['content']}\n"

    prompt_text = f"{SUMMARIZE_PROMPT}\n\n{chat_text}"

    try:
        summary = single_reply([{"role": "user", "content": prompt_text}])

        compressed = [
            system_prompt,
            {"role": "system", "content": f"[Summary of earlier conversation]\n{summary}"},
            *recent_turns,
        ]
        print("[Memory] History compressed successfully.")
        return compressed

    except Exception as e:
        print(f"[Memory] WARNING: Compression failed ({e}). Keeping full history.")
        return messages
