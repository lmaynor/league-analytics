"""Player superlatives: yearbook-style awards from the daily rosters (Most Likely to Be Out, Block Party...)."""
import json
from collections import defaultdict

from features.cheerios import ACTIVE_SLOTS, finished_games, load_days
from matchups import CURRENT

STATS = ["0", "1", "2", "3", "6", "11", "13", "14", "15", "16", "17"]
KINGS = [  # stat id, title, blurb, unit
    ("0", "Bucket Getter", "Most points while in a starting slot.", "PTS"),
    ("6", "Glass Eater", "Most rebounds while in a starting slot.", "REB"),
    ("3", "Dime Machine", "Most assists while in a starting slot.", "AST"),
    ("2", "Pickpocket", "Most steals while in a starting slot.", "STL"),
    ("1", "Block Party", "Most blocks while in a starting slot.", "BLK"),
    ("17", "Rain Man", "Most threes while in a starting slot.", "3PM"),
    ("11", "Butterfingers", "Most turnovers while in a starting slot.", "TO"),
]
MIN_FGA, MIN_FTA = 200, 100


def collect(days, games_done):
    """Per player: totals while starting, games missed, longest run of team games played, owners, best day."""
    agg = {}
    for sp in sorted(days):
        for tid, rows in days[sp].items():
            for row in rows:
                pid, name, pro, slot, played, stats = row[0], row[1], row[2], row[3], row[4], row[5]
                a = agg.setdefault(pid, {"name": name, "tot": dict.fromkeys(STATS, 0.0), "gp": 0, "missed": 0, "run": 0, "best_run": 0,
                                         "teams": set(), "best_day": (0, None)})
                a["teams"].add(tid)
                if games_done.get((sp, pro)):
                    if played:
                        a["run"] += 1
                        a["best_run"] = max(a["best_run"], a["run"])
                    else:
                        a["run"] = 0
                        if slot in ACTIVE_SLOTS:
                            a["missed"] += 1
                if played and stats:
                    day = (stats["0"] + stats["6"] + stats["3"] + 3 * stats["2"] + 3 * stats["1"] + stats["17"] - stats["11"], sp)
                    if day[0] > a["best_day"][0]:
                        a["best_day"] = (day[0], sp, {k: stats[k] for k in ("0", "6", "3", "2", "1", "17")})
                    if slot in ACTIVE_SLOTS:
                        a["gp"] += 1
                        for k in STATS:
                            a["tot"][k] += stats[k]
    return agg


def build(per_season, raw):
    recs = []
    for season in sorted(per_season):
        days = load_days(raw, season)
        sched_path = raw / str(season) / "proschedule.json"
        if not days or not sched_path.exists() or (season == CURRENT and len(days) < 14):  # too early to crown anyone
            continue
        agg = collect(days, finished_games(json.loads(sched_path.read_text(encoding="utf-8"))))
        teams = per_season[season][2]
        owners = lambda a: ", ".join(sorted({teams[int(t)]["owner_name"] for t in a["teams"]})[:3])

        def add(group, title, blurb, a, value):
            recs.append({"group": group, "title": title, "blurb": blurb, "who": a["name"], "team": owners(a), "season": season,
                         "when": str(season), "vs": "", "value": value, "extra": None, "new": season == CURRENT})

        if len(agg) < 20:
            continue
        top = lambda key, hi=True, pool=None: (max if hi else min)(pool or agg.values(), key=key)
        add("yearbook", "Most Likely to Be Out Tonight", "Most starter games missed.", top(lambda a: a["missed"]), f"{top(lambda a: a['missed'])['missed']} games")
        iron = top(lambda a: a["best_run"])
        add("yearbook", "Iron Man", "Longest run of his team's games played without missing one.", iron, f"{iron['best_run']} straight")
        wt = top(lambda a: len(a["teams"]))
        if len(wt["teams"]) > 1:
            add("yearbook", "Most Well-Traveled", "Wore the most fantasy jerseys in one season.", wt, f"{len(wt['teams'])} teams")
        best = top(lambda a: a["best_day"][0])
        s = best["best_day"][2]
        add("yearbook", "Stat Sheet Stuffer", "Biggest single game: points, rebounds, assists, steals, blocks and threes combined.", best,
            f"{s['0']:.0f} PTS, {s['6']:.0f} REB, {s['3']:.0f} AST")
        for sid, title, blurb, unit in KINGS:
            w = top(lambda a: a["tot"][sid])
            add("kings", title, blurb, w, f"{w['tot'][sid]:.0f} {unit}")
        fg = [a for a in agg.values() if a["tot"]["14"] >= MIN_FGA]
        ft = [a for a in agg.values() if a["tot"]["16"] >= MIN_FTA]
        rate = lambda a, m, t: a["tot"][m] / a["tot"][t]
        if fg:
            w = top(lambda a: rate(a, "13", "14"), True, fg)
            add("kings", "Mr. Efficient", f"Best FG% while starting (min. {MIN_FGA} attempts).", w, f"{rate(w, '13', '14') * 100:.1f}% FG")
            w = top(lambda a: rate(a, "13", "14"), False, fg)
            add("shame", "Brick Mason", f"Worst FG% while starting (min. {MIN_FGA} attempts).", w, f"{rate(w, '13', '14') * 100:.1f}% FG")
        if ft:
            w = top(lambda a: rate(a, "15", "16"), True, ft)
            add("kings", "Mr. Automatic", f"Best FT% while starting (min. {MIN_FTA} attempts).", w, f"{rate(w, '15', '16') * 100:.1f}% FT")
            w = top(lambda a: rate(a, "15", "16"), False, ft)
            add("shame", "Can't Buy a Free One", f"Worst FT% while starting (min. {MIN_FTA} attempts).", w, f"{rate(w, '15', '16') * 100:.1f}% FT")
    return {"records": recs}
