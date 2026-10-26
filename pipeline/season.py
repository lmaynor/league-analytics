"""The current NBA season, named by the year it ends (2026-27 is 2027)."""
import datetime as dt
import os


def current_season():
    """SEASON in the environment wins; otherwise Sept-Dec belongs to the season ending next year."""
    override = os.environ.get("SEASON", "").strip()
    if override:
        return int(override)
    today = dt.date.today()
    return today.year + 1 if today.month >= 9 else today.year
