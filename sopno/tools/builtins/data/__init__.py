"""
sopno/tools/builtins/data
━━━━━━━━━━━━━━━━━━━━━━━━
Structured-data tools: read-only SQLite access (databases.py) and package
management (packages.py).
"""

from . import databases, packages  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(databases, packages)
del _reexport
