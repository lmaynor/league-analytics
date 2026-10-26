"""Live matchup forecast for a category league: who wins each category, and what's swinging it.

For the current matchup week we take each side's live category totals, then simulate the rest of
the week: every remaining NBA game for each team's current starters (lineups lock weekly, so no
mid-week swaps), with negative-binomial-ish game-to-game spread. FG%/FT% are simulated
from makes and attempts, so a late high-volume shooter moves them the right amount.
"""
import datetime as dt
import time
from zoneinfo import ZoneInfo

import numpy as np

from cats import COUNTING, OD, RATIO, REVERSE, label

SIMS = 10000
ACTIVE = {0, 1, 2, 3, 4, 5, 6, 11}  # PG SG SF PF C G F UTIL; 12 = bench, 13 = IR
AVAIL = {"OUT": 0.0, "SUSPENSION": 0.0, "INJURY_RESERVE": 0.0, "DOUBTFUL": 0.2, "QUESTIONABLE": 0.6, "DAY_TO_DAY": 0.85}
ET = ZoneInfo("America/New_York")
SIM_STATS = COUNTING + [13, 14, 15, 16]
DEFAULT = {"0": 8.0, "6": 3.0, "3": 1.8, "2": 0.6, "1": 0.3, "11": 1.0, "17": 0.8, "13": 3.0, "14": 6.8, "15": 1.4, "16": 1.8}


def player_means(p, season):
    """Per-game means: current-season form blended into last season + ESPN's projection."""
    st = p["stats"]
    cur = st.get(f"00{season}")
    priors = [st[k]["avg"] for k in (f"00{season - 1}", f"10{season}") if k in st]
    if priors:
        prior = {s: sum(x.get(s, 0) for x in priors) / len(priors) for s in map(str, SIM_STATS)}
    else:
        prior = dict(DEFAULT)
    gp = (cur or {}).get("gp") or 0
    w = gp / (gp + 12) if cur else 0
    base = cur["avg"] if cur else prior
    return {s: w * base.get(s, 0) + (1 - w) * prior.get(s, 0) for s in map(str, SIM_STATS)}


def week_days(league, sched, matchup_row_home):
    """Current scoring period, the week's last day (Sunday, ET), and sp -> ET date."""
    games = sched["games"]
    first = min(g["t"] for g in games if g["sp"] == 1)
    d1 = dt.datetime.fromtimestamp(first / 1000, ET).date()
    date_of = lambda sp: d1 + dt.timedelta(days=sp - 1)
    cur_sp = league["scoringPeriodId"]
    end = cur_sp
    while date_of(end).weekday() != 6:  # roll forward to Sunday
        end += 1
    return cur_sp, end, date_of


GAME_MS = 3 * 3600 * 1000  # an NBA game is over ~3h after tip even if ESPN has not marked stats official


def game_state(g, now_ms):
    if g["final"] or g["t"] + GAME_MS < now_ms:
        return "final"
    return "live" if g["t"] <= now_ms else "upcoming"


def remaining_games(sched, cur_sp, end_sp, now_ms):
    """{sp: {pro_team: fraction_left}}"""
    out = {}
    for g in sched["games"]:
        sp = g["sp"]
        state = game_state(g, now_ms)
        if sp < cur_sp or sp > end_sp or state == "final":
            continue
        frac = 0.5 if state == "live" else 1.0
        for team in (g["home"], g["away"]):
            out.setdefault(sp, {})[team] = (frac, g)
    return out


def plan_team(players, season, rem):
    """Expected player-games for the rest of the week.

    Lineups lock for the week (each player at his first game), so the current starters play every
    game they have left. Bench players never replace an injured or resting starter."""
    pm = {p["id"]: player_means(p, season) for p in players}
    starters = [p for p in players if p["slot"] in ACTIVE and AVAIL.get(p["inj"], 1.0) > 0]
    games = []
    for sp in sorted(rem):
        for p in starters:
            if p["pro"] in rem[sp]:
                frac, g = rem[sp][p["pro"]]
                games.append({"p": p, "sp": sp, "f": frac, "q": AVAIL.get(p["inj"], 1.0), "m": pm[p["id"]], "g": g})
    return games


def simulate_team(games, rng):
    """Remaining totals per stat id: arrays of length SIMS."""
    tot = {s: np.zeros(SIMS) for s in SIM_STATS}
    contrib = {s: {} for s in SIM_STATS}
    if not games:
        return tot, contrib
    n = len(games)
    f = np.array([g["f"] for g in games])
    q = np.array([g["q"] for g in games])
    play = (rng.random((SIMS, n)) < q) * f

    def draw(sid):
        m = np.array([g["m"][str(sid)] for g in games])
        sd = np.sqrt(m + OD.get(sid, 0.07) * m * m)
        return np.maximum(0, rng.normal(m, sd, (SIMS, n)))

    for sid in COUNTING:
        x = np.rint(draw(sid) * play)
        tot[sid] = x.sum(axis=1)
    for att, made in ((14, 13), (16, 15)):
        a = np.rint(draw(att) * play)
        pct = np.clip(np.array([g["m"][str(made)] / max(g["m"][str(att)], 0.1) for g in games]), 0.05, 0.98)
        x = rng.binomial(a.astype(int), pct)
        tot[att], tot[made] = a.sum(axis=1), x.sum(axis=1)
    for sid in SIM_STATS:
        for i, g in enumerate(games):
            nm = g["p"]["name"]
            contrib[sid][nm] = contrib[sid].get(nm, 0) + g["m"][str(sid)] * g["f"] * g["q"]
    return tot, contrib


def final_values(cur, rem, cid):
    if cid in RATIO:
        made, att = RATIO[cid]
        a = cur.get(str(att), 0) + rem[att]
        return (cur.get(str(made), 0) + rem[made]) / np.maximum(a, 1)
    return cur.get(str(cid), 0) + rem[cid]


def state(p):
    if p >= 0.97: return "locked-home"
    if p <= 0.03: return "locked-away"
    if p >= 0.80: return "lean-home"
    if p <= 0.20: return "lean-away"
    if p >= 0.62: return "edge-home"
    if p <= 0.38: return "edge-away"
    return "toss-up"


def tonight(games_all, team_players, cur_sp, now_ms, abbrev):
    """Players with a game on the current day, with game status."""
    out = []
    for p in team_players:
        if p["slot"] not in ACTIVE or AVAIL.get(p["inj"], 1.0) == 0:  # bench and IR players are not "playing tonight"
            continue
        for g in games_all:
            if g["sp"] == cur_sp and p["pro"] in (g["home"], g["away"]):
                opp = g["away"] if p["pro"] == g["home"] else g["home"]
                status = game_state(g, now_ms)
                out.append({"name": p["name"], "pro": abbrev.get(str(p["pro"])), "opp": abbrev.get(str(opp)),
                            "status": status, "t": g["t"], "active": p["slot"] != 12, "inj": p["inj"]})
    out.sort(key=lambda x: (x["status"] != "upcoming", x["status"] != "live", x["t"], not x["active"]))
    return out


def build(league, season_data, roster, sched, now_ms=None):
    if not roster or not sched:
        return {"active": False}
    season = league["seasonId"]
    now_ms = now_ms or time.time() * 1000
    cur_mp = league["status"].get("currentMatchupPeriod")
    week = next((w for w in season_data["weeks"] if w["mp"] == cur_mp), None)
    if not week or not any(m.get("live") for m in week["matchups"]):
        return {"active": False}
    cur_sp, end_sp, date_of = week_days(league, sched, None)
    rem = remaining_games(sched, cur_sp, end_sp, now_ms)
    abbrev = sched["teams"]
    rng = np.random.default_rng(7)
    cids = [c["id"] for c in season_data["cats"]]
    teams = season_data["teams"]

    sims, plans = {}, {}
    for tid, players in roster.items():
        plans[tid] = plan_team(players, season, rem)
        sims[tid] = simulate_team(plans[tid], rng)

    out_matchups = []
    for m in week["matchups"]:
        h, a = str(m["home"]), str(m["away"])
        (th, ch), (ta, ca) = sims[h], sims[a]
        cats, outcomes = [], []
        for c in cids:
            fh, fa = final_values(m["hs"], th, c), final_values(m["as"], ta, c)
            o = np.sign(fh - fa) * (-1 if c in REVERSE else 1)
            outcomes.append((c, o, fh, fa))
        hw = sum((o > 0).astype(int) for _, o, _, _ in outcomes)
        aw = sum((o < 0).astype(int) for _, o, _, _ in outcomes)
        win, loss = hw > aw, aw > hw
        for c, o, fh, fa in outcomes:
            ph, pa, pt = float((o > 0).mean()), float((o < 0).mean()), float((o == 0).mean())
            wh, wl = win[o > 0], win[o < 0]
            win_if_home = float(wh.mean()) if len(wh) else None  # home matchup win chance if home takes this category
            win_if_away = float(wl.mean()) if len(wl) else None  # ...and if away takes it
            swing = float(wh.mean() - wl.mean()) if len(wh) and len(wl) else 0.0
            ph_eff = ph + 0.5 * pt
            cur_h, cur_a = m["hs"].get(str(c)), m["as"].get(str(c))
            if c in RATIO:
                made, att = RATIO[c]
                cur_h = m["hs"][str(made)] / m["hs"][str(att)] if m["hs"].get(str(att)) else None
                cur_a = m["as"][str(made)] / m["as"][str(att)] if m["as"].get(str(att)) else None
            gap = (fh - fa)
            cats.append({
                "id": c, "label": label(c), "reverse": c in REVERSE,
                "hv": cur_h, "av": cur_a,
                "exp_h": float(fh.mean()), "exp_a": float(fa.mean()),
                "p_home": round(ph, 4), "p_away": round(pa, 4), "p_tie": round(pt, 4),
                "win_if_home": None if win_if_home is None else round(win_if_home, 3),
                "win_if_away": None if win_if_away is None else round(win_if_away, 3),
                "swing": round(swing, 3), "sweat": round(4 * ph_eff * (1 - ph_eff) * abs(swing), 3),
                "gap_mean": float(gap.mean()), "gap_sd": float(gap.std()),
                "state": state(ph_eff),
                "watch_h": top(ch[watch_stat(c)], 2), "watch_a": top(ca[watch_stat(c)], 2),
            })
        out_matchups.append({
            "home": m["home"], "away": m["away"],
            "home_name": teams[h]["name"], "away_name": teams[a]["name"],
            "home_owner": teams[h]["owner_name"], "away_owner": teams[a]["owner_name"],
            "now": {"hw": m["hw"], "aw": m["aw"], "t": m["t"]},
            "p_home_win": round(float(win.mean()), 4), "p_away_win": round(float(loss.mean()), 4),
            "p_tie": round(float((~win & ~loss).mean()), 4),
            "exp_home_cats": round(float(hw.mean()), 2), "exp_away_cats": round(float(aw.mean()), 2),
            "cats": cats,
            "home_side": side_info(plans[h], roster[h], cur_sp, end_sp, now_ms, abbrev, date_of, sched),
            "away_side": side_info(plans[a], roster[a], cur_sp, end_sp, now_ms, abbrev, date_of, sched),
        })

    sweat = []
    for i, mm in enumerate(out_matchups):
        for c in mm["cats"]:
            if abs(c["swing"]) >= 0.05 and 0.1 <= c["p_home"] + c["p_tie"] / 2 <= 0.9:  # only categories still genuinely open
                sweat.append({"matchup": i, "cat": c["id"], "label": c["label"], "sweat": c["sweat"],
                              "p_home": c["p_home"], "p_tie": c["p_tie"], "swing": abs(c["swing"]), "state": c["state"],
                              "win_if_home": c["win_if_home"], "win_if_away": c["win_if_away"],
                              "home_name": mm["home_name"], "away_name": mm["away_name"],
                              "hv": c["hv"], "av": c["av"]})
    sweat.sort(key=lambda x: -x["sweat"])
    games_left = sum(len(p) for p in plans.values())
    return {
        "active": True, "asof_ms": int(now_ms), "mp": cur_mp, "cur_sp": cur_sp, "end_sp": end_sp,
        "date": date_of(cur_sp).isoformat(), "end_date": date_of(end_sp).isoformat(),
        "final_day": cur_sp == end_sp, "games_left": games_left,
        "sims": SIMS, "cats": season_data["cats"], "matchups": out_matchups, "sweat": sweat[:12],
    }


def watch_stat(c):
    """Who to watch: for FG%/FT% that is whoever takes the most shots."""
    return RATIO[c][1] if c in RATIO else c


def top(contrib, k):
    items = sorted(contrib.items(), key=lambda x: -abs(x[1]))[:k]
    return [{"name": n, "exp": round(v, 1)} for n, v in items if abs(v) > 0.05]


def side_info(games, players, cur_sp, end_sp, now_ms, abbrev, date_of, sched):
    by_day = {}
    for g in games:
        by_day[g["sp"]] = by_day.get(g["sp"], 0) + g["f"]
    return {
        "player_games_left": round(sum(g["f"] * g["q"] for g in games), 1),
        "by_day": [{"sp": sp, "date": date_of(sp).isoformat(), "n": round(n, 1)} for sp, n in sorted(by_day.items())],
        "tonight": tonight(sched["games"], players, cur_sp, now_ms, abbrev),
    }


def summary(out):
    lines = [f"live: week {out['mp']}, day {out['cur_sp']} of ..{out['end_sp']} ({'FINAL DAY' if out['final_day'] else 'in progress'}), {out['games_left']} lineup games left"]
    for m in out["matchups"]:
        lines.append(f"  {m['home_name']} {m['now']['hw']}-{m['now']['aw']}-{m['now']['t']} {m['away_name']}: "
                     f"{m['p_home_win']:.0%} / {m['p_away_win']:.0%}")
    return "\n".join(lines)
