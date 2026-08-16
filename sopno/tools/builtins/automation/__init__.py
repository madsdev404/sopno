"""
sopno/tools/builtins/automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Proactive behaviour: scheduled reminders (reminders.py), "if X then Y"
automation rules (rules.py), durable background agents (agents.py), and
delegated subagent runners (subagents.py).
"""

from . import reminders, rules, agents, subagents  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(reminders, rules, agents, subagents)
del _reexport
