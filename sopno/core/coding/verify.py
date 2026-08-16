"""
sopno/core/coding/verify.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Verification for a coding run.

The verification recipe is the core of autonomy: after every change the loop
runs the recipe and decides from this state, never from vibes. A step passes
when it exits 0 without a policy block; the first failing step stops the run.
If a ticket carries no recipe, a sensible default for a Python repo is used
(run its test suite) — or none at all when no interpreter is available.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from sopno.config.settings import settings

from sopno.core.coding.util import q

# Default verification recipe, used when the ticket does not carry an explicit
# one. ``{python}`` is substituted with the repo's interpreter at runtime.
DEFAULT_RECIPE = [
    {"command": "{python} -m unittest discover -s tests -q", "kind": "tests"},
]

VerifyRunner = Callable[[str], dict]


def guess_python() -> str:
    """The repo's venv python if present, else 'python3', else ''."""
    venv = settings.project_root / "venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    if shutil.which("python3"):
        return "python3"
    return ""


class Verifier:
    """Runs a recipe's steps and answers the only question that matters: green?"""

    def __init__(self, worktree: Path, verify_runner: VerifyRunner,
                 recipe: Optional[list[dict]] = None) -> None:
        self.worktree = Path(worktree)
        self.verify_runner = verify_runner
        self.recipe = recipe or []
        self.last_results: list[dict] = []

    @staticmethod
    def resolve_recipe(task_spec: dict) -> list[dict]:
        """The ticket's recipe, or the repo default when none was given."""
        recipe = task_spec.get("verify_recipe")
        if recipe:
            return [dict(r) for r in recipe if r.get("command")]
        python = guess_python()
        if not python:
            return []
        return [{**step, "command": step["command"].format(python=q(python))}
                for step in DEFAULT_RECIPE]

    def run(self) -> list[dict]:
        """Run the recipe scoped to the worktree; returns the step results."""
        results: list[dict] = []
        for step in self.recipe:
            command = step["command"]
            scoped = f"(cd {q(self.worktree)} && {command})"
            res = self.verify_runner(scoped)
            blocked = res.get("blocked")
            error = res.get("error")
            exit_code = res.get("exit_code")
            ok = not blocked and not error and exit_code in (0, None)
            out = (res.get("stdout") or "").strip()
            if len(out) > 1200:
                out = out[-1200:]
            results.append({
                "command": command,
                "kind": step.get("kind", "check"),
                "ok": ok,
                "exit_code": exit_code,
                "blocked": blocked,
                "error": error,
                "output": out,
            })
            if not ok:
                break
        self.last_results = results
        return results

    def green(self) -> bool:
        """True when nothing needs verification or everything passed."""
        if not self.recipe:
            return True
        if not self.last_results:
            return False
        return all(r["ok"] for r in self.last_results)
