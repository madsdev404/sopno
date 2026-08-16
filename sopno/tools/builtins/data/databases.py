"""
sopno/tools/builtins/data/databases.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Database tools — read-only SQLite first.

SQLite is supported via a file path; other engines (Postgres/MySQL/Mongo)
answer with a friendly "not supported yet" note. Reads (SELECT/PRAGMA/EXPLAIN)
run immediately; any mutating statement parks a pending-action Yes/No gate.
Queries respect the file read-roots and the blocked-paths list.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from sopno.config.settings import settings
from sopno.tools.builtins.files import files as files

_READ_ONLY = ("select", "pragma", "explain", "with")
_ROW_LIMIT = 30
_CELL_LIMIT = 60


def _enabled() -> str:
    if not getattr(settings, "database_enabled", True):
        return "Database tools are disabled (database_enabled = false in config.json)."
    return ""


def _resolve(path: str) -> tuple[Optional[Path], str]:
    if not path.strip():
        return None, "Which database file should I use?"
    target, err = files._resolve_target(path)
    if err:
        return None, err
    assert target is not None
    if not target.is_file():
        return None, f"Database file not found: {target}"
    reason = files._authorize(target, "read")
    if reason:
        return None, reason
    return target, ""


def _query(target: Path, sql: str) -> str:
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        cur = conn.execute(sql)
        if cur.description is None:
            return "Done."
        rows = cur.fetchmany(_ROW_LIMIT + 1)
        cols = [c[0] for c in cur.description]
        out = "\t".join(cols)
        for row in rows[:_ROW_LIMIT]:
            cells = [str(v) for v in row]
            cells = [c if len(c) <= _CELL_LIMIT else c[:_CELL_LIMIT] + "…" for c in cells]
            out += "\n" + "\t".join(cells)
        if len(rows) > _ROW_LIMIT:
            out += f"\n… (showing first {_ROW_LIMIT} of more rows)"
        return out
    finally:
        conn.close()


def _execute(target: Path, sql: str) -> str:
    """Run a confirmed mutating statement (read-write connection, committed)."""
    conn = sqlite3.connect(str(target))
    try:
        cur = conn.execute(sql)
        conn.commit()
        if cur.description is None:
            return f"Done — {conn.total_changes} row(s) affected."
        return _format_rows(cur)
    except sqlite3.Error as e:
        return f"Query failed: {e}"
    finally:
        conn.close()


def _format_rows(cur) -> str:
    rows = cur.fetchmany(_ROW_LIMIT + 1)
    cols = [c[0] for c in cur.description]
    out = "\t".join(cols)
    for row in rows[:_ROW_LIMIT]:
        cells = [str(v) for v in row]
        cells = [c if len(c) <= _CELL_LIMIT else c[:_CELL_LIMIT] + "…" for c in cells]
        out += "\n" + "\t".join(cells)
    if len(rows) > _ROW_LIMIT:
        out += f"\n… (showing first {_ROW_LIMIT} of more rows)"
    return out


def query_database(path: str, sql: str) -> str:
    """
    Run a SQL statement against a SQLite database file.

    Args:
        path: Absolute path to the .db file (must be inside the read roots).
        sql: The SQL statement. SELECT/PRAGMA/EXPLAIN run immediately;
            mutating statements ask for confirmation first.

    Returns:
        The result rows, confirmation text, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return "Which SQL statement should I run?"
    target, err = _resolve(path)
    if err:
        return err
    assert target is not None
    head = sql.split(None, 1)[0].lower()
    if head in _READ_ONLY:
        try:
            return _query(target, sql)
        except sqlite3.Error as e:
            return f"Query failed: {e}"
        except Exception as e:  # noqa: BLE001
            return f"Query failed: {e}"
    if "\n" in sql:
        return "One statement per query, please (no newlines)."
    if len(sql) > 2000:
        return "That statement is too long."
    return files._awaiting_confirmation(
        f"run '{sql}' on {target.name}", lambda: _execute(target, sql)
    )


def explain_schema(path: str) -> str:
    """
    List the tables, their columns, and row counts of a SQLite database.

    Args:
        path: Absolute path to the .db file.

    Returns:
        One table per section, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    target, err = _resolve(path)
    if err:
        return err
    assert target is not None
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()]
        if not tables:
            return f"{target.name} has no tables."
        parts = []
        for table in tables:
            cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            names = ", ".join(c[1] for c in cols)
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            parts.append(f"{table} ({count} rows): {names}")
        return "Tables in " + target.name + ":\n" + "\n".join(parts)
    except sqlite3.Error as e:
        return f"Could not read the schema: {e}"
    finally:
        conn.close()


def backup_database(path: str, destination: str = "") -> str:
    """
    Make a live, consistent backup copy of a SQLite database (confirmed).

    Args:
        path: Absolute path of the database to back up.
        destination: Output path (defaults to '<name>.backup.db' next to it).
            Must be inside the file write roots.

    Returns:
        Confirmation, or a failure reason.
    """
    err = _enabled()
    if err:
        return err
    target, err = _resolve(path)
    if err:
        return err
    assert target is not None
    dest = destination.strip() or str(target.with_suffix("")) + ".backup.db"
    out, err = files._resolve_target(dest)
    if err:
        return err
    assert out is not None
    reason = files._authorize(out, "write")
    if reason:
        return reason

    def _do() -> str:
        try:
            if out.is_file():
                out.unlink()
            src = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
            try:
                dst = sqlite3.connect(str(out))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        except sqlite3.Error as e:
            return f"Backup failed: {e}"
        return f"Done — backed up to {out}."

    if out.is_file() and getattr(settings, "file_confirm_writes", True):
        return files._awaiting_confirmation(f"overwrite '{out}'", _do)
    return files._awaiting_confirmation(
        f"back up {target.name} to {out}", _do
    )
