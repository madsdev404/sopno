"""
main.py
━━━━━━━
Sopno Voice Assistant — Unified Entry Point.

Brings up the assistant. Supports launching the interactive glassmorphic HUD
or the terminal console-based CLI. If HUD dependencies are missing, it falls
back gracefully to the CLI mode.

Usage:
    python main.py          # Launches HUD mode (falls back to CLI if PyQt5 is missing)
    python main.py --hud    # Launches HUD mode explicitly
    python main.py --cli    # Launches terminal CLI mode explicitly
"""

import argparse
import sys


def main() -> None:
    """Boot orchestrator for Sopno."""
    parser = argparse.ArgumentParser(description="🌙 Sopno Voice Assistant")
    
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--hud",
        action="store_true",
        help="Launch the premium glassmorphic HUD overlay (default)"
    )
    mode_group.add_argument(
        "--cli",
        action="store_true",
        help="Launch in terminal CLI console mode"
    )

    args = parser.parse_args()

    # Route execution based on flags
    if args.cli:
        from sopno.ui.cli import run_cli
        run_cli()
    elif args.hud:
        try:
            from sopno.ui.hud import run_hud
            run_hud()
        except ImportError as e:
            print(f"[Warning] HUD mode failed to load dependencies ({e}).")
            print("Falling back to terminal CLI mode...\n")
            from sopno.ui.cli import run_cli
            run_cli()
    else:
        # Default behavior: try HUD first, fallback to CLI
        try:
            from sopno.ui.hud import run_hud
            run_hud()
        except ImportError:
            from sopno.ui.cli import run_cli
            run_cli()


if __name__ == "__main__":
    main()
