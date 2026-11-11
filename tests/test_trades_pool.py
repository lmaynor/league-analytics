"""Regression tests: a traded player who is on no roster must not vanish.

Nov 11, 2026: Brunson Burners picked Keegan Murray up as a free agent at
3:39 PM CT and traded him to The Joker at 4:09 PM CT, before the add took
effect. He was in no roster in roster.json, the trades build resolved
broadcast players from rosters only, and its filter silently dropped him:
the site showed Gobert for Edey and Quickley instead of Gobert and Murray
for Edey and Quickley, graded the wrong package, and archived the wrong
receipt. These tests pin the three fixes: resolve from the player pool,
fall back to a flagged placeholder instead of dropping, and let a complete
version of a trade supersede an incomplete archived receipt.
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

from features.trades import build

SEASON = 2027
RAW_SRC = REPO / "data" / "raw" / str(SEASON)
GOBERT_TRADE_ID = "d19d12b2-5457-437f-be03-27d8414e1a2d"
KEEGAN_ID = 4594327

KEEGAN_POOL = {
    str(KEEGAN_ID): {
        "id": KEEGAN_ID, "name": "Keegan Murray", "pro": 23, "inj": None, "pos": 3,
        "stats": {
            "002027": {"avg": {"0": 13.5, "1": 0.4, "2": 0.9, "3": 1.8, "6": 5.4,
                               "11": 0.8, "13": 5.0, "14": 10.2, "15": 1.6, "16": 2.0,
                               "17": 1.9, "19": 0.49, "20": 0.8}, "gp": 9},
            "102027": {"avg": {"0": 14.0, "1": 0.5, "2": 1.0, "3": 2.0, "6": 5.8,
                               "11": 0.9, "13": 5.2, "14": 10.6, "15": 1.8, "16": 2.2,
                               "17": 2.0, "19": 0.49, "20": 0.81}, "gp": 70},
        },
    }
}


class TestTradesPool(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.season_dir = self.raw / str(SEASON)
        self.season_dir.mkdir(parents=True)
        for name in ("roster.json", "league.json", "transactions.json", "communication.json"):
            shutil.copy(RAW_SRC / name, self.season_dir / name)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def payload(self):
        out = build(SEASON, self.raw)
        return json.loads(json.dumps(out["trades.json"]))

    def gobert_trade(self, payload):
        matches = [t for t in payload["completed"] if t["id"] == GOBERT_TRADE_ID]
        self.assertEqual(len(matches), 1, "the Gobert trade must appear exactly once")
        return matches[0]

    def write_pool(self):
        (self.season_dir / "players.json").write_text(json.dumps(KEEGAN_POOL), encoding="utf-8")

    def write_archive(self, entries):
        (self.season_dir / "completed_trades.json").write_text(json.dumps(entries), encoding="utf-8")

    def read_archive(self):
        return json.loads((self.season_dir / "completed_trades.json").read_text(encoding="utf-8"))

    def test_pool_resolves_off_roster_player(self):
        self.write_pool()
        trade = self.gobert_trade(self.payload())
        self.assertEqual(sorted(p["name"] for p in trade["players_a"]),
                         ["Keegan Murray", "Rudy Gobert"])
        self.assertEqual(sorted(p["name"] for p in trade["players_b"]),
                         ["Immanuel Quickley", "Zach Edey"])
        self.assertNotIn("incomplete", trade)

    def test_unresolved_player_becomes_flagged_placeholder(self):
        trade = self.gobert_trade(self.payload())
        names = [p["name"] for p in trade["players_a"]] + [p["name"] for p in trade["players_b"]]
        self.assertEqual(len(names), 4, "every broadcast player must be listed")
        self.assertIn(f"Player {KEEGAN_ID}", names)
        self.assertTrue(trade.get("incomplete"), "a placeholder entry must be flagged incomplete")

    def test_incomplete_receipt_is_superseded_by_complete_version(self):
        self.write_pool()
        complete = self.gobert_trade(self.payload())
        damaged = json.loads(json.dumps(complete))
        damaged["players_a"] = [p for p in damaged["players_a"] if p["id"] != KEEGAN_ID]
        self.assertEqual(len(damaged["players_a"]), 1)
        self.write_archive([damaged])

        trade = self.gobert_trade(self.payload())
        self.assertEqual(sorted(p["name"] for p in trade["players_a"]),
                         ["Keegan Murray", "Rudy Gobert"])
        archived = [t for t in self.read_archive() if t["id"] == GOBERT_TRADE_ID]
        self.assertEqual(len(archived), 1)
        self.assertEqual(len(archived[0]["players_a"]), 2,
                         "the archive itself must be repaired, not just the payload")

    def test_complete_receipt_stays_write_once(self):
        self.write_pool()
        complete = self.gobert_trade(self.payload())
        complete["grade_a"]["score"] = -99.0
        others = [t for t in self.payload()["completed"] if t["id"] != GOBERT_TRADE_ID]
        self.write_archive(others + [complete])

        trade = self.gobert_trade(self.payload())
        self.assertEqual(trade["grade_a"]["score"], -99.0,
                         "a complete receipt of the same size must not be repriced")


if __name__ == "__main__":
    unittest.main()
