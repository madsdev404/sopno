"""
sopno/ui/hud/widgets
━━━━━━━━━━━━━━━━━━━━
Self-contained reusable pieces: the animated robot face, the conversation
thread, and the Voice | Text mode toggle.
"""

from sopno.ui.hud.widgets.chat import ChatThread
from sopno.ui.hud.widgets.mode_toggle import ModeToggle
from sopno.ui.hud.widgets.robot import AliveRobotFace

__all__ = ["ChatThread", "ModeToggle", "AliveRobotFace"]
