"""
sopno/tools/datetime_tool.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Date and time retrieval tools.
"""

import datetime


def get_current_time() -> str:
    """
    Get the current time, date, and day of the week.

    Returns:
        A human-readable string suitable for reading aloud.
    """
    now = datetime.datetime.now()
    return f"It is {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d')}."
