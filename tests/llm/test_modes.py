"""
tests/llm/test_modes.py
━━━━━━━━━━━━━━━━━━━━━━━━
Reasoning-mode resolution (doc/roadmap/thinking-modes.md §4/§5.1).
No Ollama involved — pure routing logic.
"""

import unittest

from sopno.llm import modes


class TestNormalize(unittest.TestCase):
    def test_valid_modes_pass_through(self) -> None:
        for name in modes.VALID:
            self.assertEqual(modes.normalize(name), name)

    def test_uppercase_and_whitespace(self) -> None:
        self.assertEqual(modes.normalize("  Quick "), modes.QUICK)
        self.assertEqual(modes.normalize("DEEP"), modes.DEEP)

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(modes.normalize("turbo"))
        self.assertIsNone(modes.normalize(""))
        self.assertIsNone(modes.normalize(None))


class TestSpec(unittest.TestCase):
    def test_quick_is_todays_budget(self) -> None:
        spec = modes.spec(modes.QUICK)
        self.assertFalse(spec["think"])
        self.assertEqual(spec["num_predict"], 120)
        self.assertEqual(spec["num_ctx"], 2048)
        self.assertEqual(spec["temperature"], 0.6)

    def test_thinking_has_think(self) -> None:
        self.assertTrue(modes.spec(modes.THINKING)["think"])
        self.assertGreater(modes.spec(modes.THINKING)["num_predict"], 120)

    def test_deep_is_biggest_budget(self) -> None:
        deep = modes.spec(modes.DEEP)
        self.assertTrue(deep["think"])
        think = modes.spec(modes.THINKING)
        self.assertGreater(deep["num_predict"], think["num_predict"])
        self.assertGreater(deep["num_ctx"], think["num_ctx"])

    def test_plan_is_separate_tier(self) -> None:
        self.assertTrue(modes.spec(modes.PLAN)["think"])

    def test_unknown_falls_back_to_quick(self) -> None:
        self.assertIs(modes.spec("turbo"), modes.MODES[modes.QUICK])


class TestResolve(unittest.TestCase):
    def test_concrete_mode_passes_through(self) -> None:
        self.assertIs(modes.resolve(modes.DEEP, "anything"), modes.MODES[modes.DEEP])
        self.assertIs(modes.resolve(modes.QUICK, "anything"), modes.MODES[modes.QUICK])

    def test_auto_routes_plan_hints_to_plan(self) -> None:
        for text in ("make a plan to refactor", "set up the project", "configure my editor"):
            self.assertIs(modes.resolve(modes.AUTO, text), modes.MODES[modes.PLAN])

    def test_auto_routes_deep_hints_to_deep(self) -> None:
        for text in (
            "deep research on X",
            "deep think about tradeoffs",
            "deep dive into the algorithm",
            "analyze in detail",
            "debug my code",
            "optimize the loop",
            "explain thoroughly",
        ):
            with self.subTest(text=text):
                self.assertIs(modes.resolve(modes.AUTO, text), modes.MODES[modes.DEEP])

    def test_deep_analyze_phrase_is_not_a_match(self) -> None:
        # The doc regex ends with \b after deep\s*(analy|…) — "deep analyze"
        # has no boundary after "analy", so it falls through to the word-count
        # tier (quick). Verbatim regex behavior, not a bug to paper over.
        self.assertIs(
            modes.resolve(modes.AUTO, "deep analyze the code"),
            modes.MODES[modes.QUICK],
        )

    def test_doc_verbatim_quirks_route_to_quick(self) -> None:
        # "research quantum computing" has no deep hint (doc only has
        # deep\s*(analy|research|…)) and is short → quick, not THINKING.
        self.assertIs(
            modes.resolve(modes.AUTO, "research quantum computing"),
            modes.MODES[modes.QUICK],
        )
        # "analyze in detail" must be literally contiguous.
        self.assertIs(
            modes.resolve(modes.AUTO, "analyze this in detail"),
            modes.MODES[modes.QUICK],
        )
        # The doc's instal?? typo never matches across the double l.
        self.assertIs(
            modes.resolve(modes.AUTO, "install ollama"),
            modes.MODES[modes.QUICK],
        )

    def test_auto_routes_short_greetings_to_quick(self) -> None:
        for text in ("hi", "good morning", "what time is it", "mute the volume"):
            self.assertIs(modes.resolve(modes.AUTO, text), modes.MODES[modes.QUICK])

    def test_auto_routes_long_questions_to_thinking(self) -> None:
        self.assertIs(
            modes.resolve(modes.AUTO, "why is the sky blue on a summer morning"),
            modes.MODES[modes.THINKING],
        )

    def test_auto_bangla_plan_hint(self) -> None:
        self.assertIs(
            modes.resolve(modes.AUTO, "একটা প্ল্যান করো"),
            modes.MODES[modes.PLAN],
        )

    def test_auto_bangla_deep_hint(self) -> None:
        # \b requires the space-separated form; bengali is not segmented so
        # "গভীরভাবে" (compounded) does NOT match the গভীর boundary.
        self.assertIs(
            modes.resolve(modes.AUTO, "গভীর ভাবো এটা"),
            modes.MODES[modes.DEEP],
        )

    def test_auto_bangla_compounded_deep_hint_routes_quick(self) -> None:
        self.assertIs(
            modes.resolve(modes.AUTO, "গভীরভাবে ভাবো এটা"),
            modes.MODES[modes.QUICK],
        )


if __name__ == "__main__":
    unittest.main()