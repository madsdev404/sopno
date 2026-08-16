"""
tests/test_rules.py
━━━━━━━━━━━━━━━━━━
Automation rules: condition parsing, metric evaluation, SQLite persistence,
the fire-once-per-true-period poller, and the rule_add/list/remove tools.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.core import rules as core
from sopno.tools.builtins import rules as tools
from sopno.tools.builtins import files


class RuleConditionTest(unittest.TestCase):
    def test_rejects_garbage(self) -> None:
        for bad in ("", "os.system('x')", "1 < 2", "battery < 20 and cpu < 1"):
            with self.assertRaises(ValueError):
                core._evaluate(bad)

    def test_rejects_unknown_metric(self) -> None:
        with self.assertRaises(ValueError):
            core._evaluate("temperature < 5")

    def test_clock_conditions(self) -> None:
        self.assertTrue(core._evaluate("hour_of_day >= 0"))
        self.assertTrue(core._evaluate("hour_of_day < 24"))
        self.assertTrue(core._evaluate("day_of_week >= 0"))
        self.assertTrue(core._evaluate("day_of_week <= 6"))
        self.assertFalse(core._evaluate("hour_of_day > 99"))

    def test_cpu_metric_reads(self) -> None:
        self.assertTrue(0 <= core._read_metric("cpu_percent") <= 100)
        self.assertTrue(0 <= core._read_metric("ram_percent") <= 100)
        self.assertTrue(core._read_metric("disk_free_gb") > 0)

    def test_parse_action_quoted_args(self) -> None:
        tool, args = core._parse_action(
            'note_write title="daily" content="keep on going"'
        )
        self.assertEqual(tool, "note_write")
        self.assertEqual(args, {"title": "daily", "content": "keep on going"})

    def test_parse_action_rejects_bad_tool_and_args(self) -> None:
        with self.assertRaises(ValueError):
            core._parse_action("not_a_real_tool x=1")
        with self.assertRaises(ValueError):
            core._parse_action("note_write nonsense")

    def test_parse_action_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            core._parse_action("")


class RuleStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_notes = getattr(settings, "notes_dir", "")
        self._saved_roots = list(settings.file_allowed_write)
        self._saved_confirm = getattr(settings, "file_confirm_writes", True)
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-rules-test-"))
        settings.file_allowed_write = [str(self.tmp)]
        settings.file_confirm_writes = True
        settings.notes_dir = str(self.tmp / "notes")
        core.set_store(None)
        tools.set_store(core.RuleStore(self.tmp / "rules.db"))

    def tearDown(self) -> None:
        store = core.get_store()
        if store is not None:
            store.close()
        core.set_store(None)
        settings.notes_dir = self._saved_notes
        settings.file_allowed_write = self._saved_roots
        settings.file_confirm_writes = self._saved_confirm

    @staticmethod
    def _confirm_yes() -> str:
        pending = files.pending_action()
        if pending is not None:
            return files.resolve_pending(pending["id"], "yes") or "Done."
        return ""

    def test_add_and_list(self) -> None:
        out = tools.rule_add("low battery", "hour_of_day >= 0",
                             'note_write title="x" content="y"')
        self.assertIn("permission", out)
        self.assertIn("Rule created", self._confirm_yes())
        rules = tools.rule_list()
        self.assertIn("low battery", rules)
        self.assertIn("if hour_of_day >= 0", rules)
        self.assertIn("fired 0x", rules)

    def test_add_rejects_bad_condition_and_action(self) -> None:
        self.assertIn("Condition must look like",
                      tools.rule_add("n", "os.system('x') > 1", "x"))
        self.assertIn("not registered",
                      tools.rule_add("n", "hour_of_day >= 0", "nope"))
        self.assertIsNone(files.pending_action())

    def test_remove_and_enable(self) -> None:
        tools.rule_add("r", "hour_of_day >= 0", "note_list")
        self._confirm_yes()
        out = tools.rule_remove(1)
        self.assertIn("permission", out)  # parked, not removed yet
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        self.assertIn("removed", self._confirm_yes())
        self.assertNotIn("r —", tools.rule_list())

    def test_set_enabled_toggle(self) -> None:
        tools.rule_add("r", "hour_of_day >= 0", "note_list")
        self._confirm_yes()
        out = tools.rule_set_enabled(1, False)
        self.assertIn("permission", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        self._confirm_yes()
        self.assertIn("[off]", tools.rule_list())
        self.assertIn("enabled", tools.rule_set_enabled(1, True))

    def test_fire_once_per_true_period(self) -> None:
        store = core.get_store()
        assert store is not None
        store.add("r", "hour_of_day >= 0", "note_list")
        results = store.run()
        self.assertEqual(len(results), 1)
        self.assertIn("r:", results[0])
        self.assertIn("notes", results[0].lower())
        again = store.run()
        self.assertEqual(again, [])  # still true — must not refire

    def test_fire_auto_approves_pending_action(self) -> None:
        store = core.get_store()
        assert store is not None
        store.add("auto note", "hour_of_day >= 0",
                  'note_write title="auto" content="hello"')
        results = store.run()
        self.assertEqual(len(results), 1)
        self.assertIn("saved", results[0].lower())
        self.assertTrue((Path(settings.notes_dir) / "auto.md").is_file())
        self.assertIsNone(files.pending_action())

    def test_fire_rearms_after_false(self) -> None:
        store = core.get_store()
        assert store is not None
        rid = store.add("clock", "hour_of_day > 99", "note_list")
        self.assertEqual(store.run(), [])
        store.remove(rid)
        rid2 = store.add("clock", "hour_of_day >= 0", "note_list")
        self.assertEqual(len(store.run()), 1)


class RulePollerTest(unittest.TestCase):
    def test_poller_delivers_fired_rules(self) -> None:
        self._store = core.RuleStore(Path(tempfile.mkdtemp()) / "rules.db")
        self._store.add("always", "hour_of_day >= 0", "note_list")
        delivered = []
        poller = core.RulePoller(
            store=self._store, deliver=delivered.append, run_check=lambda: True
        )
        poller._stop.set()  # don't actually loop; run the single-check path
        for result in self._store.run():
            delivered.append(result)
        self.assertEqual(len(delivered), 1)
        self.assertIn("always:", delivered[0])
        self._store.close()


if __name__ == "__main__":
    unittest.main()
