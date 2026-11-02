"""Race for last: simulate the rest of the regular season to see who is on pace for the bottom.

Each team's strength is its share of categories won, shrunk toward a prior (half league average, half
the owner's category share last season). The chance that team A beats team B is a logistic curve on
the strength gap; K was fit on 666 weekly matchups from 2018 to 2026 and its predictions track the
actual win rates (43% predicted vs 42% actual, 59% vs 57%, 70% vs 72%). The matchup in progress uses
the live odds instead. Every remaining scheduled matchup is simulated, standings are re-ranked, and
the share of simulations a team finishes last is its chance of last place.
"""
import json
from pathlib import Path

import numpy as np

from cats import RATIO
import injuries
from features.cheerios import ACTIVE_SLOTS, load_days
from features.live import player_means
from matchups import CURRENT, cat_result, pct_value

K = 5.73
PRIOR_CATS = 27  # about three weeks of categories
# Players who are out. Category results lag a long injury: a team that loses its stars keeps the strength it earned with them
# for weeks. Backtest (146 matchups, 2025-26, injury reports of the day): adding the share of a team's core (its 9 most
# valuable players, any slot, so a benched or IR star counts) that was listed Out for an injury at the start of the week
# improved matchup log loss in both seasons held out (.670 -> .655 overall; the healthier side won 64% where one side had 10%+
# more out, against 54% predicted from results alone). The fitted weight was 2.6 logit per unit; KAPPA applies about three
# quarters of it because the sample is small. The effect fades with the weeks ahead as players return (the carry-forward curve in
# injuries.CARRY_Q), HEALTH_PERSIST being week 1 = 1.
KAPPA = 0.35
HEALTH_PERSIST = (1.0, 0.77, 0.66, 0.59, 0.54)
# per-game mean and spread of PTS REB AST STL BLK 3PM TO over rotation players (20+ minutes), 2024-26 box scores
Z_STATS = ("0", "6", "3", "2", "1", "17", "11")
Z_MU = (14.8079, 5.3843, 3.3298, 0.9605, 0.5831, 1.6671, 1.6774)
Z_SD = (8.3953, 3.5147, 2.7922, 1.0484, 0.9199, 1.6316, 1.5099)


def core_out_shares(roster, doc, sched, season):
    """{team id: (share of core value listed Out for an injury, [their names])} from the newest official report."""
    if not roster or not doc or not doc.get("rows"):
        return {}
    players = [p for ps in roster.values() for p in ps]
    listed, _ = injuries.resolve(doc["rows"], players, sched["teams"])
    out_ids = set()
    for pid, by_day in listed.items():
        last = by_day[max(by_day)]  # his newest listing
        if last["status"] == "Out" and last["reason_cat"] in ("injury_illness", "injury_management"):
            out_ids.add(pid)
    res = {}
    for tid, ps in roster.items():
        vals = []
        for p in ps:
            m = player_means(p, season)
            v = sum(((m[k] - mu) / sd) * (-1 if k == "11" else 1) for k, mu, sd in zip(Z_STATS, Z_MU, Z_SD))
            vals.append((max(v, 0.0), p))
        core = sorted(vals, key=lambda x: -x[0])[:9]
        tot = sum(v for v, _ in core)
        gone = [(v, p) for v, p in core if p["id"] in out_ids]
        res[str(tid)] = (round(sum(v for v, _ in gone) / tot, 3) if tot else 0.0, [p["name"] for v, p in sorted(gone, key=lambda x: -x[0])])
    return res


# Win chance partway through a matchup week: logit p = ws * (K * strength gap) + wl * (category lead - 0.5), by day of the
# week. Fit on 146 matchups (2025-26, 876 matchup-days); scored on the season it was not fitted on it beat a 50/50 average
# of strength and lead by 0.559 vs 0.596 and 0.524 vs 0.590 log loss. Strength matters early, the lead takes over by midweek.
DAILY_W = {1: (0.64, 4.6), 2: (0.62, 5.0), 3: (0.32, 5.1), 4: (0.36, 5.7), 5: (0.31, 8.6), 6: (0.0, 11.3)}


def daily_win_prob(day, strength_logit, lead):
    """Home win chance after `day` scoring days of the week (1 = Monday), from the strength gap and the category lead
    (share of categories led, 0.5 = even)."""
    ws, wl = DAILY_W[min(max(day, 1), 6)]
    return float(1 / (1 + np.exp(-(ws * strength_logit + wl * (lead - 0.5)))))
SIMS = 10000
TRAIL_SIMS = 3000  # fewer runs for the weekly history points


def regular_schedule(league):
    """[(matchup period, home id, away id)] for every regular-season matchup, played or not."""
    return [(m["matchupPeriodId"], m["home"]["teamId"], m["away"]["teamId"]) for m in league["schedule"]
            if "away" in m and m.get("playoffTierType", "NONE") == "NONE"]


def places(pos):
    """Unique places for one checkpoint: teams ranked by their average finish, so the table is a real order.

    Rounding each team's own most likely place independently can give two teams the same place, which a
    final table never does. Ranking by average finish keeps every place used exactly once."""
    order = np.argsort(pos.mean(axis=0), kind="stable")
    out = np.empty(pos.shape[1], dtype=int)
    out[order] = np.arange(1, pos.shape[1] + 1)
    return [int(v) for v in out]


def build_season(season, data, rows, teams, league, prior_by_owner, live, days=None, health=None):
    sched = regular_schedule(league)
    tids = sorted(teams)
    idx = {t: i for i, t in enumerate(tids)}
    T = len(tids)
    live_mp = next((r["mp"] for r in rows if r["regular"] and r["live"]), None)
    live_p = None
    if live and live.get("active") and season == CURRENT and live_mp:
        live_p = {(live_mp, m["home"]): m["p_home_win"] + m["p_tie"] / 2 for m in live["matchups"] if not m.get("hidden")}  # hidden matchups fall back to the strength model
    live_rows = [r for r in rows if r["regular"] and r["live"]]
    live_done = bool(live_rows and (
        (live and live.get("active") and live.get("games_left") == 0) or
        (league.get("status", {}).get("latestScoringPeriod", 0) > max(r["sp1"] for r in live_rows))
    ))
    done = [r for r in rows if r["regular"] and (not r["live"] or live_done)]
    completed = sorted({r["mp"] for r in done})
    prior = {t: 0.5 * 0.5 + 0.5 * prior_by_owner.get(teams[t]["owner"], 0.5) for t in tids}
    rng = np.random.default_rng(11)

    out_share = np.array([(health or {}).get(str(t), (0.0, []))[0] for t in tids])

    def simulate(upto, live_p=None, n=SIMS, use_health=False):
        wins = np.zeros(T)
        ties = np.zeros(T)
        cw, cn = np.zeros(T), np.zeros(T)
        gp = np.zeros(T)
        for r in done:
            if r["mp"] > upto:
                continue
            h, a = idx[r["home"]], idx[r["away"]]
            gp[h] += 1; gp[a] += 1
            if r["hw"] > r["aw"]:
                wins[h] += 1
            elif r["hw"] < r["aw"]:
                wins[a] += 1
            else:
                wins[h] += 0.5; wins[a] += 0.5; ties[h] += 1; ties[a] += 1
            for t, w, l in ((h, r["hw"], r["aw"]), (a, r["aw"], r["hw"])):
                cw[t] += w + 0.5 * r["t"]; cn[t] += w + l + r["t"]
        pri = np.array([prior[t] for t in tids])
        s = (cw + PRIOR_CATS * pri) / (cn + PRIOR_CATS)
        left = [(mp, h, a) for mp, h, a in sched if mp > upto]
        left_n = np.zeros(T)
        if left:
            H = np.zeros((len(left), T)); A = np.zeros((len(left), T)); ph = np.zeros(len(left))
            for j, (mp, h, a) in enumerate(left):
                H[j, idx[h]] = 1; A[j, idx[a]] = 1
                se = s
                if use_health and out_share.any():  # teams missing core players are weaker than their results so far, fading by week
                    se = s - KAPPA * HEALTH_PERSIST[min(mp - upto, len(HEALTH_PERSIST)) - 1] * out_share
                ph[j] = 1 / (1 + np.exp(-K * (se[idx[h]] - se[idx[a]])))
                if live_p and (mp, h) in live_p:
                    ph[j] = live_p[(mp, h)]
            home_wins = rng.random((n, len(left))) < ph
            sim_wins = wins + home_wins @ H + (~home_wins) @ A
            left_n = H.sum(0) + A.sum(0)
        else:
            sim_wins = np.tile(wins, (n, 1))
        key = sim_wins + 0.05 * s + rng.random((n, T)) * 0.005  # strength breaks ties, a little noise settles the rest
        pos = np.argsort(np.argsort(-key, axis=1), axis=1)  # 0 = best
        return {"wins": wins, "ties": ties, "gp": gp, "s": s, "left": left_n, "sim_wins": sim_wins, "pos": pos}

    upto_now = max(completed) if completed else 0
    now = simulate(upto_now, live_p, use_health=season == CURRENT)
    # weekly trail: chances across prediction market models after the start and after each checkpoint
    trail = {t: [] for t in tids}  # odds of last (backward compat)
    trail_title = {t: [] for t in tids}  # title / 1st place odds
    trail_playoffs = {t: [] for t in tids}  # top 4 playoff odds
    trail_bottom3 = {t: [] for t in tids}  # bottom 3 danger odds
    expect = {t: [] for t in tids}  # projected place after each checkpoint: a whole place, unique per team (1 = best)
    labels = []

    def record_point(pos):
        exp = places(pos)
        for t in tids:
            i = idx[t]
            trail[t].append(round(float((pos[:, i] == T - 1).mean()), 4))
            trail_title[t].append(round(float((pos[:, i] == 0).mean()), 4))
            trail_playoffs[t].append(round(float((pos[:, i] < 4).mean()), 4))
            trail_bottom3[t].append(round(float((pos[:, i] >= T - 3).mean()), 4))
            expect[t].append(exp[i])

    for w in [0] + completed:
        res = simulate(w, None, TRAIL_SIMS)
        record_point(res["pos"])
        labels.append(w)
    daily_by_home = {}  # per live matchup: win chance on each day of the week (the Scoreboard's rolling chart)
    if live_mp is not None:  # live week exists; its odds may be empty while hidden, the strength model then stands in
        # one point per scoring day of the live week, then the live odds on the last day (matches the Scoreboard)
        live_rows = [r for r in rows if r["regular"] and r["live"]]
        STATS = [0, 1, 2, 3, 6, 11, 13, 14, 15, 16, 17]
        cids = [c["id"] for c in data["cats"]]
        cw, cn = {}, {}
        for r in done:
            if r["mp"] >= live_mp: continue
            for t, w, l in ((r["home"], r["hw"], r["aw"]), (r["away"], r["aw"], r["hw"])):
                cw[t] = cw.get(t, 0) + w + 0.5 * r["t"]; cn[t] = cn.get(t, 0) + w + l + r["t"]
        strength = {t: (cw.get(t, 0) + 13.5) / (cn.get(t, 0) + 27) for t in tids}
        def partial(t, sp0, d):
            tot = dict.fromkeys(STATS, 0.0)
            for sp in range(sp0, d + 1):
                for row in (days or {}).get(sp, {}).get(str(t), []):
                    if row[3] in ACTIVE_SLOTS and row[4] and row[5]:
                        for k in STATS: tot[k] += row[5][str(k)]
            return {k: tot[k] for k in STATS}
        if days and live_rows:
            daily_by_home = {r["home"]: [] for r in live_rows}
            sp0 = min(r["sp0"] for r in live_rows)
            last_day = min(max(days), max(r["sp1"] for r in live_rows))
            for d in range(sp0, last_day):
                probs = {}
                for r in live_rows:
                    h, a = r["home"], r["away"]
                    th, ta = partial(h, sp0, d), partial(a, sp0, d)
                    res_cats = [cat_result(pct_value(th, c) if c in RATIO else th[c], pct_value(ta, c) if c in RATIO else ta[c], c) for c in cids]
                    lead = (sum(1 for v in res_cats if v == 1) - sum(1 for v in res_cats if v == -1) + len(cids)) / (2 * len(cids))
                    probs[(r["mp"], h)] = daily_win_prob(d - sp0 + 1, K * (strength[h] - strength[a]), lead)
                for r in live_rows:
                    daily_by_home[r["home"]].append(round(probs[(r["mp"], r["home"])], 4))
                day_now = simulate(live_mp - 1, probs, TRAIL_SIMS)
                record_point(day_now["pos"])
                labels.append(f"d{d}")
        record_point(now["pos"])
        labels.append(f"d{max(days)}" if days else "live")

    seed_of = {s["id"]: s["seed"] for s in data["standings"]}
    out = []
    for t in tids:
        i = idx[t]
        ranks = now["pos"][:, i] + 1
        if data["complete"]:  # a finished season has a real order; no simulation needed
            ranks = np.full(1, seed_of[t])
        gp = int(now["gp"][i])
        w, ti = int(round(now["wins"][i] - 0.5 * now["ties"][i])), int(round(now["ties"][i]))
        l = gp - w - ti
        out.append({
            "id": t, "name": teams[t]["name"], "owner": teams[t]["owner_name"],
            "record": [w, l, ti],
            "games_left": int(now["left"][i]) if now["left"][i] else 0,
            "proj_wins": round(float(now["sim_wins"][:, i].mean()), 1),
            "p_title": round(float((ranks == 1).mean()), 4),
            "p_playoffs": round(float((ranks <= 4).mean()), 4),
            "p_bottom3": round(float((ranks > T - 3).mean()), 4),
            "p_last": round(float((ranks == T).mean()), 4),
            "rank_p10": int(np.percentile(ranks, 10)), "rank_med": int(np.median(ranks)), "rank_p90": int(np.percentile(ranks, 90)),
            "strength": round(float(now["s"][i]), 3),
            "out_share": (health or {}).get(str(t), (0.0, []))[0], "out_names": (health or {}).get(str(t), (0.0, []))[1],
            "trail": trail[t],
            "trail_last": trail[t],
            "trail_title": trail_title[t],
            "trail_playoffs": trail_playoffs[t],
            "trail_bottom3": trail_bottom3[t],
            "expect": expect[t],
            "finish": [round(float((ranks == r).mean()), 4) for r in range(1, T + 1)],  # chance of each finish, 1st to last
        })
    out.sort(key=lambda x: (-x["p_last"], x["proj_wins"]))

    return {"matchup_daily": {str(k): v for k, v in daily_by_home.items()}, "season": season, "teams": out, "trail_labels": labels, "weeks_done": len(completed),
            "weeks_total": len({mp for mp, _, _ in sched}), "live": bool(live_p), "complete": data["complete"]}


def build(per_season, raw, live):
    if not live:
        cached = Path(__file__).resolve().parent.parent.parent / "site" / "data" / "live.json"
        if cached.exists():
            try:
                live = json.loads(cached.read_text(encoding="utf-8"))
            except Exception:
                live = {}
    seasons = {}
    for season in sorted(per_season):
        path = raw / str(season) / "league.json"
        if season < CURRENT - 1 or not path.exists():
            continue  # the last two seasons are enough (this one and a finished one to check against)
        data, rows, teams = per_season[season]
        league = json.loads(path.read_text(encoding="utf-8"))
        prior = {}
        if season - 1 in per_season:
            prior = {s["owner"]: s["cat_pct"] for s in per_season[season - 1][0]["standings"]}
        health = None
        if season == CURRENT:
            try:
                rost = json.loads((raw / str(season) / "roster.json").read_text(encoding="utf-8"))
                sch = json.loads((raw / str(season) / "proschedule.json").read_text(encoding="utf-8"))
                health = core_out_shares(rost, injuries.load(raw / str(season)), sch, season)
            except Exception:  # no roster or report: fall back to results alone
                health = None
        seasons[str(season)] = build_season(season, data, rows, teams, league, prior, live, load_days(raw, season) if season == CURRENT else None, health)
    return {"seasons": seasons, "k": K}
