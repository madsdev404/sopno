"""
sopno/llm/client.py
━━━━━━━━━━━━━━━━━━━
Ollama LLM client wrapper.

Sends a message history to the local Ollama model and streams the reply
back token-by-token so the UI can display text in real time.

Usage:
    from sopno.llm.client import stream_reply
    for chunk in stream_reply(messages):
        print(chunk, end="", flush=True)
"""

from typing import Generator

import ollama

from sopno.config.settings import settings


def stream_reply(messages: list[dict]) -> Generator[str, None, None]:
    """
    Stream a reply from the Ollama LLM.

    Args:
        messages: Full conversation history including the system prompt,
                  formatted as [{"role": "...", "content": "..."}, ...]

    Yields:
        str — each text chunk as it arrives from the model
    """
    stream = ollama.chat(
        model=settings.model_name,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        yield chunk["message"]["content"]


def single_reply(messages: list[dict]) -> str:
    """
    Get a complete (non-streamed) reply from the Ollama LLM.
    Useful for internal calls like summarization.

    Args:
        messages: Conversation history list

    Returns:
        str — the full response text
    """
    response = ollama.chat(
        model=settings.model_name,
        messages=messages,
    )
    return response["message"]["content"].strip()
