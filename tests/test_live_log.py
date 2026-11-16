"""Tests for the rolling win-chance snapshot log (features/live.py).

A point lands only when the win chance has moved at least LOG_MIN_MOVE and
at least LOG_MIN_GAP_MS have passed, so dead hours add no points. The log
holds one scoring day of one matchup week; either rolling over resets it.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

try:
    import numpy  # noqa: F401  (features.live needs it; present in the test env)
except ImportError:
    raise unittest.SkipTest("numpy unavailable")

from features.live import LOG_MIN_GAP_MS, update_win_chance_log

T0 = 1_700_000_000_000


def payload(p=0.60, ts=T0, mp=5, sp=30, hidden=False):
    return {"active": True, "mp": mp, "cur_sp": sp, "asof_ms": ts,
            "matchups": [{"home": 4, "away": 8, "hidden": hidden, "p_home_win": p}]}


class TestWinChanceLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "win_chance_log.json"

    def tearDown(self):
        self.tmp.cleanup()

    def points(self):
        return json.loads(self.path.read_text())["points"]["4"]

    def test_first_point_always_lands(self):
        update_win_chance_log(self.path, payload())
        self.assertEqual(self.points(), [[T0, 0.60]])

    def test_small_move_within_gap_does_not_land(self):
        update_win_chance_log(self.path, payload())
        update_win_chance_log(self.path, payload(p=0.55, ts=T0 + 5 * 60 * 1000))
        self.assertEqual(len(self.points()), 1)

    def test_move_after_gap_lands(self):
        update_win_chance_log(self.path, payload())
        update_win_chance_log(self.path, payload(p=0.55, ts=T0 + LOG_MIN_GAP_MS))
        self.assertEqual(self.points()[-1], [T0 + LOG_MIN_GAP_MS, 0.55])

    def test_tiny_move_after_gap_does_not_land(self):
        update_win_chance_log(self.path, payload())
        update_win_chance_log(self.path, payload(p=0.605, ts=T0 + LOG_MIN_GAP_MS))
        self.assertEqual(len(self.points()), 1)

    def test_hidden_matchup_is_skipped(self):
        update_win_chance_log(self.path, payload(hidden=True))
        self.assertFalse(self.path.exists())

    def test_new_week_and_new_day_reset(self):
        update_win_chance_log(self.path, payload())
        update_win_chance_log(self.path, payload(mp=6, ts=T0 + LOG_MIN_GAP_MS))
        log = json.loads(self.path.read_text())
        self.assertEqual(log["mp"], 6)
        self.assertEqual(len(log["points"]["4"]), 1)
        update_win_chance_log(self.path, payload(mp=6, sp=31, ts=T0 + 2 * LOG_MIN_GAP_MS))
        log = json.loads(self.path.read_text())
        self.assertEqual(log["sp"], 31)
        self.assertEqual(len(log["points"]["4"]), 1)

    def test_inactive_payload_writes_nothing(self):
        update_win_chance_log(self.path, {"active": False})
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
