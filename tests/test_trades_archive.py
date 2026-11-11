"""Regression test: completed trades must survive ESPN's sliding feeds.

The two trades of Oct 28, 2026 appeared in trades.json on Oct 29 and were
gone by Nov 3: the communication topics and the transactions list are
recent-activity windows, and the payload was rebuilt from the current
snapshot alone. trades.build now archives every trade it sees to
data/raw/<season>/completed_trades.json and rebuilds from feed + archive.
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


class TestTradesArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        season_dir = self.raw / str(SEASON)
        season_dir.mkdir(parents=True)
        for name in ("roster.json", "league.json", "transactions.json", "communication.json"):
            shutil.copy(RAW_SRC / name, season_dir / name)
        self.season_dir = season_dir

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def payload(self):
        out = build(SEASON, self.raw)
        return json.loads(json.dumps(out["trades.json"]))

    def test_trade_survives_feed_rolloff(self):
        first = self.payload()
        self.assertGreaterEqual(len(first["completed"]), 1,
                                "the current feed should yield at least one trade")
        archive = self.season_dir / "completed_trades.json"
        self.assertTrue(archive.exists(), "build must write the trade archive")
        archived = json.loads(archive.read_text(encoding="utf-8"))
        self.assertEqual([t["id"] for t in archived],
                         [t["id"] for t in first["completed"]])

        # Simulate the Nov 3 rolloff: both ESPN feeds come back empty.
        (self.season_dir / "communication.json").write_text('{"topics": []}', encoding="utf-8")
        (self.season_dir / "transactions.json").write_text("[]", encoding="utf-8")

        second = self.payload()
        self.assertEqual([t["id"] for t in second["completed"]],
                         [t["id"] for t in first["completed"]],
                         "archived trades must still be reported after the feeds roll off")
        self.assertEqual(json.loads(archive.read_text(encoding="utf-8")), archived,
                         "an empty feed must not shrink the archive")


if __name__ == "__main__":
    unittest.main()
