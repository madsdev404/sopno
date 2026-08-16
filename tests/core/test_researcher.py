"""
tests/test_researcher.py
━━━━━━━━━━━━━━━━━━━━━━━
Automated unit tests for the Researcher (RAG) pipeline.
"""

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sopno.llm import researcher
from sopno.llm.researcher import (
    chunk_text,
    cosine_from_l2,
    embed_texts,
    normalize,
    research,
    ResearchIndex,
    _query_terms,
    _research_query,
    _summarize,
)


def _vec(fill: float, size: int = 768) -> list[float]:
    return normalize([fill] * size)


class TestChunking(unittest.TestCase):
    def test_short_text_single_chunk(self) -> None:
        self.assertEqual(chunk_text("Hello world."), ["Hello world."])

    def test_long_text_splits_into_chunks(self) -> None:
        text = ". ".join(f"Word number {i} here." for i in range(1, 120))
        chunks = chunk_text(text, max_chars=400, overlap=40)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 440 for c in chunks))

    def test_chunks_keep_all_content(self) -> None:
        text = ". ".join(f"s{i}" for i in range(1, 80)) + "."
        chunks = chunk_text(text, max_chars=100, overlap=10)
        joined = " ".join(chunks)
        self.assertIn("s1", joined)
        self.assertIn("s79", joined)


class TestVectorMath(unittest.TestCase):
    def test_normalize_returns_unit_vector(self) -> None:
        v = normalize([3.0, 4.0])
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=6)

    def test_cosine_from_l2(self) -> None:
        self.assertAlmostEqual(cosine_from_l2(0.0), 1.0)
        self.assertAlmostEqual(cosine_from_l2(math.sqrt(2.0)), 0.0, places=6)


class TestResearchQuery(unittest.TestCase):
    def test_subject_comes_first(self) -> None:
        self.assertEqual(_research_query("What is the latest version of Python?"), "python latest version")

    def test_function_words_do_not_lead(self) -> None:
        self.assertEqual(
            _research_query("Latest news about the cricket world cup"),
            "cricket latest news world cup",
        )

    def test_no_terms_falls_back(self) -> None:
        self.assertEqual(_research_query("???!!"), "???!!")

    def test_terms_extraction(self) -> None:
        self.assertEqual(_query_terms("What is Python?"), ["python"])


class TestResearchIndex(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.index = ResearchIndex(Path(self.tmp) / "mem.db")

    def tearDown(self) -> None:
        self.index.close()

    def test_add_and_search_within_run(self) -> None:
        self.index.add_chunks(1, [
            {"url": "https://a.com", "title": "A",
             "text": "Python is a high-level programming language.",
             "embedding": _vec(0.1)},
            {"url": "https://b.com", "title": "B",
             "text": "Dogs are loyal household pets.",
             "embedding": _vec(0.5)},
        ])
        results = self.index.search(1, _vec(0.1), question="python programming", k=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], "https://a.com")

    def test_search_isolated_by_run(self) -> None:
        self.index.add_chunks(1, [
            {"url": "https://a.com", "title": "A", "text": "alpha content", "embedding": _vec(0.1)},
        ])
        self.index.add_chunks(2, [
            {"url": "https://b.com", "title": "B", "text": "beta content", "embedding": _vec(0.9)},
        ])
        results = self.index.search(2, _vec(0.9), question="beta", k=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://b.com")

    def test_cached_text(self) -> None:
        self.index.add_chunks(1, [
            {"url": "https://x.com", "title": "X", "text": "hello page content", "embedding": _vec(0.1)},
        ])
        self.assertEqual(self.index.cached_text("https://x.com"), "hello page content")
        self.assertEqual(self.index.cached_text("https://missing.com"), "")

    def test_clear_removes_run(self) -> None:
        self.index.add_chunks(1, [
            {"url": "https://x.com", "title": "X", "text": "stuff", "embedding": _vec(0.1)},
        ])
        self.assertEqual(self.index.clear(1), 1)
        self.assertEqual(self.index.search(1, _vec(0.1), k=5), [])


class TestEmbedding(unittest.TestCase):
    @patch("sopno.llm.researcher.requests.post")
    def test_embed_texts_normalizes(self, mock_post) -> None:
        mock_post.return_value = MagicMock(
            json=lambda: {"embeddings": [[3.0, 4.0]]},
            raise_for_status=lambda: None,
        )
        out = embed_texts(["hello"])
        self.assertEqual(len(out), 1)
        norm = math.sqrt(sum(x * x for x in out[0]))
        self.assertAlmostEqual(norm, 1.0, places=6)

    @patch("sopno.llm.researcher.requests.post", side_effect=Exception("ollama down"))
    def test_embed_texts_unreachable(self, mock_post) -> None:
        with self.assertRaises(RuntimeError):
            embed_texts(["hello"])


class TestSummarize(unittest.TestCase):
    @patch("sopno.llm.researcher.requests.post", side_effect=Exception("down"))
    def test_summarize_degrades_gracefully(self, mock_post) -> None:
        out = _summarize("q?", [
            {"url": "https://a.com", "title": "A", "text": "Some content here."},
        ])
        self.assertIn("Summarization failed", out)
        self.assertIn("https://a.com", out)


class TestResearchPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self._old_memory_path = researcher.settings.memory_path
        researcher.settings.memory_path = Path(self.tmp) / "mem.db"

    def tearDown(self) -> None:
        researcher.settings.memory_path = self._old_memory_path

    @patch("sopno.llm.researcher._summarize")
    @patch("sopno.llm.researcher._fetch_pages")
    @patch("sopno.tools.builtins.web.search.web_search")
    @patch("sopno.llm.researcher.embed_texts")
    def test_pipeline_returns_summary(
        self, mock_embed, mock_search, mock_fetch, mock_summarize
    ) -> None:
        mock_search.return_value = [
            {"title": "A", "url": "https://a.com", "snippet": "s"},
            {"title": "B", "url": "https://b.com", "snippet": "s"},
        ]
        mock_fetch.return_value = [
            {"url": "https://a.com", "title": "A",
             "text": "Python is a high-level programming language. " * 200},
        ]
        mock_embed.side_effect = lambda texts: [_vec(0.1) for _ in texts]
        mock_summarize.return_value = "Final cited answer."

        result = research("What is Python?")
        self.assertEqual(result, "Final cited answer.")
        question, passages = mock_summarize.call_args[0]
        self.assertEqual(question, "What is Python?")
        self.assertGreater(len(passages), 0)

    @patch("sopno.tools.builtins.web.search.web_search", side_effect=Exception("net down"))
    def test_search_failure_message(self, mock_ws) -> None:
        self.assertTrue(research("anything").startswith("Research search failed"))

    def test_empty_question(self) -> None:
        self.assertEqual(research("   "), "Please provide a research question.")


if __name__ == "__main__":
    unittest.main()
