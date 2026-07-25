"""
sopno/core/dispatcher.py
━━━━━━━━━━━━━━━━━━━━━━━━
Command dispatcher.

Analyzes user utterances and routes them to system tools using rule-based
pattern matching. If a match is found, the tool is executed and its result
is returned; otherwise, it returns None, indicating the message should go
to the LLM.
"""

import re
from typing import Optional
from sopno.tools.registry import execute_tool


class CommandDispatcher:
    """Dispatches user utterances to local tools based on rules."""

    def dispatch(self, text: str) -> Optional[str]:
        """
        Analyze the input text and execute a tool if a pattern matches.

        Args:
            text: The user's spoken transcription

        Returns:
            The tool's spoken response string if a tool was executed,
            or None if no tool matched (meaning it should go to the LLM).
        """
        txt = text.lower().strip()

        # ── 1. Date / Time ─────────────────────────────────────────────────────
        if "time" in txt or "date" in txt or "day is it" in txt:
            return execute_tool("get_current_time", {})

        # ── 2. Open Application ────────────────────────────────────────────────
        if txt.startswith("open ") or txt.startswith("launch "):
            # Extract app name (everything after "open " or "launch ")
            app_name = re.sub(r'^(open|launch)\s+', '', txt)
            return execute_tool("open_application", {"app_name": app_name})

        # ── 3. Search Web ──────────────────────────────────────────────────────
        if txt.startswith("search ") or txt.startswith("search for ") or txt.startswith("google "):
            query = re.sub(r'^(search for|search|google)\s+', '', txt)
            return execute_tool("search_web", {"query": query})

        # ── 4. Volume Control ──────────────────────────────────────────────────
        if "volume up" in txt or "increase volume" in txt:
            return execute_tool("control_volume", {"action": "up"})
        if "volume down" in txt or "decrease volume" in txt:
            return execute_tool("control_volume", {"action": "down"})
        if "mute" in txt or "toggle volume" in txt or "unmute" in txt:
            return execute_tool("control_volume", {"action": "toggle"})

        # ── 5. System Stats ────────────────────────────────────────────────────
        if any(kw in txt for kw in ["system stats", "system diagnostics", "system status", "cpu load", "ram usage", "battery level"]):
            return execute_tool("get_system_stats", {})

        # ── 6. Lock Screen ─────────────────────────────────────────────────────
        if any(kw in txt for kw in ["lock screen", "lock my pc", "lock the screen", "lock pc"]):
            return execute_tool("lock_screen", {})

        # ── 7. Media Playback ──────────────────────────────────────────────────
        if any(kw in txt for kw in ["pause", "pause music", "pause playback"]):
            return execute_tool("play_media_control", {"action": "pause"})
        if any(kw in txt for kw in ["play", "resume", "play music", "resume playback"]):
            return execute_tool("play_media_control", {"action": "play"})
        if any(kw in txt for kw in ["next", "next song", "next track", "skip track"]):
            return execute_tool("play_media_control", {"action": "next"})
        if any(kw in txt for kw in ["previous", "previous song", "previous track", "go back"]):
            return execute_tool("play_media_control", {"action": "previous"})

        return None
