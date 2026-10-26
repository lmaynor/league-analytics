"""All-time history: owner totals, head-to-head, closest category finishes, sweeps."""
from collections import defaultdict

from cats import cat_ids, label


def closeness_sd(all_rows, cids):
    """Pooled sd of (home - away) per category: how big a 'normal' margin is."""
    sd = {}
    for c in cids:
        d = [(r["hs"].get(str(c)) or 0) - (r["as"].get(str(c)) or 0) for r in all_rows]
        m = sum(d) / len(d)
        sd[c] = (sum((x - m) ** 2 for x in d) / len(d)) ** 0.5 or 1
    return sd


def build_history(per_season, owners_cfg):
    cids = cat_ids()
    flat = []
    for season, (_, rows, teams) in per_season.items():
        for r in rows:
            flat.append({**r, "season": season, "teams": teams})
    reg_rows = [r for r in flat if r["regular"] or r["playoff"]]
    sd = closeness_sd(reg_rows, cids)

    owners = {}
    h2h = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))

    def owner(season, tid):
        return per_season[season][2][tid]["owner"]

    for season, (data, rows, teams) in per_season.items():
        for s in data["standings"]:
            o = owners.setdefault(s["owner"], {"owner": s["owner"], "name": s["owner_name"], "seasons": [],
                                               "w": 0, "l": 0, "t": 0, "cw": 0, "cl": 0, "ct": 0,
                                               "titles": 0, "sweeps": 0, "playoffs": 0})
            o["name"] = s["owner_name"]
            champ = s["final_rank"] == 1 and data["complete"]
            o["seasons"].append({"season": season, "team": s["name"], "seed": s["seed"], "final_rank": s["final_rank"],
                                 "w": s["w"], "l": s["l"], "t": s["t"], "cat_pct": round(s["cat_pct"], 3),
                                 "champion": champ})
            for k in ("w", "l", "t", "cw", "cl", "ct", "sweeps"):
                o[k] += s[k]
            o["titles"] += champ
        for r in rows:
            if r["tier"].endswith("CONSOLATION_LADDER"):
                continue
            a, b = owner(season, r["home"]), owner(season, r["away"])
            if a == b:
                continue
            ia = 0 if r["hw"] > r["aw"] else 1 if r["hw"] < r["aw"] else 2
            h2h[a][b][ia] += 1
            h2h[b][a][[1, 0, 2][ia]] += 1

    close, sweeps = [], []
    ties = defaultdict(int)
    for r in reg_rows:
        t = r["teams"]
        for c in cids:
            a, b = r["hs"].get(str(c)), r["as"].get(str(c))
            if a is None or b is None or (a == 0 and b == 0):
                continue
            if abs(a - b) < 1e-9:
                ties[label(c)] += 1
                continue
            z = abs(a - b) / sd[c]
            close.append((z, {
                "season": r["season"], "mp": r["mp"], "cat": label(c), "cid": c,
                "home": t[r["home"]]["name"], "away": t[r["away"]]["name"],
                "hv": a, "av": b, "hw": r["hw"], "aw": r["aw"],
            }))
        if r["hw"] == 9 or r["aw"] == 9:
            w = r["home"] if r["hw"] == 9 else r["away"]
            sweeps.append({"season": r["season"], "mp": r["mp"], "winner": t[w]["name"],
                           "loser": t[r["away"] if w == r["home"] else r["home"]]["name"]})
    close.sort(key=lambda x: x[0])
    for o in owners.values():
        o["seasons"].sort(key=lambda s: s["season"])
        o["playoffs"] = sum(1 for s in o["seasons"] if s["seed"] <= 6)
    return {
        "owners": sorted(owners.values(), key=lambda o: -(o["w"] + 0.5 * o["t"]) / max(o["w"] + o["l"] + o["t"], 1)),
        "h2h": {a: {b: v for b, v in d.items()} for a, d in h2h.items()},
        "closest_cats": [c for _, c in close[:25]],
        "tied_cats": dict(ties),
        "sweeps": sweeps,
        "cats": [{"id": c, "label": label(c)} for c in cids],
    }
