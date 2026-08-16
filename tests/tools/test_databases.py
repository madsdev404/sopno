"""
tests/test_databases.py
━━━━━━━━━━━━━━━━━━━━━━
Database tools against a real SQLite file in a temp dir: read-only queries
run immediately, mutating statements park a pending action, schema listing,
and backup gating (write roots + overwrite confirmation).
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools.builtins import databases as mod
from sopno.tools.builtins import files


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob')")
        conn.commit()
    finally:
        conn.close()


class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "enabled": settings.database_enabled,
            "roots": list(settings.file_allowed_write),
            "read": list(getattr(settings, "file_allowed_read", [])),
            "confirm": getattr(settings, "file_confirm_writes", True),
        }
        settings.database_enabled = True
        settings.file_confirm_writes = True
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-db-test-"))
        settings.file_allowed_write = [str(self.tmp)]
        settings.file_allowed_read = [str(self.tmp)]
        self.db = self.tmp / "test.db"
        _make_db(self.db)

    def tearDown(self) -> None:
        settings.database_enabled = self._saved["enabled"]
        settings.file_allowed_write = self._saved["roots"]
        settings.file_allowed_read = self._saved["read"]
        settings.file_confirm_writes = self._saved["confirm"]

    def test_disabled(self) -> None:
        settings.database_enabled = False
        self.assertIn("database_enabled", mod.query_database(str(self.db), "SELECT 1"))

    def test_empty_sql(self) -> None:
        self.assertIn("Which SQL statement", mod.query_database(str(self.db), " "))

    def test_read_only_query(self) -> None:
        out = mod.query_database(str(self.db), "SELECT name FROM users")
        self.assertIn("name", out)
        self.assertIn("Alice", out)
        self.assertIn("Bob", out)
        self.assertIsNone(files.pending_action())

    def test_row_limit_applies(self) -> None:
        out = mod.query_database(str(self.db), "SELECT * FROM users")
        self.assertNotIn("showing first", out)  # only 2 rows

    def test_missing_file(self) -> None:
        out = mod.query_database(str(self.tmp / "nope.db"), "SELECT 1")
        self.assertIn("not found", out)

    def test_outside_read_roots(self) -> None:
        outside = Path(tempfile.mkdtemp()) / "x.db"
        _make_db(outside)
        out = mod.query_database(str(outside), "SELECT 1")
        self.assertIn("outside the allowed read roots", out)

    def test_mutating_statement_confirmed(self) -> None:
        out = mod.query_database(str(self.db), "DELETE FROM users")
        self.assertIn("permission to run", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Done", result)
        self.assertEqual(mod.query_database(str(self.db), "SELECT COUNT(*) FROM users"),
                         "COUNT(*)\n0")

    def test_mutating_denied(self) -> None:
        out = mod.query_database(str(self.db), "DELETE FROM users")
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "no")
        self.assertEqual(mod.query_database(str(self.db), "SELECT COUNT(*) FROM users"),
                         "COUNT(*)\n2")

    def test_multiline_mutation_rejected(self) -> None:
        out = mod.query_database(str(self.db), "INSERT INTO users (name)\nVALUES ('Eve')")
        self.assertIn("One statement per query", out)

    def test_bad_sql(self) -> None:
        out = mod.query_database(str(self.db), "SELECT FROM nowhere")
        self.assertIn("failed", out)

    def test_explain_schema(self) -> None:
        out = mod.explain_schema(str(self.db))
        self.assertIn("users", out)
        self.assertIn("id", out)
        self.assertIn("name", out)
        self.assertIn("2 rows", out)

    def test_backup_outside_write_roots(self) -> None:
        outside = Path(tempfile.mkdtemp()) / "backup.db"
        out = mod.backup_database(str(self.db), str(outside))
        self.assertIn("outside the allowed write roots", out)

    def test_backup_confirmed(self) -> None:
        out = mod.backup_database(str(self.db))
        self.assertIn("permission to back up", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Done", result)
        dest = self.tmp / "test.backup.db"
        self.assertTrue(dest.is_file())
        self.assertEqual(mod.query_database(str(dest), "SELECT COUNT(*) FROM users"),
                         "COUNT(*)\n2")

    def test_backup_overwrite_confirmed(self) -> None:
        dest = self.tmp / "test.backup.db"
        dest.write_bytes(b"old")
        out = mod.backup_database(str(self.db), str(dest))
        self.assertIn("permission to overwrite", out)
        pending = files.pending_action()
        files.resolve_pending(pending["id"], "yes")
        self.assertTrue(dest.is_file())
        self.assertNotEqual(dest.read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main()
