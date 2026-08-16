"""
tests/test_memory.py
━━━━━━━━━━━━━━━━━━━━
Automated unit tests for the SQLite long-term memory store and
the rule-based memory intent parser in assistant.py.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.memory.store import MemoryStore
from sopno.core.context import ConversationContext
from sopno.core.assistant import parse_memory_intent


def _temp_db() -> str:
    """Return a path to a fresh temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    return path


class MemoryStoreTestBase(unittest.TestCase):
    """Base with the semantic (embedding) layer off — pure FTS5 behavior."""

    def setUp(self) -> None:
        self._saved_semantic = settings.semantic_memory_enabled
        settings.semantic_memory_enabled = False
        self._path = _temp_db()
        self.store = MemoryStore(db_path=self._path)

    def tearDown(self) -> None:
        self.store.close()
        settings.semantic_memory_enabled = self._saved_semantic


class TestMemoryStore(MemoryStoreTestBase):

    def test_remember_and_recall(self) -> None:
        """remember inserts a row; recall finds it by keyword."""
        self.store.remember("My laptop is called Athena")
        results = self.store.recall("laptop")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "My laptop is called Athena")
        self.assertEqual(self.store.stats()["total"], 1)

    def test_remember_dedupes_exact_content(self) -> None:
        """Re-remembering the same fact updates instead of duplicating."""
        first = self.store.remember("I prefer dark theme")
        second = self.store.remember("I prefer dark theme")
        self.assertEqual(first, second)
        self.assertEqual(self.store.stats()["total"], 1)

    def test_recall_bumps_usage(self) -> None:
        """recall() increments use_count for the returned memory."""
        self.store.remember("My laptop is called Athena")
        self.store.recall("laptop")
        row = self.store.all()[0]
        self.assertEqual(row["use_count"], 1)

    def test_forget_by_text(self) -> None:
        """forget(text) soft-deletes the matching memory."""
        self.store.remember("My laptop is called Athena")
        self.assertTrue(self.store.forget(text="Athena"))
        self.assertEqual(self.store.stats()["total"], 0)
        self.assertEqual(len(self.store.recall("laptop")), 0)

    def test_forget_unknown_returns_false(self) -> None:
        """forget() returns False when nothing matches."""
        self.store.remember("I prefer dark theme")
        self.assertFalse(self.store.forget(text="pink unicorn"))

    def test_forget_by_id(self) -> None:
        """forget(memory_id) soft-deletes exactly that row."""
        mem_id = self.store.remember("Buy milk on Sunday")
        self.assertTrue(self.store.forget(memory_id=mem_id))
        self.assertEqual(self.store.stats()["total"], 0)

    def test_wipe(self) -> None:
        """wipe() clears every active memory and returns the count."""
        self.store.remember("A")
        self.store.remember("B")
        self.store.remember("C")
        self.assertEqual(self.store.wipe(), 3)
        self.assertEqual(self.store.stats()["total"], 0)

    def test_recall_categories_filter(self) -> None:
        """recall(categories=[...]) only returns matching categories."""
        self.store.remember("My laptop is Athena", category="preference")
        self.store.remember("Flask is a Python framework", category="fact")
        results = self.store.recall("python", categories=["fact"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "Flask is a Python framework")

    def test_importance_ordering(self) -> None:
        """Higher-importance memories sort first."""
        self.store.remember("minor fact", importance=1)
        self.store.remember("critical fact", importance=3)
        rows = self.store.all()
        self.assertEqual(rows[0]["content"], "critical fact")

    def test_bangla_round_trip(self) -> None:
        """Bangla (Unicode) content stores and searches correctly."""
        self.store.remember("আমার ল্যাপটপের নাম অ্যাথেনা")
        results = self.store.recall("ল্যাপটপ")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"], "আমার ল্যাপটপের নাম অ্যাথেনা")

    def test_fts_syncs_on_update(self) -> None:
        """Updating content keeps the FTS index in sync (triggers)."""
        self.store.remember("My favorite color is blue")
        self.store.remember("My favorite color is blue", importance=3)
        self.assertEqual(len(self.store.recall("blue")), 1)
        self.assertEqual(len(self.store.recall("red")), 0)


class TestMemoryIntentParser(unittest.TestCase):
    """Verifies English + Bangla memory command detection."""

    def test_remember_english(self) -> None:
        self.assertEqual(
            parse_memory_intent("remember that my laptop is called Athena"),
            ("remember", "my laptop is called Athena"),
        )
        self.assertEqual(
            parse_memory_intent("remember my birthday is in May"),
            ("remember", "my birthday is in May"),
        )
        self.assertEqual(
            parse_memory_intent("don't forget my name is Sobhan"),
            ("remember", "my name is Sobhan"),
        )

    def test_remember_bangla(self) -> None:
        self.assertEqual(
            parse_memory_intent("মনে রাখো আমার ল্যাপটপের নাম অ্যাথেনা"),
            ("remember", "আমার ল্যাপটপের নাম অ্যাথেনা"),
        )
        self.assertEqual(
            parse_memory_intent("ভুলো না যে আজ রাতে মিটিং আছে"),
            ("remember", "আজ রাতে মিটিং আছে"),
        )

    def test_forget_english(self) -> None:
        self.assertEqual(
            parse_memory_intent("forget my laptop name"),
            ("forget", "my laptop name"),
        )
        self.assertEqual(
            parse_memory_intent("forget about the meeting"),
            ("forget", "the meeting"),
        )

    def test_forget_bangla(self) -> None:
        self.assertEqual(
            parse_memory_intent("ভুলে যাও আমার ল্যাপটপের নাম"),
            ("forget", "আমার ল্যাপটপের নাম"),
        )

    def test_forget_everything(self) -> None:
        self.assertEqual(
            parse_memory_intent("forget everything"),
            ("forget_all", ""),
        )
        self.assertEqual(
            parse_memory_intent("সব ভুলে যাও"),
            ("forget_all", ""),
        )

    def test_recall_english(self) -> None:
        self.assertEqual(
            parse_memory_intent("what do you remember"),
            ("recall", ""),
        )
        self.assertEqual(
            parse_memory_intent("what do you remember about flask"),
            ("recall", "flask"),
        )

    def test_recall_bangla(self) -> None:
        self.assertEqual(
            parse_memory_intent("কী মনে আছে"),
            ("recall", ""),
        )
        self.assertEqual(
            parse_memory_intent("আমার সম্পর্কে কী মনে আছে"),
            ("recall", "আমার"),
        )

    def test_non_memory_returns_none(self) -> None:
        """Ordinary chat must NOT be treated as a memory command."""
        self.assertIsNone(parse_memory_intent("what time is it"))
        self.assertIsNone(parse_memory_intent("open chrome"))
        self.assertIsNone(parse_memory_intent("tell me a joke"))
        self.assertIsNone(parse_memory_intent(""))
        self.assertIsNone(parse_memory_intent(None))


class TestMemoryContextInjection(unittest.TestCase):
    """Verifies [Memories] block injection into the LLM prompt."""

    def setUp(self) -> None:
        self._saved_semantic = settings.semantic_memory_enabled
        settings.semantic_memory_enabled = False
        self._path = _temp_db()
        self.store = MemoryStore(db_path=self._path)
        self.ctx = ConversationContext()
        self.ctx.memory_store = self.store

    def tearDown(self) -> None:
        self.store.close()
        settings.semantic_memory_enabled = self._saved_semantic

    def test_no_store_means_no_block(self) -> None:
        """Without a store, the prompt is unchanged."""
        plain = ConversationContext()
        messages = plain.get_messages_for_llm()
        self.assertEqual(len(messages), 2)  # system + language constraint

    def test_memories_injected_after_system(self) -> None:
        """Memories appear as a system block right after the system prompt."""
        self.store.remember("My laptop is called Athena")
        messages = self.ctx.get_messages_for_llm()
        self.assertEqual(messages[1]["role"], "system")
        self.assertIn("Athena", messages[1]["content"])
        self.assertIn("Memories", messages[1]["content"])

    def test_token_budget_respected(self) -> None:
        """Long memories are trimmed to the memory_max_tokens budget."""
        for i in range(20):
            self.store.remember(f"This is memory entry number {i} with lots of words")
        self.store.remember("My laptop is called Athena")
        messages = self.ctx.get_messages_for_llm()
        block = next(
            m["content"] for m in messages if m["role"] == "system" and "Memories" in m["content"]
        )
        # 400-token budget ≈ 1600 chars
        self.assertLessEqual(len(block), 1600)


if __name__ == "__main__":
    unittest.main()
