# The selection correction — a proposal, not a decision

**Status: proposed. Nothing is built. Step 1 is a test that can kill it.**

---

## 1. The thing that needs explaining

`guardfit` measured the shipped claim against what landed, by price band:

| | weighted gap | bets |
|---|---|---|
| below the 55% hinge | **+10.0%** | 99 |
| above it | **+13.8%** | 138 |

Positive means the model claimed more than it delivered. It is roughly the
same size at every price — about **+12 points, everywhere**. That is not a
favourite problem, a market problem, or a recent problem: `bleed --split`
shows both halves of the journal losing significantly on their own
(z −2.27 before August, z −2.56 after), through a product mix that changed
enormously in between (break-even 62.7% → 49.5%).

Meanwhile the deep fitter says the model is roughly fine. It calibrated
`mlb:hits` on **282,862** player-game outcomes and asked for T=1.42;
`home_runs` on 293,469 and asked for T=1.04.

Both can be true at once, and the reason they can is the whole proposal.

## 2. Why a fit on all of history cannot see this

The deep fitter calibrates over **every prop**. We bet a **subset** — the
ones where our number disagrees with the book enough to clear the edge bar.

Write our corrected estimate as `p̂ = p* + ε`: the true probability plus
estimation error. Over the whole population ε averages to zero, which is
exactly what the deep fit verifies and what it is good at.

But we do not choose bets at random. We choose them where `p̂` sits far
above the book's implied `q` — and a big gap happens either because we
know something, or because **ε happened to be positive**. Conditional on
being selected, ε no longer averages to zero:

> **E[ε | selected] > 0**, so **E[p* | selected] < E[p̂ | selected]**.

The claim runs hot on the bets we place, while remaining unbiased on the
population the deep fitter measured. This is the winner's curse, and it is
structural: **no amount of refitting on unselected history can remove it,
because the bias does not exist until selection happens.** It only shows
up in the journal, which is the one place we were not fitting.

The size of the effect is the ratio of estimation variance to the variance
of the disagreement. If the edge signal is mostly noise, the shrink needed
is large. A +12-point gap says it is large.

## 3. First: the test that could kill this

**Do not build the correction before running this.** Several other faults
produce the same +12 signature and would be mis-treated by a shrink:

- pricing against a line that has already moved (stale quotes)
- a de-vig or `fair` construction that is wrong
- grading errors
- a market-shrink weight that is simply too weak

Selection makes a prediction none of those do. **The curse grows with the
size of the claimed edge.** A bet we thought had 2 points of edge was
barely selected; one we thought had 12 was selected precisely because ε was
large. So:

> Bucket the settled journal by the `edge` column and measure the
> calibration gap in each bucket.
>
> - **Gap rising with claimed edge** → selection. Proceed.
> - **Gap flat in claimed edge** → it is a level error from something
>   else, and a selection shrink is the wrong instrument. Stop and find it.

This runs on data already in the journal, needs no new capture, and
changes nothing. It is one script (`selcheck.py`, unwritten).

A second, cheaper corroboration: the effect should be **weaker on bets
where the model and the book already agreed** and strongest on the
longest-priced disagreements.

## 4. The correction, if the test passes

One extra parameter pair, applied **after** the deep correction, fitted
**only** on journaled bets:

```
p_deep  = apply_temperature(p_raw,  T_deep, b_deep)   # unchanged, deep fitter's
p_final = apply_temperature(p_deep, S_sel,  c_sel)    # new, journal's
```

The fitting machinery already exists and is already right —
`journalfit.fit_temperatures` running `as_over` over settled bets is
exactly this fit. The only thing that was wrong was *where the answer
went*: it tried to overwrite the deep correction instead of composing with
it. Composition is the entire change.

**Storage.** A separate store, `data/models/selection.json`, keyed
`sport:market` like the other. Separate rather than a field on the existing
entry, so that the two can never be confused by a future reader — the
mistake that nearly overwrote 282,862 samples with 479 was exactly a
confusion about which fitter owned a number.

**Refitting it is safe, and this is where `undo_temperature` finally earns
its keep.** Each bet already journals `cal_temp` / `cal_bias`; the
selection layer would journal its own alongside them. A refit un-corrects
only the selection layer, leaves the deep layer alone, and fits again — no
compounding, and the deep fitter is never touched.

## 5. Pooled first, per-market later

Selection bias is a property of **the selection process** — the edge bar,
the shopping, the grade filter — not of the market. It should be roughly
common across markets, and `guardfit`'s table agrees: the gap is flat
across price bands rather than concentrated anywhere.

The journal currently holds **2,871 settled MLB bets** (1,860 home runs,
491 total bases, 481 hits, 39 strikeouts). That is a comfortable sample for
**one pooled parameter pair per sport**, and a thin-to-useless one for four
separate ones. So:

- **Ship pooled per sport.** One `(S, c)` for `mlb`.
- Let a per-market correction earn its way in later, when its own record
  convicts it — the house rule everywhere else.

## 6. The hazard I would not hand-wave

**This correction feeds back on its own training set.** Shrinking claims
toward 50% shrinks edges; fewer bets clear the bar; the ones that still do
are the most extreme disagreements — which carry *more* curse, not less.
The next fit could ask for a bigger shrink, and so on.

That loop may converge or may run away. Nothing in the current design
proves which. Three guards, all cheap:

1. **Cap it.** A maximum shrink per refit, and a hard floor on `S`.
2. **Refit on a fixed window**, not on the post-correction board only, so
   the training population does not chase the correction.
3. **Watch it.** If `S` climbs on consecutive refits without the measured
   gap closing, that is the runaway signature — stop and re-diagnose.

## 7. The bar before it prices anything

Fitted is not validated. The bar is out-of-sample, and it should be:

- Split the journal by date. Fit `(S, c)` on the earlier part only.
- Measure the calibration gap on the **later** part, with and without.
- Ship only if the held-out gap closes materially. A correction that only
  improves the data it was fitted on has demonstrated nothing.

`bleed.py --split` already does the date-splitting arithmetic and can host
the comparison.

## 8. What it will do to the board — read this before agreeing

A 12-point over-claim means bets claiming 60% are landing near 48%. At
−110 the break-even is 52.4%, so a claim of 60% shows **+7.6 points of
edge** and is really **−4.4**.

Correcting that honestly will not trim the board. **It may empty it.**

That is the correct outcome if the measurement is right — those bets were
losing money, which is what the −15.6% ROI has been saying all along. But
it means the visible result of shipping this is a site that recommends far
less, possibly nothing, for a while. Worth deciding that you want that
before it happens, rather than discovering it on a Tuesday.

## 9. What would make me abandon this

- The edge-bucket test in §3 comes back flat. Then it is not selection.
- The held-out gap in §7 does not close. Then the correction is fitting
  noise.
- `S` runs away across refits. Then the feedback loop is real and the
  design needs a fixed reference population before it can ship.
- The gap turns out to be concentrated in one market or one book after
  all — `bookcheck`'s field reconstruction is currently too noisy to rule
  this out (its field spread is 23.33%, five times the effect it measures).

## 10. Order

1. `selcheck.py` — the edge-bucket test. Diagnostic only, ships nothing.
2. If it passes: fit pooled `(S, c)` per sport, store separately, journal
   the applied values, **do not apply yet**.
3. Out-of-sample check per §7.
4. Only then compose it into pricing, capped, behind the existing
   evidence gate.
