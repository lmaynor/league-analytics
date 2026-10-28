"""Trade Machine feature: export rosters and analyze completed trades."""
import json
from pathlib import Path

from matchups import calendar_weeks
from espn_client import ROOT

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
            matching_tx = next((t for t in txs if abs(t.get("proposedDate", 0) - top_date) < 120000), None)
            sp = matching_tx.get("scoringPeriodId", 1) if matching_tx else 1
            mp = get_mp(sp)
            from_teams = {m["from"] for m in trade_msgs if m.get("from")}
            to_teams = {m["to"] for m in trade_msgs if m.get("to")}
            team_ids = sorted(from_teams | to_teams)
            if len(team_ids) == 2:
                t_a, t_b = team_ids[0], team_ids[1]
                to_a = [player_map.get(m["targetId"]) for m in trade_msgs if m.get("to") == t_a and player_map.get(m["targetId"])]
                to_b = [player_map.get(m["targetId"]) for m in trade_msgs if m.get("to") == t_b and player_map.get(m["targetId"])]
                score_a, score_b, deltas = evaluate_trade(to_a, to_b)

                if score_a > score_b:
                    winner_id = t_a
                    margin_str = f"+{int(score_a - score_b)} categories ({int(score_a)}–{int(score_b)})"
                elif score_b > score_a:
                    winner_id = t_b
                    margin_str = f"+{int(score_b - score_a)} categories ({int(score_b)}–{int(score_a)})"
                else:
                    winner_id = None
                    margin_str = f"Even trade ({score_a}–{score_b})"

                entry = {
                    "id": top_id,
                    "mp": mp,
                    "date": top_date,
                    "team_a": teams_meta.get(t_a, {"id": t_a, "name": f"Team {t_a}", "owner": ""}),
                    "team_b": teams_meta.get(t_b, {"id": t_b, "name": f"Team {t_b}", "owner": ""}),
                    "players_a": to_a,
                    "players_b": to_b,
                    "score_a": score_a,
                    "score_b": score_b,
                    "winner_id": winner_id,
                    "margin": margin_str,
                    "deltas": deltas,
                }
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
                to_a = [player_map.get(it["playerId"]) for it in trade_items if it["toTeamId"] == t_a and player_map.get(it["playerId"])]
                to_b = [player_map.get(it["playerId"]) for it in trade_items if it["toTeamId"] == t_b and player_map.get(it["playerId"])]
                score_a, score_b, deltas = evaluate_trade(to_a, to_b)

                if score_a > score_b:
                    winner_id = t_a
                    margin_str = f"+{int(score_a - score_b)} categories ({int(score_a)}–{int(score_b)})"
                elif score_b > score_a:
                    winner_id = t_b
                    margin_str = f"+{int(score_b - score_a)} categories ({int(score_b)}–{int(score_a)})"
                else:
                    winner_id = None
                    margin_str = f"Even trade ({score_a}–{score_b})"

                entry = {
                    "id": t_id,
                    "mp": mp,
                    "date": t.get("proposedDate"),
                    "team_a": teams_meta.get(t_a, {"id": t_a, "name": f"Team {t_a}", "owner": ""}),
                    "team_b": teams_meta.get(t_b, {"id": t_b, "name": f"Team {t_b}", "owner": ""}),
                    "players_a": to_a,
                    "players_b": to_b,
                    "score_a": score_a,
                    "score_b": score_b,
                    "winner_id": winner_id,
                    "margin": margin_str,
                    "deltas": deltas,
                }
                completed_trades.append(entry)
                weeks_trades.setdefault(str(mp), []).append(entry)

    trades_payload = {
        "season": season,
        "completed": completed_trades,
        "weeks": weeks_trades,
    }

    return {
        "rosters.json": rosters_out,
        "trades.json": trades_payload,
    }
