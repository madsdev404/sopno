"""
sopno/ui/hud/behaviors
━━━━━━━━━━━━━━━━━━━━━━
Mixins that dress the window: chrome, responsive sizing, drag-resize,
status rendering, and the system tray.
"""

from sopno.ui.hud.behaviors.chrome import ChromeMixin
from sopno.ui.hud.behaviors.responsive import ResponsiveMixin
from sopno.ui.hud.behaviors.resizing import ResizeMixin
from sopno.ui.hud.behaviors.status import StatusMixin
from sopno.ui.hud.behaviors.tray import TrayMixin

__all__ = ["ChromeMixin", "ResponsiveMixin", "ResizeMixin", "StatusMixin", "TrayMixin"]
