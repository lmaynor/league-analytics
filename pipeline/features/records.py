"""League records: single-week highs and lows, streaks, season luck, career oddities."""
import statistics
from collections import defaultdict

from cats import RATIO, label
from matchups import CURRENT


def build_records(per_season):
    entries = []  # one per team-week
    for season, (data, rows, teams) in per_season.items():
        for r in rows:
            if r["tier"].endswith("CONSOLATION_LADDER") or r["live"]:
                continue
            for me, opp, mine, theirs, cw, cl in ((r["home"], r["away"], r["hs"], r["as"], r["hw"], r["aw"]),
                                                   (r["away"], r["home"], r["as"], r["hs"], r["aw"], r["hw"])):
                if not mine.get("0"):
                    continue  # unplayed / empty week
                entries.append({"season": season, "mp": r["mp"], "team": teams[me]["name"], "owner": teams[me]["owner_name"],
                                "opp": teams[opp]["name"], "s": mine, "cw": cw, "cl": cl, "t": r["t"]})
    # All-Star breaks and two-week finals are not comparable weeks: keep weeks near each season's typical scoring volume
    import statistics
    wk_pts = defaultdict(list)
    for e in entries:
        wk_pts[(e["season"], e["mp"])].append(e["s"]["0"])
    wk_avg = {k: sum(v) / len(v) for k, v in wk_pts.items()}
    typical = {}
    for (season, _), a in wk_avg.items():
        typical.setdefault(season, []).append(a)
    typical = {k: statistics.median(v) for k, v in typical.items()}
    all_entries = entries
    entries = [e for e in entries if 0.85 <= wk_avg[(e["season"], e["mp"])] / typical[e["season"]] <= 1.15]
    recs = []

    def add(group, title, blurb, e, value, pick):
        recs.append({"group": group, "title": title, "blurb": blurb, "who": e["owner"], "team": e["team"], "season": e["season"],
                     "when": f"{e['season']} wk {e['mp']}", "vs": e["opp"], "value": value, "extra": pick})

    def stat_rec(cid, group, title, blurb, hi=True, fmt=lambda v: f"{v:.0f}", where=lambda e: True):
        pool = [e for e in entries if e["s"].get(str(cid)) is not None and where(e)]
        if not pool:
            return
        e = max(pool, key=lambda e: e["s"][str(cid)]) if hi else min(pool, key=lambda e: e["s"][str(cid)])
        add(group, title, blurb, e, f"{fmt(e['s'][str(cid)])} {label(cid)}", None)

    pct = lambda v: f"{v * 100:.1f}%"
    def ratio(e, c):
        made, att = RATIO[c]
        return e["s"][str(made)] / e["s"][str(att)] if e["s"].get(str(att)) else None
    for e in entries:
        e["s"]["19"] = ratio(e, 19) if e["s"].get("14") else None
        e["s"]["20"] = ratio(e, 20) if e["s"].get("16") else None

    stat_rec(0, "fame", "Scoring Explosion", "The most points anyone has dropped in a single week.")
    stat_rec(6, "fame", "Glass Cleaner", "Most rebounds in a week. Someone's bigs ate.")
    stat_rec(3, "fame", "Dime Machine", "Most assists in a week.")
    stat_rec(2, "fame", "Pickpocket", "Most steals in a week.")
    stat_rec(1, "fame", "Rejection District", "Most blocks in a week. Not in my house.")
    stat_rec(17, "fame", "Rain Man", "Most threes in a week.")
    stat_rec(11, "fame", "Butter Hands", "Fewest turnovers in a week (min. 300 points).", hi=False, where=lambda e: e["s"]["0"] > 300)
    stat_rec(19, "fame", "Splash Accuracy", "Best FG% in a week (min. 150 attempts).", fmt=pct, where=lambda e: (e["s"].get("14") or 0) >= 150)
    stat_rec(20, "fame", "Free Money", "Best FT% in a week (min. 50 attempts).", fmt=pct, where=lambda e: (e["s"].get("16") or 0) >= 50)
    stat_rec(0, "shame", "Offensive Drought", "The fewest points in a week by a team that still showed up (min. 100).", hi=False, where=lambda e: e["s"]["0"] > 100)
    stat_rec(11, "shame", "Turnover Festival", "Most turnovers in a week. Careful with it.")
    stat_rec(19, "shame", "Bricklayer", "Worst FG% in a week (min. 150 attempts).", hi=False, fmt=pct, where=lambda e: (e["s"].get("14") or 0) >= 150)
    stat_rec(20, "shame", "Can't Hit a Free One", "Worst FT% in a week (min. 50 attempts).", hi=False, fmt=pct, where=lambda e: (e["s"].get("16") or 0) >= 50)
    stat_rec(1, "shame", "Blocked Out of the League", "Fewest blocks in a week (min. 100 points).", hi=False, where=lambda e: e["s"]["0"] > 100)

    losses = [e for e in entries if e["cl"] > e["cw"]]
    wins = [e for e in entries if e["cw"] > e["cl"]]
    if losses:
        e = max(losses, key=lambda e: e["s"]["0"])
        add("shame", "Scored Plenty, Lost Anyway", "Most points in a week by a team that still lost.", e, f"{e['s']['0']:.0f} PTS in a {e['cw']}-{e['cl']} loss", None)
    if wins:
        e = min(wins, key=lambda e: e["s"]["0"])
        add("fun", "Highway Robbery", "Fewest points in a week by a team that still won.", e, f"{e['s']['0']:.0f} PTS and a W", None)
    ties = sum(1 for e in entries if e["cw"] == e["cl"]) // 2
    recs.append({"group": "fun", "title": "Nobody Wins", "blurb": "Matchups that ended in an exact category tie.", "who": "the league", "team": "", "season": None,
                 "when": "all time", "vs": "", "value": f"{ties} ties", "extra": None})

    # streaks per owner across seasons
    by_owner = {}
    for e in sorted(all_entries, key=lambda e: (e["season"], e["mp"])):
        by_owner.setdefault(e["owner"], []).append(e)
    best = {"W": ("", 0, ""), "L": ("", 0, "")}
    for owner, es in by_owner.items():
        run, kind, start = 0, None, None
        for e in es:
            k = "W" if e["cw"] > e["cl"] else "L" if e["cw"] < e["cl"] else None
            if k and k == kind:
                run += 1
            else:
                kind, run, start = k, 1 if k else 0, f"{e['season']} wk {e['mp']}"
            if k and run > best[k][1]:
                best[k] = (owner, run, start)
    for k, group, title, blurb in (("W", "fame", "Hot Streak", "Longest winning streak, across seasons."), ("L", "shame", "Cold Front", "Longest losing streak, across seasons.")):
        owner, n, start = best[k]
        if n:
            recs.append({"group": group, "title": title, "blurb": blurb, "who": owner, "team": "", "season": int(start.split()[0]), "when": f"from {start}", "vs": "", "value": f"{n} straight", "extra": None})

    # season and career
    seasons = []
    for season, (data, _, _) in per_season.items():
        if not data["complete"]:
            continue
        for t in data["standings"]:
            seasons.append((season, t))
    def srec(group, title, blurb, key, hi, fmt, name):
        if not seasons:
            return
        season, t = (max if hi else min)(seasons, key=key)
        recs.append({"group": group, "title": title, "blurb": blurb, "who": t["owner_name"], "team": t["name"], "season": season, "when": str(season), "vs": "",
                     "value": fmt(t), "extra": None})
    srec("fame", "Best Regular Season", "Highest category win rate over a full regular season.", lambda x: x[1]["cat_pct"], True, lambda t: f"{t['cat_pct'] * 100:.1f}% of cats, {t['w']}-{t['l']}-{t['t']}", "")
    srec("shame", "Worst Regular Season", "Lowest category win rate over a full regular season.", lambda x: x[1]["cat_pct"], False, lambda t: f"{t['cat_pct'] * 100:.1f}% of cats, {t['w']}-{t['l']}-{t['t']}", "")
    srec("fame", "Blessed Schedule", "Most matchup wins above xWin.", lambda x: x[1]["luck"], True, lambda t: f"+{t['luck']:.1f} wins of luck", "")
    srec("shame", "Cursed Schedule", "Most matchup wins below xWin.", lambda x: x[1]["luck"], False, lambda t: f"{t['luck']:.1f} wins of luck", "")
    srec("shame", "Heartbreak Season", "Most one-category losses in a regular season.", lambda x: x[1]["one_cat_l"], True, lambda t: f"{t['one_cat_l']} one-cat losses", "")

    career = {}
    for season, t in seasons:
        c = career.setdefault(t["owner_name"], {"spoons": 0, "close_l": 0, "close_w": 0, "swept": 0, "sweeps": 0})
        c["close_l"] += t["one_cat_l"]; c["close_w"] += t["one_cat_w"]
        n = len(per_season[season][0]["standings"])
        c["spoons"] += t["final_rank"] == n
    for e in all_entries:  # sweeps count playoffs too
        c = career.setdefault(e["owner"], {"spoons": 0, "close_l": 0, "close_w": 0, "swept": 0, "sweeps": 0})
        c["sweeps"] += e["cw"] == 9
        c["swept"] += e["cl"] == 9

    def crec(group, title, blurb, key, fmt):
        if not career:
            return
        top = max(c[key] for c in career.values())
        owners = [o for o, c in career.items() if c[key] == top]
        c = {key: top}
        if top and len(owners) <= 3:
            recs.append({"group": group, "title": title, "blurb": blurb, "who": ", ".join(sorted(owners)), "team": "", "season": None, "when": "career", "vs": "", "value": fmt(c[key]), "extra": None})
    crec("shame", "Wooden Spoon Collector", "Most last-place finishes.", "spoons", lambda n: f"{n} last place" + ("s" if n != 1 else "") + " each" )
    crec("shame", "Heartbreak Kid", "Most career losses by exactly one category.", "close_l", lambda n: f"{n} one-cat losses")
    crec("fun", "Ice in the Veins", "Most career wins by exactly one category.", "close_w", lambda n: f"{n} one-cat wins")
    crec("fun", "The Terminator", "Most 9-0 sweeps handed out.", "sweeps", lambda n: f"{n} sweep" + ("s" if n != 1 else ""))
    crec("shame", "Punching Bag", "Most times swept 0-9.", "swept", lambda n: f"swept {n} time" + ("s" if n != 1 else ""))
    for r in recs:
        r["new"] = r["season"] == CURRENT
    return recs
