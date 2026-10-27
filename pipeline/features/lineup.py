"""Lineup award: the worst healthy starter each completed matchup week.

Each starter-game is scored against the season's average starter-game, stat by stat (turnovers
count against), and a player's week is the sum over his starts. The award goes to the lowest total
among players with at least two starts who did not miss a starter game that week and carry no
injury flag. Weeks still in progress are left out so an award cannot change.
"""
import json

import numpy as np

from features.cheerios import ACTIVE_SLOTS, load_days
from matchups import parse_matchups

STATS = ["0", "1", "2", "3", "6", "11", "13", "14", "15", "16", "17"]
SIGN = np.array([-1 if k == "11" else 1 for k in STATS])
MIN_STARTS = 2
HEALTHY = (None, "ACTIVE", "NORMAL")


def build_season(season, data, rows, teams, days, games):
    """games: {(scoring period, NBA team id)} for every NBA game, so a benched day without a game is not a miss."""
    lines = []  # (sp, team, player, name, slot, played, stats, injury)
    for sp, tm in days.items():
        for tid, rs in tm.items():
            for r in rs:
                if r[3] in ACTIVE_SLOTS:
                    lines.append((sp, tid, r[0], r[1], r[4], r[5], r[6] if len(r) > 6 else None, r[2], sp))
    played = [l for l in lines if l[4] and l[5]]
    if len(played) < 50:
        return {}
    M = np.array([[l[5][k] for k in STATS] for l in played], float)
    mu, sd = M.mean(0), M.std(0) + 1e-9
    weeks = {}
    for r in rows:
        if r["regular"] and not r["live"] and r.get("sp0"):
            weeks.setdefault(r["mp"], (r["sp0"], r["sp1"]))
    out = {}
    for mp, (a, b) in weeks.items():
        agg, missed = {}, set()
        for sp, tid, pid, name, pl, st, inj, pro, _ in lines:
            if not (a <= sp <= b):
                continue
            if not pl or not st:
                if (sp, pro) in games:
                    missed.add(pid)
                continue
            z = float(((np.array([st[k] for k in STATS]) - mu) / sd * SIGN).sum())
            e = agg.setdefault(pid, {"tid": tid, "name": name, "starts": 0, "score": 0.0, "inj": inj})
            e["starts"] += 1; e["score"] += z; e["inj"] = inj
        cands = [(v["score"], pid, v) for pid, v in agg.items()
                 if v["starts"] >= MIN_STARTS and pid not in missed and v["inj"] in HEALTHY]
        if not cands:
            continue
        score, pid, v = min(cands, key=lambda c: c[0])
        best_score, best_pid, best_v = max(cands, key=lambda c: c[0])
        t = teams[int(v["tid"])]
        bt = teams[int(best_v["tid"])]
        out[str(mp)] = {
            "name": v["name"], "owner": t["owner_name"], "team": t["name"],
            "starts": v["starts"], "score": round(score, 1),
            "worst": {"name": v["name"], "owner": t["owner_name"], "team": t["name"], "starts": v["starts"], "score": round(score, 1)},
            "best": {"name": best_v["name"], "owner": bt["owner_name"], "team": bt["name"], "starts": best_v["starts"], "score": round(best_score, 1)},
        }
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
        sched = json.loads((raw / str(season) / "proschedule.json").read_text(encoding="utf-8"))
        games = {(g["sp"], t) for g in sched["games"] for t in (g["home"], g["away"])}
        res = build_season(season, data, rows, teams, days, games)
        if res:
            seasons[str(season)] = res
    return {"seasons": seasons}
