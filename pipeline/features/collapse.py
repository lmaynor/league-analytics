"""Biggest throw: the lost matchup where the loser's projected win chance fell furthest.

Each day of a completed matchup gets a projected win chance for both teams, from the same blend the
rolling chart uses: the season strength model (category share before the week) and that day's
category lead (rebuilt from daily starter stats, which match ESPN's weekly totals exactly). The
collapse is the loser's highest daily chance minus its chance on the last day before the final.
"""
import json
from math import exp

from features.cheerios import ACTIVE_SLOTS, load_days
from matchups import cat_result, parse_matchups, pct_value
from features.race import K

STATS = [0, 1, 2, 3, 6, 11, 13, 14, 15, 16, 17]
MIN_PEAK = 0.55  # the loser was at least a 55% favorite at some point


def partial(days, tid, sp0, d):
    tot = dict.fromkeys(STATS, 0.0)
    for sp in range(sp0, d + 1):
        for row in days.get(sp, {}).get(str(tid), []):
            if row[3] in ACTIVE_SLOTS and row[4] and row[5]:
                for k in STATS: tot[k] += row[5][str(k)]
    return tot


def lead(a, b, cids):
    """Share of categories the first team leads (0.5 = even), counting ties as even."""
    wa = wb = 0
    for c in cids:
        va = pct_value(a, c) if c in (19, 20) else a[c]
        vb = pct_value(b, c) if c in (19, 20) else b[c]
        r = cat_result(va, vb, c)
        wa += r == 1; wb += r == -1
    return (wa - wb + len(cids)) / (2 * len(cids))


def build_season(season, data, rows, teams, days):
    cids = [c["id"] for c in data["cats"]]
    done = [r for r in rows if r["regular"] and not r["live"]]
    out = {}
    for mp in sorted({r["mp"] for r in done}):
        cw, cn = {}, {}
        for r in done:
            if r["mp"] >= mp: continue
            for t, w, l in ((r["home"], r["hw"], r["aw"]), (r["away"], r["aw"], r["hw"])):
                cw[t] = cw.get(t, 0) + w + 0.5 * r["t"]; cn[t] = cn.get(t, 0) + w + l + r["t"]
        share = lambda t: (cw.get(t, 0) + 13.5) / (cn.get(t, 0) + 27)
        for r in (x for x in done if x["mp"] == mp):
            if r["winner"] is None or r["sp1"] - r["sp0"] < 2: continue
            h, a = r["home"], r["away"]
            strength = 1 / (1 + exp(-K * (share(h) - share(a))))
            daily = []
            has_history = cn.get(h, 0) > 0 or cn.get(a, 0) > 0
            for d in range(r["sp0"], r["sp1"]):  # the final day is the ESPN result
                lh = lead(partial(days, h, r["sp0"], d), partial(days, a, r["sp0"], d), cids)
                daily.append((0.5 * strength + 0.5 * lh) if has_history else lh)
            if not daily: continue
            for me, opp, p_series, final_me, final_opp in (
                (h, a, daily, r["hw"], r["aw"]), (a, h, [1 - p for p in daily], r["aw"], r["hw"])):
                if final_me >= final_opp: continue  # losses only
                peak = max(p_series)
                if peak < MIN_PEAK: continue
                drop = peak - p_series[-1]
                cur = out.get(str(mp))
                if cur is None or drop > cur["drop"]:
                    out[str(mp)] = {"team": teams[me]["name"], "owner": teams[me]["owner_name"], "opp": teams[opp]["name"],
                                    "peak": round(peak, 3), "end": round(p_series[-1], 3), "drop": round(drop, 3),
                                    "final": final_me, "final_opp": final_opp, "ties": r["t"]}
    return out


def build(per_season, raw):
    seasons = {}
    for season in sorted(per_season):
        days = load_days(raw, season)
        if not days:
            continue
        data, _, teams = per_season[season]
        league = json.loads((raw / str(season) / "league.json").read_text(encoding="utf-8"))
        _, rows = parse_matchups(league, season)
        res = build_season(season, data, rows, teams, days)
        if res:
            seasons[str(season)] = res
    return {"seasons": seasons}
