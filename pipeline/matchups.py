"""Shared matchup parsing: turn ESPN schedule entries into category results."""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from cats import RATIO, REVERSE, cat_ids
from season import current_season

CURRENT = current_season()
ALL_STATS = [0, 1, 2, 3, 6, 11, 13, 14, 15, 16, 17, 19, 20]


_weeks = {}


def calendar_weeks(season):
    """[(first sp, last sp)] per matchup week, from the NBA calendar: Monday to Sunday (ET).

    ESPN leaves each week's scoring periods empty for older seasons. This matched ESPN's own weeks
    in 2025 and 2026 once a week with almost no games (the All-Star break) is folded into the next."""
    if season not in _weeks:
        path = Path(__file__).resolve().parent.parent / "data" / "raw" / str(season) / "proschedule.json"
        weeks = []
        if path.exists():
            games = json.loads(path.read_text(encoding="utf-8"))["games"]
            s0 = min(g["sp"] for g in games)  # some seasons have no game on scoring period 1
            first = min(g["t"] for g in games if g["sp"] == s0)
            d1 = dt.datetime.fromtimestamp(first / 1000, ZoneInfo("America/New_York")).date() - dt.timedelta(days=s0 - 1)
            per_sp = {}
            for g in games:
                per_sp[g["sp"]] = per_sp.get(g["sp"], 0) + 1
            blocks, start = [], 1
            for sp in range(1, max(per_sp) + 1):
                if (d1 + dt.timedelta(days=sp - 1)).weekday() == 6:
                    blocks.append((start, sp)); start = sp + 1
            if start <= max(per_sp):
                blocks.append((start, max(per_sp)))
            counts = [sum(per_sp.get(sp, 0) for sp in range(a, b + 1)) for a, b in blocks]
            typical = sorted(counts)[len(counts) // 2]
            carry = None
            for (a, b), n in zip(blocks, counts):
                a = carry if carry is not None else a
                if n < 0.2 * typical:
                    carry = a  # an almost empty week joins the next one
                    continue
                weeks.append((a, b)); carry = None
        _weeks[season] = weeks
    return _weeks[season]


def week_range(entry, season, mp):
    """(first sp, last sp, estimated) for one schedule entry: ESPN's own days if it gives a real span, else the calendar."""
    keys = [int(k) for k in (entry["home"].get("pointsByScoringPeriod") or [])]
    if keys and max(keys) - min(keys) >= 4:
        return min(keys), max(keys), False
    weeks = calendar_weeks(season)
    if 0 < mp <= len(weeks):
        return weeks[mp - 1][0], weeks[mp - 1][1], True
    return (min(keys), max(keys), False) if keys else (0, 0, True)


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
            "sp0": week_range(m, season, mp)[0], "sp1": week_range(m, season, mp)[1], "sp_est": week_range(m, season, mp)[2],
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
