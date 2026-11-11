"""Unit tests for the completed-trade week matching in features/trades.py.

Regression: the first completed trade of the 2027 season (broadcast
2026-11-11 06:56:19 UTC) was filed under Week 5 instead of Week 4. The old
rule took the first transaction within 120 seconds of the broadcast, which
was a FUTURE_ROSTER lineup set for scoring period 28, returned ahead of the
trade's own TRADE_UPHOLD transaction (scoring period 22, 43 ms away).
"""
import sys
import types
import unittest
from pathlib import Path

pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

# features.trades pulls in the ESPN client, which needs requests and dotenv.
# Neither affects the matching helper, so stub them when they are absent
# (the rest of the suite runs on the bare standard library).
for _name, _attrs in (("requests", {"Session": object}),
                      ("dotenv", {"load_dotenv": lambda *a, **k: None})):
    try:
        __import__(_name)
    except ImportError:
        _mod = types.ModuleType(_name)
        for _k, _v in _attrs.items():
            setattr(_mod, _k, _v)
        sys.modules[_name] = _mod

from features.trades import match_trade_scoring_period

BROADCAST = 1794380179539  # the real 2027 trade broadcast, ms epoch


def tx(type_, sp, when):
    return {"type": type_, "scoringPeriodId": sp, "proposedDate": when}


class TestMatchTradeScoringPeriod(unittest.TestCase):
    def test_future_roster_inside_window_does_not_win(self):
        # The real transaction list shape: the FUTURE_ROSTER entries for
        # scoring period 28 sit ahead of the TRADE_UPHOLD in list order.
        txs = [
            tx("FUTURE_ROSTER", 28, BROADCAST + 75722),
            tx("FUTURE_ROSTER", 28, BROADCAST + 79397),
            tx("TRADE_UPHOLD", 22, BROADCAST - 43),
        ]
        self.assertEqual(match_trade_scoring_period(txs, BROADCAST), 22)

    def test_closest_trade_transaction_wins(self):
        txs = [
            tx("TRADE_ACCEPT", 22, BROADCAST - 16 * 60 * 1000),
            tx("TRADE_UPHOLD", 22, BROADCAST - 43),
            tx("TRADE_DECLINE", 21, BROADCAST - 20 * 60 * 1000),
        ]
        self.assertEqual(match_trade_scoring_period(txs, BROADCAST), 22)

    def test_fallback_to_closest_any_kind(self):
        txs = [tx("ROSTER", 22, BROADCAST + 5000),
               tx("FUTURE_ROSTER", 28, BROADCAST + 60000)]
        self.assertEqual(match_trade_scoring_period(txs, BROADCAST), 22)

    def test_no_match_defaults_to_first_period(self):
        txs = [tx("TRADE_UPHOLD", 22, BROADCAST - 3600000)]
        self.assertEqual(match_trade_scoring_period(txs, BROADCAST), 1)
        self.assertEqual(match_trade_scoring_period([], BROADCAST), 1)


if __name__ == "__main__":
    unittest.main()
