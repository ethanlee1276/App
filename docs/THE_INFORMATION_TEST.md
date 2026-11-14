# The model is a price-reader — 2026-08-09

**Status: measured, not proposed. Three independent instruments agree.**

The night began with Ethan asking why a +100 winner returned 0.05 units. It
ended with a number that says what this model is.

---

## 1. The finding, in one table

`python3 stakecheck.py --info`, on 307 settled main-category bets — 145
winners, 162 losers:

| ranked by | AUC | 95% CI |
|---|---|---|
| the model's `hit_prob` | 0.570 | [0.508, 0.633] |
| the market's price | 0.566 | [0.505, 0.629] |
| **our claimed edge** | **0.479** | **[0.414, 0.545]** |

| | value | 95% CI |
|---|---|---|
| model − market (paired) | **+0.004** | **[−0.006, +0.014]** |

AUC is the chance a random winner is ranked above a random loser. 0.50 is a
coin flip.

**Read the third row and the last row together and the model has a name.**

The model discriminates — 0.570 is real. So does the price — 0.566. And the
paired difference between them is four thousandths, in an interval a fifth as
wide as either AUC's own. That narrowness is the result: the two scores are
nearly the same score, so their difference is estimated precisely. This is not
"we cannot tell whether the model beats the market". It is **"we can tell
precisely, and it is zero."**

The claimed edge — the residual, the part where the model *disagrees* with the
price — has an AUC of 0.479. Indistinguishable from a coin flip, tilted very
slightly the wrong way.

**The model is an excellent price-reader that contributes nothing beyond the
price.** It has learned to reproduce what the market already knows. Every
"edge" it reports is the difference between its estimate and the market's, and
that difference is noise.

---

## 2. Why AUC, and why it can be trusted here

AUC is rank-based. The vig shifts every implied probability up by roughly a
constant, and **a monotone shift cannot change a ranking** — so the test runs
on the prices actually paid, with no de-vigging step, and therefore none of the
ways de-vigging goes wrong can happen. (`test_auc_ignores_the_vig_because_it_is_rank_based`
asserts exactly this.)

Ties use midranks. Prices cluster hard on round numbers, so dozens of bets
share an implied probability exactly; resolving those by list order would let
SQLite's return order decide the answer. Ranking ties by position instead fails
70 of 95 tests in the file.

The model-minus-market bootstrap is **paired** — both scores describe the same
bets, and resampling them independently would discard the correlation that
makes the difference measurable at n=307.

---

## 3. What it explains

Three measurements, taken independently, with one cause underneath:

- **The calibration gap.** `guardfit` has the model claiming about +12 points
  more than it delivers, at every price band. If the claimed edge is noise,
  claimed probability systematically exceeds realized by exactly the size of
  the noise. See `docs/SELECTION_CORRECTION.md`, which proposed a correction
  for this — that proposal is now answered rather than pending.
- **The null CLV.** `--clv` on a cleaned instrument: −0.30% ± 0.59, t = −0.5.
  Nothing to move toward.
- **The −28% ROI.** Vig, paid repeatedly, on a coin flip.

---

## 4. What this rules out

Every gate, threshold, cap, stake rule, calibration temperature, and loss-miner
pattern in this repo is a function of `edge`. **There is no setting of a noise
variable that produces money.** That is most of the machinery here, and none of
it is either the problem or the fix.

Specifically parked by this finding, unless the underlying model changes:

- tuning the §1.3 thresholds (task #48, already decided once)
- the selection correction (`docs/SELECTION_CORRECTION.md`)
- the movement veto (task #80)
- further loss-pattern mining (task #78)

None of these are wrong. They are all downstream of a number that carries no
information.

---

## 5. What it does not say

**This is conditional on the bets we chose.** The model's AUC is "how well it
sorted the spots it liked", not "how good it is at baseball". The right
question for deciding whether to keep betting this way; the wrong one for
judging the projections in general.

**n=307 leaves the edge interval at ±0.065.** A small real signal is not
excluded. What is excluded is one large enough to pay for the vig.

**Unders are barely in it.** 116 of 307 settled bets are unders, and until
2026-08-09 the snapshot recorder held only the over price, so the CLV half of
the evidence is over-only. The AUC test uses the price taken, which exists on
every row, so `--info` covers the whole book — but the corroborating CLV number
does not.

---

## 6. What would actually change the answer

The model needs **information the market does not have**, not better processing
of information it already has. In MLB player props at major books that is a
hard ask: those markets are priced by well-resourced people using the same
public inputs.

The two honest directions:

1. **A data source that is not public at pick time.** Lineups before they are
   posted, weather better than the feed, something local.
2. **A market where the books are lazier.** The CFB document (§1) argues
   exactly this case for Group of Five and weeknight games — scale overwhelms
   the books, and the further from the spotlight the softer the number. That
   argument is *about* information asymmetry, which is the thing this test says
   we currently lack.

Anything that reprocesses the same public inputs will reproduce the price,
because that is demonstrably what this model already does.

---

## 7. State as of tonight

- **Paper mode is ON** (`python3 launch.py --paper`). Picks are journaled to
  the `paper` bucket with zero dollars. The headline record has stopped moving.
- **The banked closes are repaired** (`--repair-closes`, applied). All 113 now
  agree with the independent rebuild.
- **Both sides of the price are recorded** from 2026-08-09, so unders become
  CLV-measurable from that date.

Six bugs were fixed in the measurement layer to get here — the stake floor, the
cap reweighting, the CLV side, the CLV line, impossible prices, and the missing
under side. **The finding was the same after every one of them.** That
stability is the strongest thing we know about this model.

---

## 8. How to re-run it

```
python3 stakecheck.py --info      # this document's table
python3 stakecheck.py --clv       # the corroborating CLV number
python3 stakecheck.py --paper     # the paper book, once it has settled bets
```

Re-run `--info` when the paper book reaches roughly 150 settled bets. If the
claimed edge's interval has moved clear of 0.50 by then, something changed and
this document is out of date. If it has not, it is not the sample size.
