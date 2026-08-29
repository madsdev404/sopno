"""
sopno/llm/client.py
━━━━━━━━━━━━━━━━━━
Ollama LLM client wrapper.

Keeps replies fast for voice:
  - think=False disables Qwen3/R1 hidden reasoning (huge CPU win)
  - num_predict caps spoken reply length
  - timeout prevents the assistant from hanging forever

Reasoning modes (doc/roadmap/thinking-modes.md): every call may take a
concrete mode ("quick" | "thinking" | "deep" | "plan") via `modes.spec`.
Callers that do not pass a mode keep today's quick budget.
"""

from __future__ import annotations

from typing import Any, Generator, Optional, Tuple

import ollama

from sopno.config.settings import settings
from sopno.llm import modes

# Persistent client with httpx timeout — avoids hangs when Ollama is slow.
_client: Optional[ollama.Client] = None


def _get_client() -> ollama.Client:
    global _client
    if _client is None:
        _client = ollama.Client(timeout=settings.llm_timeout)
    return _client


def _chat_options(mode: str = "quick") -> dict[str, Any]:
    """Per-mode Ollama options, with settings.py overrides merged in."""
    spec = dict(modes.spec(mode))
    if mode == modes.THINKING:
        spec["num_predict"] = settings.llm_think_num_predict
    elif mode == modes.DEEP:
        spec["num_predict"] = settings.llm_deep_num_predict
        spec["num_ctx"] = settings.llm_deep_num_ctx
    return {
        "num_predict": spec["num_predict"],
        "num_ctx":     spec["num_ctx"],
        "temperature": spec["temperature"],
    }


def chat(
    messages: list[dict],
    *,
    tools: Optional[list] = None,
    stream: bool = False,
    mode: Optional[str] = None,
):
    """
    Call Ollama chat with Sopno's speed-oriented defaults.

    mode: reasoning mode. Defaults to settings.llm_mode; callers resolve
    `auto` first via `modes.resolve` (§5.3). Unresolved modes fall back to
    the quick budget so standalone tool loops stay instant.
    """
    resolved_mode = modes.normalize(mode) or getattr(settings, "llm_mode", modes.AUTO)
    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "messages": messages,
        "stream": stream,
        "options": _chat_options(resolved_mode),
    }
    if tools is not None:
        kwargs["tools"] = tools
    # Always explicit for hybrid models (Qwen3 needs the flag every request)
    kwargs["think"] = bool(modes.spec(resolved_mode)["think"])

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


def stream_mode(
    messages: list[dict], *, mode: str = "quick"
) -> Generator[Tuple[str, str], None, None]:
    """
    Stream a reply tagged by phase — the "Cursor feel" piece (design §5.3).

    Yields ("thinking", text) chunks first, then ("answer", text) chunks,
    so a UI can animate the reasoning phase before the final answer.
    """
    for chunk in chat(messages, mode=mode, stream=True):
        msg = chunk.get("message", {})
        if msg.get("thinking"):
            yield "thinking", msg["thinking"]
        elif msg.get("content"):
            yield "answer", msg["content"]


def single_reply(messages: list[dict], *, mode: str = "quick") -> str:
    """
    Get a complete (non-streamed) reply from the Ollama LLM.
    Useful for internal calls like summarization.

    Args:
        messages: Conversation history list
        mode: Reasoning mode override for this call

    Returns:
        str — the full response text
    """
    response = chat(messages, mode=mode)
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
    thinking = getattr(msg, "thinking", None)
    if thinking:
        data["thinking"] = thinking
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = tool_calls
    return data