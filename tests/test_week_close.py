"""Tests for the week-close rule (features/live.py week_is_done).

The week closes on its final day once no games remain, instead of staying
"live" until ESPN flips currentMatchupPeriod overnight.
"""
import sys
import unittest
from pathlib import Path

pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

try:
    import numpy  # noqa: F401  (features.live needs it; present in the test env)
except ImportError:
    raise unittest.SkipTest("numpy unavailable")

from features.live import week_is_done


class TestWeekClose(unittest.TestCase):
    def test_final_day_nothing_remaining_closes(self):
        self.assertTrue(week_is_done(25, 25, {}))

    def test_final_day_with_a_game_left_stays_open(self):
        self.assertFalse(week_is_done(25, 25, {25: {24: (0.5, {})}}))

    def test_midweek_nothing_remaining_today_stays_open(self):
        # A day with no games left still has later days in the week.
        self.assertFalse(week_is_done(23, 25, {}))


if __name__ == "__main__":
    unittest.main()
