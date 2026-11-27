"""Regression tests: a trade with no nearby transaction must not file at Week 1.

Nov 26, 2026, 2:34 AM ET: the Bam Adebayo trade was broadcast (Acuff me
daddy received Adebayo and Donovan Clingan; Coward in Fears received
Damian Lillard and Scottie Barnes). When the next build ran, the
transactions window held 3 records, none of them trades, so
match_trade_scoring_period found nothing near the broadcast and fell
back to scoring period 1: the trade was archived under Week 1 instead of
Week 6. These tests pin the fix: the broadcast date itself dates the
trade (via the schedule's day anchor), and a misfiled archived receipt
adopts the week from its next feed sighting.
"""
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
pipeline_dir = REPO / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

for _name, _attrs in (("requests", {"Session": object}),
                      ("dotenv", {"load_dotenv": lambda *a, **k: None})):
    try:
        __import__(_name)
    except ImportError:
        _mod = types.ModuleType(_name)
        for _k, _v in _attrs.items():
            setattr(_mod, _k, _v)
        sys.modules[_name] = _mod

from features.trades import build, match_trade_scoring_period, sp_for_timestamp

SEASON = 2027
RAW_SRC = REPO / "data" / "raw"


def bam_entry(payload):
    matches = [t for t in payload["completed"]
               if any(p["name"] == "Bam Adebayo" for p in t["players_a"] + t["players_b"])]
    assert len(matches) == 1, "the Adebayo trade must appear exactly once"
    return matches[0]


class TestSpForTimestamp(unittest.TestCase):
    def test_broadcast_lands_in_its_own_period(self):
        archived = json.loads((RAW_SRC / str(SEASON) / "completed_trades.json").read_text(encoding="utf-8"))
        entry = bam_entry({"completed": archived})
        self.assertEqual(sp_for_timestamp(RAW_SRC, SEASON, entry["date"]), 38,
                         "Nov 26, 2026 is scoring period 38 (Week 6)")

    def test_no_nearby_transaction_uses_fallback(self):
        self.assertEqual(match_trade_scoring_period([], 0, fallback_sp=38), 38)
        self.assertEqual(match_trade_scoring_period([], 0), 1,
                         "the legacy default stays when no fallback is supplied")


class TestMisfiledReceiptIsRefilled(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.season_dir = self.raw / str(SEASON)
        self.season_dir.mkdir(parents=True)
        for name in ("roster.json", "league.json", "transactions.json",
                     "communication.json", "completed_trades.json", "proschedule.json"):
            shutil.copy(RAW_SRC / str(SEASON) / name, self.season_dir / name)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_bam_trade_files_at_week_6_and_archive_is_repaired(self):
        archived = json.loads((self.season_dir / "completed_trades.json").read_text(encoding="utf-8"))
        self.assertEqual(bam_entry({"completed": archived})["mp"], 1,
                         "fixture check: the committed archive holds the Week 1 misfiling")

        out = build(SEASON, self.raw)
        payload = json.loads(json.dumps(out["trades.json"]))
        self.assertEqual(bam_entry(payload)["mp"], 6)

        repaired = json.loads((self.season_dir / "completed_trades.json").read_text(encoding="utf-8"))
        self.assertEqual(bam_entry({"completed": repaired})["mp"], 6,
                         "the archive itself must be repaired, not just the payload")


if __name__ == "__main__":
    unittest.main()
