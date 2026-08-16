"""
sopno/tools/builtins/dev
━━━━━━━━━━━━━━━━━━━━━━━━
Developer tools: the persistent terminal shell (terminal.py) and git
repository tools (git.py).
"""

from . import terminal, git  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(terminal, git)
del _reexport
