# Gridiron Edge — Owner's Guide

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
each page's data is, how many rows are in each database, journal status,
and backups. When something seems broken, run this first and paste me the
output.

---

## The six pages — what each one is

| Button | What it does | Live when |
|---|---|---|
| **⚾ MLB** | The betting model: player props, sharp-anchor game bets, Edge Board, Long Shots (home-run board), Record | Now (daily in season) |
| **🏈 NFL** | Same engine for football | September |
| **🛰️ Polymarket** | Informed-flow detection on prediction markets: whale flags with scores, top traders by profit, our flag report card | Now |
| **🏆 Fantasy** | Usage trends, buy-low/sell-high (xFP), game scripts, Sleeper league sync | Now (2025 data until September) |
| **🏀 NBA** | Scalpy: minutes engine, probability distributions, humility clamp, max 4 picks a slate | October |
| **🥊 UFC** | Scalpy MMA: fighter dossiers, joint method-of-victory model, pass list | Fight weeks (needs dossiers — see below) |
| **🧭 Why Us** | The positioning page: what makes this different from picks services, live receipts from the journal, and an open math toolbox (de-vig, Kelly sizing, parlay-vs-singles calculators) | Always (no data feed needed) |

Shared ideas everywhere: **real prices only** (nothing is recommended
against a placeholder line), **every pick is journaled and graded**
(Record tab), and **an empty board explains itself** — if a page shows
nothing, read the message; it says exactly why and it's usually "working
as designed," not broken.

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
- first cycle each day: ingest yesterday's MLB results, settle the bet
  journal, update the Record page, harvest closing odds when affordable
- Polymarket: records the trade tape every cycle (it can't be rebuilt if
  missed — this is why the launcher should run daily)
- weekly: an automatic **backup** of both databases, the line-history
  file, and your UFC dossiers → `data/backups/` (newest 6 kept)

## The few manual commands (rare)

| When | Command |
|---|---|
| I say "pull and relaunch" | `git pull`, then Ctrl+C the launcher and `python3 launch.py` |
| NFL data refresh (few times a season) | `python3 ingest.py nfl` |
| MLB history rebuild (rarely needed) | `python3 ingest.py mlb --from 2026-03-26 --to <today>` |
| NBA history (from October, occasionally) | `python3 ingest.py nba --from <start> --to <today>` |
| New Odds API key | put it in `secrets.local`, then `python3 launch.py --reset-budget` |
| Health check | `python3 launch.py --check` |

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
3. Anything you edit by hand is never overwritten by the tool. Fighters
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
