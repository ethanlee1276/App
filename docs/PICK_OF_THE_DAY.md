# Pick of the Day — what it selects on, and what that is worth

Ethan, 2026-09-15, twice. First: "find 1 pick that is guaranteed to hit
... between -190 and +190 so we can basically have a 'one props doubles
money' type of hit." Then, after seeing what the first version selected
on: "maybe the pick of the day should not go off of our 70% model thing
... We shouldn't use that 70%" and "I want it to be a 50-50 money flip,
basically, either from 80% to 100% flip of your money. And we need to
look at other pro sports bettors' logic and models ... So we need to
figure out the models they're using and implement that."

This file is the measurement behind the second version. The code is
`engine/potd.py`; its header carries the same numbers, and this is the
working that produced them.

---

## 1. What the band can physically contain

Ethan said it twice on 2026-09-15 and the second time was the clearer
one:

> maybe the pick of the day should not go off of our 70% model thing …
> I want it to be a 50-50 money flip, basically, either from 80% to 100%
> flip of your money

> I guess I should reword that … I just wanted it to be a guaranteed for
> the day like I'm putting 100 bucks on it. I wanna make at least $70 if
> that makes sense … I feel like my wording is kind of fucked up a little
> bit.

The reworded spec is a **floor on the winnings**, not a window, and it is
the better spec. $70 on $100 is a payout of **0.70 units**, which is
**-142** (-143 pays $69.93 and misses by seven cents), which is the
market claiming at most **58.8%**.

That ceiling is arithmetic, not opinion. No price inside this band can
imply more than 58.8%, so **a main-market favourite inside this band
cannot be a heavy favourite.** `tests/test_potd.py` executes this rather
than asserting it, because every other decision in the module follows
from it.

## 2. What that costs, replayed on our own history

`data/history.db` holds 4,431 completed games carrying a two-way closing
moneyline (NFL 2021-26, CFB 2022-26). De-vig both sides, take the safer
one, one pick per slate:

| floor | league | picks | won | hit rate | price implied | ROI | sd above the price |
|---|---|---|---|---|---|---|---|
| **$70 (-143)** | NFL | 109 | 56 | **51.4%** | 55.4% | -7.1% | -0.86 |
| **$70 (-143)** | CFB | 242 | 122 | **50.4%** | 52.0% | -4.4% | -0.50 |
| $80 (-125) | NFL | 82 | 44 | 53.7% | 54.6% | -1.7% | -0.16 |
| $80 (-125) | CFB | 150 | 80 | 53.3% | 53.8% | -1.1% | -0.11 |
| $60 (-167) | NFL | 109 | 58 | 53.2% | 59.8% | -11.5% | -1.41 |
| $60 (-167) | CFB | 242 | 134 | 55.4% | 56.9% | -3.4% | -0.49 |
| $53 (-190) | NFL | 109 | 72 | 66.1% | 62.5% | +5.3% | +0.77 |
| $53 (-190) | CFB | 242 | 150 | 62.0% | 60.3% | +3.1% | +0.52 |
| any price | NFL | 110 | 94 | 85.5% | 84.7% | -0.3% | +0.22 |
| any price | CFB | 325 | 266 | 81.8% | 80.1% | +1.7% | +0.84 |

Three readings, and all three matter.

**The floor decides how much favourite you may buy, and the market
prices that almost exactly.** Every row's hit rate tracks its own implied
probability within a few points. That is what an efficient market looks
like from the inside.

**The trade is real and it is steep.** Ethan's $70 floor costs about ten
to fifteen points of hit rate against a $53 floor (-190), and no
selector can buy them back — nobody sells a 65% outcome for 70 cents.
That is his call and `potd.MIN_PAYOUT` is the one constant that reverses
it.

**Nothing here is an edge.** Every row lands within one and a half
standard deviations of what the price already said. Swept across floors
from -110 to -350 in both leagues, the largest figure was +1.17 sd on
108 NFL picks — one good season inside noise. Picking the safest side is
not a strategy; it is buying the favourite at the favourite's price.

**And none of this table is what the selector does.** It buys a
disagreement, not a favourite (§3). The band only says which prices may
be shopped, which is why the plus-money end is left open to +190 and
`MIN_FAIR` — the pick must be likelier to win than lose by the fair we
trust — does the work of keeping it a favourite.

## 3. So the pick has to be a disagreement, which is also what pros do

Strip the marketing off the public +EV method — Unabated, OddsJam,
Outlier, Sharp Lines all describe the same three steps — and it is:

1. Take a **sharp book's** two-way price. Pinnacle is the reference
   because it runs a 2-3% margin and does not limit winners, so its
   number is the one priced by the sharpest money.
2. **Remove the vig** to get a fair probability.
3. Bet only where a book you can actually reach prices that outcome
   **worse than the sharp fair**.

The edge is the gap between two books. It is never the gap between a
model and the world.

We already had this machinery for the Edge board
(`betting.sharp_anchor_for`, `gamebets.sharp_anchor_two_way`,
`odds.devig_two_way`, `odds.consensus_fair`). What we did not have was a
surface that selected on it *alone*. That is what the rebuild is.

### The evidence ladder

| tier | the fair comes from | why it ranks here |
|---|---|---|
| `sharp` | a sharp book's own two-way de-vig | the professional method, unmodified |
| `market` | the de-vigged consensus of ≥3 books | line-shopping; the market's own opinion |
| `model` | our number alone | **refused** — see below |

`potd.rank_key` sorts on the **tier first**, then the edge, then the
payout. That inversion is the point: sorting on edge size hands every
day to the loudest disagreement, and the loudest disagreements come from
the weakest witness.

## 4. Why our own model is not allowed to be the evidence

Not a style preference. `likely.GAME_RANK_MEASURED` against
`likely.GAME_RANK_MARKET`:

| market | our model | the market's own de-vigged number |
|---|---|---|
| NFL moneyline (1,420 games) | 0.677 | **0.722** |
| CFB moneyline (3,011 games) | 0.752 | **0.791** |
| spreads, totals, team totals | 0.492-0.504 | — |

The market ranks winners better than we do, and on the derived markets
we cannot rank at all. A pick chosen because *our* number disagrees with
the price is a pick chosen by the weaker of the two opinions in the
room. `potd.shortfall` returns "only our own model disputes this price"
and the row is shown as a near miss, never as the day's pick.

## 5. What the EV floor actually asks for

`MIN_EV` is 0.02 units. Across the band that works out to about **one
point** of disagreement with the price (0.7 to 1.2 points —
`tests/test_potd.py` solves for it rather than quoting it). That is the size
of gap a genuine sharp-versus-soft difference produces. A floor that
needed ten points would only ever be cleared by our own model being
wrong, which is the failure this rebuild exists to stop
(`betting.MAX_CREDIBLE_EDGE` is the same lesson from the other side).

`MIN_FAIR` is 0.50: a +EV underdog is a fine bet and a bad thing to name
the day after.

## 6. The de-vig method barely matters here

The literature argues constantly about multiplicative vs additive vs
power vs Shin. They diverge on longshots — that is the whole
favourite-longshot-bias argument — and converge in the middle of the
board. At -110/-110 they are identical; across the whole 0.80-1.00
payout band they disagree by about a point at the plus-money end and
well under one everywhere else.
`odds.devig_two_way` is multiplicative and stays that way here. A power
de-vig is the right argument to have on the touchdown ladders
(`engine/devig` already had it), not on a coin flip.

## 7. How we find out whether any of this is real

**Not from the win-loss record.** The industry's own rule of thumb is
500-1,000 graded plays before a record means anything; at one pick a day
that is three years.

**From closing-line value.** CLV grades the *decision* at kickoff,
accrues on every pick including the losers, and is the metric the sharp
side actually keeps. The `potd` book flows into
`clvboard.scoreboard(conn, category="potd")` for free. If these picks do
not beat the close, this module is wrong and that page will say so.

## 8. The gap that would change the answer

`backtest_sharp_anchor` returns **zero priced games** for NFL, CFB and
MLB. `odds_history` holds 64 rows — NFL only, book "best" only, spread
and total only, from a two-minute window on 2026-09-10. There are no
stored Pinnacle closes anywhere, so the sharp-anchor strategy has never
been measured on our own data; it is adopted here on the published
evidence for the method, not on ours.

**Harvesting Pinnacle moneyline closes nightly into `odds_history` is
the single piece of work that would let us measure it.** Four to six
weeks of harvest makes `backtest_sharp_anchor` answerable, and that is
what would turn this from "the method the professionals use" into "the
method we have measured here".

## 9. What the page may not say

No bet is guaranteed. The disagreement was raised once and Ethan's call
stands on everything else — the band, the daily cadence, the showcase
framing. What the page may not do is promise a paying reader a
certainty, because the first loss then reads as a lie rather than as
variance. `tests/test_potd_card.py::test_neither_surface_promises_a_certainty`
holds that line, and its banned list is why the module is named for a
pick rather than for a lock.

## 10. Sources

The public method, as described by the tools that sell it:

- <https://unabated.com/articles/finding-positive-ev-wagers-step-by-step-guide>
- <https://help.outlier.bet/en/articles/8208129-how-to-devig-odds-comparing-the-methods>
- <https://8rainstation.com/blog/understanding-positive-ev-betting-exploring-multiple-devigging-options>
- <https://picktheodds.app/en/blog/sharp-sportsbooks-what-they-are-and-how-to-use-them-to-find-edges>
- <https://www.pinnacleoddsdropper.com/blog/closing-line-value>
- <https://www.boydsbets.com/closing-line-value/>

Derivative markets (first-half, team totals, alternate rungs) as the
place where soft books are laziest — the next thing to mine once the
main-market anchor is measured:

- <https://www.predictem.com/betting/strategy/betting-derivatives/>
- <https://oddsindex.com/guides/first-half-totals-strategy>

Reverse line movement, which we do NOT use: profitable in some
published samples, explicitly not profitable in college-football totals
over 2005-2016 (Journal of Economics and Finance,
<https://link.springer.com/article/10.1007/s12197-019-09479-3>). It needs
ticket-vs-handle splits we do not buy, and the evidence is mixed enough
that it is not worth one pick a day.
