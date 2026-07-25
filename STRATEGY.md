# Strategy Review — the honest edit of the Scalpy 3.0 / MLB 2.0 specs

This is the working strategy document for Gridiron Edge: your two instruction
sets, graded against what our own backtests have *measured* (not guessed),
and turned into a prioritized build order. The one-line summary:

> **Your central thesis is correct — profit comes from risk management and
> market analysis, not from being a better handicapper. But several of the
> specific rules would repeat mistakes our measurements already caught, and
> the 38 proposed engines need a ruthless ordering by (a) proven value,
> (b) free data availability, (c) measurability.**

## What we know for sure (our measurements, real closing lines)

| Model | Result | Verdict |
|---|---|---|
| MLB total-bases props | -0.1% ROI, 661 bets | Calibrated, worth ~the vig, no edge vs close |
| MLB moneylines (ratings-only) | -12.4% ROI, 179 bets, Brier worse than base rate | Actively harmful → gated off the site |
| Grade tiers (Strong/Play/Lean) | Scrambled, no ranking | Conviction ≠ signal at current info level |
| Every "exciting" small sample (+9.9%, +14.5% unders) | Vanished at 3-6x the data | Small-sample noise, every time |

These four facts are the lens every idea below is judged through.

---

## Part 1 — Where your spec is RIGHT (and what we'll do about it)

### ✅ +EV over hit-rate thresholds (NFL #1)
Correct in principle — and it's already how the engine works: we bet when
`model probability > implied probability`, at any hit rate. **But your
example hides the trap.** "Book implies 52.4%, model says 58%" sounds like a
fantastic bet; our 661-bet measurement says that after calibration the model
*never* honestly disagrees with a real closing price by 5+ points. When a
model does claim that gap, history says the model is the one that's wrong.
The fix isn't the EV filter (we have it) — it's that the market must be
treated as the prior: our `temper_edge` shrinks the model 50% toward the
book price and caps credible edge at 10%. That discipline stays.

### ✅ Passing is a winning decision (NFL #2, MLB #3)
Already implemented and displayed ("0 recommended" is a valid, common
outcome; no forced slates, no forced parlays). No change needed — but worth
keeping in the doc as a principle we never regress on.

### ✅ CLV as the north-star metric (NFL big addition #1, MLB #1)
**Your single best point, and the heart of the rebuild.** We cannot beat
closing prices head-on (measured, twice). What a small operation *can* do:
bet earlier than the close at the best shopped price, and measure whether
the picks systematically beat the number they closed at. Beating CLV
consistently is the leading indicator of long-term profit — and it's
measurable within weeks, not seasons. The forward CLV tracker exists;
Phase 1 below makes every recommendation feed the learning database.

### ✅ Opportunity before outcome (NFL #6, MLB "biggest missing piece")
Right, and the strongest modeling idea in either doc. Volume is stickier
than efficiency: PAs, carries, targets, pitches seen stabilize much faster
than yards and hits. MLB versions are buildable free (lineup spot → PA
projection is already partially in the model via `lineup_spot`). Phase 2.

### ✅ Pitchers drive MLB markets (MLB #2)
Correct — and it's exactly what our moneyline backtest lacked (it replayed
bullpen-vs-bullpen). **Built now:** starting pitchers are ingested per game
and the moneyline backtest runs an A/B — ratings-only vs pitcher-aware —
so the claim gets a number instead of a vibe.

### ✅ Sharp books as reference (NFL #4, MLB #19)
Right idea, one correction: sharp books aren't "priority books to bet at"
— they're the *truth serum*. The realistic play for us: use a sharp book's
de-vigged price as fair value and flag soft-book prices that deviate from
it. That manufactures +EV without needing our model to out-think the
market — the most proven retail strategy that exists. Practical constraint:
Pinnacle sits in a different Odds API region (extra credits per request),
so this is a deliberate Phase 1 build with a budget plan, not a config
tweak.

### ✅ Market-type tiers (NFL #12)
Directionally right and *testable with machinery we already have*. Count
markets (receptions / hits / strikeouts) are lower-variance and books are
sometimes softer there than in headline yardage markets. We don't adopt
the tier list on faith — we run the same real-line backtest per market and
let ROI decide. Costs harvest credits; phased accordingly.

### ✅ Kelly staking (NFL #18)
Already implemented (quarter-Kelly-style stake with caps). No change.

---

## Part 2 — Where your spec is WRONG (measured, not opinion)

### ❌ "Only recommend confidence 85+ / B+ or better" (NFL #13-14)
Our grade-split test measured exactly this idea: Strong picks did NOT
outperform Lean picks against real prices. Conviction thresholds don't
create edge; they just shrink the sample and add false confidence. A
confidence score is fine as *display*; it must never be sold as a filter
that makes picks profitable. Killed until a measurement says otherwise.

### ❌ Overweighting the last 2 games (NFL #3: 45% weight)
The books also watch the last two games — recent form is the single most
public information there is. A 2-game baseball/football sample is mostly
noise; overweighting it makes the model *more* like the public, not
sharper. Our projections already recency-weight with measured calibration
(ECE ≈ 0.02, which is genuinely good). Keep recency, reject the 45/35/20
split — any reweighting must pass the real-line backtest first.

### ❌ "A hitter 1-for-15 with elite contact quality is a buy-low" (MLB #3)
The *idea* is sound (contact quality > results), but as a rule it's a trap
without Statcast data feeding it — otherwise "buy-low" is just "bet on
cold hitters," which our under/over measurements give no support for.
Parked until Phase 2 brings in quality-of-contact data.

### ❌ Public % / sharp % feeds (NFL market movement engine)
Reliable splits data is paywalled and the free versions are marketing
numbers. What we CAN do honestly: our own harvested snapshots give real
line-movement history (open → close drift), which supports steam/RLM-style
signals from primary data. Reframed into Phase 2, sourced from our own DB.

### ❌ NFL coordinator & coverage-scheme engines (NFL #3-4, #16)
This is PFF/SIS charting data — paid, no free structured source. Everything
here (coverage shells, funnel defenses, OC tendencies) is real but not
buildable on our stack today. Parked with that stated reason, not because
the football logic is wrong.

### ❌ Live betting module (NFL #17)
We measured why pre-game models must not price live games (the Phillies
+1400 fiasco). A real live model is a separate product with streaming data
needs. Explicitly out of scope.

### ⚠️ The sheer number of engines
38 engines across two docs. Professional groups have teams per engine. The
failure mode for us isn't building too few — it's half-building twenty,
measuring none, and trusting all of them. The roadmap below is deliberately
narrow: nothing ships to the site without passing the real-line backtest.

---

## Part 3 — The four pillars, adopted

Your Scalpy architecture is right and becomes the official structure:

1. **Probability Engine** — projections → calibrated probabilities → fair
   prices. (Exists; grows opponent/pitcher/park adjustments in Phase 2.)
2. **Market Intelligence** — line shopping, sharp-anchor fair value, line
   movement from our own snapshots, CLV on every pick. (Phase 1 focus.)
3. **Risk Engine** — Kelly stakes, juice caps, exposure/correlation caps,
   volatility tiers. (Mostly exists; correlation rules in Phase 2.)
4. **Learning Engine** — every recommendation logged with context, settled
   automatically, analyzed by market/team/park/situation. (Phase 1 focus.)

## The build order

**Phase 1 — now (all free or near-free):**
1. ✅ Pitcher-aware game model + A/B backtest (this commit).
2. Learning database: auto-log every daily recommendation with price,
   line, EV, context; settle against results; CLV per pick. After 200-500
   live picks this answers "which markets/situations make money" from OUR
   data — your "biggest missing piece," and I agree completely.
3. Sharp-anchor pricing: add a sharp reference book, de-vig it as fair
   value, surface soft-book deviations as the primary +EV signal.

**Phase 2 — next (needs new data, still free):**
4. MLB opportunity model: PA projection from lineup spot/park/total.
5. Umpire assignments (free MLB API) → strikeout/run environment effects.
6. Platoon splits from our own game-log DB (bats/throws already stored).
7. Line-movement signals from our own harvested snapshot history.
8. Per-market real-line backtests (hits, strikeouts) before promoting any
   new market on the site.

**Phase 3 — later / needs paid or heavy data:**
9. Statcast quality-of-contact (barrel %, xwOBA) via Baseball Savant.
10. Bullpen fatigue model; park factors by handedness; SB engine.
11. NFL: nflverse snap/route/target shares for usage-stability scores —
    the best free approximation of your NFL usage engine.

**Killed (with cause):** confidence-gated recommendations (measured: no
signal), 45% last-2-game weighting (adds noise), public-% feeds (junk
data), coordinator/coverage engines (paid data), live betting (separate
product), forced slate constructions (already never do it).
