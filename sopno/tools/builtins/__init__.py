"""
sopno/tools/builtins
━━━━━━━━━━━━━━━━━━━━
The skills — what Sopno can DO.

Skills are grouped into category packages (mirroring the HUD's subpackage
layout). Each category re-exports its modules' full namespaces, and this
package aliases every module at the old flat path so all imports keep working:

    from sopno.tools.builtins import files                 # the category pkg
    from sopno.tools.builtins.files import read_file       # still works
    from sopno.tools.builtins.system import open_application

Categories:
  - system/      system, desktop, manage, media, datetime_tool
  - files/       files, readers
  - dev/         terminal, git
  - web/         browser, search, network
  - data/        databases, packages
  - knowledge/   vision, email, calendar, notes
  - automation/  reminders, rules, subagents

To add a new skill:
  1. create ``<name>.py`` in the matching category package,
  2. alias it in the category ``__init__.py`` and (if you want the old path)
     in this file,
  3. register it in ``sopno/tools/registry.py``,
  4. declare its schema in ``sopno/tools/schema.py``.
"""

from . import system, files, dev, web, data, knowledge, automation  # noqa: F401

# Flat-path aliases — keep the historical ``from sopno.tools.builtins.X import …``
# working for every module, wherever it now lives.
from .system import system, desktop, manage, media, datetime_tool  # noqa: F401
from .files import files, readers  # noqa: F401
from .dev import terminal, git  # noqa: F401
from .web import browser, search, network  # noqa: F401
from .data import databases, packages  # noqa: F401
from .knowledge import vision, email, calendar, notes  # noqa: F401
from .automation import reminders, rules, subagents  # noqa: F401

__all__: list[str] = []
