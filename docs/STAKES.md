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

## 4. The rule (v4, from 2026-10-31) — `engine/stakeplan`

Per league:

- **Edge picks are staked** on the price ladder (`engine/staking`: −110 is
  1u, −200 is 1.25u, +200 is 0.64u, never under 0.35u). A league's Edge book
  stops being staked when it is clearly losing (100 graded at z −2.0 or
  worse, the bar `ledger.LIVE_STOP_*` already held the staked Most Likely
  board to). It is staked again above z −1.0. It journals on paper (no
  dollars) while stopped.
- **Most Likely picks are tracked, not staked.** Every pick still posts, is
  graded and counts toward the board's hit rate. A league's Most Likely book
  is staked once it beats the price (200 graded at z +2.0 or better, the bar
  the stale-line book had to clear before it risked a penny). It goes back
  to paper at z 0 or worse.

Walked forward over the same record, the rule stakes 1,699 picks: 867–832,
**+13.50u, +1.64% ROI**. It keeps 7,270 Most Likely picks on paper. The
NBA's Most Likely book cleared the bar on the walk and stays staked. The
NFL, college and hockey books do not.

| rule | all | through Oct 15 | after |
|---|---:|---:|---:|
| v4 | +13.50u, +1.64% | +21.36u, +4.05% | −7.86u, −2.66% |

**The honest part.** The last two weeks were a losing stretch for the Edge
picks: college −6.3u, the NBA's new Edge model −3.1u, the NFL +2.0u. No rule
tested was positive in both windows except staking NFL Edge alone, and that
was chosen after seeing the first window. Nothing here is significant on
its own (z +0.6). What the rule does is take the money off the half that
loses by design and keep it on the half built to beat the price.

## 5. The record on the site

The site's record leads with the picks this rule stakes: every graded pick
at the stake the rule gave it on its day, decided only from the days before
it (`stakeplan.staked_reports`, `ledger.performance` over those picks).
The picks are the same picks, made in public at the time. Only which of
them carried units is today's rule.

- Most Likely is shown by its hit rate against what its prices need.
- The record as placed (every pick at the stake it carried, Most Likely
  included) stays on the Record page as its own tile.
- The real-money bankroll is untouched. Dollars moved and stay moved.

The journal follows the same rule from the export that first runs it: the
plan is stored with the record (`ledger.STAKE_PLAN_KEY`), and
`ledger.likely_is_staked` reads it. To see it on the box:

```
cd /srv/qellys && sudo -u qellys python3 -m engine.stakeplan
```
