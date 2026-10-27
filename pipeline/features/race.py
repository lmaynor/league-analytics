"""Race for last: simulate the rest of the regular season to see who is on pace for the bottom.

Each team's strength is its share of categories won, shrunk toward a prior (half league average, half
the owner's category share last season). The chance that team A beats team B is a logistic curve on
the strength gap; K was fit on 666 weekly matchups from 2018 to 2026 and its predictions track the
actual win rates (43% predicted vs 42% actual, 59% vs 57%, 70% vs 72%). The matchup in progress uses
the live odds instead. Every remaining scheduled matchup is simulated, standings are re-ranked, and
the share of simulations a team finishes last is its chance of last place.
"""
import json

import numpy as np

from cats import RATIO
from features.cheerios import ACTIVE_SLOTS, load_days
from matchups import CURRENT, cat_result, pct_value

K = 5.73
PRIOR_CATS = 27  # about three weeks of categories
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


def build_season(season, data, rows, teams, league, prior_by_owner, live, days=None):
    sched = regular_schedule(league)
    tids = sorted(teams)
    idx = {t: i for i, t in enumerate(tids)}
    T = len(tids)
    live_mp = next((r["mp"] for r in rows if r["regular"] and r["live"]), None)
    live_p = None
    if live and live.get("active") and season == CURRENT and live_mp:
        live_p = {(live_mp, m["home"]): m["p_home_win"] + m["p_tie"] / 2 for m in live["matchups"] if not m.get("hidden")}  # hidden matchups fall back to the strength model
    # a week with no games left to simulate is played, even if ESPN has not finalized it yet
    done = [r for r in rows if r["regular"] and (not r["live"] or live_p is None)]
    completed = sorted({r["mp"] for r in done})
    prior = {t: 0.5 * 0.5 + 0.5 * prior_by_owner.get(teams[t]["owner"], 0.5) for t in tids}
    rng = np.random.default_rng(11)

    def simulate(upto, live_p=None, n=SIMS):
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
                ph[j] = 1 / (1 + np.exp(-K * (s[idx[h]] - s[idx[a]])))
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
    now = simulate(upto_now, live_p)
    # weekly trail: chance of last after the start and after each completed week
    trail = {t: [] for t in tids}
    expect = {t: [] for t in tids}  # projected place after each checkpoint: a whole place, unique per team (1 = best)
    labels = []
    for w in [0] + completed:
        res = simulate(w, None, TRAIL_SIMS)
        for t in tids:
            trail[t].append(round(float((res["pos"][:, idx[t]] == T - 1).mean()), 4))
            expect[t].append(places(res["pos"])[idx[t]])
        labels.append(w)
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
            sp0 = min(r["sp0"] for r in live_rows)
            last_day = min(max(days), max(r["sp1"] for r in live_rows))
            for d in range(sp0, last_day):
                probs = {}
                for r in live_rows:
                    h, a = r["home"], r["away"]
                    th, ta = partial(h, sp0, d), partial(a, sp0, d)
                    res_cats = [cat_result(pct_value(th, c) if c in RATIO else th[c], pct_value(ta, c) if c in RATIO else ta[c], c) for c in cids]
                    lead = (sum(1 for v in res_cats if v == 1) - sum(1 for v in res_cats if v == -1) + len(cids)) / (2 * len(cids))
                    strength_p = 1 / (1 + np.exp(-K * (strength[h] - strength[a])))
                    probs[(r["mp"], h)] = 0.5 * strength_p + 0.5 * lead  # a simple blend: this week's category lead and the strength model
                day_now = simulate(live_mp - 1, probs, TRAIL_SIMS)
                for t in tids:
                    trail[t].append(round(float((day_now["pos"][:, idx[t]] == T - 1).mean()), 4))
                    expect[t].append(places(day_now["pos"])[idx[t]])
                labels.append(f"d{d}")
        for t in tids:
            trail[t].append(round(float((now["pos"][:, idx[t]] == T - 1).mean()), 4))
            expect[t].append(places(now["pos"])[idx[t]])
        labels.append(f"d{max(days)}" if days else "live")

    seed_of = {s["id"]: s["seed"] for s in data["standings"]}
    standing = {t: [0, 0, 0] for t in tids}  # the live week as it stands right now
    for r in rows:
        if r["regular"] and r["live"] and live_p:
            for me, mine, theirs in ((r["home"], r["hw"], r["aw"]), (r["away"], r["aw"], r["hw"])):
                standing[me][0 if mine > theirs else 1 if mine < theirs else 2] += 1
    out = []
    for t in tids:
        i = idx[t]
        ranks = now["pos"][:, i] + 1
        if data["complete"]:  # a finished season has a real order; no simulation needed
            ranks = np.full(1, seed_of[t])
        gp = int(now["gp"][i])
        w, ti = now["wins"][i], int(now["ties"][i])
        out.append({
            "id": t, "name": teams[t]["name"], "owner": teams[t]["owner_name"],
            "record": [int(w - 0.5 * ti) + standing[t][0], int(gp - w - 0.5 * ti) + standing[t][1], ti + standing[t][2]],
            "games_left": int(now["left"][i]) if now["left"][i] else 0,
            "proj_wins": round(float(now["sim_wins"][:, i].mean()), 1),
            "p_last": round(float((ranks == T).mean()), 4),
            "p_bottom3": round(float((ranks > T - 3).mean()), 4),
            "rank_p10": int(np.percentile(ranks, 10)), "rank_med": int(np.median(ranks)), "rank_p90": int(np.percentile(ranks, 90)),
            "strength": round(float(now["s"][i]), 3), "trail": trail[t], "expect": expect[t],
            "finish": [round(float((ranks == r).mean()), 4) for r in range(1, T + 1)],  # chance of each finish, 1st to last
        })
    out.sort(key=lambda x: (-x["p_last"], x["proj_wins"]))
    return {"season": season, "teams": out, "trail_labels": labels, "weeks_done": len(completed),
            "weeks_total": len({mp for mp, _, _ in sched}), "live": bool(live_p), "complete": data["complete"]}


def build(per_season, raw, live):
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
        seasons[str(season)] = build_season(season, data, rows, teams, league, prior, live, load_days(raw, season) if season == CURRENT else None)
    return {"seasons": seasons, "k": K}
