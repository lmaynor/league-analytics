"""Player superlatives: yearbook-style awards from the daily rosters (Most Likely to Be Out, Block Party...)."""
import json
import statistics

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
    ("14", "Shot Hog", "Most field goal attempts while in a starting slot.", "FGA"),
    ("16", "Charity Stripe Regular", "Most free throw attempts while in a starting slot.", "FTA"),
]
SINGLE = [  # stat id, title, blurb, unit, shame
    ("17", "Splash Game", "Most threes in a single game.", "3PM", False),
    ("6", "Board Meeting", "Most rebounds in a single game.", "REB", False),
    ("3", "Dime Drop", "Most assists in a single game.", "AST", False),
    ("2", "Sticky Fingers", "Most steals in a single game.", "STL", False),
    ("1", "Swat Team", "Most blocks in a single game.", "BLK", False),
    ("11", "Giveaway Night", "Most turnovers in a single game.", "TO", True),
]
MIN_FGA, MIN_FTA, MIN_GP = 200, 100, 40


def day_score(s):
    return s["0"] + s["6"] + s["3"] + 3 * s["2"] + 3 * s["1"] + s["17"] - s["11"]


def collect(days, games_done):
    """Per player: starting totals, misses, streaks, single-game highs, benched games, owners."""
    agg = {}
    for sp in sorted(days):
        for tid, rows in days[sp].items():
            for row in rows:
                pid, name, pro, slot, played, stats = row[0], row[1], row[2], row[3], row[4], row[5]
                a = agg.setdefault(pid, {"name": name, "tot": dict.fromkeys(STATS, 0.0), "gp": 0, "missed": 0, "run": 0, "best_run": 0,
                                         "teams": set(), "best_day": (-99, None, None), "scores": [], "dd": 0, "g30": 0, "bench": 0,
                                         "single": {}})
                a["teams"].add(tid)
                if games_done.get((sp, pro)):
                    if played:
                        a["run"] += 1
                        a["best_run"] = max(a["best_run"], a["run"])
                    else:
                        a["run"] = 0
                        if slot in ACTIVE_SLOTS:
                            a["missed"] += 1
                if not (played and stats):
                    continue
                if slot not in ACTIVE_SLOTS:
                    a["bench"] += 1  # played while sitting on the bench or in IR
                    continue
                a["gp"] += 1
                for k in STATS:
                    a["tot"][k] += stats[k]
                score = day_score(stats)
                a["scores"].append(score)
                if score > a["best_day"][0]:
                    a["best_day"] = (score, sp, {k: stats[k] for k in ("0", "6", "3", "2", "1", "17")})
                a["dd"] += stats["0"] >= 10 and stats["6"] >= 10
                a["g30"] += stats["0"] >= 30
                for sid, *_ in SINGLE:
                    if stats[sid] > a["single"].get(sid, (-1, 0))[0]:
                        a["single"][sid] = (stats[sid], sp)
    return agg


def build(per_season, raw):
    recs = []
    for season in sorted(per_season):
        days = load_days(raw, season)
        sched_path = raw / str(season) / "proschedule.json"
        if not days or not sched_path.exists() or (season == CURRENT and len(days) < 14):  # too early to crown anyone
            continue
        agg = collect(days, finished_games(json.loads(sched_path.read_text(encoding="utf-8"))))
        if len(agg) < 20:
            continue
        teams = per_season[season][2]
        owners = lambda a: ", ".join(sorted({teams[int(t)]["owner_name"] for t in a["teams"]})[:3])

        def add(group, title, blurb, a, value):
            recs.append({"group": group, "title": title, "blurb": blurb, "who": a["name"], "team": owners(a), "season": season,
                         "when": str(season), "vs": "", "value": value, "extra": None, "new": season == CURRENT})

        def top(key, hi=True, pool=None):
            return (max if hi else min)(pool or list(agg.values()), key=key)

        regulars = [a for a in agg.values() if a["gp"] >= MIN_GP]
        # personalities
        w = top(lambda a: a["missed"])
        add("yearbook", "Most Likely to Be Out Tonight", "Most starter games missed.", w, f"{w['missed']} games")
        w = top(lambda a: a["best_run"])
        add("yearbook", "Iron Man", "Longest run of his team's games played without missing one.", w, f"{w['best_run']} straight")
        w = top(lambda a: len(a["teams"]))
        if len(w["teams"]) > 1:
            add("yearbook", "Most Well-Traveled", "Wore the most fantasy jerseys in one season.", w, f"{len(w['teams'])} teams")
        w = top(lambda a: a["bench"])
        if w["bench"]:
            add("yearbook", "Wasted Talent", "Most games played while sitting on a fantasy bench.", w, f"{w['bench']} games")
        w = top(lambda a: a["dd"])
        add("yearbook", "Double-Double Machine", "Most games with 10 points and 10 rebounds.", w, f"{w['dd']} games")
        w = top(lambda a: a["g30"])
        add("yearbook", "Heat Check", "Most 30-point games.", w, f"{w['g30']} games")
        if regulars:
            cv = lambda a: statistics.pstdev(a["scores"]) / max(statistics.mean(a["scores"]), 1)
            w = top(cv, False, regulars)
            add("yearbook", "Mr. Consistent", f"Steadiest night to night (min. {MIN_GP} starts).", w, f"{statistics.mean(w['scores']):.0f} avg, ±{statistics.pstdev(w['scores']):.0f}")
            w = top(cv, True, regulars)
            add("yearbook", "Boom or Bust", f"Wildest swings night to night (min. {MIN_GP} starts).", w, f"{statistics.mean(w['scores']):.0f} avg, ±{statistics.pstdev(w['scores']):.0f}")
        w = top(lambda a: a["best_day"][0])
        s = w["best_day"][2]
        add("yearbook", "Stat Sheet Stuffer", "Biggest single game: points, rebounds, assists, steals, blocks and threes combined.", w,
            f"{s['0']:.0f} PTS, {s['6']:.0f} REB, {s['3']:.0f} AST")
        # volume kings
        for sid, title, blurb, unit in KINGS:
            w = top(lambda a: a["tot"][sid])
            add("kings", title, blurb, w, f"{w['tot'][sid]:.0f} {unit}")
        fg = [a for a in agg.values() if a["tot"]["14"] >= MIN_FGA]
        ft = [a for a in agg.values() if a["tot"]["16"] >= MIN_FTA]
        rate = lambda a, m, t: a["tot"][m] / a["tot"][t]
        if fg:
            w = top(lambda a: rate(a, "13", "14"), True, fg)
            add("kings", "Mr. Efficient", f"Best FG% while starting (min. {MIN_FGA} attempts).", w, f"{rate(w, '13', '14') * 100:.1f}% FG")
        if ft:
            w = top(lambda a: rate(a, "15", "16"), True, ft)
            add("kings", "Mr. Automatic", f"Best FT% while starting (min. {MIN_FTA} attempts).", w, f"{rate(w, '15', '16') * 100:.1f}% FT")
        # single-game highs
        for sid, title, blurb, unit, shame in SINGLE:
            w = top(lambda a: a["single"].get(sid, (0, 0))[0])
            add("shame" if shame else "games", title, blurb, w, f"{w['single'][sid][0]:.0f} {unit}")
        # shame
        if fg:
            w = top(lambda a: rate(a, "13", "14"), False, fg)
            add("shame", "Brick Mason", f"Worst FG% while starting (min. {MIN_FGA} attempts).", w, f"{rate(w, '13', '14') * 100:.1f}% FG")
        if ft:
            w = top(lambda a: rate(a, "15", "16"), False, ft)
            add("shame", "Can't Buy a Free One", f"Worst FT% while starting (min. {MIN_FTA} attempts).", w, f"{rate(w, '15', '16') * 100:.1f}% FT")
        if regulars:
            w = top(lambda a: a["tot"]["0"] / a["gp"], False, regulars)
            add("shame", "Invisible Man", f"Fewest points per game while starting (min. {MIN_GP} starts).", w, f"{w['tot']['0'] / w['gp']:.1f} PPG")
    return {"records": recs}
