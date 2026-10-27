"""Trade Analyzer feature: export current rosters with per-game averages for 9-cat analysis."""
import json
from pathlib import Path

# ESPN stat IDs:
# 0: PTS, 1: BLK, 2: STL, 3: AST, 6: REB, 11: TO, 13: FGM, 14: FGA, 15: FTM, 16: FTA, 17: 3PM, 19: FG%, 20: FT%
POS_MAP = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}


def build(season, raw_dir):
    roster_path = raw_dir / str(season) / "roster.json"
    if not roster_path.exists():
        return {}
    raw = json.loads(roster_path.read_text(encoding="utf-8"))
    out = {}
    for tid, players in raw.items():
        team_players = []
        for p in players:
            stats = p.get("stats", {})
            # Prefer: current season actuals ("00<season>"), then projection ("10<season>"), then prior season ("00<season-1>")
            s_curr = f"00{season}"
            s_proj = f"10{season}"
            s_prev = f"00{season - 1}"
            st = (stats.get(s_curr) or stats.get(s_proj) or stats.get(s_prev) or {}).get("avg", {})
            gp = (stats.get(s_curr) or stats.get(s_proj) or stats.get(s_prev) or {}).get("gp", 0)

            team_players.append({
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
            })
        out[str(tid)] = sorted(team_players, key=lambda x: -x["pts"])
    return {"rosters.json": out}
