"""
sopno/core/context.py
━━━━━━━━━━━━━━━━━━━━━
Conversation history & memory management.

Manages the list of chat messages, triggers history compression when the
history gets too long, and appends language constraints dynamically before
sending prompts to the LLM.
"""

from sopno.config.settings import settings
from sopno.config.prompts import SYSTEM_PROMPT
from sopno.llm.summarizer import compress_history


class ConversationContext:
    """Manages the conversation state and history for the voice assistant."""

    def __init__(self):
        self._messages: list[dict[str, str]] = []
        self.current_language: str = "en"  # "en" or "bn"
        self.reset()

    def reset(self) -> None:
        """Reset the conversation history to the initial state."""
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def add_user_message(self, content: str) -> None:
        """Add a user message to the history and trigger summarization if necessary."""
        self._messages.append({"role": "user", "content": content})
        self._compress_if_needed()

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant response to the history."""
        self._messages.append({"role": "assistant", "content": content})

    def _compress_if_needed(self) -> None:
        """Trigger dynamic summarization if history length exceeds settings."""
        if len(self._messages) >= settings.max_history_length:
            self._messages = compress_history(self._messages)

    def get_messages_for_llm(self) -> list[dict[str, str]]:
        """
        Get the messages list with language constraints appended.
        This guides the LLM to reply in the correct language.
        """
        chat_messages = list(self._messages)
        if self.current_language == "bn":
            chat_messages.append({
                "role": "system",
                "content": "IMPORTANT: You MUST respond in Bangla (বাংলা) only."
            })
        else:
            chat_messages.append({
                "role": "system",
                "content": "IMPORTANT: You MUST respond in English only."
            })
        return chat_messages

    @property
    def raw_messages(self) -> list[dict[str, str]]:
        """Direct access to the underlying message history list."""
        return self._messages
