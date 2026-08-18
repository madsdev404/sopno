"""
sopno/ui/hud/widgets
━━━━━━━━━━━━━━━━━━━
Self-contained reusable pieces: the animated robot face, the conversation
thread, and the Voice | Text mode toggle.
"""

from sopno.ui.hud.widgets.chat import ChatThread
from sopno.ui.hud.widgets.mode_toggle import ModeToggle
from sopno.ui.hud.widgets.robot import AliveRobotFace
from sopno.ui.hud.widgets.voice_orb import VoiceModeOrb

__all__ = ["ChatThread", "ModeToggle", "AliveRobotFace", "VoiceModeOrb"]
