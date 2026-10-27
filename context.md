# Project context

Notes for anyone (human or Claude) picking this project up cold.

## What this is

Analytics site for an ESPN **H2H 9-category** fantasy basketball league: Big Ballers and Kenneth, ESPN league `173530`, 10 teams, seasons 2018 to now. Categories: PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO (turnovers: lower wins).

- Repo: `lmaynor/league-analytics` (a fork of `MidZayAI/league-analytics`, which was a points-league project; this is a full rewrite for categories). Open PRs against **your own fork** (`--repo lmaynor/league-analytics`), never the upstream.
- Live site: https://lmaynor.github.io/league-analytics/ (GitHub Pages, deployed by Actions).
- Python pipeline reads ESPN, writes JSON to `site/data/`. `site/` is a static page: plain HTML, CSS, JS, no build step.

## Layout

```
pipeline/
  build.py          orchestrator; runs each feature and writes its JSON (--fetch, --only a,b)
  fetch.py          ESPN -> data/raw/<season>/ (league, rosters, daily rosters, NBA schedule)
  espn_client.py    cookie auth is optional for past seasons
  season.py         current season from the date (SEASON env overrides)
  cats.py           stat ids, display order, spread model
  matchups.py       shared parsing: schedule entries -> category results
  should_run.py     CI gate: only run while an NBA game is on
  features/         standings, history, records, live, cheerios, superlatives, race, swaps
site/
  index.html        shell, footer "How This Works", tab bar, theme/refresh buttons
  style.css         Cobalt theme, dark theme, phone shell
  js/core.js        state S, TABS registry, router, sortable tables, theme, haptics
  js/tab-*.js       one file per view; odds.js = shared live-odds cards
  js/main.js        boot, pull to refresh, refresh button
data/raw/           cached ESPN data (committed)
config/owners.json  owner id -> first name; "same_as" merges duplicate accounts
.github/workflows/refresh.yml
```

Each feature writes its own file (`live.json`, `records.json`, `cheerios.json`, `superlatives.json`, `history.json`, `season_<year>.json`). One failing feature does not stop the rest.

## How the numbers work

- **Win chance (live):** the rest of the matchup week is simulated 10,000 times from live category totals, current rosters and the remaining NBA games. Lineups lock weekly (see below), so each team's current starters play every game they have left; bench players never replace an injured or resting starter. Players blend this season's form into last season and ESPN's projection. FG%/FT% are simulated from makes and attempts. A game counts as over once ESPN marks it official or 3 hours after tip.
- **Odds stay hidden until lineups lock.** Per matchup, every starter on both teams must have tipped off (a starter locks at his NBA team's first game of the matchup week) before win chance, category odds, swing, projections, tonight's watch lists, Bench Regret or the live part of Race for Last are computed into the published JSON. Until then `live.json` carries only names, the score so far and current category values (`hidden: true` plus lock counts), so the data files cannot be used to plan lineups. Starters with no game that week do not count. See `lock_counts` and `hide` in `features/live.py`.
- **Swing** = how much a category moves matchup win chance. **Sweat** = swing x how open the category is.
- **xWin** = each week, matchups your totals would win against all other teams, summed. **Luck** = actual wins - xWin.
- **Power** = 60% season category win rate + 40% last four weeks.
- **Red Cheerios:** a "miss" is a starter in an active slot on a day his NBA team played who did not play. Injuries and rest days both count. Each miss adds his per-game average back to the team's totals and the week is re-scored against the real opponent. Daily rosters are cached for every season since 2018; the nightly refresh only pulls the newest days (`DAILY_SEASONS`, default the last two seasons).
- **Race for Last:** the chart toggles between Chance of Last and Final Position (expected finish, 1st at top; `expect` and `finish` in `race.json`). The rest of the regular season is simulated 10,000 times from category strength (this season blended with the owner's share last season) and the real schedule; the live week uses live odds. The win model (K = 5.73) was fit on 2018-2026 matchups. Finished seasons use the real order.
- **Bench Regret:** lineups lock for the week, so a swap is a whole week: a benched player who played is swapped into the slot of a starter he was eligible to replace (`eligibleSlots` is stored in the daily rows), his week of real stats against the starter's, and swaps that improve the matchup result are shown. Hindsight only, since nothing can change once the lock holds.
- **Records / Superlatives:** single-week records skip All-Star breaks and two-week finals; the week in progress is excluded. Superlatives are **all-time**: each award goes to the single best season or game across every season on record, shown once with its year; they count games in a starting slot, and the current season is held back until it has 14 days.

## ESPN quirks learned the hard way

- Category scores live in `scoreByStat` on each schedule entry (`totalPoints` is 0 in a category league). `cumulativeScoreLive` has the in-progress week.
- Stat ids: 0 PTS, 1 BLK, 2 STL, 3 AST, 6 REB, 11 TO, 13/14 FGM/FGA, 15/16 FTM/FTA, 17 3PM, 19 FG%, 20 FT%.
- A player who did not play gets an **empty** stat line (`stats: {}`) for that day. ESPN may also send two game lines per day (the previous game and the day's own): match on `scoringPeriodId == day`.
- `injuryStatus` is only the status as of the fetch, never historical.
- Without cookies ESPN returns zeroed scores for the current season. Cookies live in `.env` locally and in Actions secrets.
- **Lineups lock weekly**: `lineupLocktimeType: INDIVIDUAL_FIRSTGAME_WEEKLY`, each player locks at his first game of the matchup week, and slots barely change after day one (about 3% of player-weeks, all before the lock). No mid-week pickups or bench swaps, so injuries stay injuries (Red Cheerios) and the live simulation keeps the current starters.
- Seasons before 2025 have empty `pointsByScoringPeriod` on schedule entries, and `matchupPeriods` is useless (period n maps to [n]); see the calendar derivation in `matchups.py`.
- Matchup weeks run Monday to Sunday (ET); the final day comes from the NBA schedule, not the device clock.

## Deploy and hands-off operation

- Actions workflow `Refresh league data`: cron every 10 min from midday ET through late games, every 5 min on Sundays (ET). The first step (`should_run.py`) skips the run when no game is on. Manual runs always go.
- Data is committed **once a night** (last run of the evening) to keep history small; the site redeploys on every run that does work.
- Secrets: `LEAGUE_ID`, `ESPN_S2` (decoded, no `%2F`), `SWID` (with braces). Cookies expire about yearly: runs fail, GitHub emails the owner, replace the two cookie secrets.
- Season rolls over by date; set the `SEASON` repo variable only to override. GitHub disables scheduled workflows after 60 days of repo inactivity.
- Bot commits land on `main` while you work: `git pull --rebase -X ours origin main` before pushing (generated data conflicts take the bot's version).
- Static assets are stamped with content hashes by `build.py` (`?v=...`); the refresh button reloads the page if it was redeployed.

## Front end notes

- `TABS` registry in `core.js`; views with sub-views use `subnav()` and render into `#panel`. Hash routes: `#scoreboard`, `#standings/power`, `#history/supers`. Old links (`#sweat`, `#scores`, `#cats`, `#regret`) still resolve.
- Scoreboard has Auto / Compact / Full detail (Auto switches to Full on the final day) and a Week dropdown for the current season's earlier weeks; past weeks show final scores.
- Phones (<=700px): bottom tab bar, matchup tile strip + snap-scroll card deck that loops (copies of the last and first card sit at the ends and the deck jumps back once the swipe stops; deck height and the jump wait for the scroll to settle), pull to refresh, haptic ticks (Android vibrate; iOS checkbox-switch trick), safe-area padding. Installable (manifest + apple-touch-icon).
- Light/dark theme: `data-theme` set before paint; follows the system until the user taps the toggle. Colors are tokens in `:root` and `:root[data-theme="dark"]`.
- Test at phone widths with an iframe harness; headless Chrome cannot go narrower than ~500px as a window, and does not deliver scroll or rAF events promptly.

## Conventions and preferences

- Design: "Cobalt" (near-white paper, hairlines, one cobalt accent, graphite panels, keycap buttons). Title Case headings and column headers. No emoji, gradients, glass or left-stripe cards in the UI.
- Copy: short, plain, natural; no em dashes; no hype words; do not explain the joke (the name Red Cheerios stands alone). Owner names are first names.
- Comments: only where they say something the code does not (why, constraints); no banners, narration or end markers.
- Ship style: commit and push straight to `main`, then `gh workflow run refresh.yml` to deploy. End commit messages with the Claude co-author line.
- Never commit `.env` or cookie values; owner account ids are hashed in raw data.

## Known leftovers

- Header wraps in the 701 to 740px width range.
- Real-device touch (haptics, pull to refresh feel, 44px targets) was never tested off a simulated browser.
- Older seasons (2018 to 2024) have no day-by-day week breakdown from ESPN, so their matchup weeks are derived from the NBA calendar (Monday to Sunday ET, an almost empty All-Star week folds into the next). This matched ESPN's own weeks in 2025 and 2026. Estimated playoff weeks are skipped by Red Cheerios because finals can span two weeks.
