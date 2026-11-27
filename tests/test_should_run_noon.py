"""The noon floor: at least one build a day, games or not.

pipeline/should_run.py gates refreshes on a game being on. Thanksgiving
2026 had no games, so nothing fetched ESPN for 36+ hours and a trade
executed that night waited a day to reach the site. noon_floor() forces
one run in the noon hour (America/Chicago) when no build has landed yet
that day, judged by the asof_ms stamped into the committed live.json.
"""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
pipeline_dir = REPO / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

import should_run

CT = ZoneInfo("America/Chicago")


def ms(dt):
    return dt.timestamp() * 1000


NOON = ms(datetime(2026, 11, 27, 12, 30, tzinfo=CT))       # Friday, games that evening
MORNING = ms(datetime(2026, 11, 27, 11, 30, tzinfo=CT))
YESTERDAY = ms(datetime(2026, 11, 26, 1, 25, tzinfo=CT))    # the Thanksgiving freeze
TODAY_EARLY = ms(datetime(2026, 11, 27, 9, 0, tzinfo=CT))


class TestNoonFloor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_root = should_run.ROOT
        should_run.ROOT = self.tmp
        self.live = self.tmp / "site" / "data" / "live.json"
        self.live.parent.mkdir(parents=True)

    def tearDown(self):
        should_run.ROOT = self.orig_root
        shutil.rmtree(self.tmp)

    def stamp(self, asof_ms):
        self.live.write_text(json.dumps({"active": True, "asof_ms": asof_ms}), encoding="utf-8")

    def test_noon_with_no_build_today_runs(self):
        self.stamp(YESTERDAY)
        self.assertTrue(should_run.noon_floor(NOON))

    def test_noon_after_a_build_today_stays_gated(self):
        self.stamp(TODAY_EARLY)
        self.assertFalse(should_run.noon_floor(NOON))

    def test_before_noon_stays_gated(self):
        self.stamp(YESTERDAY)
        self.assertFalse(should_run.noon_floor(MORNING))

    def test_missing_live_json_counts_as_no_build(self):
        self.assertTrue(should_run.noon_floor(NOON))

    def test_missing_stamp_counts_as_no_build(self):
        self.live.write_text('{"active": false}', encoding="utf-8")
        self.assertTrue(should_run.noon_floor(NOON))

    def test_corrupt_live_json_falls_back_without_crashing(self):
        self.live.write_text("not json", encoding="utf-8")
        self.assertFalse(should_run.noon_floor(NOON))


if __name__ == "__main__":
    unittest.main()
