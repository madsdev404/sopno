"""
sopno/tools/builtins
━━━━━━━━━━━━━━━━━━━━
The skills — what Sopno can DO.

Each file here is one skill (or one small domain) and lives next to its
machinery: a plain function that returns a short spoken answer.

To add a new skill:
  1. create ``<name>.py`` here with your function,
  2. register it in ``sopno/tools/registry.py``,
  3. declare its schema in ``sopno/tools/schema.py``.

Files:
  - datetime_tool.py → get_current_time
  - search.py        → search_web
  - system.py        → open_application, control_volume, get_system_stats, lock_screen
  - media.py         → play_media_control
"""

__all__: list[str] = []
