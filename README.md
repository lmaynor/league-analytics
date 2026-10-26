# League Analytics (H2H categories)

Analytics for an ESPN **H2H 9-category** fantasy basketball league (PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO):

- **Scoreboard** for the live matchup week, with a Full view that adds each category's win probability, ranked by how much it can swing the matchup, plus who still plays tonight. It switches to Full on the final day of the week.
- **Red Cheerios** (named for ESPN's red O marking a player Out): what each week would have looked like if no starter had missed a game, with wins lost and gifted
- Standings with category record, xWin (expected wins against every team) and luck, one-category results, and power rankings
- Category strength heatmap for every team
- Weekly scoreboard with category-by-category results
- All-time history: titles, head-to-head records, closest category finishes, 9-0 sweeps

A Python pipeline pulls ESPN data and writes JSON to `site/data/`. `site/` is a static page (plain HTML/CSS/JS, no build step). GitHub Actions refreshes the data on a schedule and publishes `site/` to GitHub Pages.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # fill in LEAGUE_ID, SEASON, ESPN_S2, SWID
.venv/bin/python pipeline/build.py --fetch   # pull ESPN data + rebuild
.venv/bin/python -m http.server 8000 -d site
```

Then open http://localhost:8000.

`ESPN_S2` and `SWID` are your ESPN cookies (browser dev tools, Cookies, fantasy.espn.com; keep the braces on `SWID`). Past seasons load without them, but the current season's live scores and rosters need them. Use the decoded `ESPN_S2` value (no `%2F`-style escapes).

## How the live odds work

For the current matchup week, `pipeline/features/live.py` takes each side's live category totals, then simulates the rest of the week 10,000 times:

- every remaining NBA game for each team's current starters (lineups lock weekly, so nobody swaps mid-week)
- player averages blend this season's form into last season and ESPN's projection
- game-to-game spread per category; FG% and FT% are simulated from makes and attempts
- games in progress count as half remaining, and a game counts as over 3 hours after tip-off; injured players are discounted

Each category gets a win probability and a **swing**: how many points of matchup win probability change depending on who takes it. **Sweat** = swing x how uncertain the category is, which is what ranks the board.

## Hosting (GitHub Pages + auto-refresh)

1. In the GitHub repo go to **Settings, Pages, Build and deployment, Source** and choose **GitHub Actions**.
2. Under **Settings, Secrets and variables, Actions** add the secrets `LEAGUE_ID`, `ESPN_S2` (decoded) and `SWID` (with braces).
3. Run **Actions, Refresh league data** once. After that it runs every 10 minutes from midday ET through the late games, and every 5 minutes on Sundays (the fastest GitHub allows; it often runs a few minutes late). Each run first checks the NBA schedule and skips itself when no game is on, so off days cost almost nothing. The site redeploys on every run, but the data is committed once a night so the repo stays small. ESPN cookies last about a year; when they expire the runs fail and GitHub emails you, and you replace the `ESPN_S2` and `SWID` secrets.

Hosted pages are public, so team names and scores are visible to anyone with the URL. Your cookies are not. Raw files keep only owners' ESPN display names, and account IDs are hashed.

**New season:** nothing to do. The season is detected from the date (September to December belongs to the season ending next year). Set a `SEASON` repository variable only to override it.

## Files

The pipeline and the site are both split by feature, so each can change or break on its own.

| Piece | Files |
|---|---|
| ESPN client (cookie auth, optional for public data) | `pipeline/espn_client.py` |
| Fetch and cache raw data, including daily rosters | `pipeline/fetch.py` |
| Category ids, order, spread model | `pipeline/cats.py` |
| Matchup parsing shared by every feature | `pipeline/matchups.py` |
| Orchestrator (`--only live,records` rebuilds some features) | `pipeline/build.py` |
| Standings, luck, category strength, power rank | `pipeline/features/standings.py` |
| All-time owners, head to head, closest finishes | `pipeline/features/history.py` |
| League records | `pipeline/features/records.py` |
| Live forecast and sweat engine | `pipeline/features/live.py` |
| Red Cheerios what-if | `pipeline/features/cheerios.py` |
| Site: shared state, router, sortable tables | `site/js/core.js` |
| Site: one file per tab | `site/js/tab-*.js` |
| Site: odds cards shared by the Scoreboard's Full view | `site/js/odds.js` |

Each feature writes its own file in `site/data/` (`live.json`, `records.json`, `cheerios.json`, `history.json`, `season_<year>.json`). A feature that fails is reported and skipped; the rest still build.

Daily rosters are cached in `data/raw/<season>/days/`. The first fetch of a season pulls about 150 days. After that only the last three days of the current season are refreshed. `DAILY_SEASONS=2025,2026,2027` chooses which seasons get daily data (default: this season and last).

Owner display names live in `config/owners.json` (generated from ESPN handles). Edit them to real names or nicknames. Add `"same_as": "<owner id>"` to merge a duplicate account into another owner.
