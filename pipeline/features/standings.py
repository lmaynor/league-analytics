"""Standings, xWin and luck, category strength and power rank for one season."""
from collections import defaultdict

from cats import RATIO, REVERSE, label
from matchups import CURRENT, cat_result, parse_matchups, pct_value


def build_season(season, league, owners_cfg):
    cids, rows = parse_matchups(league, season)
    teams = {}
    members = {m["id"]: m.get("displayName") for m in league.get("members", [])}
    for t in league["teams"]:
        owner = t.get("primaryOwner")
        owner = (owners_cfg.get(owner) or {}).get("same_as") or owner  # merged duplicate accounts
        teams[t["id"]] = {
            "id": t["id"], "name": t["name"], "abbrev": t.get("abbrev"), "logo": t.get("logo"),
            "owner": owner, "owner_name": (owners_cfg.get(owner) or {}).get("name") or members.get(owner) or "?",
            "final_rank": t.get("rankCalculatedFinal") or None,
        }

    reg = [r for r in rows if r["regular"]]
    rec = {tid: dict(w=0, l=0, t=0, cw=0, cl=0, ct=0, one_cat_w=0, one_cat_l=0, sweeps=0, swept=0) for tid in teams}
    tot = {tid: defaultdict(float) for tid in teams}
    weeks = sorted({r["mp"] for r in reg})
    weekly = {tid: [] for tid in teams}  # chronological cat-win share per team

    for r in reg:
        for me, opp, mine, theirs, cw, cl in ((r["home"], r["away"], r["hs"], r["as"], r["hw"], r["aw"]),
                                               (r["away"], r["home"], r["as"], r["hs"], r["aw"], r["hw"])):
            x = rec[me]
            x["cw"] += cw; x["cl"] += cl; x["ct"] += r["t"]
            if cw > cl:
                x["w"] += 1
                x["one_cat_w"] += cw - cl == 1
                x["sweeps"] += cl == 0 and r["t"] == 0
            elif cw < cl:
                x["l"] += 1
                x["one_cat_l"] += cl - cw == 1
                x["swept"] += cw == 0 and r["t"] == 0
            else:
                x["t"] += 1
            for k, v in mine.items():
                tot[me][int(k)] += v or 0
            tot[me]["weeks"] += 1
            weekly[me].append((r["mp"], (cw + 0.5 * r["t"]) / len(cids)))

    # all-play (each week vs every other team) -> expected matchup wins and luck
    by_week = defaultdict(dict)
    for r in reg:
        by_week[r["mp"]][r["home"]] = r["hs"]
        by_week[r["mp"]][r["away"]] = r["as"]
    xw = defaultdict(float)
    for mp, wk in by_week.items():
        for a, sa in wk.items():
            for b, sb in wk.items():
                if a == b:
                    continue
                res = [cat_result(sa.get(str(c)), sb.get(str(c)), c) for c in cids]
                w, l = res.count(1), res.count(-1)
                xw[a] += (1 if w > l else 0.5 if w == l else 0) / (len(wk) - 1)

    # category strength: season totals, ranks, z-scores
    strength = {}
    for tid in teams:
        n = tot[tid]["weeks"] or 1
        strength[tid] = {}
        for c in cids:
            v = pct_value(tot[tid], c) if c in RATIO else tot[tid][c] / n
            strength[tid][str(c)] = v
    cat_rank = {}
    for c in cids:
        vals = {tid: strength[tid][str(c)] for tid in teams if strength[tid][str(c)] is not None}
        order = sorted(vals, key=lambda t: vals[t], reverse=c not in REVERSE)
        mean = sum(vals.values()) / max(len(vals), 1)
        sd = (sum((v - mean) ** 2 for v in vals.values()) / max(len(vals), 1)) ** 0.5 or 1
        for i, tid in enumerate(order):
            z = (vals[tid] - mean) / sd * (-1 if c in REVERSE else 1)
            cat_rank.setdefault(tid, {})[str(c)] = {"rank": i + 1, "z": round(z, 2)}

    standings = []
    for tid, x in rec.items():
        gp = x["w"] + x["l"] + x["t"]
        tc = x["cw"] + x["cl"] + x["ct"]
        recent = [s for _, s in sorted(weekly[tid])[-4:]]
        row = {
            **teams[tid], **x, "gp": gp,
            "win_pct": (x["w"] + 0.5 * x["t"]) / gp if gp else 0,
            "cat_pct": (x["cw"] + 0.5 * x["ct"]) / tc if tc else 0,
            "recent_cat_pct": sum(recent) / len(recent) if recent else 0,
            "xw": round(xw[tid], 2), "luck": round(x["w"] + 0.5 * x["t"] - xw[tid], 2),
            "strength": strength[tid], "cat_rank": cat_rank.get(tid, {}),
        }
        standings.append(row)
    standings.sort(key=lambda s: (-s["win_pct"], -s["cat_pct"]))
    for i, s in enumerate(standings):
        s["seed"] = i + 1
    power = sorted(standings, key=lambda s: -(0.6 * s["cat_pct"] + 0.4 * s["recent_cat_pct"]))
    for i, s in enumerate(power):
        s["power"] = i + 1

    return {
        "season": season, "complete": season != CURRENT or not any(r["live"] for r in rows),
        "cats": [{"id": c, "label": label(c), "reverse": c in REVERSE, "pct": c in RATIO} for c in cids],
        "teams": {str(k): v for k, v in teams.items()},
        "standings": standings,
        "weeks": [{"mp": mp, "matchups": [r for r in rows if r["mp"] == mp]} for mp in sorted({r["mp"] for r in rows})],
        "current_mp": league["status"].get("currentMatchupPeriod") if season == CURRENT else None,
    }, rows, teams
