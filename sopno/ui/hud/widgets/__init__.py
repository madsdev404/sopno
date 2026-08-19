"""
sopno/ui/hud/widgets
━━━━━━━━━━━━━━━━━━━━━
Self-contained reusable pieces: the animated robot face, the conversation
thread, and the holographic toggle switch.
"""

from sopno.ui.hud.widgets.chat import ChatThread
from sopno.ui.hud.widgets.holo_toggle import HoloToggle
from sopno.ui.hud.widgets.robot import AliveRobotFace
from sopno.ui.hud.widgets.voice_orb import VoiceModeOrb

__all__ = ["ChatThread", "HoloToggle", "AliveRobotFace", "VoiceModeOrb"]
