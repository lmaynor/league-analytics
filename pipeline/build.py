"""Build site/data/*.json from the raw ESPN files.

    python pipeline/build.py                      # rebuild every feature from data/raw
    python pipeline/build.py --fetch              # pull ESPN first
    python pipeline/build.py --only live,records  # rebuild just some features

Each feature lives in pipeline/features/ and writes its own JSON file(s), so one feature
failing never takes the others down.
"""
import json
import sys
import traceback

from espn_client import ROOT
from features import cheerios, history, live, lineup, race, records, standings, superlatives, swaps
from matchups import CURRENT

RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data"
OWNERS = ROOT / "config" / "owners.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def seasons_available():
    return sorted(int(p.name) for p in RAW.iterdir() if p.name.isdigit() and (p / "league.json").exists())


def load_owner_config(per_season):
    """config/owners.json maps owner id -> display name; new owners are added automatically."""
    cfg = read(OWNERS) or {}
    for data, _, _ in per_season.values():
        for t in data["standings"]:
            cfg.setdefault(t["owner"], {"name": t["owner_name"]})
    OWNERS.parent.mkdir(exist_ok=True)
    OWNERS.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cfg


def league_name():
    d = read(RAW / str(CURRENT) / "league.json")
    return (d or {}).get("settings", {}).get("name", "League")


def run(name, only, fn):
    """Run one feature, writing whatever files it returns. Failures are reported, not fatal."""
    if only and name not in only:
        return []
    try:
        files = fn() or {}
    except Exception:
        print(f"[{name}] FAILED:")
        traceback.print_exc()
        return []
    for fname, obj in files.items():
        write(fname, obj)
    return list(files)


def stamp_assets():
    """Add ?v=<content hash> to the script, stylesheet and icon links so browsers never serve stale files."""
    import hashlib
    import re
    page = ROOT / "site" / "index.html"
    html = page.read_text(encoding="utf-8")

    def tag(m):
        path = ROOT / "site" / m.group(2)
        digest = hashlib.md5(path.read_bytes()).hexdigest()[:8] if path.exists() else "0"
        return f'{m.group(1)}{m.group(2)}?v={digest}"'

    new = re.sub(r'((?:src|href)=")((?:js/[\w-]+\.js|style\.css|img/[\w-]+\.png))(?:\?v=\w+)?"', tag, html)
    if new != html:
        page.write_text(new, encoding="utf-8")


def main():
    if "--fetch" in sys.argv:
        import fetch
        fetch.main()
    only = set()
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = set(a.split("=", 1)[1].split(","))
        elif a == "--only" and sys.argv.index(a) + 1 < len(sys.argv):
            only = set(sys.argv[sys.argv.index(a) + 1].split(","))

    # core: per-season standings feed every other feature
    owners_cfg = read(OWNERS) or {}
    per_season = {s: standings.build_season(s, read(RAW / str(s) / "league.json"), owners_cfg) for s in seasons_available()}
    owners_cfg = load_owner_config(per_season)
    per_season = {s: standings.build_season(s, read(RAW / str(s) / "league.json"), owners_cfg) for s in per_season}
    written = []
    for s, (data, _, _) in per_season.items():
        write(f"season_{s}.json", data)
        written.append(f"season_{s}.json")

    league = read(RAW / str(CURRENT) / "league.json")
    written += run("history", only, lambda: {"history.json": history.build_history(per_season, owners_cfg)})
    written += run("records", only, lambda: {"records.json": {"records": records.build_records(per_season)}})
    live_out = {}
    def do_live():
        out = live.build(league, per_season[CURRENT][0], read(RAW / str(CURRENT) / "roster.json"),
                         read(RAW / str(CURRENT) / "proschedule.json"))
        live_out.update(out or {})
        return {"live.json": out or {"active": False}}
    written += run("live", only, do_live)
    written += run("cheerios", only, lambda: {"cheerios.json": cheerios.build(per_season, RAW)})
    written += run("lineup", only, lambda: {"lineup.json": lineup.build(per_season, RAW)})
    written += run("swaps", only, lambda: {"swaps.json": swaps.build(per_season, RAW, live_out)})
    written += run("race", only, lambda: {"race.json": race.build(per_season, RAW, live_out)})
    written += run("superlatives", only, lambda: {"superlatives.json": superlatives.build(per_season, RAW)})
    stamp_assets()
    write("meta.json", {"current": CURRENT, "seasons": sorted(per_season), "league_name": league_name()})
    print(f"wrote {len(written) + 1} files to {OUT}")
    if live_out.get("active"):
        print(live.summary(live_out))


if __name__ == "__main__":
    main()
