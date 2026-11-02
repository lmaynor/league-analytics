"""The official NBA injury report: fetch the newest PDF, parse it, match it to our rostered players.

ESPN's injuryStatus is one flag as of whenever we fetched. The league publishes a PDF about every 15 minutes
with a status per player per game (Out, Doubtful, Questionable, Probable, Available) and a reason, which is
the list the teams actually submit. The parser is a port of mlb-betting's nba/data/nba_injury_report.py (word
geometry from `pdftotext -bbox`, no pandas), kept standard library only so it can run anywhere.

Facts (verified against live files, see mlb-betting docs/solutions/integration-issues/nba-official-injury-report-pdf.md):
  * files: Injury-Report_{YYYY-MM-DD}_{HH}_{MM}{AM|PM}.pdf every 15 minutes (hourly files also exist on the hour)
  * a missing file answers 403, not 404; any other error status or a non-PDF body is a real failure
  * the title time inside the PDF, not the file stamp, is when the list was current
  * the report lists only players with a designation; a team can carry NOT YET SUBMITTED, which means unknown
Fail closed: no pdftotext, an unreadable PDF or zero parsed rows raises, and the caller keeps the last good report.
"""
import json
import re
import subprocess
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://ak-static.cms.nba.com/referee/injury"
ET = ZoneInfo("America/New_York")
STATUSES = ("Out", "Doubtful", "Questionable", "Probable", "Available")
NOT_SUBMITTED = "NOT_SUBMITTED"
# Chance a listed player plays that game, measured on 14,435 report listings from the 2024-25 and 2025-26 regular seasons
# (one report per game day at about 5 PM ET) against the box scores, for rotation players (20+ minutes lately). The report
# from the same day is sharper than the one from the day before. When a rotation player does play he gets 93-99% of his usual
# minutes, so no minutes adjustment is applied. Doubtful has few listings (160), so both days share one pooled value.
STATUS_Q_SAME = {"Out": 0.09, "Doubtful": 0.27, "Questionable": 0.64, "Probable": 0.83, "Available": 0.96}
STATUS_Q_AHEAD = {"Out": 0.01, "Doubtful": 0.27, "Questionable": 0.54, "Probable": 0.93, "Available": 0.98}
# a player listed Out the same day, by reason (measured: rest 26%, G League 0%, injury 8%, personal 18%, suspension 8%)
OUT_SAME_BY_REASON = {"rest": 0.25, "g_league": 0.0, "injury_illness": 0.08, "injury_management": 0.08}
FINAL_MIN = 60  # an Out listing within an hour of tip-off is final: late changes are already in
MAX_AGE_MIN = 6 * 60  # a report older than this is not trusted for anything
# Chance a rotation player listed Out for an injury plays his k-th team game after the report stops covering him, measured on
# the same listings: .13 .24 .29 .33 .35 .38 .40 .44 .45 .46 (a first estimate from ordinary missed games was far too high,
# .55 .67 .71, because injury absences are much longer). Beyond 10 games the last value is used. Being listed for several days
# in a row does not raise the odds of a return (first day .15, 2nd-3rd .10, 4th-9th .05), so one curve is used.
CARRY_Q = (0.13, 0.24, 0.29, 0.33, 0.35, 0.38, 0.40, 0.44, 0.45, 0.46)
# team nickname in the report's Team column -> ESPN abbreviation (the keys of proschedule.json "teams")
NICKNAMES = {"Hawks": "ATL", "Celtics": "BOS", "Nets": "BKN", "Hornets": "CHA", "Bulls": "CHI", "Cavaliers": "CLE",
             "Mavericks": "DAL", "Nuggets": "DEN", "Pistons": "DET", "Warriors": "GS", "Rockets": "HOU", "Pacers": "IND",
             "Clippers": "LAC", "Lakers": "LAL", "Grizzlies": "MEM", "Heat": "MIA", "Bucks": "MIL", "Timberwolves": "MIN",
             "Pelicans": "NO", "Knicks": "NY", "Thunder": "OKC", "Magic": "ORL", "76ers": "PHI", "Suns": "PHX",
             "Trail Blazers": "POR", "Kings": "SAC", "Spurs": "SA", "Raptors": "TOR", "Jazz": "UTAH", "Wizards": "WSH"}
LOOKBACK_SLOTS = 16   # 15-minute stamps to try, newest first (4 hours)

_TITLE = re.compile(r"Injury Report:\s*(\d{2}/\d{2}/\d{2})\s+(\d{1,2}:\d{2})\s*([AP]M)", re.I)
_FOOTER = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.I)
_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', re.S)
# column starts (x0 of the header words on a landscape 842pt page), used when the header is not found
_DEFAULT_STARTS = {"date": 23.0, "time": 119.0, "matchup": 200.0, "team": 264.0, "player": 425.0, "status": 585.0, "reason": 666.0}
_ORDER = ("date", "time", "matchup", "team", "player", "status", "reason")
# ESPN team abbreviations that differ from the league's tricodes (matchups in the report use tricodes)
ESPN_TO_TRI = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "WSH": "WAS", "UTAH": "UTA"}


class PdfToolMissing(RuntimeError):
    """pdftotext (poppler) is not installed, so the report cannot be parsed here."""


class ReportParseError(ValueError):
    """The PDF produced no usable table (layout change, empty report, wrong file)."""


# ---------------------------------------------------------------------------------------------- fetch
def report_urls(ts):
    """Both filename conventions for the stamp `ts` (ET): hourly only on the hour, quarter-hour always."""
    h12, ap, day = ts.strftime("%I"), ts.strftime("%p"), ts.strftime("%Y-%m-%d")
    urls = []
    if ts.minute == 0:
        urls.append(f"{BASE}/Injury-Report_{day}_{h12}{ap}.pdf")
    urls.append(f"{BASE}/Injury-Report_{day}_{h12}_{ts.strftime('%M')}{ap}.pdf")
    return urls


def newest_report(now=None, have_url=None, session=None, timeout=30):
    """(url, pdf bytes) of the newest published report, or None when none exists in the lookback window.

    A probe that finds `have_url` returns (url, None): nothing new to download."""
    import requests
    s = session or requests
    now = (now or datetime.now(ET)).astimezone(ET).replace(second=0, microsecond=0)
    t = now - timedelta(minutes=now.minute % 15)
    for i in range(LOOKBACK_SLOTS):
        for url in report_urls(t - timedelta(minutes=15 * i)):
            probe = s.get(url, headers={"Range": "bytes=0-1023"}, timeout=timeout)
            if probe.status_code in (403, 404):
                continue
            probe.raise_for_status()
            if url == have_url:
                return url, None
            r = s.get(url, timeout=timeout)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ReportParseError(f"not a PDF: {url} ({len(r.content)} bytes)")
            return url, r.content
    return None


# ---------------------------------------------------------------------------------------------- parse
def _unescape(s):
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")


def pdf_words(data, pdftotext="pdftotext"):
    """PDF bytes to a list (one per page) of words (x0, y0, x1, y1, text), via `pdftotext -bbox`."""
    try:
        p = subprocess.run([pdftotext, "-bbox", "-", "-"], input=data, capture_output=True, timeout=60)
    except FileNotFoundError as exc:
        raise PdfToolMissing("pdftotext (poppler-utils) is not installed") from exc
    if p.returncode != 0:
        raise ReportParseError(f"pdftotext failed ({p.returncode}): {p.stderr[:200]!r}")
    html = p.stdout.decode("utf-8", "replace")
    pages = []
    for chunk in html.split("<page ")[1:]:
        pages.append([(float(a), float(b), float(c), float(d), _unescape(t).strip())
                      for a, b, c, d, t in _WORD.findall(chunk) if _unescape(t).strip()])
    return pages


def _boundaries(pages):
    """x cut points between columns, from the header words on page 1 (else the defaults)."""
    starts = dict(_DEFAULT_STARTS)
    if pages:
        by_text = {}
        for x0, y0, _x1, _y1, t in pages[0]:
            by_text.setdefault(t, []).append((y0, x0))
        hdr_y = min((y for y, _x in by_text.get("Matchup", [])), default=None)
        if hdr_y is not None:
            def x_of(word):
                c = [x for y, x in by_text.get(word, []) if abs(y - hdr_y) < 3]
                return min(c) if c else None
            found = {"date": x_of("Game"), "matchup": x_of("Matchup"), "team": x_of("Team"), "player": x_of("Player"),
                     "status": x_of("Current"), "reason": x_of("Reason")}
            gt = sorted(x for y, x in by_text.get("Game", []) if abs(y - hdr_y) < 3)
            if len(gt) >= 2:
                found["date"], found["time"] = gt[0], gt[1]
            starts.update({k: v for k, v in found.items() if v is not None})
    xs = [starts[k] for k in _ORDER]
    return [(a + b) / 2.0 for a, b in zip(xs[:-1], xs[1:])]


def _col(x0, cuts):
    for name, cut in zip(_ORDER, cuts):
        if x0 < cut:
            return name
    return _ORDER[-1]


def _lines(words):
    """Cluster words into visual lines by y."""
    out = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2.0, w[0])):
        yc = (w[1] + w[3]) / 2.0
        if out and abs(out[-1]["y"] - yc) <= 3.0:
            out[-1]["words"].append(w)
        else:
            out.append({"y": yc, "words": [w]})
    return out


def flip_name(raw):
    """'Porter Jr., Michael' -> 'Michael Porter Jr.'; no comma -> unchanged."""
    if "," not in raw:
        return raw.strip()
    last, first = raw.split(",", 1)
    return f"{first.strip()} {last.strip()}".strip()


def reason_category(reason):
    """Class of the league's reason string. Wrapped lines can arrive out of order, so look for the label anywhere."""
    r = (reason or "").strip().lower()
    if not r:
        return "none"
    for label, cat in (("injury/illness", "injury_illness"), ("g league", "g_league"), ("not with team", "not_with_team"),
                       ("injury management", "injury_management"), ("suspen", "suspension"), ("personal", "personal"),
                       ("return to competition", "return_to_competition")):
        if label in r:
            return cat
    return "rest" if re.search(r"\brest\b", r) else "other"


def parse_words(pages):
    """Pure: pdftotext word pages to (report time as ISO ET or None, rows). Raises ReportParseError with no player rows."""
    cuts = _boundaries(pages)
    title, parsed = None, []
    for k, pg in enumerate(pages):
        for ln in _lines(pg):
            cols = {}
            for x0, _y0, _x1, _y1, t in sorted(ln["words"], key=lambda w: w[0]):
                cols.setdefault(_col(x0, cuts), []).append(t)
            st = cols.get("status")
            if st and cols.get("player") and st[0] not in STATUSES:
                # a long name overruns into the status column: tokens before the first status word belong to the player
                i = next((j for j, t in enumerate(st) if t in STATUSES), len(st))
                cols["player"] = cols["player"] + st[:i]
                cols["status"] = st[i:]
                if not cols["status"]:
                    del cols["status"]
            txt = {k2: " ".join(v) for k2, v in cols.items()}
            whole = " ".join(w[4] for w in sorted(ln["words"], key=lambda w: w[0]))
            m = _TITLE.search(whole)
            if m:
                title = title or m
                continue
            if "NOT YET SUBMITTED" in whole.upper():  # a team-level row: its text must not leak into a player's reason
                parsed.append({"y": ln["y"] + 10000.0 * k, "nys": True, **{c: txt[c] for c in ("date", "time", "matchup", "team") if c in txt}})
                continue
            if _FOOTER.match(whole.strip()) or whole.startswith("Game Date") or whole.strip().startswith("Injury Report"):
                continue
            parsed.append({"y": ln["y"] + 10000.0 * k, **txt})
    players = [p for p in parsed if p.get("player") and not p.get("nys")]
    if not players:
        raise ReportParseError("no player rows found (layout changed, empty report, or wrong file)")
    reason_lines = [p for p in parsed if p.get("reason")]
    carry = {k: [p for p in parsed if p.get(k)] for k in ("date", "time", "matchup")}
    merged_team = []  # wrapped team-name lines (under 16pt apart) are one name
    for p in (p for p in parsed if p.get("team")):
        if merged_team and 0 <= p["y"] - merged_team[-1]["y_last"] < 16:
            merged_team[-1]["team"] += " " + p["team"]
            merged_team[-1]["y_last"] = p["y"]
        else:
            merged_team.append({"y": p["y"], "y_last": p["y"], "team": p["team"]})
    by_player = {i: [] for i in range(len(players))}
    for rl in reason_lines:  # a reason wraps onto lines above and below the player's line: nearest player line wins
        i = min(range(len(players)), key=lambda j: abs(players[j]["y"] - rl["y"]))
        if abs(players[i]["y"] - rl["y"]) <= 30:
            by_player[i].append(rl)
    rows = []
    for nl in (p for p in parsed if p.get("nys")):
        t = [p for p in merged_team if p["y"] <= nl["y"] + 8]
        dates = [p for p in carry["date"] if p["y"] <= nl["y"] + 8]
        mu = [p for p in carry["matchup"] if p["y"] <= nl["y"] + 8]
        try:
            gd = datetime.strptime(dates[-1]["date"] if dates else "", "%m/%d/%Y").date().isoformat()
        except ValueError:
            gd = None
        rows.append({"game_date": gd, "matchup": mu[-1]["matchup"] if mu else None, "team": t[-1]["team"] if t else None,
                     "player": None, "status": NOT_SUBMITTED, "reason": "", "reason_cat": "none"})
    for i, pl in enumerate(players):
        def above(key):
            c = [p for p in carry[key] if p["y"] <= pl["y"] + 8]
            return c[-1][key] if c else None
        t = [p for p in merged_team if p["y"] <= pl["y"] + 8]
        reason = " ".join(r["reason"] for r in sorted(by_player[i], key=lambda r: r["y"]))
        status = pl.get("status")
        if status not in STATUSES:
            continue  # an unknown status is dropped, never guessed
        try:
            gd = datetime.strptime(above("date") or "", "%m/%d/%Y").date().isoformat()
        except ValueError:
            gd = None
        rows.append({"game_date": gd, "matchup": above("matchup"), "team": t[-1]["team"] if t else None,
                     "player": flip_name(pl["player"]),
                     "status": status, "reason": reason, "reason_cat": reason_category(reason)})
    if not rows:
        raise ReportParseError("no valid player rows (layout changed or unknown statuses)")
    asof = None
    if title:
        ts = datetime.strptime(f"{title.group(1)} {title.group(2)} {title.group(3).upper()}", "%m/%d/%y %I:%M %p")
        asof = ts.replace(tzinfo=ET).isoformat()
    return asof, rows


def parse_pdf(data, pdftotext="pdftotext"):
    return parse_words(pdf_words(data, pdftotext))


# ---------------------------------------------------------------------------------------------- identity
_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm(name):
    """Lowercase, accents folded, punctuation dropped, generational suffix removed."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", s).split() if t not in _SUFFIX]
    return " ".join(toks)


def resolve(rows, players, abbrev):
    """Match report rows to our rostered players.

    players: [{"id", "name", "pro"}], abbrev: {ESPN pro team id (str): ESPN abbreviation}.
    -> ({player id: {game_date: row}}, stats). A name that is ambiguous among rostered players is narrowed by the
    teams in the row's matchup and otherwise dropped; unmatched report names (almost always unrostered) are counted."""
    by_name = {}
    for p in players:
        by_name.setdefault(norm(p["name"]), []).append(p)
    out, matched, unmatched, ambiguous = {}, 0, 0, 0
    for r in rows:
        if r["status"] == NOT_SUBMITTED or not r["player"] or not r["game_date"]:
            continue
        cands = by_name.get(norm(r["player"]), [])
        if len(cands) > 1:
            teams = set((r["matchup"] or "").upper().replace("@", " ").split())
            cands = [p for p in cands if ESPN_TO_TRI.get(abbrev.get(str(p["pro"]), ""), abbrev.get(str(p["pro"]), "")) in teams]
        if len(cands) == 1:
            out.setdefault(cands[0]["id"], {})[r["game_date"]] = r
            matched += 1
        elif cands:
            ambiguous += 1
        else:
            unmatched += 1
    return out, {"matched": matched, "ambiguous": ambiguous, "unmatched": unmatched}


def team_abbr(name):
    """ESPN abbreviation for a team name from the report ('Boston Celtics' -> 'BOS'), or None."""
    n = name or ""
    return next((ab for nick, ab in NICKNAMES.items() if n.endswith(nick)), None)


def not_submitted(rows):
    """[(ESPN abbreviation, game date)] that carry a NOT YET SUBMITTED row: that list is unknown, not healthy."""
    return sorted({(team_abbr(r["team"]), r["game_date"]) for r in rows if r["status"] == NOT_SUBMITTED and team_abbr(r["team"])})


def et_date(ms):
    return datetime.fromtimestamp(ms / 1000, ET).date().isoformat()


def build_lookup(doc, players, sched, now_ms):
    """lookup(player, game) -> (chance he plays, status label) from the official report, or None for no official verdict.

    * a player listed for the game's date: the measured chance for his status (STATUS_Q_SAME for a report written that
      day, STATUS_Q_AHEAD for one written the day before; an Out listing within an hour of tip-off counts as 0)
    * a game the report does not cover (a later date, or his team's list is not submitted yet): a starter listed Out
      for an injury at his team's last covered game carries forward with CARRY_Q by games since (a rest day is a
      one-game absence and does not carry)
    * anything else (unlisted, team not submitted, report too old): None, and the caller keeps its own estimate"""
    if not doc or not doc.get("rows") or not doc.get("asof"):
        return None
    asof_ms = datetime.fromisoformat(doc["asof"]).timestamp() * 1000
    if (now_ms - asof_ms) / 60000 > MAX_AGE_MIN:
        return None
    asof_day = et_date(asof_ms)
    abbrev = sched["teams"]
    listed, _ = resolve(doc["rows"], players, abbrev)
    nys = set(map(tuple, not_submitted(doc["rows"])))
    last_date = max((r["game_date"] for r in doc["rows"] if r["game_date"]), default=None)
    if last_date is None:
        return None
    team_dates = {}
    for g in sched["games"]:
        for t in (g["home"], g["away"]):
            team_dates.setdefault(str(t), set()).add(et_date(g["t"]))
    team_dates = {t: sorted(d) for t, d in team_dates.items()}

    def lookup(p, g):
        d = et_date(g["t"])
        mine = listed.get(p["id"], {})
        if d in mine:
            r = mine[d]
            if d != asof_day:  # the report was written the day before
                return STATUS_Q_AHEAD[r["status"]], r["status"]
            if r["status"] == "Out":
                final = (g["t"] - asof_ms) / 60000 <= FINAL_MIN
                return (0.0 if final else OUT_SAME_BY_REASON.get(r["reason_cat"], 0.10)), "Out"
            return STATUS_Q_SAME[r["status"]], r["status"]
        dates, ab = team_dates.get(str(p["pro"]), []), abbrev.get(str(p["pro"]))
        if d <= last_date and (ab, d) not in nys:
            return None  # the report covers this game and does not list him: no official verdict
        # past the report, or his team has not submitted that day's list: lean on his last covered game
        covered = [x for x in dates if x < d and x <= last_date and (ab, x) not in nys]
        if not covered:
            return None
        r0 = mine.get(covered[-1])
        if r0 and r0["status"] == "Out" and r0["reason_cat"] not in ("rest", "none", "other"):
            k = sum(1 for x in dates if covered[-1] < x <= d)
            return CARRY_Q[min(k, len(CARRY_Q)) - 1], "Out"
        return None
    return lookup


# ---------------------------------------------------------------------------------------------- storage
def load(season_dir):
    path = season_dir / "injuries.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def refresh(season_dir, players, abbrev, now=None, pdftotext="pdftotext"):
    """Fetch the newest report, parse it, store it as injuries.json and archive each game day's statuses.

    Never raises for a missing report or a missing pdftotext: returns a short reason string and leaves the last
    good report in place. -> (status, note)."""
    try:
        have = load(season_dir)
        got = newest_report(now, have_url=(have or {}).get("url"))
        if got is None:
            return "none", "no report published in the last 4 hours"
        url, pdf = got
        if pdf is None:
            return "same", url
        asof, rows = parse_pdf(pdf, pdftotext)
    except (PdfToolMissing, ReportParseError) as e:
        return "skipped", str(e)
    except Exception as e:  # network trouble must never break a refresh
        return "error", f"{type(e).__name__}: {e}"
    matched, stats = resolve(rows, players, abbrev)
    doc = {"asof": asof, "url": url, "fetched": int((now or datetime.now(ET)).timestamp() * 1000),
           "n_rows": len(rows), "not_submitted": [list(x) for x in not_submitted(rows)], **stats, "rows": rows}
    (season_dir / "injuries.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    # archive: the newest listing for each game day, so a past week can be checked or calibrated later
    arch = season_dir / "injuries"
    arch.mkdir(exist_ok=True)
    days = {}
    for r in rows:
        if r["game_date"] and r["status"] != NOT_SUBMITTED:
            days.setdefault(r["game_date"], []).append({k: r[k] for k in ("player", "status", "reason_cat", "matchup")})
    for day, rs in days.items():
        (arch / f"{day}.json").write_text(json.dumps({"asof": asof, "rows": rs}, separators=(",", ":")), encoding="utf-8")
    return "ok", f"{len(rows)} rows, {stats['matched']} matched"


if __name__ == "__main__":  # python -I pipeline/injuries.py <report.pdf>: parse one file and print a summary
    import sys
    from collections import Counter
    asof, rows = parse_pdf(open(sys.argv[1], "rb").read())
    print("report time:", asof, "| rows:", len(rows))
    print("statuses:", dict(Counter(r["status"] for r in rows)))
    print("reasons:", dict(Counter(r["reason_cat"] for r in rows)))
    print("dates:", dict(Counter(r["game_date"] for r in rows)))
    for r in rows[:6]:
        print(" ", r["game_date"], r["matchup"], "|", r["team"], "|", r["player"], "|", r["status"], "|", r["reason"][:50])
