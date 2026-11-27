"""Decide whether a scheduled refresh is worth running: only when an NBA game is on.

Prints run=true or run=false (the format GitHub Actions reads from $GITHUB_OUTPUT).
Manual runs always go; an external scheduler (REFRESH_SOURCE=cron) is gated like the GitHub schedule. Uses only the standard library so it can run before pip install.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from season import current_season

ROOT = Path(__file__).resolve().parent.parent

SEASON = str(current_season())
BEFORE_MS = 20 * 60 * 1000          # start a little before tip-off
AFTER_MS = int(3.5 * 3600 * 1000)   # keep going through the game and ESPN's final stat updates


def should_run(now_ms):
    path = ROOT / "data" / "raw" / SEASON / "proschedule.json"
    if not path.exists():
        return True
    games = json.loads(path.read_text(encoding="utf-8"))["games"]
    return any(g["t"] - BEFORE_MS <= now_ms <= g["t"] + AFTER_MS for g in games)


CHICAGO = ZoneInfo("America/Chicago")


def noon_floor(now_ms):
    """At least one build a day, games or not.

    The game gate alone leaves no-game days unfetched for 36+ hours:
    Thanksgiving 2026 had no games, so a trade executed that night only
    reached the site the next evening. In the noon hour (Chicago), run if
    no build has landed yet today. The last build's stamp is the asof_ms
    of the committed site/data/live.json; a missing stamp counts as no
    build yet. Any read problem falls back to the game gate alone.
    """
    try:
        now_ct = datetime.fromtimestamp(now_ms / 1000, CHICAGO)
        if now_ct.hour != 12:
            return False
        live_path = ROOT / "site" / "data" / "live.json"
        if not live_path.exists():
            return True
        live = json.loads(live_path.read_text(encoding="utf-8"))
        asof = live.get("asof_ms")
        if not asof:
            return True
        return datetime.fromtimestamp(asof / 1000, CHICAGO).date() < now_ct.date()
    except Exception:
        return False


if __name__ == "__main__":
    now = float(os.environ.get("NOW_MS", time.time() * 1000))
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and os.environ.get("REFRESH_SOURCE") != "cron"
    print(f"run={'true' if manual or should_run(now) or noon_floor(now) else 'false'}")
