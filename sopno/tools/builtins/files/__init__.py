"""
sopno/tools/builtins/files
━━━━━━━━━━━━━━━━━━━━━━━━━━
Filesystem access: permission-gated file tools (files.py) and the layered
binary document readers — PDF / image OCR / Office (readers.py).
"""

from . import files, readers  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(files, readers)
del _reexport
