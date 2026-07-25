"""
sopno/tools/media.py
━━━━━━━━━━━━━━━━━━━━
Media playback controls.

Uses 'playerctl' via MPRIS to control running media players on Linux.
"""

import subprocess


def play_media_control(action: str) -> str:
    """
    Control player music/video playback.

    Args:
        action: "play", "pause", "next", or "previous"

    Returns:
        Spoken confirmation or error message.
    """
    action_clean = action.lower().strip()
    
    # Map friendly action names to playerctl commands
    # 'play' and 'pause' might also map to playerctl commands directly
    if action_clean == "play":
        cmd_args = ["play"]
        confirm_text = "Resuming playback."
    elif action_clean == "pause":
        cmd_args = ["pause"]
        confirm_text = "Pausing playback."
    elif action_clean == "next":
        cmd_args = ["next"]
        confirm_text = "Skipping to next track."
    elif action_clean == "previous":
        cmd_args = ["previous"]
        confirm_text = "Going back to previous track."
    else:
        return f"Unknown media action: {action}. Supported: play, pause, next, previous."

    try:
        # Run playerctl
        subprocess.run(["playerctl"] + cmd_args, check=True, capture_output=True)
        return confirm_text
    except FileNotFoundError:
        return "I need 'playerctl' installed on the system to control media playback."
    except subprocess.CalledProcessError:
        # Often happens if no active player is found
        return f"Could not perform {action} action. Is a media player running?"
    except Exception as e:
        return f"Failed to control media: {e}"
