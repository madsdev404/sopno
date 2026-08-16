"""Semantic memory: vector recall layered on top of FTS5.

The embedding function (``sopno.memory.semantic.embed_texts``, normally an
Ollama call) is patched with a tiny deterministic fake so tests run offline.
"""

import tempfile
import unittest
from unittest import mock

from sopno.config.settings import settings
from sopno.memory import semantic
from sopno.memory.store import MemoryStore

EMBED_DIM = 768


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic 768-d unit vectors for a handful of "concepts"."""
    out = []
    for t in texts:
        v = [0.0] * EMBED_DIM
        low = t.lower()
        if any(w in low for w in ("fox", "canine", "animal")):
            v[0] = 1.0
        if any(w in low for w in ("laptop", "athena", "computer")):
            v[1] = 1.0
        if "garden" in low:
            v[2] = 1.0
        if "unknown" in low:
            v[5] = 1.0
        out.append(v)
    return out


def _temp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    return path


class SemanticMemoryTestBase(unittest.TestCase):
    """Creates a store with the fake embedding active."""

    def setUp(self) -> None:
        self._saved_enabled = settings.semantic_memory_enabled
        settings.semantic_memory_enabled = True
        self._patcher = mock.patch(
            "sopno.memory.semantic.embed_texts", side_effect=_fake_embed
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self._path = _temp_db()
        self.store = MemoryStore(db_path=self._path)

    def tearDown(self) -> None:
        self.store.close()
        settings.semantic_memory_enabled = self._saved_enabled


class TestSemanticLayerSetup(SemanticMemoryTestBase):
    def test_vec_table_created_when_enabled(self) -> None:
        self.assertTrue(semantic.available(self.store._conn))

    def test_vector_stored_on_remember(self) -> None:
        mid = self.store.remember("my laptop is called Athena")
        row = self.store._conn.execute(
            "SELECT rowid FROM memory_vectors WHERE rowid = ?", (mid,)
        ).fetchone()
        self.assertIsNotNone(row)

    def test_zero_vector_not_stored(self) -> None:
        mid = self.store.remember("nothing meaningful here")
        count = self.store._conn.execute(
            "SELECT COUNT(*) AS n FROM memory_vectors WHERE rowid = ?", (mid,)
        ).fetchone()["n"]
        self.assertEqual(count, 0)


class TestSemanticRecall(SemanticMemoryTestBase):
    def test_finds_memory_by_meaning_when_keywords_miss(self) -> None:
        self.store.remember("the quick brown fox jumped")
        self.store.remember("my laptop is called Athena")
        results = self.store.recall("animal friend")
        self.assertEqual([r["content"] for r in results], ["the quick brown fox jumped"])

    def test_multiple_semantic_hits(self) -> None:
        self.store.remember("the quick brown fox jumped")
        self.store.remember("a second fox lives near the garden")
        self.store.remember("my laptop is called Athena")
        results = self.store.recall("canine")
        self.assertEqual(len(results), 2)
        self.assertTrue(all("fox" in r["content"] for r in results))

    def test_orthogonal_query_is_excluded(self) -> None:
        self.store.remember("the quick brown fox jumped")
        self.store.remember("my laptop is called Athena")
        results = self.store.recall("unknown topic")
        self.assertEqual(results, [])

    def test_keyword_matches_stay_first_and_dedupe(self) -> None:
        self.store.remember("the quick brown fox jumped")
        self.store.remember("my laptop is called Athena")
        results = self.store.recall("laptop")
        self.assertEqual([r["content"] for r in results], ["my laptop is called Athena"])
        self.assertEqual(len(results), 1)

    def test_semantic_fills_remaining_slots_after_keywords(self) -> None:
        self.store.remember("the quick brown fox jumped", importance=3)
        self.store.remember("meeting with the fox tomorrow")
        self.store.remember("the brown animal runs fast")
        results = self.store.recall("fox", limit=3)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["content"], "the quick brown fox jumped")
        self.assertTrue("the brown animal runs fast" in [r["content"] for r in results])

    def test_category_filter_applies_to_semantic(self) -> None:
        self.store.remember("the quick brown fox jumped", category="fact")
        self.store.remember("my laptop is called Athena", category="fact")
        self.store.remember("I need to buy a new computer", category="task")
        results = self.store.recall("animal", categories=["task"])
        self.assertEqual(results, [])

    def test_semantic_limit_caps_results(self) -> None:
        for i in range(6):
            self.store.remember(f"fox sighting number {i}")
        results = self.store.recall("canine", limit=2)
        self.assertLessEqual(len(results), 2)

    def test_recall_bumps_usage_via_semantic_hits(self) -> None:
        mid = self.store.remember("my laptop is called Athena")
        self.store.recall("computer")
        row = self.store._conn.execute(
            "SELECT use_count FROM memories WHERE id = ?", (mid,)
        ).fetchone()
        self.assertGreaterEqual(row["use_count"], 1)


class TestSemanticDegradation(unittest.TestCase):
    def test_embedding_failure_degrades_to_fts_only(self) -> None:
        with mock.patch(
            "sopno.memory.semantic.embed_texts",
            side_effect=RuntimeError("ollama down"),
        ):
            store = MemoryStore(db_path=_temp_db())
            try:
                mid = store.remember("my laptop is called Athena")
                self.assertGreater(mid, 0)
                self.assertEqual(store.recall("computer"), [])
                self.assertEqual(store.recall("laptop")[0]["content"], "my laptop is called Athena")
            finally:
                store.close()

    def test_disabled_skips_vectors_and_uses_keywords(self) -> None:
        saved = settings.semantic_memory_enabled
        settings.semantic_memory_enabled = False
        try:
            with mock.patch(
                "sopno.memory.semantic.embed_texts", side_effect=_fake_embed
            ):
                store = MemoryStore(db_path=_temp_db())
                try:
                    self.assertFalse(store._vec_ok)
                    self.assertFalse(semantic.available(store._conn))
                    mid = store.remember("my laptop is called Athena")
                    self.assertGreater(mid, 0)
                    results = store.recall("laptop")
                    self.assertEqual(
                        [r["content"] for r in results], ["my laptop is called Athena"]
                    )
                finally:
                    store.close()
        finally:
            settings.semantic_memory_enabled = saved


class TestSemanticRecallLimitSetting(unittest.TestCase):
    def test_recall_limit_read_from_settings(self) -> None:
        saved = settings.semantic_recall_limit
        try:
            settings.semantic_recall_limit = 2
            self.assertEqual(semantic.recall_limit(), 2)
        finally:
            settings.semantic_recall_limit = saved


if __name__ == "__main__":
    unittest.main()
