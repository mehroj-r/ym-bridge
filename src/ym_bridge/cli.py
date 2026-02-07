from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ym-bridge: Yandex Music Linux bridge")
    parser.add_argument("--config", type=Path, help="Path to config.toml", default=None)
    parser.add_argument("--log-level", default="INFO", help="Python log level (INFO, DEBUG, ...)")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="Run the bridge daemon")
    subparsers.add_parser("recon", help="Probe candidate Yandex API endpoints")
    subparsers.add_parser("doctor", help="Check runtime dependencies and config")
    subparsers.add_parser("account", help="Fetch account/about using current config")
    subparsers.add_parser("like", help="Like currently selected track")
    subparsers.add_parser("dislike", help="Dislike currently selected track")

    ctl = subparsers.add_parser("ctl", help="Control running daemon over IPC")
    ctl.add_argument(
        "action",
        choices=[
            "status",
            "play",
            "pause",
            "play_pause",
            "next",
            "previous",
            "like",
            "dislike",
        ],
    )
    subparsers.add_parser("waybar", help="Emit Waybar JSON from daemon state")

    return parser.parse_args()
