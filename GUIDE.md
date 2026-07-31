# Qellys Book — Owner's Guide

Written for the owner, assuming no coding background. Everything you need
to run, check, and troubleshoot the system is on this page.

---

## The 30-second version

```
cd ~/App          (or wherever the project lives)
git pull          ← get the newest code whenever I tell you I pushed
python3 launch.py ← start everything → http://localhost:8000
```

Leave `launch.py` running in its terminal window. It refreshes every page
about once a minute, runs the nightly chores by itself, and prints one
line per product each cycle. **You almost never need any other command.**

To check health at any time (safe to run while the site is up):

```
python3 launch.py --check
```

That prints a full checklist: which data feeds are reachable, how fresh
each page's data is, whether every page's JSON is valid, how many rows
are in each database, journal status, and backups.

It can also **render all 13 pages in a headless browser** and report any
JavaScript error — the class of bug no data check can see (it is how a
phantom arbitrage on the Scanner and a broken parlay calculator were both
caught). That part is optional and skips with instructions unless you run
once:

```
npm install playwright && npx playwright install chromium
``` When something seems broken, run this first and paste me the
output.

---

## The six pages — what each one is

| Button | What it does | Live when |
|---|---|---|
| **⚾ MLB** | The betting model: player props, sharp-anchor game bets, Edge Board, Long Shots (home-run board), Record | Now (daily in season) |
| **🏈 NFL** | Same engine for football | September |
| **🛰️ Polymarket** | Informed-flow detection on prediction markets: whale flags with scores, top traders by profit, our flag report card | Now |
| **🏆 Fantasy** | Usage trends, buy-low/sell-high (xFP), game scripts, Sleeper league sync, **draft kit** (VORP board, tiers, live draft sync) | Now (2025 data until September) |
| **🏀 NBA** | Scalpy: minutes engine, probability distributions, humility clamp, max 4 picks a slate | October |
| **🥊 UFC** | Scalpy MMA: fighter dossiers, joint method-of-victory model, pass list | Fight weeks (needs dossiers — see below) |
| **🧭 Why Us** | The positioning page: what makes this different from picks services, live receipts from the journal, and an open math toolbox (de-vig, Kelly sizing, parlay-vs-singles calculators) | Always (no data feed needed) |

Shared ideas everywhere: **real prices only** (nothing is recommended
against a placeholder line), **every pick is journaled and graded**
(Record tab), and **an empty board explains itself** — if a page shows
nothing, read the message; it says exactly why and it's usually "working
as designed," not broken.

**Click any stadium.** The ballpark/stadium strip at the top of the MLB
and NFL boards is now clickable — each card says how many picks that game
has, and tapping it opens a page for just that matchup: the park and
weather, the game bets, every player prop in it, and any long shots. The
back button returns you to the board, and the page has its own link you
can bookmark or share.

That page also carries a **venue panel**. For all 30 ballparks it shows
the dimensions (left / center / right, plus any wall worth knowing about
— Fenway's 37-foot Monster, the 21-foot Clemente Wall at PNC), the three
park factors the model actually prices with, drawn as bars centered on
the league-average park, and a line on what the park is known for. The
dimensions are there to explain the factors, not to double-count them:
they're display only and never reach the model.

NFL stadiums get a shorter version — roof, altitude, surface — and say
so. A ballpark changes what identical contact produces, which is why MLB
park factors are large and worth modelling; a football field is 100 yards
everywhere, so the venue effect is almost entirely indoors-vs-outdoors
and then Denver's altitude. Live weather is the number that moves an NFL
total, and the game card already shows it.

## How to read the numbers (the honest version)

- **Edge / EV** — how much better the model thinks a price is than fair.
  A +5% EV bet still loses often; the edge only shows up over hundreds of
  bets.
- **CLV (closing line value)** — did the line move our way after we bet?
  This is the earliest real signal the process works. Win/loss over a
  week is noise; CLV over hundreds of bets is the scoreboard.
- **"No qualifying plays" / small pick counts** — the models are built to
  pass on most things. That is the discipline, not a bug.
- **Calibration readouts** (Record tab, Polymarket report card) — "model
  said X%, reality delivered Y%." When those track each other, trust
  grows; when they don't, we fix the model, not the story.

---

## What runs automatically

While `launch.py` is running, with no input from you:

- every ~60s: all six pages rebuild (scores free, odds only when the
  budget allows — cached prices in between, never placeholder lines)
- **every ~15 min: tonight's finished games are graded automatically.**
  Picks settle within about a quarter hour of the final out, and the
  Record page updates itself. You should never need `--settle` again.
- **at launch:** the same settle runs immediately, ignoring the timer —
  so opening the site the morning after a slate catches everything up.
- first cycle each day: ingest yesterday's MLB results, re-settle,
  update the Record page, harvest closing odds when affordable
- Polymarket: records the trade tape every cycle (it can't be rebuilt if
  missed — this is why the launcher should run daily)
- weekly: an automatic **backup** of both databases, the line-history
  file, and your UFC dossiers → `data/backups/` (newest 6 kept)

**"Why are my picks still open?"** Tonight's picks stay open until the
games actually end — that's correct, not a bug. `python3 launch.py
--check` now tells you which kind you have: it flags anything older than
yesterday as a real problem and says so, and confirms when the open ones
are just tonight's board waiting on results. It also prints when the
auto-settle last ran, so you can see the loop is alive.

## The few manual commands (rare)

| When | Command |
|---|---|
| I say "pull and relaunch" | `git pull`, then Ctrl+C the launcher and `python3 launch.py` |
| NFL data refresh (few times a season) | `python3 ingest.py nfl` |
| MLB history rebuild (rarely needed) | `python3 ingest.py mlb --from 2026-03-26 --to <today>` |
| NBA history (from October, occasionally) | `python3 ingest.py nba --from <start> --to <today>` |
| New Odds API key | put it in `secrets.local`, then `python3 launch.py --reset-budget` |
| Health check | `python3 launch.py --check` |
| Force a settle right now (rarely needed — it's automatic) | `python3 launch.py --settle` |
| Fold old 0.00-unit picks back into the record (once) | `python3 launch.py --resize-unstaked` |
| Separate long shots from the main record (once) | `python3 launch.py --repair-journal` |
| Why is the board empty? | `python3 launch.py --why-empty` |

**About `--settle`:** this used to be a nightly chore, because the journal
only graded itself on the first cycle of the *next* day. It doesn't work
that way any more — the launcher settles finished games every ~15 minutes
and again the moment you start it, so picks close out on their own within
about a quarter hour of the last out.

`--settle` is still there for two cases: grading an **older** date
(`python3 launch.py --settle 2026-07-25`), and forcing a run when you want
to watch it happen. It ingests that day's results, grades every open pick
against them, and prints the open → settled counts for both buckets so
nothing has to be taken on faith.

## Draft day (Fantasy page, before your Sleeper draft)

The Fantasy page carries a **draft kit** built from last season's usage:

- **Overall board** ranked by VORP — value over the best freely-available
  player at the same position. This is why the 4th-best QB sits below the
  15th-best WR: the QB you can get ten rounds later scores nearly as much.
- **Position tiers** — draft by tier, not rank. Inside a tier the
  differences are noise; the gaps between tiers are the real information.
- **Usage says buy** — players whose opportunity outran their scoring
  last year; the draft-day version of buy-low.
- **Live draft sync** — when your Sleeper draft room opens, paste the
  draft link into the "Draft day" box and hit Connect. Taken players
  cross off everywhere on the page as picks come in, and a best-available
  strip (overall + per position) stays current. Read-only, no password.

Honest limits, because they matter at the table: the board is last
season's volume run forward. Rookies carry no projection (none exists),
and a moved player's numbers came from his old offense — but the page
now TELLS you all of that instead of leaving you to remember it.

## The offseason panel (Fantasy page)

Above the draft kit, the page shows **what the league changed under last
season's numbers** — refreshed automatically on every build, derived
from data rather than from a news list that goes stale:

- **Coaching changes** come from the nflverse schedule file itself:
  every game row is stamped with both head coaches, so "new coach" is a
  diff between a team's last game of last season and next season's rows.
- **Current teams & rookies** come from Sleeper's public players feed
  (the same one league sync uses, cached daily). Board players who
  changed teams get a NEW TEAM flag — their projection is deliberately
  NOT adjusted, because nobody knows what the new offense does to their
  volume, and flagging honestly beats inventing a number.
- **New starting QBs**: current depth-chart QB1 vs the QB who actually
  started late last season.
- **Rookies** are listed with their current depth-chart slot and no
  projection — no NFL volume exists, and the site doesn't fake numbers.

The launcher's daily maintenance also re-pulls the NFL schedule, so as
books post next season's lines over the summer, the **game scripts**
section fills in on its own.

## UFC dossiers (a two-minute review before each card)

The UFC model follows "no dossier, no bet" — and dossiers now draft
themselves. Before a card you care about, run:

```
python3 ufc_dossiers.py
```

It reads the upcoming card from the odds feed (free), pulls every
fighter's real fight-by-fight stats from ESPN's public MMA data, and
writes drafted dossiers into `data/ufc_dossiers.json`. First run takes a
few minutes for a full card (~30s per fighter, then cached). Your job is
the two-minute review it prints at the end:

1. Open `data/ufc_dossiers.json` and check each entry's `review` notes —
   the archetype is guessed from stats, so fix any style you know better.
2. **Red flags block bets on purpose** (chin damage, long layoffs, age).
   Delete a red flag only once you've checked it; leave it and the fight
   stays on the pass list.
3. Or skip the JSON entirely: `python3 ufc_dossiers.py --review` lists
   every flag with context, and
   `python3 ufc_dossiers.py --clear "Fighter Name"` clears one once
   you've checked it.
4. Anything you edit by hand is never overwritten by the tool. Fighters
   it can't find (debutants) stay on the pass list — which is correct.

---

## Money & API facts

- **One API key total**: `ODDS_API_KEY` in `secrets.local` (The Odds
  API — sportsbook prices for MLB/NFL/NBA/UFC). Everything else —
  Polymarket, NBA CDN, MLB Stats, nflverse, Sleeper, Savant, weather —
  is free and keyless.
- The odds budget is paced automatically (credits reset monthly). If the
  board says prices are cached, that's the pacer saving credits, not an
  error. Don't buy extra credits.
- Nothing here places bets. It recommends, journals, and grades.

## When something looks wrong

1. Screenshot the page **and** copy the last ~20 lines from the launcher
   terminal.
2. Run `python3 launch.py --check` and copy its output.
3. Send me all of it. The terminal usually names the exact failing feed —
   that's how we've fixed every issue so far (Statcast, nflverse, the
   Polymarket leaderboard…).

Golden rules: an empty section with an explanation is usually the filters
working. Odd numbers at ~11pm are usually in-play prices. And if the data
looks frozen, check that the launcher terminal is still running — it's
the heartbeat of the whole system.
