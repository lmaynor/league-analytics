"""Red Cheerios: re-score each week as if no starter had missed a game.

A miss is a starter in an active slot on a day his NBA team played who did not play. Each miss
adds his own per-game average back to the team's totals, which are re-scored against the
opponent's real totals. Doing the same to the opponent shows wins handed over by their absences.
"""
import json
import time
from collections import defaultdict

from cats import RATIO, REVERSE, label
from cats import label
from matchups import CURRENT, cat_result, pct_value

ACTIVE_SLOTS = {0, 1, 2, 3, 4, 5, 6, 11}  # PG SG SF PF C G F UTIL; 12 = bench, 13 = IR
STAT_IDS = ["0", "1", "2", "3", "6", "11", "13", "14", "15", "16", "17"]
MIN_GAMES_FOR_BASELINE = 3
GAME_MS = 3 * 3600 * 1000  # a game counts as over ~3h after tip, even if ESPN has not marked it official


def cat_zscores(base):
    """{pid: {cat label: z}}: how far each player's per-game output sits above the pool in each category.

    Turnovers are flipped (fewer is better). FG% and FT% use makes above what the league rate would give."""
    fg = sum(m["13"] for m in base.values()) / max(sum(m["14"] for m in base.values()), 1)
    ft = sum(m["15"] for m in base.values()) / max(sum(m["16"] for m in base.values()), 1)
    feats = {pid: {label(0): m["0"], label(6): m["6"], label(3): m["3"], label(2): m["2"], label(1): m["1"],
                   label(17): m["17"], label(11): -m["11"], label(19): m["13"] - fg * m["14"],
                   label(20): m["15"] - ft * m["16"]} for pid, m in base.items()}
    z = {pid: {} for pid in base}
    for cat in next(iter(feats.values())):
        vals = [f[cat] for f in feats.values()]
        mean = sum(vals) / len(vals)
        sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 or 1
        for pid, f in feats.items():
            z[pid][cat] = (f[cat] - mean) / sd
    return z


def strengths(z, m, games):
    """The categories a player is best in, with what his missed games cost (counting stats only)."""
    ids = {label(0): "0", label(6): "6", label(3): "3", label(2): "2", label(1): "1", label(17): "17"}
    top = sorted(z.items(), key=lambda kv: -kv[1])[:2]
    name = lambda c: "Low TO" if c == label(11) else c
    return [{"cat": name(c), "lost": round(m[ids[c]] * games) if c in ids else None} for c, v in top if v > 0.4] or \
           [{"cat": name(top[0][0]), "lost": None}]


def load_days(raw, season):
    d = raw / str(season) / "days"
    if not d.exists():
        return None
    days = {}
    for f in d.glob("*.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        days[j["sp"]] = j["teams"]
    return days


def baselines(days):
    """Per-player per-game means over the days he played."""
    tot, n = defaultdict(lambda: dict.fromkeys(STAT_IDS, 0.0)), defaultdict(int)
    for teams in days.values():
        for rows in teams.values():
            for row in rows:
                pid, played, stats = row[0], row[4], row[5]
                if played and stats:
                    n[pid] += 1
                    for k in STAT_IDS:
                        tot[pid][k] += stats[k]
    return {pid: {k: v / n[pid] for k, v in tot[pid].items()} for pid in n if n[pid] >= MIN_GAMES_FOR_BASELINE}, n


HEALTHY = (None, "ACTIVE", "NORMAL")


def missed_by_team_day(days, games_done, base):
    """{team_id: {sp: [(pid, name)]}} starters who sat out a game their NBA team played.

    A lone one-game absence with no injury flag is treated as rest and ignored. A miss counts
    when ESPN flagged the player (Out, Day-to-Day, ...) or he also missed a neighboring team game."""
    log = defaultdict(list)  # pid -> [(sp, team_id, name, slot, played, inj)] for games his team finished
    for sp in sorted(days):
        for tid, rows in days[sp].items():
            for row in rows:
                pid, name, pro, slot, played = row[0], row[1], row[2], row[3], row[4]
                if games_done.get((sp, pro)):
                    log[pid].append((sp, tid, name, slot, played, row[6] if len(row) > 6 else None))
    out = defaultdict(lambda: defaultdict(list))
    for pid, games in log.items():
        if pid not in base:
            continue
        for i, (sp, tid, name, slot, played, inj) in enumerate(games):
            if played or slot not in ACTIVE_SLOTS:
                continue
            neighbor_out = (i > 0 and not games[i - 1][4]) or (i + 1 < len(games) and not games[i + 1][4])
            if inj not in HEALTHY or neighbor_out:
                out[tid][sp].append((pid, name))
    return out


def add_back(stats, lost):
    """Team totals with the missed games added back (turnovers rise with them, as they would have)."""
    t = {k: (stats.get(k) or 0) for k in stats}
    for k in STAT_IDS:
        t[k] = (stats.get(k) or 0) + lost.get(k, 0)
    for cid, (made, att) in RATIO.items():
        t[str(cid)] = pct_value({int(k): v for k, v in t.items() if k.isdigit()}, cid)
    return t


def score(a, b, cids):
    res = [cat_result(a.get(str(c)), b.get(str(c)), c) for c in cids]
    w, l = res.count(1), res.count(-1)
    return w, l, res.count(0), (1 if w > l else 0 if w < l else 0.5)


def build_season(season, data, rows, teams, days, games_done, fallback=None):
    base, played_n = baselines(days)
    # early in a season few players have 3 games yet: use last season's averages for them
    for pid, v in (fallback or {}).items():
        base.setdefault(pid, v)
    missed = missed_by_team_day(days, games_done, base)
    zs = cat_zscores(base)
    zsum = {pid: sum(z.values()) for pid, z in zs.items()}
    cids = [c["id"] for c in data["cats"]]
    tstat = {str(t): dict(name=teams[t]["name"], owner=teams[t]["owner_name"], games=0, own_cost=0.0, gifts=0.0,
                          cats_cost=0, reg=[0, 0, 0], healthy=[0, 0, 0], who=defaultdict(lambda: [0, 0.0])) for t in teams}
    ouch, player_totals = [], defaultdict(lambda: {"games": 0, "team": "", "value": 0.0, "pid": None})

    def lost_vec(tid, r):
        vec, names = dict.fromkeys(STAT_IDS, 0.0), []
        for sp in range(r["sp0"], r["sp1"] + 1):
            for pid, name in missed.get(str(tid), {}).get(sp, []):
                for k in STAT_IDS:
                    vec[k] += base[pid][k]
                names.append((name, zsum[pid], pid))
        return vec, names

    live = []
    for r in rows:
        if r["live"] and r["hs"].get("0") is not None:
            sides = {}
            for key, me, opp, mine, theirs in (("home_side", r["home"], r["away"], r["hs"], r["as"]), ("away_side", r["away"], r["home"], r["as"], r["hs"])):
                vec, names = lost_vec(me, r)
                aw, al, at, ares = score(mine, theirs, cids)
                hw, hl, ht, hres = score(add_back(mine, vec), theirs, cids)
                by = defaultdict(int)
                for n, _, _ in names:
                    by[n] += 1
                sides[key] = {"games": len(names), "missed": [{"name": n, "games": g} for n, g in sorted(by.items(), key=lambda kv: -kv[1])],
                              "actual": [aw, al, at], "healthy": [hw, hl, ht], "cats_lost": max(0, hw - aw), "flips": hres > ares}
            live.append({"home": r["home"], "away": r["away"], "mp": r["mp"], **sides})
        if r["tier"].endswith("CONSOLATION_LADDER") or not r["hs"].get("0"):  # the week in progress counts too, as it stands
            continue
        sides = ((r["home"], r["away"], r["hs"], r["as"]), (r["away"], r["home"], r["as"], r["hs"]))
        for me, opp, mine, theirs in sides:
            ts = tstat[str(me)]
            aw, al, at, ares = score(mine, theirs, cids)
            vec, names = lost_vec(me, r)
            hw, hl, ht, hres = score(add_back(mine, vec), theirs, cids)
            ovec, _ = lost_vec(opp, r)
            gw, gl, gt, gres = score(mine, add_back(theirs, ovec), cids)
            n_missed = len(names)
            if r["regular"]:
                ts["games"] += n_missed
                ts["own_cost"] += max(0.0, hres - ares)
                ts["gifts"] += max(0.0, ares - gres)
                ts["cats_cost"] += max(0, hw - aw)
                for i, x in enumerate((ares, hres)):
                    tgt = ts["reg"] if i == 0 else ts["healthy"]
                    tgt[0 if x == 1 else 1 if x == 0 else 2] += 1
                for name, val, pid in names:
                    ts["who"][name][0] += 1
                    ts["who"][name][1] = val
                    player_totals[name]["games"] += 1
                    player_totals[name]["team"] = ts["name"]
                    player_totals[name]["value"] = val
                    player_totals[name]["pid"] = pid
            if hres > ares:
                top = sorted(set((n, v) for n, v, _ in names), key=lambda x: -x[1])[:3]
                ouch.append({"season": season, "mp": r["mp"], "team": ts["name"], "owner": ts["owner"], "opp": teams[opp]["name"],
                             "actual": f"{aw}-{al}" + (f"-{at}" if at else ""), "healthy": f"{hw}-{hl}" + (f"-{ht}" if ht else ""),
                             "swing": hw - aw, "games": n_missed, "players": [n for n, _ in top],
                             "playoff": not r["regular"]})
    out_teams = []
    for tid, ts in tstat.items():
        who = sorted(ts["who"].items(), key=lambda kv: (-kv[1][0] * kv[1][1]))[:3]
        out_teams.append({"team": ts["name"], "owner": ts["owner"], "games_missed": ts["games"],
                          "wins_lost": round(ts["own_cost"], 1), "wins_gifted": round(ts["gifts"], 1),
                          "cats_lost": ts["cats_cost"], "record": ts["reg"], "healthy_record": ts["healthy"],
                          "most_missed": [{"name": n, "games": g} for n, (g, _) in who]})
    out_teams.sort(key=lambda t: -t["wins_lost"])
    players = sorted(({"name": n, **v} for n, v in player_totals.items()), key=lambda p: -p["games"] * p["value"])[:10]
    ouch.sort(key=lambda o: (-o["swing"], -o["games"]))
    return {"teams": out_teams, "ouch": ouch[:12], "players": [{"name": p["name"], "team": p["team"], "games": p["games"],
            "hits": strengths(zs[p["pid"]], base[p["pid"]], p["games"])} for p in players],
            "complete": data["complete"], "live": live}


def build(per_season, raw):
    out = {}
    prev_base = {}
    for season, (data, rows, teams) in sorted(per_season.items()):
        days = load_days(raw, season)
        sched = json.loads((raw / str(season) / "proschedule.json").read_text(encoding="utf-8")) if (raw / str(season) / "proschedule.json").exists() else None
        if not days or not sched:
            continue
        now = time.time() * 1000
        games_done = {(g["sp"], t): bool(g["final"] or g["t"] + GAME_MS < now) for g in sched["games"] for t in (g["home"], g["away"])}
        out[str(season)] = build_season(season, data, rows, teams, days, games_done, prev_base)
        prev_base = baselines(days)[0]
    return {"seasons": out}
