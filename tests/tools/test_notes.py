"""
tests/test_notes.py
━━━━━━━━━━━━━━━━━━
Notes knowledge base: confirmed write, overwrite confirmation, title
sanitising, listing, and keyword search.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools.builtins import notes as mod
from sopno.tools.builtins import files


class NotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "dir": getattr(settings, "notes_dir", ""),
            "roots": list(settings.file_allowed_write),
            "confirm": getattr(settings, "file_confirm_writes", True),
        }
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-notes-test-"))
        settings.file_allowed_write = [str(self.tmp)]
        settings.file_confirm_writes = True
        settings.notes_dir = str(self.tmp)

    def tearDown(self) -> None:
        settings.notes_dir = self._saved["dir"]
        settings.file_allowed_write = self._saved["roots"]
        settings.file_confirm_writes = self._saved["confirm"]

    def test_write_requires_title(self) -> None:
        self.assertIn("title", mod.note_write("", "body"))

    def test_write_requires_content(self) -> None:
        self.assertIn("empty", mod.note_write("Title", "  "))

    def test_write_confirmed(self) -> None:
        out = mod.note_write("Groceries", "Buy milk and eggs")
        self.assertIn("permission to save the note", out)
        pending = files.pending_action()
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("saved", result)
        target = self.tmp / "Groceries.md"
        self.assertTrue(target.is_file())
        self.assertIn("# Groceries", target.read_text(encoding="utf-8"))

    def test_title_sanitised(self) -> None:
        mod.note_write("A/B: notes!", "x")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        names = [p.name for p in self.tmp.glob("*.md")]
        self.assertTrue(any("/" not in n and "!" not in n for n in names))

    def test_overwrite_confirmed(self) -> None:
        target = self.tmp / "Same.md"
        target.write_text("# old\n", encoding="utf-8")
        out = mod.note_write("Same", "new content")
        self.assertIn("permission to overwrite", out)
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        self.assertIn("new content", target.read_text(encoding="utf-8"))

    def test_list_empty(self) -> None:
        self.assertIn("No notes", mod.note_list())

    def test_list_shows_notes(self) -> None:
        mod.note_write("Alpha", "content A")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        out = mod.note_list()
        self.assertIn("Alpha", out)
        self.assertIn("bytes", out)

    def test_search_matches(self) -> None:
        mod.note_write("Recipe", "add garlic and salt")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        out = mod.note_search("garlic")
        self.assertIn("Recipe", out)
        self.assertIn("garlic and salt", out)

    def test_search_no_match(self) -> None:
        mod.note_write("Recipe", "add garlic")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        self.assertIn("No notes match", mod.note_search("zebra"))

    def test_search_requires_query(self) -> None:
        self.assertIn("What should I search", mod.note_search("  "))


if __name__ == "__main__":
    unittest.main()
