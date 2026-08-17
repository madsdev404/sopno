"""
sopno/llm/client.py
━━━━━━━━━━━━━━━━━━━
Ollama LLM client wrapper.

Keeps replies fast for voice:
  - think=False disables Qwen3/R1 hidden reasoning (huge CPU win)
  - num_predict caps spoken reply length
  - timeout prevents the assistant from hanging forever
"""

from __future__ import annotations

from typing import Any, Generator, Optional

import ollama

from sopno.config.settings import settings

# Persistent client with httpx timeout — avoids hangs when Ollama is slow.
_client: Optional[ollama.Client] = None


def _get_client() -> ollama.Client:
    global _client
    if _client is None:
        _client = ollama.Client(timeout=settings.llm_timeout)
    return _client


def _chat_options() -> dict[str, Any]:
    return {
        "num_predict": settings.llm_num_predict,
        "num_ctx": settings.llm_num_ctx,
        "temperature": settings.llm_temperature,
    }


def chat(
    messages: list[dict],
    *,
    tools: Optional[list] = None,
    stream: bool = False,
):
    """
    Call Ollama chat with Sopno's speed-oriented defaults.
    """
    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "messages": messages,
        "stream": stream,
        "options": _chat_options(),
    }
    if tools is not None:
        kwargs["tools"] = tools
    # Top-level (not inside options) — required for Qwen3 / thinking models
    if not settings.llm_think:
        kwargs["think"] = False

    return _get_client().chat(**kwargs)


def stream_reply(messages: list[dict]) -> Generator[str, None, None]:
    """
    Stream a reply from the Ollama LLM.

    Args:
        messages: Full conversation history including the system prompt,
                  formatted as [{"role": "...", "content": "..."}, ...]

    Yields:
        str — each text chunk as it arrives from the model
    """
    stream = chat(messages, stream=True)
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
    response = chat(messages)
    msg = response["message"]
    content = msg["content"] if isinstance(msg, dict) else (msg.content or "")
    return str(content).strip()


def message_as_dict(msg) -> dict:
    """Normalize Ollama message objects to plain dicts for history/tool loops."""
    if isinstance(msg, dict):
        return msg
    data = {
        "role": getattr(msg, "role", "assistant"),
        "content": getattr(msg, "content", None) or "",
    }
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = tool_calls
    return data
