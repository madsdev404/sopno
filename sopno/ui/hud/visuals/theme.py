"""
sopno/ui/hud/visuals/theme.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shared constants and QSS templates for the HUD package.
"""

from sopno.config.settings import settings
from PyQt5.QtGui import QColor

SIZE_PRESETS = {
    "small":  (280, 360),
    "medium": (380, 560),
    "full":   (520, 740),
}
MIN_SIZE = (260, 320)
EDGE = 8


def motion_enabled() -> bool:
    """True when HUD animations should run (respects hud_reduced_motion)."""
    return not getattr(settings, "hud_reduced_motion", False)

STATUS_COPY = {
    "standby":   ("Idle", "#8B9BB4"),
    "listening": ("Listening", "#5EB1F5"),
    "thinking":  ("Thinking", "#9B8CF2"),
    "speaking":  ("Speaking", "#4ADE9A"),
    "error":     ("Error", "#F07178"),
}

STATE_ACCENT = {
    "standby":   QColor(139, 155, 180),
    "listening": QColor(94, 177, 245),
    "thinking":  QColor(155, 140, 242),
    "speaking":  QColor(74, 222, 154),
    "error":     QColor(240, 113, 120),
}

_CHROME = """
    QPushButton {{
        background: transparent;
        color: #5C6B82;
        border: none;
        font-size: {font_size}px;
        font-weight: 500;
        padding: 0px;
    }}
    QPushButton:hover {{ color: {hover}; }}
"""

_SEGMENT = """
    QPushButton {{
        background: {bg};
        color: {fg};
        border: none;
        border-radius: {radius};
        padding: {pad_v}px {pad_h}px;
        font-size: {font_size}px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }}
    QPushButton:hover {{
        background: {hover_bg};
        color: {hover_fg};
    }}
    QPushButton:pressed {{
        background: {pressed_bg};
    }}
"""

_ICON_BTN = """
    QPushButton {{
        background: {bg};
        border: 1px solid {border};
        border-radius: 18px;
        padding: 0px;
    }}
    QPushButton:hover {{
        background: {hover_bg};
        border-color: {hover_border};
    }}
    QPushButton:pressed {{
        background: {pressed_bg};
    }}
"""
