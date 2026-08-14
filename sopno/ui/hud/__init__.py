"""
sopno/ui/hud
━━━━━━━━━━━━━
Public API of the HUD package. Imports elsewhere must not change —
`from sopno.ui.hud import run_hud` still works after the module → package split.
"""

from sopno.ui.hud.app import run_hud
from sopno.ui.hud.window import SopnoHUDWindow

__all__ = ["run_hud", "SopnoHUDWindow"]
