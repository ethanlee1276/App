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
