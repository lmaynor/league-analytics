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
  features/         standings, history, records, live, cheerios, superlatives, race, swaps, trades
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

Each feature writes its own file (`live.json`, `records.json`, `cheerios.json`, `superlatives.json`, `history.json`, `rosters.json`, `season_<year>.json`). One failing feature does not stop the rest.

## How the numbers work

- **Win chance (live):** the rest of the matchup week is simulated 10,000 times from live category totals, current rosters and the remaining NBA games. Lineups lock weekly (see below), so each team's current starters play every game they have left; bench players never replace an injured or resting starter. Players blend this season's form into last season and ESPN's projection. FG%/FT% are simulated from makes and attempts. A game counts as over once ESPN marks it official or 3 hours after tip.
- **Odds stay hidden until lineups lock.** Per matchup, every starter on both teams must have tipped off (a starter locks at his NBA team's first game of the matchup week) before win chance, category odds, swing, projections, tonight's watch lists, Bench Regret or the live part of Race for Last are computed into the published JSON. Until then `live.json` carries only names, the score so far and current category values (`hidden: true` plus lock counts), so the data files cannot be used to plan lineups. Starters with no game that week do not count. See `lock_counts` and `hide` in `features/live.py`.
- **Rolling win chance:** each open matchup's card on the Full Scoreboard shows its win chance day by day (from `matchup_daily` in `race.json`), ending on the live odds. Hidden matchups never show it.
- **Worst Healthy Starter:** each completed week, the starter with the lowest contribution (his starts scored stat by stat against the season's average starter-game, turnovers flipped) among players with 2+ starts, no missed starter games that week and no injury flag. From `lineup.json`, shown on the Scoreboard for that week. Only completed weeks, so it can't change.
- **Injuries come from the official NBA injury report** (`pipeline/injuries.py`, a port of mlb-betting's `nba/data/nba_injury_report.py` without pandas). ESPN's `injuryStatus` is `NORMAL` for every rostered player, so it carries no information here. The newest 15-minute PDF is fetched in `fetch.py` (never fatal, needs `pdftotext`, installed by the workflow), parsed by word geometry, matched by normalized name to rostered players, stored as `data/raw/<season>/injuries.json`, and each game day's listing is archived in `data/raw/<season>/injuries/<date>.json`. `live.plan_team` asks `injuries.build_lookup` for each starter's chance of playing each game. The numbers are MEASURED, not priors: 14,435 report listings (one report per game day at ~5 PM ET, 2024-25 and 2025-26 regular seasons, fetched from the NBA CDN with `injuries.py`) scored against mlb-betting's SportsBlaze NBA box-score master (`NBA/player_boxscores_master.csv` in its data lake), rotation players (20+ minutes lately). Same-day report: Out .09, Doubtful .27, Questionable .64, Probable .83, Available .96; day-before report: Out .01, Doubtful .27, Questionable .54, Probable .93, Available .98; Out same day by reason: rest .25, G League 0, injury .08; an Out within an hour of tip counts as 0. Team-level NOT YET SUBMITTED rows mean unknown, not healthy. Past the report's last date (or a team's unfiled day), a starter listed Out for an injury (not rest) carries forward at `CARRY_Q` = .13 .24 .29 .33 .35 .38 .40 .44 .45 .46 for his k-th later team game (measured the same way; an earlier guess from ordinary missed games, .55 .67 .71, was far too high). Listing streaks do not raise the return odds (first day .15, 2nd-3rd .10, 4th-9th .05). Minutes when he plays are 93-99% of usual, so no minutes adjustment. Report older than 6 h is ignored. `live.json` carries `injury_report` for the page.
- **Live model backtest (2026-11-01):** point-in-time replay of 876 matchup-days (end of each day 1-6 of 146 regular weeks, 2025 and 2026) using the real locked lineups from the daily rosters, category totals so far, remaining NBA games, player averages from box scores before that date (mlb-betting's NBA box-score master; the ESPN projection blend cannot be reproduced point in time), and the injury reports fetched for those days. Scored against the real results: matchup log loss .433 vs .532 for the strength+lead logistic; category log loss .341. The first version (independent players) was overconfident (favorites predicted 83% won 80%), so the simulation now has shared swings, `SHARED_PLAYER` = `SHARED_TEAM` = .2 in `features/live.py`, which moved matchup log loss .461 -> .433 and category log loss .352 -> .341 (better in both seasons; favorites predicted 79.2% won 79.5%). Injury information alone: +.012 matchup log loss per matchup-day, 95% interval -.006 to +.036 across weeks, so not significant on its own at the weekly level (categories .362 -> .352). Home/away is arbitrary here, so judge calibration from the favorite's side. The replay script was not kept in the repo (it needs the box-score master); rebuild it from `live.plan_team`, `live.simulate_team`, `injuries.build_lookup` and `features/collapse.partial`.
- **Season projection backtest (2026-11-01):** replayed 9 finished seasons (2018-2026) at weeks 2, 4, 6, 8, 10, 12, 14, 16 using only results to that point (678 team-checkpoints), with the matchup scale K fitted without the scored season (K 5.0-6.0), scored against the real regular-season finish. Projected final wins beat both 'assume .500' and 'win pace' at every checkpoint (MAE 1.35 vs 1.47 wins overall). Event odds were far better than base rates (top-4 log loss .40 vs .68; last place .23 vs .34; top seed .23 vs .34; bottom 3 .40 vs .62) but overconfident at the extremes (last-place odds of 70% came true half the time; 70-90% top-4 odds came true 67%), because strength was treated as known. `STRENGTH_SD_MULT` = 2 in `features/race.py` draws each team's true strength around its estimate with sd shrinking as results accumulate; average log loss over the four events .314 -> .301 chosen without each season in turn, better in 8 of 9 seasons. The injury adjustment below was backtested on matchups only (2025-26), not on whole seasons. The replay script was not kept in the repo; it is a reimplementation of `race.simulate` over `standings.build_season` rows.
- **Season projections and injuries** (`race.core_out_shares`, `KAPPA` .35, `HEALTH_PERSIST`): for the current projection only (not past chart points), each team's strength is lowered by `KAPPA * persistence[weeks ahead] * out_share`, where `out_share` is the share of its core (9 most valuable players by a z-sum of PTS REB AST STL BLK 3PM TO from ESPN per-game means, any slot) listed Out for an injury in the newest report. Backtest (146 matchups, 2025-26, reports of the day, `value_before` from box scores): matchup log loss .670 -> .655 leave-one-season-out, healthier side won 64% where one side had 10%+ more out vs 54% from results alone; fitted weight 2.6 logit per unit, 95% interval from slightly below 0 to about +5 across weeks (small sample), so 3/4 of it is applied. The fade after week 1 is not separately validated; it follows the measured return curve. `race.json` teams carry `out_share` and `out_names`; the Race tab lists them. Dropped for a lineup-only definition: the core version tested at least as well and also counts a benched or IR star.
- **Daily win chance** (partway through a week, used by the Race for Last day points, the Scoreboard rolling chart and Biggest Throw): `race.daily_win_prob`, a logistic on the strength gap and the category lead with weights by day of the week (strength matters early, the lead takes over by midweek), fit on 146 matchups from 2025-26 and checked on the other season (log loss .559/.524 vs .596/.590 for the old 50/50 average, which understated late-week certainty). Not the live Monte Carlo; that is only used after lineups lock.
- **Biggest Throw:** each completed week, the lost matchup where the loser's daily win chance fell furthest from its peak to the last day before the final (peak at least 55%). From `collapse.json` (score includes ties), shown on the Scoreboard.
- **Swing** = how much a category moves matchup win chance. **Sweat** = swing x how open the category is.
- **xWin** = each week, matchups your totals would win against all other teams, summed. **Luck** = actual wins - xWin.
- **Power** = 60% season category win rate + 40% last four weeks.
- **Red Cheerios:** a "miss" is a starter in an active slot on a day his NBA team played who did not play. Injuries and rest days both count. Each miss adds his per-game average back to the team's totals and the week is re-scored against the real opponent. Daily rosters are cached for every season since 2018; the nightly refresh only pulls the newest days (`DAILY_SEASONS`, default the last two seasons).
- **Race for Last:** the chart toggles between Chance of Last and Final Position (projected place, 1st at top, each place used once per checkpoint by ranking teams on average finish; `expect` holds those per checkpoint and `finish` the odds of each place in `race.json`). The live week adds one point per scoring day. The rest of the regular season is simulated 10,000 times from category strength (this season blended with the owner's share last season) and the real schedule; the live week uses live odds. The win model (K = 5.73) was fit on 2018-2026 matchups. Finished seasons use the real order.
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

- `TABS` registry in `core.js`; 4 top-level pillars (`matchups`, `season`, `teams`, `history`), each using `subnav()` rendering into `#panel`. Hash routes: `#matchups/scoreboard`, `#matchups/recap`, `#season/standings`, `#season/power`, `#season/projections`, `#teams/categories`, `#teams/cheerios`, `#teams/trades`, `#history/owners`, `#history/h2h`, `#history/records`, `#history/supers`. Legacy routes still resolve.
- Scoreboard has Auto / Compact / Full detail (Auto switches to Full on the final day) and a Week dropdown for the current season's earlier weeks; past weeks show final scores.
- Phones (<=700px): bottom tab bar, matchup tile strip + snap-scroll card deck that loops (copies of the last and first card sit at the ends and the deck jumps back once the swipe stops; deck height and the jump wait for the scroll to settle), pull to refresh, haptic ticks (Android vibrate; iOS checkbox-switch trick), safe-area padding. Installable (manifest + apple-touch-icon).
- Light/dark theme: `data-theme` set before paint; follows the system until the user taps the toggle. Colors are tokens in `:root` and `:root[data-theme="dark"]`.
- Test at phone widths with an iframe harness; headless Chrome cannot go narrower than ~500px as a window, and does not deliver scroll or rAF events promptly.

## Conventions and preferences

- Design: "Cobalt" (near-white paper, hairlines, one cobalt accent, graphite panels, keycap buttons). Title Case headings and column headers. No emoji, gradients, glass or left-stripe cards in the UI.
- Copy: short, plain, natural; no em dashes; no hype words; do not explain the joke (the name Red Cheerios stands alone). Owner names are first names.
- Comments: only where they say something the code does not (why, constraints); no banners, narration or end markers.
- Scheduling: cron-job.org POSTs a `workflow_dispatch` with `inputs.source=cron` (fine-grained token, Actions write only) every 5 minutes; GitHub's own `schedule` stays as a backup because it drops runs. `source=cron` applies the NBA game gate and the nightly-commit rule; the default `manual` bypasses both. Steps are in the README.
- Ship style: commit and push straight to `main`, then `gh workflow run refresh.yml` to deploy. End commit messages with the Claude co-author line.
- Never commit `.env` or cookie values; owner account ids are hashed in raw data.

## Known leftovers

- Header wraps in the 701 to 740px width range.
- Real-device touch (haptics, pull to refresh feel, 44px targets) was never tested off a simulated browser.
- Older seasons (2018 to 2024) have no day-by-day week breakdown from ESPN, so their matchup weeks are derived from the NBA calendar (Monday to Sunday ET, an almost empty All-Star week folds into the next). This matched ESPN's own weeks in 2025 and 2026. Estimated playoff weeks are skipped by Red Cheerios because finals can span two weeks.
