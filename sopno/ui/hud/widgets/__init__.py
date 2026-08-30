"""
sopno/ui/hud/widgets
━━━━━━━━━━━━━━━━━━━━
Self-contained reusable pieces: the animated robot face, the conversation
thread, and the holographic toggle switch.
"""

from sopno.ui.hud.widgets.chat import ChatThread
from sopno.ui.hud.widgets.composer import ChatComposer
from sopno.ui.hud.widgets.context_meter import ContextMeter
from sopno.ui.hud.widgets.holo_toggle import HoloToggle
from sopno.ui.hud.widgets.reasoning_dropdown import ModelDropdown, ReasoningModeDropdown
from sopno.ui.hud.widgets.robot import AliveRobotFace
from sopno.ui.hud.widgets.status_dot import StatusDot
from sopno.ui.hud.widgets.text_hero import TextHero
from sopno.ui.hud.widgets.voice_orb import VoiceModeOrb

__all__ = [
    "ChatComposer",
    "ChatThread",
    "ContextMeter",
    "HoloToggle",
    "ModelDropdown",
    "ReasoningModeDropdown",
    "AliveRobotFace",
    "StatusDot",
    "TextHero",
    "VoiceModeOrb",
]
