"""Decide whether a scheduled refresh is worth running: only when an NBA game is on.

Prints run=true or run=false (the format GitHub Actions reads from $GITHUB_OUTPUT).
Manual runs always go. Uses only the standard library so it can run before pip install.
"""
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASON = os.environ.get("SEASON", "2027")
BEFORE_MS = 20 * 60 * 1000          # start a little before tip-off
AFTER_MS = int(3.5 * 3600 * 1000)   # keep going through the game and ESPN's final stat updates


def should_run(now_ms):
    path = ROOT / "data" / "raw" / SEASON / "proschedule.json"
    if not path.exists():
        return True
    games = json.loads(path.read_text(encoding="utf-8"))["games"]
    return any(g["t"] - BEFORE_MS <= now_ms <= g["t"] + AFTER_MS for g in games)


if __name__ == "__main__":
    now = float(os.environ.get("NOW_MS", time.time() * 1000))
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    print(f"run={'true' if manual or should_run(now) else 'false'}")
