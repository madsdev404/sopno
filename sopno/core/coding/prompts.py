"""
sopno/core/coding/prompts.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Prompt assembly for the coding agent.

Pure string building — the harness's job is the loop around the model, so the
prompts carry the safety rules, the ticket, and the anti-drift **recitation**
(the plan + progress + verification state recited into the tail of every turn).
"""

from __future__ import annotations

from pathlib import Path


def system_prompt(branch: str, repo: Path) -> str:
    return (
        "You are Sopno's autonomous coding agent. You are working in an "
        "isolated git worktree on branch '{}' of {} — the main checkout is "
        "untouched. You take small, verifiable steps and commit after each "
        "one.\n\n"
        "Rules:\n"
        "- Read files before editing them (read_file first).\n"
        "- After every change, run the verification recipe yourself if "
        "needed (run_terminal).\n"
        "- Never touch protected files: PLAN.md, progress.md, SUMMARY.md, "
        "config.json, sopno/memory/, .git, or anything outside paths_allowed.\n"
        "- Respect the repo's conventions and existing code style.\n"
        "- Write conventional commit messages (feat/fix/docs/test/chore).\n"
        "- When the goal is met, reply with ONLY a one-paragraph summary of "
        "what you changed and how you verified it — no tool calls.\n"
        "- Never claim success when verification fails. If blocked, say so "
        "and ask for help."
    ).format(branch, repo)


def task_prompt(goal: str, task_spec: dict, paths_allowed: list[str],
                recipe: list[dict]) -> str:
    parts = [f"Goal: {goal}"]
    criteria = task_spec.get("acceptance_criteria") or []
    if criteria:
        parts.append("Acceptance criteria:\n" + "\n".join(f"- {c}" for c in criteria))
    if paths_allowed:
        parts.append("Scope (only these paths):\n"
                     + "\n".join(f"- {p}" for p in paths_allowed))
    if recipe:
        parts.append("Verification recipe (run after changes):\n"
                     + "\n".join(f"- {s['command']}" for s in recipe))
    return "\n\n".join(parts)


def recitation(worktree: Path, recipe: list[dict], last_verify: list[dict]) -> str:
    """The current plan + progress + verification state, for the turn's tail."""
    lines = ["=== Plan (PLAN.md) ==="]
    try:
        plan = (worktree / "PLAN.md").read_text(encoding="utf-8")
        lines.append(plan.strip()[-1500:] or "(empty)")
    except OSError:
        lines.append("(no plan yet)")
    lines.append("=== Progress (last lines) ===")
    try:
        progress = (worktree / "progress.md").read_text(encoding="utf-8")
        lines.append("\n".join(progress.strip().splitlines()[-12:]) or "(no progress)")
    except OSError:
        lines.append("(no progress yet)")
    lines.append("=== Verification state ===")
    if not recipe:
        lines.append("no auto-recipe configured — verify via run_terminal")
    elif last_verify:
        lines.append("\n".join(
            f"- {r['kind']}: {'PASS' if r['ok'] else 'FAIL'} {r['command']}"
            for r in last_verify
        ))
    else:
        lines.append("no verification run yet")
    return "\n".join(lines)
