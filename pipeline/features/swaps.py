"""Bench Regret: lineup swaps that would be flipping this week's matchup.

For every day of the live week, take a bench player who played and put his real line in place of a
starter he was eligible to replace (a starter who played, or one who sat out). Re-score the week
against the opponent's current totals. Only swaps that improve the result are kept.
"""
import json

from features.cheerios import ACTIVE_SLOTS, add_back, load_days, score
from features.live import week_days
from matchups import CURRENT

BENCH = 12
SHOWN = 2


def side_swaps(tid, mine, theirs, days, row, date_of, cids):
    w0, _, _, cur = score(mine, theirs, cids)
    found = []
    for sp in range(row["sp0"], row["sp1"] + 1):
        lineup = days.get(sp, {}).get(str(tid))
        if not lineup:
            continue
        starters = [p for p in lineup if p[3] in ACTIVE_SLOTS]
        for x in (p for p in lineup if p[3] == BENCH and p[4] and p[5]):
            for y in starters:
                if len(y) < 8 or y[3] not in x[7] or y[0] == x[0]:
                    continue
                gone = y[5] if (y[4] and y[5]) else {}
                delta = {k: x[5][k] - gone.get(k, 0) for k in x[5]}
                w, l, t, res = score(add_back(mine, delta), theirs, cids)
                if res > cur:
                    found.append({"day": date_of(sp).strftime("%a"), "in": x[1], "out": y[1], "from": [score(mine, theirs, cids)[i] for i in range(3)],
                                  "to": [w, l, t], "cats": w - w0, "_gain": (res - cur, w - w0)})
    found.sort(key=lambda s: s["_gain"], reverse=True)
    seen, keep = set(), []
    for s in found:  # one line per bench player, best swap first
        if s["in"] in seen:
            continue
        seen.add(s["in"])
        keep.append({k: v for k, v in s.items() if k != "_gain"})
    return keep[:SHOWN]


def build(per_season, raw, live):
    if CURRENT not in per_season:
        return {"matchups": []}
    data, rows, teams = per_season[CURRENT]
    days = load_days(raw, CURRENT)
    sched_path, league_path = raw / str(CURRENT) / "proschedule.json", raw / str(CURRENT) / "league.json"
    live_rows = [r for r in rows if r["live"]]
    if not days or not live_rows or not sched_path.exists():
        return {"matchups": []}
    sched = json.loads(sched_path.read_text(encoding="utf-8"))
    league = json.loads(league_path.read_text(encoding="utf-8"))
    _, _, date_of = week_days(league, sched, None)
    cids = [c["id"] for c in data["cats"]]
    out = []
    for r in live_rows:
        out.append({"home": r["home"], "away": r["away"],
                    "home_swaps": side_swaps(r["home"], r["hs"], r["as"], days, r, date_of, cids),
                    "away_swaps": side_swaps(r["away"], r["as"], r["hs"], days, r, date_of, cids)})
    return {"matchups": out}
