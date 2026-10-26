"""Bench Regret: whole-week lineup swaps that would be flipping this week's matchup.

Lineups lock for the week (each player at his first game), so a swap means starting a benched
player in a starter's slot for the whole week. For each team, take a bench player who played this
week and put his week of real stats in place of a starter he was eligible to replace (a starter
who played, or one who sat out all week). Re-score against the opponent's current totals and keep
only swaps that improve the result.
"""
from collections import Counter

from features.cheerios import ACTIVE_SLOTS, add_back, load_days, score
from matchups import CURRENT

BENCH = 12
SHOWN = 2
STATS = ["0", "1", "2", "3", "6", "11", "13", "14", "15", "16", "17"]


def week_players(days, tid, sp0, sp1):
    """{pid: {name, slot, elig, stats}}: each player's lineup slot for the week and his stats over it."""
    seen = {}
    for sp in range(sp0, sp1 + 1):
        for p in days.get(sp, {}).get(str(tid), []):
            e = seen.setdefault(p[0], {"name": p[1], "slots": [], "elig": [], "stats": dict.fromkeys(STATS, 0.0), "played": 0})
            e["slots"].append(p[3])
            if len(p) > 7:
                e["elig"] = p[7]
            if p[4] and p[5]:
                e["played"] += 1
                for k in STATS:
                    e["stats"][k] += p[5][k]
    for e in seen.values():
        e["slot"] = Counter(e["slots"]).most_common(1)[0][0]  # the lock holds the slot; day-one shuffles before it do not
    return seen


def side_swaps(tid, mine, theirs, days, row, cids):
    w0, l0, t0, cur = score(mine, theirs, cids)
    players = week_players(days, tid, row["sp0"], row["sp1"])
    starters = [p for p in players.values() if p["slot"] in ACTIVE_SLOTS]
    bench = [p for p in players.values() if p["slot"] == BENCH and p["played"]]
    found = []
    for x in bench:
        for y in starters:
            if y["slot"] not in x["elig"]:
                continue
            delta = {k: x["stats"][k] - y["stats"][k] for k in STATS}
            w, l, t, res = score(add_back(mine, delta), theirs, cids)
            if res > cur:
                found.append(((res - cur, w - w0), {"in": x["name"], "out": y["name"], "from": [w0, l0, t0], "to": [w, l, t], "cats": w - w0}))
    found.sort(key=lambda f: f[0], reverse=True)
    seen, keep = set(), []
    for _, s in found:  # one line per bench player, best swap first
        if s["in"] not in seen:
            seen.add(s["in"])
            keep.append(s)
    return keep[:SHOWN]


def build(per_season, raw, live):
    if CURRENT not in per_season:
        return {"matchups": []}
    data, rows, teams = per_season[CURRENT]
    days = load_days(raw, CURRENT)
    live_rows = [r for r in rows if r["live"]]
    if not days or not live_rows:
        return {"matchups": []}
    cids = [c["id"] for c in data["cats"]]
    return {"matchups": [{"home": r["home"], "away": r["away"],
                          "home_swaps": side_swaps(r["home"], r["hs"], r["as"], days, r, cids),
                          "away_swaps": side_swaps(r["away"], r["as"], r["hs"], days, r, cids)} for r in live_rows]}
