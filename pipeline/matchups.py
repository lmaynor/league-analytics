"""Shared matchup parsing: turn ESPN schedule entries into category results."""
from cats import RATIO, REVERSE, cat_ids
from season import current_season

CURRENT = current_season()
ALL_STATS = [0, 1, 2, 3, 6, 11, 13, 14, 15, 16, 17, 19, 20]


def cat_result(a, b, cid):
    """+1 if a wins the category, -1 if loses, 0 tie."""
    if a is None or b is None or abs(a - b) < 1e-9:
        return 0
    better = a < b if cid in REVERSE else a > b
    return 1 if better else -1


def side_stats(side, use_live):
    cs = (side.get("cumulativeScoreLive") if use_live else None) or side.get("cumulativeScore") or {}
    return {int(k): v.get("score") for k, v in (cs.get("scoreByStat") or {}).items() if int(k) in ALL_STATS}


def parse_matchups(league, season):
    cids = cat_ids(league["settings"])
    cur_mp = league["status"].get("currentMatchupPeriod")
    rows = []
    for m in league["schedule"]:
        if "away" not in m or "home" not in m:
            continue
        mp = m["matchupPeriodId"]
        use_live = season == CURRENT and mp == cur_mp
        h, a = side_stats(m["home"], use_live), side_stats(m["away"], use_live)
        if not h or not a:
            continue
        res = [cat_result(h.get(c), a.get(c), c) for c in cids]
        hw, aw, t = res.count(1), res.count(-1), res.count(0)
        tier = m.get("playoffTierType", "NONE")
        rows.append({
            "mp": mp, "tier": tier, "regular": tier == "NONE", "playoff": tier == "WINNERS_BRACKET",
            "live": use_live,
            "home": m["home"]["teamId"], "away": m["away"]["teamId"],
            "sp0": min(map(int, m["home"].get("pointsByScoringPeriod") or [0])),
            "sp1": max(map(int, m["home"].get("pointsByScoringPeriod") or [0])),
            "hs": {str(k): v for k, v in h.items()}, "as": {str(k): v for k, v in a.items()},
            "hw": hw, "aw": aw, "t": t,
            "winner": m["home"]["teamId"] if hw > aw else m["away"]["teamId"] if aw > hw else None,
        })
    return cids, rows


def pct_value(stats, cid):
    """Category value from component totals when possible."""
    if cid in RATIO:
        made, att = RATIO[cid]
        return stats[made] / stats[att] if stats.get(att) else None
    return stats.get(cid)
