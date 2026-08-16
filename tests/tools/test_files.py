"""
tests/test_files.py
━━━━━━━━━━━━━━━━━━━
Automated unit tests for the permission-gated file/folder tools.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools.builtins import files
from sopno.tools.builtins.files import (
    copy_file,
    delete_file,
    edit_file,
    list_directory,
    move_file,
    pending_action,
    read_file,
    rename_file,
    resolve_pending,
    search_files,
    write_file,
)


class FilesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="sopno-files-test-")
        self.root = Path(self._td.name)
        self._saved = {
            "read": settings.file_allowed_read,
            "write": settings.file_allowed_write,
            "confirm": settings.file_confirm_writes,
            "enabled": settings.file_enabled,
            "max_size": settings.file_max_size_bytes,
            "output_chars": settings.file_output_chars,
        }
        settings.file_allowed_read = [str(self.root)]
        settings.file_allowed_write = [str(self.root)]
        settings.file_confirm_writes = False
        settings.file_enabled = True
        settings.file_max_size_bytes = 2_000_000
        settings.file_output_chars = 6000
        files._PENDING_ACTION = None

    def tearDown(self) -> None:
        files._PENDING_ACTION = None
        settings.file_allowed_read = self._saved["read"]
        settings.file_allowed_write = self._saved["write"]
        settings.file_confirm_writes = self._saved["confirm"]
        settings.file_enabled = self._saved["enabled"]
        settings.file_max_size_bytes = self._saved["max_size"]
        settings.file_output_chars = self._saved["output_chars"]
        self._td.cleanup()

    def make(self, name: str, content: str = "hello\nworld\n") -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p


# ── Authorization gate ───────────────────────────────────────────────────────

class TestAuthorization(FilesTestCase):
    def test_read_allowed_inside_root(self) -> None:
        p = self.make("notes.txt")
        self.assertIn("hello", read_file(str(p)))

    def test_read_refused_outside_root(self) -> None:
        out = read_file("/etc/hostname")
        self.assertIn("outside the allowed read roots", out)

    def test_write_refused_outside_root(self) -> None:
        out = write_file("/tmp/nope-sopno.txt", "x")
        self.assertIn("outside the allowed write roots", out)

    def test_disabled_master_switch(self) -> None:
        settings.file_enabled = False
        self.assertIn("File access is disabled", read_file(str(self.make("a.txt"))))
        self.assertIn("File access is disabled", write_file(str(self.root / "b.txt"), "x"))

    def test_blocks_env_files(self) -> None:
        self.assertIn("off-limits", read_file(str(self.make(".env", "SECRET=1"))))

    def test_blocks_git_and_ssh_dirs(self) -> None:
        self.assertIn("off-limits", read_file(str(self.make(".git/config", "x"))))
        self.assertIn("off-limits", read_file(str(self.make(".ssh/id_rsa", "x"))))

    def test_blocks_pem_and_key_glob(self) -> None:
        self.assertIn("off-limits", read_file(str(self.make("server.pem", "x"))))
        self.assertIn("off-limits", read_file(str(self.make("my.key", "x"))))

    def test_blocks_own_config_and_memory_db(self) -> None:
        self.assertIn("off-limits", read_file(str(self.make("config.json", "{}"))))
        real_db = settings.project_root / "sopno/memory/memory.db"
        self.assertIn("off-limits", read_file(str(real_db)))

    def test_empty_path(self) -> None:
        self.assertIn("Please provide a path", read_file(""))

    def test_relative_path_rejected(self) -> None:
        self.assertIn("absolute path", read_file("notes.txt"))


# ── read_file ────────────────────────────────────────────────────────────────

class TestReadFile(FilesTestCase):
    def test_reads_content(self) -> None:
        p = self.make("hello.txt", "line1\nline2\nline3\n")
        out = read_file(str(p))
        self.assertIn("line1", out)
        self.assertIn("line3", out)

    def test_head_and_tail_lines(self) -> None:
        p = self.make("n.txt", "\n".join(f"l{i}" for i in range(10)))
        out = read_file(str(p), lines=2)
        self.assertEqual(out, "l0\nl1")
        out = read_file(str(p), lines=-2)
        self.assertEqual(out, "l8\nl9")

    def test_missing_file(self) -> None:
        self.assertIn("No file", read_file(str(self.root / "missing.txt")))

    def test_directory_target(self) -> None:
        self.assertIn("is a folder", read_file(str(self.root)))

    def test_empty_file(self) -> None:
        p = self.make("empty.txt", "")
        self.assertIn("empty", read_file(str(p)))

    def test_size_cap(self) -> None:
        settings.file_max_size_bytes = 10
        p = self.make("big.txt", "x" * 100)
        self.assertIn("larger than", read_file(str(p)))

    def test_output_cap(self) -> None:
        settings.file_output_chars = 10
        p = self.make("long.txt", "a" * 100)
        out = read_file(str(p))
        self.assertIn("truncated", out)
        self.assertLessEqual(len(out), 40)


# ── write_file ───────────────────────────────────────────────────────────────

class TestWriteFile(FilesTestCase):
    def test_creates_new_file(self) -> None:
        target = self.root / "new.txt"
        out = write_file(str(target), "hello world")
        self.assertIn("Done", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello world")

    def test_creates_parent_dirs(self) -> None:
        target = self.root / "deep" / "nested" / "file.txt"
        write_file(str(target), "x")
        self.assertTrue(target.is_file())

    def test_overwrites_existing(self) -> None:
        target = self.make("doc.txt", "old content")
        out = write_file(str(target), "new content")
        self.assertIn("Done", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "new content")

    def test_identical_content_short_circuits(self) -> None:
        target = self.make("same.txt", "identical")
        out = write_file(str(target), "identical")
        self.assertIn("already contains", out)

    def test_size_cap(self) -> None:
        settings.file_max_size_bytes = 10
        self.assertIn("larger than", write_file(str(self.root / "big.txt"), "x" * 100))

    def test_outside_write_root(self) -> None:
        self.assertIn("outside the allowed write roots",
                      write_file("/tmp/evil.txt", "x"))


# ── edit_file ────────────────────────────────────────────────────────────────

class TestEditFile(FilesTestCase):
    def test_replaces_unique_string(self) -> None:
        target = self.make("code.txt", "alpha beta alpha gamma")
        out = edit_file(str(target), "beta", "BETA")
        self.assertIn("Done", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "alpha BETA alpha gamma")

    def test_not_found(self) -> None:
        target = self.make("code.txt", "nothing here")
        out = edit_file(str(target), "nope", "x")
        self.assertIn("was not found", out)

    def test_multiple_occurrences_refused(self) -> None:
        target = self.make("code.txt", "x x x")
        out = edit_file(str(target), "x", "y")
        self.assertIn("appears 3 times", out)

    def test_missing_file(self) -> None:
        self.assertIn("No file", edit_file(str(self.root / "no.txt"), "a", "b"))


# ── delete_file / rename_file ────────────────────────────────────────────────

class TestDeleteRename(FilesTestCase):
    def test_deletes_file(self) -> None:
        target = self.make("trash.txt")
        out = delete_file(str(target))
        self.assertIn("Done", out)
        self.assertFalse(target.exists())

    def test_delete_folder_refused(self) -> None:
        out = delete_file(str(self.root))
        self.assertIn("only delete individual files", out)

    def test_delete_missing(self) -> None:
        self.assertIn("No file", delete_file(str(self.root / "ghost.txt")))

    def test_rename_moves_file(self) -> None:
        src = self.make("old.txt", "data")
        dst = self.root / "sub" / "new.txt"
        out = rename_file(str(src), str(dst))
        self.assertIn("Done", out)
        self.assertFalse(src.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "data")

    def test_rename_refuses_overwrite(self) -> None:
        src = self.make("a.txt")
        dst = self.make("b.txt")
        out = rename_file(str(src), str(dst))
        self.assertIn("already exists", out)
        self.assertTrue(src.exists())

    def test_rename_missing_source(self) -> None:
        self.assertIn("No file", rename_file(str(self.root / "ghost.txt"),
                                             str(self.root / "x.txt")))

    def test_rename_folder_refused(self) -> None:
        folder = self.root / "folder"
        folder.mkdir()
        out = rename_file(str(folder), str(self.root / "folder2"))
        self.assertIn("only rename individual files", out)


# ── list_directory ───────────────────────────────────────────────────────────

class TestListDirectory(FilesTestCase):
    def test_lists_entries(self) -> None:
        self.make("a.txt")
        self.make("b.txt")
        (self.root / "subdir").mkdir()
        out = list_directory(str(self.root))
        self.assertIn("3 entries", out)
        self.assertIn("a.txt", out)
        self.assertIn("subdir", out)
        self.assertIn("dir", out)

    def test_empty_dir(self) -> None:
        self.assertIn("is empty", list_directory(str(self.root)))

    def test_file_target(self) -> None:
        p = self.make("f.txt")
        out = list_directory(str(p))
        self.assertIn("is a file", out)

    def test_defaults_to_project_root(self) -> None:
        settings.file_allowed_read = [str(self.root), str(settings.project_root)]
        out = list_directory("")
        self.assertIn("entries", out)


# ── Confirmation flow ────────────────────────────────────────────────────────

class TestConfirmation(FilesTestCase):
    def setUp(self) -> None:
        super().setUp()
        settings.file_confirm_writes = True

    def test_write_waits_for_confirmation(self) -> None:
        target = self.root / "pending.txt"
        out = write_file(str(target), "data")
        self.assertIn("permission", out)
        self.assertIn("pending action", out)
        self.assertFalse(target.exists())
        self.assertIsNotNone(pending_action())

    def test_confirm_yes_executes(self) -> None:
        target = self.root / "pending.txt"
        write_file(str(target), "data")
        pid = pending_action()["id"]
        result = resolve_pending(pid, "yes")
        self.assertIn("Done", result)
        self.assertTrue(target.exists())
        self.assertIsNone(pending_action())

    def test_confirm_no_cancels(self) -> None:
        target = self.root / "pending.txt"
        write_file(str(target), "data")
        pid = pending_action()["id"]
        result = resolve_pending(pid, "no")
        self.assertIn("Cancelled", result)
        self.assertFalse(target.exists())
        self.assertIsNone(pending_action())

    def test_edit_confirmation_runs(self) -> None:
        target = self.make("e.txt", "old text")
        out = edit_file(str(target), "old", "new")
        self.assertIn("permission", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "old text")
        pid = pending_action()["id"]
        resolve_pending(pid, "yes")
        self.assertEqual(target.read_text(encoding="utf-8"), "new text")

    def test_edit_rereads_before_execute(self) -> None:
        target = self.make("e.txt", "word word")
        edit_file(str(target), "word", "X")  # 2 occurrences → error, no pending
        self.assertIn("appears 2 times", edit_file(str(target), "word", "X"))
        self.assertIsNone(pending_action())

    def test_wrong_id_returns_none(self) -> None:
        write_file(str(self.root / "x.txt"), "data")
        self.assertIsNone(resolve_pending("bogus", "yes"))

    def test_delete_confirmation(self) -> None:
        target = self.make("gone.txt")
        out = delete_file(str(target))
        self.assertIn("permission", out)
        self.assertTrue(target.exists())
        pid = pending_action()["id"]
        resolve_pending(pid, "yes")
        self.assertFalse(target.exists())

    def test_rename_confirmation(self) -> None:
        src = self.make("from.txt")
        dst = self.root / "to.txt"
        rename_file(str(src), str(dst))
        pid = pending_action()["id"]
        resolve_pending(pid, "yes")
        self.assertFalse(src.exists())
        self.assertTrue(dst.exists())


# ── search_files ─────────────────────────────────────────────────────────────

class TestSearchFiles(FilesTestCase):
    def search(self, query: str, mode: str = "content") -> str:
        return search_files(query, path=str(self.root), mode=mode)

    def test_search_by_name(self) -> None:
        self.make("report.txt")
        self.make("notes/report.md")
        self.make("other.txt")
        out = self.search("report*", mode="name")
        self.assertIn("report.txt", out)
        self.assertIn("report.md", out)
        self.assertNotIn("other.txt", out)

    def test_search_name_substring(self) -> None:
        self.make("my-notes.txt")
        self.make("other.txt")
        out = self.search("notes", mode="name")
        self.assertIn("my-notes.txt", out)
        self.assertNotIn("other.txt", out)

    def test_search_by_content(self) -> None:
        self.make("a.txt", "alpha beta\nline two\n")
        self.make("b.txt", "nothing here\n")
        out = self.search("beta")
        self.assertIn("a.txt:1", out)
        self.assertIn("beta", out)
        self.assertNotIn("b.txt", out)

    def test_content_regex(self) -> None:
        self.make("a.txt", "Hello Sopno\n")
        out = self.search(r"sopno")
        self.assertIn("a.txt:1", out)

    def test_content_skips_binary_like(self) -> None:
        self.make("a.txt", "alpha beta\n")
        binp = self.root / "bin.dat"
        binp.write_bytes(b"\x00\x01alpha\x00beta\x00")
        out = self.search("alpha")
        self.assertIn("a.txt", out)
        self.assertNotIn("bin.dat", out)

    def test_skips_blocked_paths(self) -> None:
        self.make(".env", "SECRET")
        self.make("ok.txt", "SECRET")
        out = self.search("SECRET")
        self.assertNotIn(".env", out)
        self.assertIn("ok.txt", out)

    def test_empty_query(self) -> None:
        self.assertIn("something to search for", search_files("", path=str(self.root)))

    def test_bad_mode(self) -> None:
        self.assertIn("Unknown mode", search_files("x", path=str(self.root), mode="bogus"))

    def test_result_cap(self) -> None:
        settings.file_search_max_results = 2
        for i in range(5):
            self.make(f"hit{i}.txt", "needle\n")
        out = self.search("needle")
        self.assertIn("capped at 2", out)

    def test_outside_root_refused(self) -> None:
        out = search_files("x", path="/etc")
        self.assertIn("outside the allowed read roots", out)

    def test_no_matches(self) -> None:
        self.make("a.txt", "hello\n")
        self.assertIn("No matches", self.search("zebra"))

    def test_defaults_to_project_root(self) -> None:
        settings.file_allowed_read = [str(self.root), str(settings.project_root)]
        out = search_files("sopno")
        self.assertNotIn("No matches", out)


# ── copy_file / move_file ────────────────────────────────────────────────────

class TestCopyMove(FilesTestCase):
    def test_copy_file(self) -> None:
        src = self.make("src.txt", "data")
        dst = self.root / "sub" / "copy.txt"
        out = copy_file(str(src), str(dst))
        self.assertIn("Done", out)
        self.assertEqual(dst.read_text(encoding="utf-8"), "data")

    def test_copy_folder(self) -> None:
        folder = self.root / "tree"
        folder.mkdir()
        (folder / "inner.txt").write_text("hi", encoding="utf-8")
        dst = self.root / "tree-copy"
        copy_file(str(folder), str(dst))
        self.assertTrue((dst / "inner.txt").is_file())

    def test_copy_refuses_overwrite(self) -> None:
        src = self.make("a.txt")
        dst = self.make("b.txt")
        out = copy_file(str(src), str(dst))
        self.assertIn("already exists", out)
        self.assertEqual(dst.read_text(encoding="utf-8"), "hello\nworld\n")

    def test_copy_overwrite_true(self) -> None:
        src = self.make("a.txt", "new")
        dst = self.make("b.txt", "old")
        out = copy_file(str(src), str(dst), overwrite=True)
        self.assertIn("Done", out)
        self.assertEqual(dst.read_text(encoding="utf-8"), "new")

    def test_copy_same_path(self) -> None:
        src = self.make("a.txt")
        out = copy_file(str(src), str(src))
        self.assertIn("same path", out)

    def test_copy_confirmation(self) -> None:
        settings.file_confirm_writes = True
        src = self.make("a.txt")
        dst = self.root / "b.txt"
        out = copy_file(str(src), str(dst))
        self.assertIn("permission", out)
        self.assertFalse(dst.exists())
        pid = pending_action()["id"]
        resolve_pending(pid, "yes")
        self.assertTrue(dst.exists())

    def test_move_alias_of_rename(self) -> None:
        src = self.make("old.txt", "data")
        dst = self.root / "new.txt"
        out = move_file(str(src), str(dst))
        self.assertIn("Done", out)
        self.assertFalse(src.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "data")

    def test_move_refuses_overwrite(self) -> None:
        src = self.make("a.txt")
        dst = self.make("b.txt")
        out = move_file(str(src), str(dst))
        self.assertIn("already exists", out)
        self.assertTrue(src.exists())

    def test_copy_outside_write_root(self) -> None:
        src = self.make("a.txt")
        out = copy_file(str(src), "/tmp/evil.txt")
        self.assertIn("outside the allowed write roots", out)


if __name__ == "__main__":
    unittest.main()
