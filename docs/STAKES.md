# What we stake, and why

Ethan, 2026-10-31: *"I feel like we're winning a lot of bets, but not winning
money. And we're still down ROI. We're still down units ... We need to find
what bets and what unit bets ... works best for our ROI to be positive and
our units to be positive, and then we need to implement that, and then also
update our current record on the site."*

Every number here reruns from the public receipts (`/api/record/receipts.csv`,
every graded pick the journal holds) with:

```
python3 tools/stake_study.py
```

It reads the headline record: the books `ledger.POOLED_BOOKS` names (the Edge
picks, the Most Likely list and the one board), each pick once, from the
record's epoch (2026-08-06), with the benched league out. That was 8,969
graded picks on 2026-10-31.

## 1. Each half, as placed and at flat stakes

| | picks | won | staked | units | ROI |
|---|---:|---:|---:|---:|---:|
| Edge, as placed (the price ladder) | 1,414 | 48.9% | 753.9u | **+13.92** | **+1.85%** |
| Edge, flat 1u | 1,414 | 48.9% | 1,414u | +2.09 | +0.15% |
| Most Likely, as placed | 7,542 | 60.8% | 1,216.5u | **−17.43** | **−1.43%** |
| Most Likely, flat 1u | 7,542 | 60.8% | 7,542u | −121.61 | −1.61% |

The Most Likely half wins six bets in ten and still loses money. It pays −162
on average, where 61.8% only breaks even. Its chances are honest (it said
61.8% and hit 60.8%), and they do not beat the price.

The Edge half is the one that makes money, and only on its ladder. Flat
stakes on the same picks are about even, because the ladder puts less on the
long prices that lost (MLB's plus-money Edge picks made −13% flat).

## 2. Does our claimed edge over the price predict the result?

If it did, staking on it would pay. At flat stakes:

| | picks | ROI |
|---|---:|---:|
| Edge, we said 0–5% better than the price | 1,193 | +0.69% |
| Edge, we said 5%+ better | 221 | −2.81% |
| Most Likely, we said worse than the price | 4,883 | −1.67% |
| Most Likely, we said 0–5% better | 1,346 | −0.43% |
| Most Likely, we said 5%+ better | 1,313 | −2.61% |

It doesn't, in either half or in any league. So no stake rule built on our
own edge figure can fix the units.

## 3. Stake rules, walked forward

Each day's rule is read only from the days before it, and every rule is
scored through 2026-10-15 and again after it, so a rule that only fits the
past shows up as one.

| rule | through Oct 15 | after |
|---|---:|---:|
| as placed | +4.42u, +0.38% | −7.94u, −0.98% |
| flat 1u, every pick | −117.19u, −2.33% | −2.33u, −0.06% |
| flat 1u, Edge only | +11.71u, +1.06% | −9.62u, −3.08% |
| drop the markets that had been losing | −96.76u, −2.92% | +7.52u, +0.35% |
| drop the leagues that had been losing | −94.54u, −4.14% | +0.19u, +0.01% |
| drop the sportsbooks that had been losing | −30.67u, −1.41% | +4.50u, +0.51% |
| stake more where it had been winning (league) | −68.79u, −7.55% | +25.46u, +2.53% |

Every "follow what's winning" rule lost more than flat stakes in the first
window. The winners of one fortnight were not the winners of the next.
What held up is structural: picks chosen for their edge over the price pay,
and picks chosen for how likely they are pay the juice.

## 4. The price: nothing past +130

The Edge picks by price, flat 1u (study section 5):

| price | picks | we said | the price said | hit | ROI |
|---|---:|---:|---:|---:|---:|
| −150 or shorter | 39 | 63.5% | 61.4% | 74.4% | +21.7% |
| −149 to −121 | 209 | 57.8% | 56.8% | 56.5% | −0.6% |
| −120 to −101 | 392 | 53.8% | 52.8% | 52.0% | −1.5% |
| +100 to +130 | 481 | 48.6% | 47.2% | 50.5% | **+6.9%** |
| +131 to +160 | 178 | 42.9% | 41.1% | 37.6% | −8.5% |
| +161 to +200 | 81 | 37.3% | 35.6% | 29.6% | −16.6% |
| +201 or longer | 34 | 25.7% | 23.3% | 17.6% | −12.6% |

Past +130 the picks hit less often than the price itself said, never mind
our number, and the longer the price the wider the miss. It happened in
every league that had them (MLB 230 picks, the NBA 38, the NFL 24), in both
windows. It is the favourite-longshot bias, the oldest finding in betting
markets: long prices pay less than their odds say, and a model's long-shot
chances run high with them. As placed, those 293 picks lost 9.6 units on
105 staked. So **an Edge pick longer than +130 carries no stake**
(`stakeplan.EDGE_MAX_ODDS`). It still posts, is graded and is tracked on
paper, and the card says "Tracked · no stake". The cap was chosen after
seeing the record. What makes it more than a fit is that it is the same
in every league and has a reason older than this site.

## 5. Does our chance beat the price's?

Scored as forecasts on the picks after 2026-10-15 (log loss, lower is
better; study section 6), against the price's own chance with the average
hold taken out:

| | picks | ours | the price's |
|---|---:|---:|---:|
| NFL Edge | 212 | **0.6901** | 0.6925 |
| NBA Edge | 75 | 0.6877 | 0.6691 |
| NFL Most Likely | 774 | 0.6727 | 0.6706 |
| College Most Likely | 575 | 0.6802 | 0.6754 |
| NBA Most Likely | 828 | 0.6485 | 0.6486 |
| NHL Most Likely | 1,191 | 0.6567 | 0.6560 |
| MLB Most Likely | 247 | 0.6500 | 0.6402 |

Only the NFL's Edge chances forecast better than the price (and the NBA's
Most Likely ties it). Everywhere else the market already knows what our
number knows. That is why Most Likely is tracked and not staked. It is
also why re-weighting our own number cannot fix the units. A correction of
each market's chance toward the price, fitted on the first window, scored
no better on the second (NFL Most Likely: 0.6724 against 0.6727 raw). The
nightly correction already in place (`engine/likelycal`) stays as it is.
Better picks need information the price does not have yet (injuries and
role changes before the books move, weather, the matchup), not a
different weighting of the same number.

## 6. The rule (v4, from 2026-10-31) — `engine/stakeplan`

Per league:

- **Edge picks are staked** on the price ladder (`engine/staking`: −110 is
  1u, −200 is 1.25u, +200 is 0.64u, never under 0.35u). A league's Edge book
  stops being staked when it is clearly losing (100 graded at z −2.0 or
  worse, the bar `ledger.LIVE_STOP_*` already held the staked Most Likely
  board to). It is staked again above z −1.0. It journals on paper (no
  dollars) while stopped.
- **No Edge pick longer than +130 is staked** (section 4). It journals on
  paper and is left out of its league's evidence, which judges the picks
  the rule would stake.
- **Most Likely picks are tracked, not staked.** Every pick still posts, is
  graded and counts toward the board's hit rate. A league's Most Likely book
  is staked once it beats the price (200 graded at z +2.0 or better, the bar
  the stale-line book had to clear before it risked a penny). It goes back
  to paper at z 0 or worse.

Walked forward over the same record, the rule stakes 1,406 picks: 770–636,
**+23.08u, +3.22% ROI**. It keeps 7,563 picks on paper: the Most Likely
picks, and the Edge picks past +130. The NBA's Most Likely book cleared the
bar on the walk and stays staked. The NFL, college and hockey books do not.

| rule | all | through Oct 15 | after |
|---|---:|---:|---:|
| as placed | −3.51u | +4.42u, +0.38% | −7.94u, −0.98% |
| v4 without the price cap | +13.50u, +1.64% | +21.36u, +4.05% | −7.86u, −2.66% |
| **v4** | **+23.08u, +3.22%** | **+28.19u, +6.21%** | **−5.11u, −1.94%** |

**The honest part.** The last two weeks were still a losing stretch: college
Edge −7.4u on 25 picks, the NBA's Edge and Most Likely about even, the NFL's
Edge +2.6u. Nothing here is significant on its own (z +1.1 over the whole
walk). What the rule does is take the money off the picks that lose by
design (the juice on Most Likely, the long prices on Edge) and keep it on
the half built to beat the price. The NFL's Edge book is the one with a
real record (417 staked, +6.9% flat, positive in both windows).

## 7. The record on the site

The site's record leads with the picks this rule stakes: every graded pick
at the stake the rule gave it on its day, decided only from the days before
it (`stakeplan.staked_reports`, `ledger.performance` over those picks).
The picks are the same picks, made in public at the time. Only which of
them carried units is today's rule.

- Most Likely is shown by its hit rate against what its prices need.
- "Tracked, not staked" counts every pick the rule kept on paper.
- The record as placed (every pick at the stake it carried, Most Likely
  included) stays on the Record page as its own tile.
- The real-money bankroll is untouched. Dollars moved and stay moved.

The journal follows the same rule from the export that first runs it: the
plan is stored with the record (`ledger.STAKE_PLAN_KEY`), and
`ledger.likely_is_staked` reads it. To see it on the box:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.stakeplan
```
