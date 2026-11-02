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
- game-to-game spread per category, with swings shared across a player's stats (minutes) and across a team's players that day (pace, blowouts); FG% and FT% are simulated from makes and attempts
- games in progress count as half remaining, and a game counts as over 3 hours after tip-off; injured players are discounted

Each category gets a win probability and a **swing**: how many points of matchup win probability change depending on who takes it. **Sweat** = swing x how uncertain the category is, which is what ranks the board.

## Injuries

ESPN's `injuryStatus` is one flag as of the moment of the fetch, and it reads `NORMAL` for every player on the league's rosters, so it cannot tell the live model who is out. `pipeline/injuries.py` fetches the newest **official NBA injury report** (a PDF the league publishes about every 15 minutes), parses it with `pdftotext` word geometry, and matches names to the league's rostered players. The live model then uses a per-game chance of playing, measured on 14,435 report listings from the 2024-25 and 2025-26 seasons against the box scores (rotation players): for a report written the same day Out 0.09, Doubtful 0.27, Questionable 0.64, Probable 0.83, Available 0.96; for a report written the day before Out 0.01, Doubtful 0.27, Questionable 0.54, Probable 0.93, Available 0.98. An Out listing within an hour of tip-off counts as 0. Players the report does not list, and teams whose list is not filed yet, fall back to ESPN's flag.

The report only covers today and tomorrow. For later games a starter listed Out for an injury at his team's last covered game keeps a low but rising chance of playing (0.13 for his next game, 0.24, 0.29, 0.33, up to 0.46 ten games out), measured on the same listings. Each game day's listing is archived in `data/raw/<season>/injuries/` so these numbers can be refit by designation later. Needs poppler (`brew install poppler`, installed in the workflow); without it the step is skipped and ESPN's flag is used.

**Season projections and injuries.** Category results lag a long injury, so a team that loses its stars keeps the strength it earned with them. `features/race.py` measures the share of each team's core (its 9 most valuable players, any slot, so a benched or IR star counts) that is listed Out for an injury in the newest report and lowers the team's strength for the games still to play, fading over the next five weeks (`KAPPA`, `HEALTH_PERSIST`). In a backtest on 146 matchups from 2025-26 this improved prediction in both seasons held out, and the weight is applied at about three quarters of its fitted size because the sample is small. The Race for Last table lists who is out under each team.

## Hosting (GitHub Pages + auto-refresh)

1. In the GitHub repo go to **Settings, Pages, Build and deployment, Source** and choose **GitHub Actions**.
2. Under **Settings, Secrets and variables, Actions** add the secrets `LEAGUE_ID`, `ESPN_S2` (decoded) and `SWID` (with braces).
3. Run **Actions, Refresh league data** once. After that it runs every 10 minutes from midday ET through the late games, and every 5 minutes on Sundays (the fastest GitHub allows; it often runs a few minutes late). Each run first checks the NBA schedule and skips itself when no game is on, so off days cost almost nothing. The site redeploys on every run, but the data is committed once a night so the repo stays small. GitHub's scheduler is unreliable and drops runs, so a free external scheduler (see below) is the primary trigger and the GitHub schedule is the backup. ESPN cookies last about a year; when they expire the runs fail and GitHub emails you, and you replace the `ESPN_S2` and `SWID` secrets.

### Reliable trigger with cron-job.org

1. GitHub, **Settings, Developer settings, Fine-grained tokens**: new token, only this repository, **Actions: Read and write** (nothing else), 1-year expiry. It can start workflows but cannot touch the code.
2. cron-job.org, new cron job:
   - URL `https://api.github.com/repos/lmaynor/league-analytics/actions/workflows/refresh.yml/dispatches`
   - Schedule: every 5 minutes, timezone America/New_York, hours 11 to 23 and 0 to 1
   - Advanced: method **POST**, body `{"ref":"main","inputs":{"source":"cron"}}`, headers `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - A success is HTTP 204. Turn on failure notifications.
3. `source: cron` makes the run behave like a scheduled one: it skips itself when no NBA game is on and commits data once a night. The default `manual` always builds and commits.

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

Daily rosters are cached in `data/raw/<season>/days/`. The first fetch of a season pulls about 150 days (every season since 2018 is already cached in the repo). After that only the last three days of the current season are refreshed. `DAILY_SEASONS=2025,2026,2027` chooses which seasons get daily data (default: this season and last).

Owner display names live in `config/owners.json` (generated from ESPN handles). Edit them to real names or nicknames. Add `"same_as": "<owner id>"` to merge a duplicate account into another owner.
