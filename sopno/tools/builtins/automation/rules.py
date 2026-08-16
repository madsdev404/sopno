"""
sopno/tools/builtins/automation/rules.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automation-rule tools — create, list, toggle, and delete "if X then Y" rules.

A rule is approved once at creation: from then on its action runs automatically
whenever the condition is true (checked by the background RulePoller). The
store lives in ``sopno.core.rules``.
"""

from __future__ import annotations

from sopno.core.rules import RuleStore, get_store, set_store


def _store() -> RuleStore:
    store = get_store()
    if store is None:
        store = RuleStore()
        set_store(store)
    return store


def _confirm(description: str, fn) -> str:
    from sopno.tools.builtins import files
    return files._awaiting_confirmation(description, fn)


def _validate(condition: str, action: str) -> str:
    """Re-run RuleStore's own validation to give the LLM a friendly reason."""
    from sopno.core.rules import _evaluate, _parse_action
    try:
        _evaluate(condition)
    except ValueError as e:
        return str(e)
    try:
        _parse_action(action)
    except ValueError as e:
        return str(e)
    return ""


def rule_add(name: str, condition: str, action: str) -> str:
    """
    Create an automation rule: "if {condition} then {action}" (confirmed once).

    Args:
        name: Short rule name.
        condition: e.g. 'battery_percent < 20' — one of battery_percent,
            cpu_percent, ram_percent, disk_free_gb, hour_of_day,
            day_of_week (0=Monday..6=Sunday), compared with < <= > >= ==.
        action: A registered tool with args, e.g. 'open_application app="Files"'
            or 'note_write title="daily" content="..."'.

    Returns:
        Confirmation, or a validation reason.
    """
    name = (name or "").strip()
    reason = _validate(condition, action)
    if reason:
        return reason

    def _do() -> str:
        rule_id = _store().add(name, condition, action)
        return (f"Rule created (id {rule_id}): if {condition.strip()} "
                f"then {action.strip()}. It will run automatically whenever "
                f"the condition is true.")

    return _confirm(
        f"create the rule '{name}' — it will act automatically", _do
    )


def rule_list() -> str:
    """
    List the automation rules with their conditions, actions, and fire counts.

    Returns:
        One rule per line, or a reason none exist.
    """
    rules = _store().list_rules()
    if not rules:
        return "No automation rules yet. Try rule_add."
    parts = []
    for r in rules:
        state = "on" if r["enabled"] else "off"
        parts.append(
            f"#{r['id']} [{state}] {r['name']} — if {r['condition']} "
            f"then {r['action']} (fired {r['fire_count']}x)"
        )
    return "Rules:\n" + "\n".join(parts)


def rule_remove(rule_id: int) -> str:
    """
    Delete an automation rule (confirmed).

    Args:
        rule_id: The rule id from rule_list.

    Returns:
        Confirmation, or a reason it doesn't exist.
    """
    def _do() -> str:
        ok = _store().remove(int(rule_id))
        return f"Rule {rule_id} removed." if ok else f"No rule with id {rule_id}."

    return _confirm(f"delete rule #{rule_id}", _do)


def rule_set_enabled(rule_id: int, enabled: bool) -> str:
    """
    Enable or disable an automation rule (disabling is confirmed).

    Args:
        rule_id: The rule id from rule_list.
        enabled: True to arm the rule, False to pause it.

    Returns:
        Confirmation of the new state, or a reason it doesn't exist.
    """
    def _do() -> str:
        ok = _store().set_enabled(int(rule_id), bool(enabled))
        state = "enabled" if enabled else "disabled"
        if not ok:
            return f"No rule with id {rule_id}."
        return f"Rule {rule_id} {state}."

    if not enabled:
        return _confirm(f"disable rule #{rule_id}", _do)
    return _do()
