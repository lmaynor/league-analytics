"""Trade Machine feature: export rosters and analyze completed trades."""
import json
from pathlib import Path

from matchups import calendar_weeks
from espn_client import ROOT
from trade_analyzer import analyze_trade, compute_replacement_player, STAT_KEYS

# ESPN stat IDs:
# 0: PTS, 1: BLK, 2: STL, 3: AST, 6: REB, 11: TO, 13: FGM, 14: FGA, 15: FTM, 16: FTA, 17: 3PM, 19: FG%, 20: FT%
POS_MAP = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}
CAT_IDS = [0, 6, 3, 2, 1, 17, 19, 20, 11]
CAT_LABELS = {0: "PTS", 6: "REB", 3: "AST", 2: "STL", 1: "BLK", 17: "3PM", 19: "FG%", 20: "FT%", 11: "TO"}
GP_WEEK = 3.25


def extract_player_stat(p, season):
    stats = p.get("stats", {})
    s_curr = f"00{season}"
    s_proj = f"10{season}"
    s_prev = f"00{season - 1}"
    st = (stats.get(s_curr) or stats.get(s_proj) or stats.get(s_prev) or {}).get("avg", {})
    gp = (stats.get(s_curr) or stats.get(s_proj) or stats.get(s_prev) or {}).get("gp", 0)
    return {
        "id": p["id"],
        "name": p["name"],
        "pos": POS_MAP.get(p.get("pos"), "UTIL"),
        "inj": p.get("inj") if p.get("inj") not in (None, "ACTIVE", "NORMAL") else None,
        "gp": int(gp) if gp else 0,
        "pts": round(float(st.get("0", 0)), 1),
        "reb": round(float(st.get("6", 0)), 1),
        "ast": round(float(st.get("3", 0)), 1),
        "stl": round(float(st.get("2", 0)), 1),
        "blk": round(float(st.get("1", 0)), 1),
        "tpm": round(float(st.get("17", 0)), 1),
        "fg_pct": round(float(st.get("19", 0)), 3),
        "ft_pct": round(float(st.get("20", 0)), 3),
        "to": round(float(st.get("11", 0)), 1),
        "fgm": round(float(st.get("13", 0)), 1),
        "fga": round(float(st.get("14", 0)), 1),
        "ftm": round(float(st.get("15", 0)), 1),
        "fta": round(float(st.get("16", 0)), 1),
    }


def trade_key(team_a_id, team_b_id, ids_a, ids_b):
    """Identity of a completed trade, independent of which ESPN id a source gave it."""
    return (team_a_id, team_b_id, tuple(sorted(ids_a)), tuple(sorted(ids_b)))


def match_trade_scoring_period(txs, when_ms):
    """Scoring period of the trade a communication broadcast (type 244) belongs to.

    The broadcast lands within milliseconds of the trade's TRADE_UPHOLD
    transaction, but unrelated transactions often land inside any fixed time
    window too: here a FUTURE_ROSTER lineup set for next week (scoring period
    28) arrived 76 seconds after the broadcast, ahead of the uphold in the
    list, and the old first-match-in-120s rule filed the trade under the wrong
    week (Week 5 instead of Week 4). Prefer the closest trade transaction;
    fall back to the closest transaction of any kind.
    """
    def closest(pool):
        return min(pool, key=lambda t: abs(t.get("proposedDate", 0) - when_ms), default=None)

    trade_txs = [t for t in txs
                 if str(t.get("type", "")).startswith("TRADE")
                 and abs(t.get("proposedDate", 0) - when_ms) < 600000]
    match = closest(trade_txs)
    if match is None:
        match = closest([t for t in txs if abs(t.get("proposedDate", 0) - when_ms) < 120000])
    return match.get("scoringPeriodId", 1) if match else 1


def evaluate_trade(players_to_a, players_to_b):
    """Evaluate 9-cat head-to-head winner between two player packages."""
    stat_keys = {0: "pts", 6: "reb", 3: "ast", 2: "stl", 1: "blk", 17: "tpm", 11: "to"}
    score_a, score_b = 0.0, 0.0
    deltas = {}

    for cid in [0, 6, 3, 2, 1, 17, 11]:
        k = stat_keys[cid]
        val_a = sum(p.get(k, 0) for p in players_to_a) * GP_WEEK
        val_b = sum(p.get(k, 0) for p in players_to_b) * GP_WEEK
        deltas[cid] = round(val_a - val_b, 1)
        if cid == 11:  # turnovers: lower is better
            if val_a < val_b:
                score_a += 1
            elif val_b < val_a:
                score_b += 1
            else:
                score_a += 0.5; score_b += 0.5
        else:
            if val_a > val_b:
                score_a += 1
            elif val_b > val_a:
                score_b += 1
            else:
                score_a += 0.5; score_b += 0.5

    # FG% and FT% volume-weighted comparison
    fgm_a = sum(p.get("fgm", 0) for p in players_to_a)
    fga_a = sum(p.get("fga", 0) for p in players_to_a)
    fgm_b = sum(p.get("fgm", 0) for p in players_to_b)
    fga_b = sum(p.get("fga", 0) for p in players_to_b)
    fg_a = fgm_a / max(1, fga_a) if fga_a else 0
    fg_b = fgm_b / max(1, fga_b) if fga_b else 0
    deltas[19] = round(fg_a - fg_b, 3)
    if fg_a > fg_b:
        score_a += 1
    elif fg_b > fg_a:
        score_b += 1
    else:
        score_a += 0.5; score_b += 0.5

    ftm_a = sum(p.get("ftm", 0) for p in players_to_a)
    fta_a = sum(p.get("fta", 0) for p in players_to_a)
    ftm_b = sum(p.get("ftm", 0) for p in players_to_b)
    fta_b = sum(p.get("fta", 0) for p in players_to_b)
    ft_a = ftm_a / max(1, fta_a) if fta_a else 0
    ft_b = ftm_b / max(1, fta_b) if fta_b else 0
    deltas[20] = round(ft_a - ft_b, 3)
    if ft_a > ft_b:
        score_a += 1
    elif ft_b > ft_a:
        score_b += 1
    else:
        score_a += 0.5; score_b += 0.5

    return score_a, score_b, deltas


def build(season, raw_dir):
    roster_path = raw_dir / str(season) / "roster.json"
    if not roster_path.exists():
        return {}
    raw = json.loads(roster_path.read_text(encoding="utf-8"))
    rosters_out = {}
    player_map = {}

    for tid, players in raw.items():
        team_players = [extract_player_stat(p, season) for p in players]
        rosters_out[str(tid)] = sorted(team_players, key=lambda x: -x["pts"])
        for p_stat in team_players:
            player_map[p_stat["id"]] = p_stat

    # Fallback for players who are on no roster in the snapshot above: a
    # free agent picked up and traded again before the add takes effect
    # (Keegan Murray, Nov 11, 2026) exists only in the player pool. A traded
    # player must never be dropped silently: roster first, then the pool,
    # then a flagged placeholder.
    pool_path = raw_dir / str(season) / "players.json"
    pool_map = {}
    if pool_path.exists():
        for pool_entry in json.loads(pool_path.read_text(encoding="utf-8")).values():
            pool_map[pool_entry["id"]] = extract_player_stat(pool_entry, season)

    def unknown_player(pid):
        print(f"trades: player {pid} is on no roster and not in the player pool; using a placeholder")
        return {"id": pid, "name": f"Player {pid}", "pos": "UTIL", "inj": None, "gp": 0,
                "pts": 0.0, "reb": 0.0, "ast": 0.0, "stl": 0.0, "blk": 0.0, "tpm": 0.0,
                "fg_pct": 0.0, "ft_pct": 0.0, "to": 0.0,
                "fgm": 0.0, "fga": 0.0, "ftm": 0.0, "fta": 0.0}

    def resolve_player(pid):
        return player_map.get(pid) or pool_map.get(pid) or unknown_player(pid)

    def is_placeholder(p):
        return p["name"] == f"Player {p['id']}" and p["gp"] == 0 and p["pts"] == 0.0

    # Parse league team info for name lookups
    league_path = raw_dir / str(season) / "league.json"
    owners_path = ROOT / "config" / "owners.json"
    owners_cfg = json.loads(owners_path.read_text(encoding="utf-8")) if owners_path.exists() else {}
    teams_meta = {}
    if league_path.exists():
        lg = json.loads(league_path.read_text(encoding="utf-8"))
        for t in lg.get("teams", []):
            owner_hash = t.get("primaryOwner") or (t.get("owners") or [None])[0]
            owner_name = owners_cfg.get(owner_hash, {}).get("name", "")
            teams_meta[t["id"]] = {
                "id": t["id"],
                "name": t.get("name", f"Team {t['id']}"),
                "abbrev": t.get("abbrev", ""),
                "owner": owner_name,
            }

    # Compute league-wide replacement level and team strengths for simulations
    def compute_team_strength(roster_players):
        top10 = roster_players[:10] if roster_players else []
        s = {}
        for cid in [0, 6, 3, 2, 1, 17, 11]:
            k = STAT_KEYS[cid]
            s[str(cid)] = round(sum(p.get(k, 0.0) for p in top10) * GP_WEEK, 1)
        fgm = sum(p.get("fgm", 0.0) for p in top10)
        fga = sum(p.get("fga", 0.0) for p in top10)
        s["19"] = round(fgm / max(1.0, fga), 3) if fga else 0.465
        ftm = sum(p.get("ftm", 0.0) for p in top10)
        fta = sum(p.get("fta", 0.0) for p in top10)
        s["20"] = round(ftm / max(1.0, fta), 3) if fta else 0.770
        return s

    rep_player = compute_replacement_player(rosters_out)

    all_teams = []
    for tid_str, players in rosters_out.items():
        tid = int(tid_str)
        meta = teams_meta.get(tid, {"id": tid, "name": f"Team {tid}", "owner": ""})
        all_teams.append({
            "id": tid,
            "name": meta["name"],
            "owner": meta.get("owner", ""),
            "roster": players,
            "strength": compute_team_strength(players),
        })

    def make_trade_entry(trade_id, mp, date, t_a, t_b, to_a, to_b, incomplete=False):
        team_a_meta = teams_meta.get(t_a, {"id": t_a, "name": f"Team {t_a}", "owner": ""})
        team_b_meta = teams_meta.get(t_b, {"id": t_b, "name": f"Team {t_b}", "owner": ""})
        team_a_obj = next((t for t in all_teams if t["id"] == t_a), {
            "id": t_a, "name": team_a_meta["name"], "owner": team_a_meta.get("owner", ""),
            "roster": rosters_out.get(str(t_a), []), "strength": compute_team_strength(rosters_out.get(str(t_a), []))
        })
        team_b_obj = next((t for t in all_teams if t["id"] == t_b), {
            "id": t_b, "name": team_b_meta["name"], "owner": team_b_meta.get("owner", ""),
            "roster": rosters_out.get(str(t_b), []), "strength": compute_team_strength(rosters_out.get(str(t_b), []))
        })

        analysis = analyze_trade(team_a_obj, team_b_obj, to_a, to_b, all_teams, rep_player)

        return {
            "id": trade_id,
            "mp": mp,
            "date": date,
            "team_a": team_a_meta,
            "team_b": team_b_meta,
            "players_a": to_a,
            "players_b": to_b,
            "score_a": analysis["package_comparison"]["score_a"],
            "score_b": analysis["package_comparison"]["score_b"],
            "winner_id": analysis["verdict"]["winner_id"],
            "margin": analysis["verdict"]["margin_str"],
            "deltas": analysis["deltas_a"],
            "deltas_b": analysis["deltas_b"],
            "verdict": analysis["verdict"],
            "grade_a": analysis["grade_a"],
            "grade_b": analysis["grade_b"],
            "roster_adjustment": analysis["roster_adjustment"],
            "assumptions": analysis["assumptions"],
            **({"incomplete": True} if incomplete else {}),
        }

    # Matchup week derivation
    weeks = calendar_weeks(season)
    def get_mp(sp):
        for i, (a, b) in enumerate(weeks, 1):
            if a <= sp <= b:
                return i
        return 1

    # Check for executed trades in transactions and communication topics
    tx_path = raw_dir / str(season) / "transactions.json"
    comm_path = raw_dir / str(season) / "communication.json"
    txs = json.loads(tx_path.read_text(encoding="utf-8")) if tx_path.exists() else []
    comm = json.loads(comm_path.read_text(encoding="utf-8")) if comm_path.exists() else {}

    completed_trades = []
    weeks_trades = {}
    seen_trade_ids = set()

    # 1. Parse executed trades from ESPN communication topics (where executed trades are broadcast)
    for top in comm.get("topics", []):
        trade_msgs = [m for m in top.get("messages", []) if m.get("messageTypeId") == 244]
        if trade_msgs:
            top_id = top.get("id")
            if top_id in seen_trade_ids:
                continue
            seen_trade_ids.add(top_id)
            top_date = top.get("date", 0)
            sp = match_trade_scoring_period(txs, top_date)
            mp = get_mp(sp)
            from_teams = {m["from"] for m in trade_msgs if m.get("from")}
            to_teams = {m["to"] for m in trade_msgs if m.get("to")}
            team_ids = sorted(from_teams | to_teams)
            if len(team_ids) == 2:
                t_a, t_b = team_ids[0], team_ids[1]
                to_a = [resolve_player(m["targetId"]) for m in trade_msgs if m.get("to") == t_a]
                to_b = [resolve_player(m["targetId"]) for m in trade_msgs if m.get("to") == t_b]
                incomplete = any(is_placeholder(p) for p in to_a + to_b)
                entry = make_trade_entry(top_id, mp, top_date, t_a, t_b, to_a, to_b, incomplete)
                completed_trades.append(entry)
                weeks_trades.setdefault(str(mp), []).append(entry)

    # 2. Check for executed trades in transactions (fallback)
    for t in txs:
        status = str(t.get("status", "")).upper()
        items = t.get("items") or []
        trade_items = [it for it in items if isinstance(it, dict) and it.get("type") == "TRADE"]
        if trade_items and status in ("EXECUTED", "COMPLETE"):
            t_id = t.get("id")
            if t_id in seen_trade_ids:
                continue
            seen_trade_ids.add(t_id)
            sp = t.get("scoringPeriodId", 1)
            mp = get_mp(sp)
            team_ids = list(set([it["fromTeamId"] for it in trade_items] + [it["toTeamId"] for it in trade_items]))
            if len(team_ids) == 2:
                t_a, t_b = team_ids[0], team_ids[1]
                to_a = [resolve_player(it["playerId"]) for it in trade_items if it["toTeamId"] == t_a]
                to_b = [resolve_player(it["playerId"]) for it in trade_items if it["toTeamId"] == t_b]
                incomplete = any(is_placeholder(p) for p in to_a + to_b)
                entry = make_trade_entry(t_id, mp, t.get("proposedDate"), t_a, t_b, to_a, to_b, incomplete)
                completed_trades.append(entry)
                weeks_trades.setdefault(str(mp), []).append(entry)

    # ESPN's communication and transactions feeds are sliding windows. The
    # two trades of Oct 28, 2026 rolled out of both within days, and because
    # the payload was rebuilt from the current snapshot alone, trades.json
    # went from 2 completed trades (Oct 29 commit) to 0 (Nov 3 commit).
    # Archive the full receipt of every trade at first sight (data/raw is
    # committed by the nightly data commit) and serve feed + archive, so a
    # completed trade, once seen, is never lost again. Write-once: the
    # archived receipt keeps the grades computed from the rosters and stats
    # of its own day instead of being repriced against later rosters.
    archive_path = raw_dir / str(season) / "completed_trades.json"
    archived = []
    if archive_path.exists():
        archived = json.loads(archive_path.read_text(encoding="utf-8"))
    # Supersede rule: a receipt stored from an incomplete snapshot must not
    # freeze the error. The Nov 11, 2026 Gobert trade was first archived
    # without Keegan Murray (see the pool fallback above), so when the same
    # trade id comes back with more players, or complete instead of flagged
    # incomplete, the new version replaces the stored one. A complete
    # receipt of the same size is never overwritten: write-once stands.
    def player_count(e):
        return len(e.get("players_a", [])) + len(e.get("players_b", []))

    def supersedes(new, old):
        if player_count(new) != player_count(old):
            return player_count(new) > player_count(old)
        return bool(old.get("incomplete")) and not new.get("incomplete")

    by_id = {}
    for e in archived:
        by_id[e["id"]] = e
    for entry in completed_trades:
        cur = by_id.get(entry["id"])
        if cur is None or supersedes(entry, cur):
            by_id[entry["id"]] = entry
    by_key = {}
    for e in by_id.values():
        key = trade_key(e["team_a"]["id"], e["team_b"]["id"],
                        [p["id"] for p in e["players_a"]],
                        [p["id"] for p in e["players_b"]])
        cur = by_key.get(key)
        if cur is None or supersedes(e, cur):
            by_key[key] = e
    completed_trades = sorted(by_key.values(), key=lambda e: e["date"] or 0)
    weeks_trades = {}
    for entry in completed_trades:
        weeks_trades.setdefault(str(entry["mp"]), []).append(entry)
    if completed_trades != archived:
        archive_path.write_text(json.dumps(completed_trades, separators=(",", ":")), encoding="utf-8")

    trades_payload = {
        "season": season,
        "completed": completed_trades,
        "weeks": weeks_trades,
    }

    return {
        "rosters.json": rosters_out,
        "trades.json": trades_payload,
    }
