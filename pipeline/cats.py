"""Category definitions for the ESPN H2H categories league."""

# ESPN stat id -> label
STATS = {
    0: "PTS", 1: "BLK", 2: "STL", 3: "AST", 6: "REB", 11: "TO",
    13: "FGM", 14: "FGA", 15: "FTM", 16: "FTA", 17: "3PM", 19: "FG%", 20: "FT%",
}
# display order for the 9 scored categories
ORDER = [0, 6, 3, 2, 1, 17, 19, 20, 11]
REVERSE = {11}
RATIO = {19: (13, 14), 20: (15, 16)}  # FG% = FGM/FGA, FT% = FTM/FTA
COUNTING = [0, 6, 3, 2, 1, 17, 11]
COMPONENTS = [13, 14, 15, 16]

# per-game overdispersion: var = mean + od * mean^2 (negative-binomial style spread)
OD = {0: 0.07, 6: 0.07, 3: 0.05, 2: 0.10, 1: 0.20, 17: 0.12, 11: 0.08, 14: 0.04, 16: 0.30}


def label(sid):
    return STATS[int(sid)]


def cat_ids(settings=None):
    """The scored stat ids for a season, in display order."""
    if settings:
        items = {i["statId"] for i in settings["scoringSettings"]["scoringItems"]}
        return [s for s in ORDER if s in items]
    return list(ORDER)
