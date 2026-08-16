"""
sopno/tools/builtins/knowledge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Knowledge & communication: vision / OCR (vision.py), email (email.py, opt-in),
file-based calendar (calendar.py), and the markdown notes base (notes.py).
"""

from . import vision, email, calendar, notes  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(vision, email, calendar, notes)
del _reexport
