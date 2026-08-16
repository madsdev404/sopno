"""
sopno/tools/builtins/system
━━━━━━━━━━━━━━━━━━━━━━━━━━
OS-level control & hardware: app launching / volume / system stats
(system.py), desktop control (desktop.py), process & service management
(manage.py), media playback (media.py), and time (datetime_tool.py).

Re-exports each module's full namespace (including private helpers) so both
``from sopno.tools.builtins import system`` and
``from sopno.tools.builtins.system.system import open_application`` keep working.
"""

from . import system, desktop, manage, media, datetime_tool  # noqa: F401


def _reexport(*modules):
    namespace = globals()
    for module in modules:
        own = module.__name__.rpartition(".")[2]
        for name, value in vars(module).items():
            if name.startswith("__") or name == own:
                continue
            namespace.setdefault(name, value)


_reexport(system, desktop, manage, media, datetime_tool)
del _reexport
