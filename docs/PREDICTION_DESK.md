# The Prediction Desk

Ethan, 2026-08-11: *"We need to be better with our polly market and
kalshi bets. I've never once seen a recommended bet for our prediction
market... Maybe we can have an ai scan news and real world data and
politics and weather and shit like that."*

## Why there was never a recommendation

Three stacked reasons, found by reading the pipeline:

1. **The Kalshi feed failed at build time** on the machine that builds
   the site (`kalshi.json` said "unreachable" with no detail). The note
   now carries the exception's own words, and `python3 launch.py --desk`
   prints live status — feed down vs. nothing matched vs. no edge is
   the difference between a bug and a quiet night.
2. **The board had no gate.** It listed markets and computed an edge
   column but nothing ever said "bet this," and nothing was journaled.
3. **The edge column had a sign bug.** It compared P(home) to every
   market's YES price, but Kalshi's YES is a *named team* that is the
   away side half the time. Fixed (`yes_team`), with ambiguity resolved
   to "unmodeled" rather than a coin flip.

## Where an edge can honestly come from

A recommendation requires a probability estimate independent of — and
better than — the market's. We have exactly two such sources today:

**1. Our own game models (sports markets).** The MLB/NFL/NBA/WNBA
moneyline engines already produce win probabilities. When a Kalshi
market maps to a game on tonight's slate, the desk compares our number
to the exchange's mid. Gate: edge ≥ 6 probability points, a real
two-sided book (never a stale last-trade print), ≥$250 of 24h volume,
spread ≤ 6¢.

**2. The National Weather Service (weather markets).** Kalshi's
daily-high markets settle against a named station reading that NWS
forecasts hours ahead, free and keyless. The desk models the daily high
as Normal(NWS forecast, σ), with σ set from published NWS/MOS
verification (2.0°F same-day, 3.0°F next-day, conservative end), and
integrates each bracket. Gate: edge ≥ 8 points — higher than sports
because σ is a prior about the world, not a fitted model — plus the
same liquidity bars. Every (forecast, price) pair is logged in
`kalshi_wx_log` so the σs get **fit from our own history** once it
exists. Weather settles same-day: a hundred graded rows take weeks.

## What the desk deliberately does NOT do

**No politics recommendations.** There is no public number to price a
political market against; an LLM's reading of headlines is not a
calibrated probability, and a bucket that takes months to grade cannot
earn stakes in any reasonable time. Politics stays with the Polymarket
flow detector — smart-wallet flags that already carry their own graded
report card on the Results page. If the flag record ever proves out at
scale, *that* is the politics signal, and it earned its evidence.

## Paper first, always

Every recommendation journals at a flat 0.1u **paper** stake,
`category='predmarket'`, resolved against the exchange's own
settlements (`resolve_predmarket`), reported as its own bucket in
`record.json` and never mixed into the headline record. Promotion to
real stakes takes 100+ graded rows in profit — the identical contract
the loose book runs under. `launch.py --desk` prints the running
scoreboard.

## Files

- `engine/sources/kalshi.py` — yes-side fix, gate, settlement fetch
- `engine/kalshiweather.py` — NWS vs bracket pricing, σ priors, wx log
- `engine/ledger.py` — `log_predmarket` / `resolve_predmarket` /
  `predmarket_report`
- `pm_build.py` — wiring, failure domains, desk summary in kalshi.json
- Intel page: "The desk's recommendations" section, paper-labeled

## The 2026-09-26 audit — the crowd, measured

Ethan, 2026-09-26: *"we should also look into where we can use pollymarket
and kalshi odds for money lines and other bets since crowd betting is more
accurate … we should audit our pollymarket and kalshi predictions and
predictor model … we can study market swings … usually a market has swung
a certain way when a large group of people already know the answer."*

### What the audit found

1. **The desk has had no model number since the paywall.** `pm_build`
   read each league's board from `web/data/`, the public copy, where
   `game_bets` is stripped. Every row came back "no model number" and the
   desk could recommend nothing. It now reads the members' copy through
   `gate.board_source`, the helper written for exactly this mistake.
2. **The books-vs-Kalshi read never fired.** `kalshi.board` compares the
   exchange with the books' de-vigged moneyline when a game carries
   `home_ml`/`away_ml`, and `pm_build` rebuilt the games without them.
   They ride along now.
3. **"Our model" on the desk is mostly the books.** A moneyline card's
   `win_prob` is the books' fair plus our model's move times the measured
   shrink, and the largest edge that survives the fitted shrink is under
   a point (`gamebets.shrink_in_force`). So a 6-point "edge" against
   Kalshi is really the books disagreeing with Kalshi. That is a real
   strategy, but which venue to follow depends on which one is more
   accurate, and nothing had ever measured that.
4. **Kalshi reached one place and Polymarket none.** Kalshi's price fed
   only the Pick of the Day's evidence, on Most Likely moneyline rows.
   Polymarket's game markets were never read. Now:
   `engine/sources/polysports` reads Polymarket's game moneylines, and
   `engine/crowd` hangs both venues and the books on every game (the game
   page shows it as "Win chance, every market").
5. **No side-by-side record existed**, so "is the crowd more accurate?"
   had no rows to answer it. Every build now writes each game's pregame
   prices to `crowd_snaps`: Kalshi, Polymarket, the books, our card, and
   our engine before the shrink. Our two numbers are recorded, never put
   on the public game, because the moneyline card is the members'.
6. **The swing study did not exist.** `engine/crowdfit` (run it with
   `python3 crowdfit.py`) joins the record to the finals and answers:
   - **Who is most accurate?** Brier and log loss per source, and each
     source head to head against the books on the same games.
   - **Does the crowd know something the books do not?** The books'
     price as a fixed offset, the venue's gap as the feature. A β of 0
     means the books already knew; a β of 1 means lean all the way to
     the venue.
   - **Do late swings keep going?** The last price as the offset, the
     move over the prior six hours as the feature. A β above 0 means
     informed money is still arriving; below 0 means fade it.

   Nothing counts as measured below 200 finished games, or with a
   coefficient under two standard errors from zero.

### What it does not do yet, and what comes next

- **Nothing moves a pick.** The numbers are shown and recorded. When
  `crowdfit` has measured a β, it becomes the lean in the moneyline's
  fair price, and the desk follows whichever venue measured more
  accurate.
- **Spreads and totals.** Kalshi and Polymarket both list them. The
  moneyline comes first because it is the one both venues price on every
  game.
- **The Polymarket flow feed** (whale, fresh-wallet and niche-market
  flags) already has its own fit, `engine/pmfit`. It needs 400 resolved
  flags before any weight moves.

### A line on "insider trading"

Everything here reads public prices and public on-chain trades. Following
where informed money has visibly moved a market is legal, and it is what
the flow feed and the swing study do. We never trade on information that
is not public, and the site never tells anyone to.
