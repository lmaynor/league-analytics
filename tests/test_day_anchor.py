"""Tests for the day anchor (features/live.py effective_sp).

ESPN's scoringPeriodId can lag the calendar (Week 5: still Saturday at
Sunday noon), which left the live page showing Saturday's finished games
as the player chips under a header counting Sunday's remaining games.
The anchor advances to the calendar day once ESPN's day is fully final.
"""
import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

try:
    import numpy  # noqa: F401  (features.live needs it; present in the test env)
except ImportError:
    raise unittest.SkipTest("numpy unavailable")

from features.live import effective_sp, tonight

ET = ZoneInfo("America/New_York")
D1 = dt.date(2026, 10, 20)  # sp 1, as in week_days


def date_of(sp):
    return D1 + dt.timedelta(days=sp - 1)


def ms(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=ET).timestamp() * 1000


def game(sp, t, final=False, home=1, away=2):
    return {"sp": sp, "home": home, "away": away, "t": t, "final": final}


# Week 5's shape: sp 33 = Sat Nov 21, sp 34 = Sun Nov 22 (first tip 3:30 PM ET)
SAT_GAMES = [game(33, ms(2026, 11, 21, 13), final=True), game(33, ms(2026, 11, 21, 22), final=True)]
SUN_GAMES = [game(34, ms(2026, 11, 22, 15, 30)), game(34, ms(2026, 11, 22, 20, 30))]
SUN_NOON = ms(2026, 11, 22, 12, 8)


class EffectiveSpTests(unittest.TestCase):
    def test_lagging_espn_advances_to_today(self):
        sched = {"games": SAT_GAMES + SUN_GAMES}
        self.assertEqual(effective_sp(33, 34, sched, SUN_NOON, date_of), 34)

    def test_current_espn_unchanged(self):
        sched = {"games": SAT_GAMES + SUN_GAMES}
        self.assertEqual(effective_sp(34, 34, sched, SUN_NOON, date_of), 34)

    def test_live_game_blocks_advance(self):
        late = game(33, ms(2026, 11, 21, 22))  # tipped 10 PM, not final-flagged
        sched = {"games": [late] + SUN_GAMES}
        self.assertEqual(effective_sp(33, 34, sched, ms(2026, 11, 22, 0, 30), date_of), 33)

    def test_no_jump_into_future(self):
        sched = {"games": SAT_GAMES + SUN_GAMES}
        self.assertEqual(effective_sp(33, 34, sched, ms(2026, 11, 21, 12), date_of), 33)

    def test_never_past_week_end(self):
        sched = {"games": SAT_GAMES + SUN_GAMES}
        self.assertEqual(effective_sp(33, 33, sched, SUN_NOON, date_of), 33)

    def test_off_day_advances(self):
        sched = {"games": SUN_GAMES}  # no games at all on sp 33
        self.assertEqual(effective_sp(33, 34, sched, SUN_NOON, date_of), 34)


class TonightTests(unittest.TestCase):
    def test_chips_follow_the_effective_day(self):
        games = [game(34, ms(2026, 11, 22, 18), home=4, away=5)]
        players = [{"name": "Sun Player", "pro": 4, "slot": 0, "inj": None}]
        abbrev = {"4": "CHI", "5": "CLE"}
        self.assertEqual(tonight(games, players, 33, SUN_NOON, abbrev), [])
        chips = tonight(games, players, 34, SUN_NOON, abbrev)
        self.assertEqual(len(chips), 1)
        self.assertEqual(chips[0]["status"], "upcoming")


if __name__ == "__main__":
    unittest.main()
