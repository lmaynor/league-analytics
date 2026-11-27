"""Regression tests: one executed trade, two ESPN records, one receipt.

Nov 25, 2026: the Kyrie Irving / Michael Porter Jr. trade between Black
Towns and Shai Boyz was recorded twice in Week 6, as mirror images. ESPN
reported the same execution in both feeds: the TRADE_ACCEPT transaction
(id f1382c67, timestamp ...571428) and the communication topic (id
b7724664, 47 ms later). The broadcast path sorts team ids before keying;
the transactions path took them from a set, in arbitrary order, so its
receipt was flipped, and the orientation-sensitive trade_key let both
receipts survive the archive merge. These tests pin the fix: the key
ignores side order, and an archive already holding both copies collapses
to the canonically oriented one.
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

from features.trades import build, trade_key

SEASON = 2027
RAW_SRC = REPO / "data" / "raw" / str(SEASON)
KYRIE_PACKAGE = {4397688, 4869342, 6442, 4278104}  # Murphy, Dyson, Kyrie, MPJ


class TestTradeKey(unittest.TestCase):
    def test_key_ignores_side_order(self):
        self.assertEqual(trade_key(3, 10, [6442, 4278104], [4397688, 4869342]),
                         trade_key(10, 3, [4397688, 4869342], [4278104, 6442]))

    def test_reverse_trade_keys_differently(self):
        self.assertNotEqual(trade_key(3, 10, [6442], [4397688]),
                            trade_key(3, 10, [4397688], [6442]))


class TestFlippedDuplicateArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.season_dir = self.raw / str(SEASON)
        self.season_dir.mkdir(parents=True)
        for name in ("roster.json", "league.json", "completed_trades.json"):
            shutil.copy(RAW_SRC / name, self.season_dir / name)
        # Feeds empty: the payload must be rebuilt from the archive alone,
        # which is exactly where the flipped pair lives.
        (self.season_dir / "communication.json").write_text('{"topics": []}', encoding="utf-8")
        (self.season_dir / "transactions.json").write_text("[]", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_flipped_pair_collapses_to_canonical_receipt(self):
        archived = json.loads((RAW_SRC / "completed_trades.json").read_text(encoding="utf-8"))
        out = build(SEASON, self.raw)
        completed = json.loads(json.dumps(out["trades.json"]))["completed"]

        matches = [t for t in completed
                   if {p["id"] for p in t["players_a"]} | {p["id"] for p in t["players_b"]} == KYRIE_PACKAGE]
        self.assertEqual(len(matches), 1, "the Kyrie/MPJ trade must appear exactly once")
        self.assertEqual(matches[0]["team_a"]["id"], 3,
                         "the surviving receipt keeps the canonical orientation (lower team id first)")
        self.assertEqual(len(completed), len(archived) - 1,
                         "exactly the one flipped duplicate is removed, nothing else")


if __name__ == "__main__":
    unittest.main()
