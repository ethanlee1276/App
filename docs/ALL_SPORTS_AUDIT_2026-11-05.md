# Every league, audited: what each model reads, what was added, what is open (2026-11-05)

Ethan, 2026-11-05: *"Go through nfl and CFB and nba and mlb and wnba and
nhl and pollymarkwt and crypto and make sure we have all the tools and
data we can be using like how we just added for nba and have had for
nfl ... create new things, add new things ... Don't stop till you're
done."*

The NFL has had the most work since August, and the NBA got its lab on 4
November: two full seasons of the league's own play-by-play, every idea
fitted on one season and judged on the next. This document takes every
other league through the same questions. What does its model read? Has
each piece been measured on games the model never saw? What data could
still be reached?

The rule is the one every lab here follows: a new piece of data is shown
first, measured second, and only then allowed to move a number.

Each line is one of:

* **Built today**: in the code, tested, on the box within five minutes
  of the push.
* **Box run**: a read-only check on the box's own data, with its step in
  `docs/WHEN_YOU_ARE_HOME.md` and its line in `docs/RUN_NEXT.md`.
* **Parked**: possible, waiting on data or a measurement first.
* **Not possible**: no feed we can reach has it.

---

## NHL (in season)

Until today every NHL constant was a plain prior written on 3 October.
The lab (`docs/NHL_LAB.md`) used three seasons of every NHL box score.

| | Status |
|---|---|
| A skater's rate reads a longer memory (half-life 12 → 30 games), his ice time a shorter one (6 → 3), from up to 60 games | **Built today**. Every prop market better on the season the fit never saw |
| A team's strength believed slowly (shrinkage 15 → 100 games, memory 25 → 40) | **Built today**. Moneyline, puck line and totals better in both seasons |
| Back-to-backs on both sides. The tired side scores 0.93 of the model's goals (was 0.97), its rested opponent 1.04 (was nothing) | **Built today** |
| Each skater's number on a back-to-back: fewer shots and goals for the tired side, more against it, more blocks for it; the card says `Rest: ...` | **Built today**. Three-quarters of the measured size, better in all five markets both ways |
| The goalie on a back-to-back: last night's starter starts again 9% of the time, the backup 78%; the card names him | **Built today**. Still no saves bet on an unsettled starter |
| **The crowd's price on every hockey game**: the board called the crowd hook, but neither Polymarket's nor Kalshi's reader listed the NHL, so no hockey game ever had a prediction-market price | **Built today**. Both readers list it. Kalshi's spread and total names wait for `crowdprobe.py nhl` on the box, as every other league's did |
| The lab's changes re-read on the box's own games, this season's included | **Box run** (KK, `nhllabcheck.py`) |
| **The saves model**: it ran 5–6% high (a starter does not face every shot his team allows) and its spread 22% narrow, so every saves pick was too sure of itself | **Built today**. Saves log loss 0.012 and 0.022 better held out, the lab's biggest gain |
| The goalie board names the likely backup the night after a starter played | **Built today** |
| Who takes a missing regular's ice time | **Measured twice, left off**: the depth chart moving up predicts his teammates' ice time 4–5% better in both seasons, but the prices got worse: the minutes go down the depth chart while the scoring goes to the forwards above (+5% to +10% points, +9% to +14% goals). A scoring lift holds only on a projection whose level is right, and the skaters' level moves by several percent between seasons. Next: the absent man's power-play time (`docs/NHL_LAB.md`) |
| The league's own API (api-web.nhle.com) | **Not possible** from the build sandbox; the box reads it, as it always has |

## WNBA (off season; next tip in May)

The WNBA board is the NBA's code with its own tuning. The NBA lab's
measured pieces were switched off for it until the WNBA's own seasons
said so. Lab: `docs/WNBA_LAB.md`, six seasons of box scores.

| | Status |
|---|---|
| The starting five's news, his first game back, and the NBA's weights on his newest games | **Built today**. Better in minutes and points in all six seasons; minutes error 2.6–3.3% lower |
| The role jump, his second game back, a regular's return | **Measured, left off**: each made points worse in at least one season |
| The spread that follows the projection (variance = a × mean^c) | **Built today**, behind the NBA's spread switch: fitted on one season and judged on the next, the Brier lower in every judged season for points, rebounds, assists, PRA and the combos; threes keep their CV. It goes on when the NBA's check and refit turn the NBA's on, and the refit fits the WNBA right after |
| The spread re-read on the box's own WNBA games | **Box run** (KM, `nbalabcheck.py --league wnba`) |
| Calibration | **Parked**: `calibrated=False` until next season's graded picks |

## NBA (in season)

The deepest after the NFL, as of the 4 November lab (`docs/NBA_LAB.md`):
shooting regression, the starting five's news, the rotation's three
rules, teammate-out minutes, first basket, per-player spread, the
alternate rungs' own correction.

| | Status |
|---|---|
| The spread that follows the projection | **Box run** (JY): waits for its refit and the switch |
| The weekly refit's verdicts on the rotation rules and the starters | **Box run** (KC/KG): file themselves |
| The confirmed five before the tip, first basket's opening tips, the closes re-read | **Box run** (KH, KI, KJ) |
| The data hunt: every reachable source | **Done** (`docs/NBA_LAB.md`, the data hunt): each source the box reads or could, and what it adds. The one left, the league's player tracking (`stats.nba.com`), is built for research at your word (5 November, "do it"): a backfill on the box and a held-out test before anything reads it (runbook KR). Parked on 6 November: the league refused the box (403) on its first request (runbook KT). The revenge game was measured on two seasons, up in most markets but under two standard errors: not built |

## NFL and college football (in season)

The NFL is the reference toolkit. College has its own checklist
(`docs/CFB_PARITY.md`).

| | Status |
|---|---|
| College's lineup step (who is out, what it opens) | **Measuring**: x1.00 until college's own games clear the NFL's bar (2 SE, 3+ seasons) |
| The deep refit, which reaches the NFL again in pieces | **In progress** (DF2): it resumes inside a sport, and now inside the recency dial (each market kept as it is fitted); its walks ask the disk once a walk, not once a game (the dial 257 s here instead of 388, the same numbers), and the book-line replay reads the 49 MB coverage file once a season instead of once a defence (two weeks in 6 s instead of 40, the same numbers). Confirmed when the heartbeat's round reaches the NFL |
| The Lab's weekly replay, stuck at 29 September | **In progress** (LW1): each sport publishes as it finishes, MLB's and the NFL's replays fit their share, and the whole run now fits its hour (a sport starts only with time to finish; the NBA's and WNBA's markets stop at the pace the last one took, a market not reached keeping last week's numbers, dated; the sports left over go first the next night). Confirmed when every sport on the page carries a November date |
| A college target count | **Not possible** honestly: the feed leaves some incompletions unnamed |
| The fits learn on the model's raw chance, as MLB's and basketball's do | **Fixed** (below); college's temperatures and the NFL's dial and player memory move at the next round |

### The NFL and college fits were learning on the shrunk chance (fixed 5 November)

The board takes the model's raw chance, corrects it with the stored
temperature, and only then shrinks it toward the market. The fitters'
walk for the NFL and college (`engine/logwalk`) handed every fit the
chance after the shrink instead: shrunk toward the walk's own -110 proxy,
it ran 0.28-0.68 where the board's raw chance runs 0.01-0.90. MLB's walk
and basketball's carried the raw chance already (`backtest._raw_over`
reads it). Replayed here on four NFL seasons, each correction fitted on
2022-24 and judged on 2025 the way the board applies it, to the raw
chance (Brier / log loss, lower is better):

| Market | Judged on | Raw, no correction | Fitted on the shrunk chance (before) | Fitted on the raw chance (now) |
|---|---|---|---|---|
| Passing yards | 396 | 0.2495 / 0.6922 | 0.2576 / 0.7107 (T 0.52) | 0.2495 / 0.6922 (T 1.00, none) |
| Rushing yards | 4,053 | 0.1606 / 0.4805 | 0.1389 / 0.4427 | **0.1320 / 0.4007** |
| Receiving yards | 4,049 | 0.2330 / 0.6543 | 0.2279 / 0.6881 | **0.2128 / 0.6063** |
| Receptions | 3,825 | 0.2123 / 0.6058 | 0.2246 / 0.6692 (T 0.48) | **0.2078 / 0.5958** (T 1.12) |

The old fit lost to the new on all four and did worse than no correction
on three. A temperature near 0.5 doubled the raw chance's distance from
even before the board shrank it, which is also why the curves fitted in
August flattened out past the narrow band they were fitted on. On the raw
chance, rushing and receiving yards' curves still top out under 50% (0.41
and 0.48), so the one-sided check keeps them unapplied and both markets
stay shut, as they are for losing to real books (AUC 0.47). What moves at
the next round: college's eight markets (fitted only through this walk),
the NFL's and college's recency dial and player memory, and the rank fit.
The NFL's four yardage and catch markets keep a fit against real book
lines wherever `engine/propcal` made one (it read the raw chance already,
and the store never lets another fitter overwrite it).

## MLB (off season; Opening Day in March)

| | Status |
|---|---|
| RBI, runs, hits + runs + RBI, walks, stolen bases | **Parked, for the winter** (H): in the game log the box already pulls; each costs odds credits and is measured before it is posted |
| Sprint speed and pop time (steals), team defence (hits allowed) | **Parked, for the winter** (H): Savant publishes them on the site we already read |
| Travel and rest (cross-country trips, a day game after a night game, getaway days) | **Measured, nothing over the bar** on five seasons of Retrosheet's game logs (`docs/MLB_MODEL.md` §7); the closest are 1,500+ miles without a day off (−5.8% runs scored) and the first home game after a long trip (+3% allowed), the same side in all five. **Box run** (KN, `mlbtravelcheck.py`) adds 2024-25 and the stored closing totals. Built only where it holds |

## Prediction markets (Polymarket, Kalshi)

`docs/PREDICTION_DESK.md`: the crowd's price is on every game page, every
build records it pregame (`crowd_snaps`), and `engine/crowdfit` measures
whether it knows anything the books do not.

| | Status |
|---|---|
| Hockey's games carry both venues | **Built today** (above) |
| The crowd's lean on the moneyline | **Parked**: `crowdfit` needs 200 finished games and a coefficient two standard errors from zero |
| The flow feed's weights (whale, fresh-wallet and niche-market flags) | **Parked**: `pmfit` needs 400 resolved flags |
| Kalshi spreads and totals for the NBA, WNBA and NHL | **Box run**: `crowdprobe.py` says which candidate series are real before any is wired in |
| The weather desk's picks | **Paused** (WX1) while its read-only check finds why it lost |

## Crypto (Rocket Radar)

`docs/MEMECOIN_MODEL.md`: a radar, not a sport. It journals, grades and
recommends nothing, by design. Momentum and risk are two scores that
never blend, and risk is a gate.

| | Status |
|---|---|
| Discovery, order flow, holder concentration, mint/freeze authority, LP lock, wash flags, the exit channel | **Built** (free tier) |
| The radar's own record (`engine/memeledger`): every coin on either channel at the price seen, marked at 1 hour, 6 hours, a day and a week, its peak and trough, and a coin that vanishes kept as an outcome | **Fixed today**: it called a coin gone when it left the 60-coin scan (99% of rocket calls, 80,104 of 80,834, while their coins traded on), so only coins still trending got their later marks, and a late sighting filled earlier horizons. Each owed call is now priced by its own lookup, marks count only on time, gone means no pool quoting it, and the record counts from 6 November (`docs/MEMECOIN_MODEL.md` §6) |
| Do the radar's scores mean anything: momentum, rank and risk against what the coins did | **Parked** until the fixed record has a week of followed calls; every call stores its momentum, risk and rank, so the split is a read of data already kept |
| Smart-money wallets, holder velocity, bundle and sniper detection, dev-wallet sells, bonding-curve stage | **Parked**: each needs a paid firehose feed; the page says so rather than scoring the gap as safe |
| Every venue (GeckoTerminal, DexScreener, RugCheck, Solana RPC) | **Not reachable** from the build sandbox; the box reads them live |

---

Each **Built today** line has its tests, and the push that carries it
is in the changelog. Each **Box run** has its step in the runbook.
