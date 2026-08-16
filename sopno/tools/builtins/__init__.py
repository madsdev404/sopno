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
  - terminal.py      → run_terminal, terminal_send, terminal_status
  - manage.py        → list_processes, kill_process, manage_service, read_logs, manage_cron
  - files.py         → read_file, write_file, edit_file, list_directory, delete_file, rename_file, copy_file, move_file, search_files
  - readers.py       → binary document readers (PDF / image OCR / Office) used by read_file
  - reminders.py     → set_reminder, list_reminders, cancel_reminder (SQLite + poller in core)
  - browser.py       → browser_navigate/click/type/extract/screenshot/back/close (Playwright, opt-in)
  - git.py           → git_status, git_log, git_diff, git_branch, git_add, git_commit, git_stash, git_commit_message
"""

__all__: list[str] = []
