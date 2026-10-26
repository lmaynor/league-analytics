"""Pull category-league data from ESPN into data/raw/<season>/.

    python pipeline/fetch.py            # all seasons that have category data
    python pipeline/fetch.py 2027       # one season
"""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from espn_client import ROOT, ESPNClient
from season import current_season
import os

RAW = ROOT / "data" / "raw"
CURRENT = current_season()
HEALTHY = (None, "ACTIVE", "NORMAL")
DAILY_STATS = ["0", "1", "2", "3", "6", "11", "13", "14", "15", "16", "17"]
REFRESH_DAYS = 3  # re-pull the most recent days of the current season (late stat corrections)
WORKERS = 6
# seasons that get daily rosters (Red Cheerios feature); override with DAILY_SEASONS=2025,2026,2027
DAILY = {int(x) for x in os.environ.get("DAILY_SEASONS", f"{CURRENT - 1},{CURRENT}").split(",") if x}
VIEWS = ["mSettings", "mTeam", "mBoxscore", "mMatchupScore", "mStatus"]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def hid(guid):
    """Short stable hash of an ESPN account GUID (keeps GUIDs out of the repo)."""
    return hashlib.sha1((guid or "").encode()).hexdigest()[:10] if guid else None


def scrub_members(members):
    """Keep only the public display names (drop everything else ESPN returns)."""
    return [{"id": hid(m.get("id")), "displayName": m.get("displayName")} for m in (members or [])]


def has_category_data(league):
    return any(
        (m.get("home", {}).get("cumulativeScore") or {}).get("scoreByStat")
        for m in league.get("schedule", [])
    )


def compact_roster(raw, season):
    """Current rosters: just what the projection needs."""
    out = {}
    for t in raw.get("teams", []):
        players = []
        for e in t.get("roster", {}).get("entries", []):
            p = e["playerPoolEntry"]["player"]
            avgs = {}
            for s in p.get("stats", []):
                if s.get("statSplitTypeId") in (0, 1, 2, 3) and s.get("averageStats"):
                    avgs[s["id"]] = {"avg": s["averageStats"], "gp": (s.get("stats") or {}).get("42")}
                elif s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 0 and s.get("averageStats"):
                    avgs[s["id"]] = {"avg": s["averageStats"], "gp": None}
            players.append({
                "id": e["playerId"], "name": p["fullName"], "pro": p.get("proTeamId"),
                "slot": e["lineupSlotId"], "inj": e.get("injuryStatus") or p.get("injuryStatus"),
                "pos": p.get("defaultPositionId"), "stats": avgs,
            })
        out[str(t["id"])] = players
    return out


def compact_schedule(raw):
    """NBA game start times / official-ness per team per scoring period."""
    games = {}
    teams = {}
    for t in raw["settings"]["proTeams"]:
        teams[str(t["id"])] = t.get("abbrev")
        for sp, gs in (t.get("proGamesByScoringPeriod") or {}).items():
            for g in gs:
                games[str(g["id"])] = {"sp": int(sp), "home": g["homeProTeamId"], "away": g["awayProTeamId"],
                                       "t": g["date"], "final": bool(g.get("statsOfficial"))}
    return {"teams": teams, "games": list(games.values())}


def compact_day(raw, sp):
    """One day's rosters: who sat in which slot and what each player did that day.

    ESPN returns the player's latest game line, so a game only counts for this day when the
    line's scoring period matches; otherwise the player did not play."""
    teams = {}
    for t in raw.get("teams", []):
        rows = []
        for e in t.get("roster", {}).get("entries", []):
            p = e["playerPoolEntry"]["player"]
            # ESPN can send two game lines (the previous game and this day's): take the one for this day
            line = next((x for x in p.get("stats", []) if x.get("statSplitTypeId") == 5 and x.get("statSourceId") == 0
                         and x.get("scoringPeriodId") == sp), None)
            line_stats = (line or {}).get("stats") or {}
            # an empty line (stats {}) is how ESPN reports a player who did not play that day
            played = bool(line and line.get("scoringPeriodId") == sp and line_stats and line_stats.get("42", 1) != 0)
            stats = {k: (line_stats.get(k) or 0) for k in DAILY_STATS} if played else None
            rows.append([e["playerId"], p["fullName"], p.get("proTeamId"), e["lineupSlotId"], int(played), stats, p.get("injuryStatus")])
        teams[str(t["id"])] = rows
    return {"sp": sp, "teams": teams}


def fetch_days(c, season, league):
    d = RAW / str(season) / "days"
    st = league["status"]
    first, last = st.get("firstScoringPeriod", 1), st.get("finalScoringPeriod") or 1
    if season == CURRENT:
        last = min(last, league.get("scoringPeriodId") or last)
    days = list(range(first, last + 1))
    recent = set(days[-REFRESH_DAYS:]) if season == CURRENT else set()
    todo = [sp for sp in days if sp in recent or not (d / f"{sp}.json").exists()]

    def pull(sp):
        raw = c.league(season, ["mRoster"], scoring_period=sp)
        day = compact_day(raw, sp)
        old = _read(d / f"{sp}.json")
        if old:  # ESPN only reports the status as of now: keep a flag seen on an earlier pull
            seen = {r[0]: r[6] for rows in old["teams"].values() for r in rows if len(r) > 6 and r[6] not in HEALTHY}
            for rows in day["teams"].values():
                for r in rows:
                    if r[6] in HEALTHY and r[0] in seen:
                        r[6] = seen[r[0]]
        _write(d / f"{sp}.json", day)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(pull, todo))
    print(f"{season}: {len(days)} days ({len(todo)} fetched)")


def fetch_season(c, season):
    d = RAW / str(season)
    league = c.league(season, VIEWS)
    if league is None or not has_category_data(league):
        print(f"{season}: no category data, skipped")
        return False
    league["members"] = scrub_members(league.get("members"))
    for t in league.get("teams", []):
        t["owners"] = [hid(o) for o in t.get("owners", [])]
        t["primaryOwner"] = hid(t.get("primaryOwner"))
    _write(d / "league.json", league)
    n = len(league["schedule"])
    print(f"{season}: {len(league['teams'])} teams, {n} matchups")
    if season in DAILY:
        if season != CURRENT:
            _write(d / "proschedule.json", compact_schedule(c.pro_schedule(season)))
        fetch_days(c, season, league)
    if season == CURRENT:
        sp = league.get("scoringPeriodId")
        _write(d / "roster.json", compact_roster(c.league(season, ["mRoster"], scoring_period=sp), season))
        _write(d / "proschedule.json", compact_schedule(c.pro_schedule(season)))
    return True


def main():
    args = [int(a) for a in sys.argv[1:] if not a.startswith("--")]
    c = ESPNClient()
    if args:
        seasons = args
    else:
        cur = c.league(CURRENT, ["mStatus"])
        seasons = (cur.get("status", {}).get("previousSeasons") or []) + [CURRENT]
    for s in seasons:
        try:
            fetch_season(c, s)
        except PermissionError as e:
            if s == CURRENT:
                raise
            print(f"{s}: skipped ({e})")


if __name__ == "__main__":
    main()
