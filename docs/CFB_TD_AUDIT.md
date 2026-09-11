# CFB touchdown model — audit findings, 2026-09-06

Ethan: *"focus deeply on the models and shit for cfb, specifically the TD
model. we need to be showing the best bets possible for the most likley
bets."*

Six independent agents read the college anytime-TD chain and measured it
against real data pulled from the sportsdataverse / cfbfastR mirror —
roughly 291,000 college player-game rows, 7,234 games and 3,580 closing
lines, rebuilt into a scratch database because `data/history.db` on a
fresh clone is empty. Everything below that carries a number was measured
on that rebuild, not reasoned from the source.

## Read this first: verification is INCOMPLETE

Each proposal was to be attacked by an adversarial verifier. **Thirty of
those thirty verifiers died on a session limit**; a resumed run had
produced four verdicts when this was written:

| verdict | what it means |
|---|---|
| 3 refuted | including one reading *"REFUTED ON MAGNITUDE, ON THE SPECIFIED FIX, AND ON THE PLAN — though the underlying defect is real and I confirm it"* |
| 1 upheld | the `merged_usage` fields defect (below) |

So: **the FINDINGS are measurements and mostly replicate. The PROPOSALS
are not verified, and the first three attacked did not survive as
written.** Do not implement a proposal from this document without
re-measuring it. A verifier that rebuilt the chain independently
reproduced the shipped held-out AUC at 0.6753 against the 0.675 in
`engine/likely.py:291`, so the replay itself is sound — it is the
proposed *fixes* that came apart.

## What was fixed in this pass

Two halves of one regression, both measured, both shipped:

* `ab20781` rekeyed a college game row to `away@home` so `engine.ledger`
  could join a college total like every other sport's. Real fix. But every
  other file on the mirror still keys by the numeric ESPN id, and nothing
  carried it forward. **Player stats joined 0 of 182,694 rows; closing
  lines 0 of 1,183,529.** Both now alias under both keys
  (`fe6901a`, `d0ab7bd`). There are TWO games maps over that table —
  fixing one left the other broken, which is why the test pins both.
* `CFB_WATCH_LIMIT` 5 → 20. Five was the NFL's number, sized for a
  sixteen-game Sunday; college plays sixty-eight. It matters more here
  because `anytime_td` is the ONLY college player market that clears
  `likely.rankable` — every yardage market has no measured AUC — so TD
  rows are the whole player half of Most Likely, and the board holds 40.

## Findings, by how much they matter

### 1. The board's share denominator is not the fitter's
`engine/cfb/tds.py:904` sums every player's per-game AVERAGE; each average
is over the games that player recorded in that market, so ~20 of them
over-count the team. `engine/cfbtdfit.py:267` — the fitter that set
`POSITION_TD_SHARE`, the blend and `RZ_SHARE_WEIGHT` — uses the team's
ACTUAL per-game rush+rec yardage. Measured inflation **1.52x** mid-season.

Consequence measured over 38,309 player-games: shares of team TDs sum to
**0.570** rather than 1.0; expected distinct scorers **1.52** against a
realised **2.43**. **Verified by hand** — the two lines are different
quantities and the constants were fitted against the second.

The proposed fix (swap the denominator) was **refuted on magnitude and on
the plan** while the defect itself was confirmed. Re-measure before acting.

### 2. The floors, not the supply, are what starve the board
`likely.MIN_PROB = 0.55` refuses **656 of 690 watch rows (95.1%)** — and
it sits at **85% of the model's own ceiling**, because the rate clamp caps
any probability at `1 - exp(-1.05) = 0.65`. It is a floor near the top of
the range, not the middle. The effective admissible price window for a
college TD row is **[-250, +105]**: past +110 no model probability can
produce a row at all, since `MIN_PROB` plus `MAX_CREDIBLE_EDGE` make it
arithmetically impossible.

`CFB_WATCH_LIMIT = 20` was then measured as *still* truncating: 34 rows
clear the floor, the cap keeps 20, 17 survive `admissible`.

### 3. The calibration prior corrects the wrong end
The shipped `cfb:anytime_td` prior (T=1.24, bias -0.120) helps the bottom
of the range and hurts the only band Most Likely publishes: it pulls 0.60
to 0.55. Held out, the raw model claims 61.6% where **66.6%** lands — it
is already under-confident there. The prior pushes **232 of 727 eligible
rows under the floor, and those rows scored 56%**.

### 4. The defence term was deleted and measures positive
Opponent points-allowed-to-date adds **+0.0039 AUC leave-one-season-out,
positive in all four seasons** (2022 +0.0023, 2023 +0.0045, 2024 +0.0021,
2025 +0.0080). The team-level measurement that killed it does not
reproduce at the size reported. `defense_multiplier` currently returns 1.0
unconditionally.

### 5. `merged_usage` blends usage but not touchdowns — UPHELD
`tds.py:319` omits `anytime_td` from `fields`, so `merged['anytime_td']`
stays the current season's mean while `merged['games']` counts both
seasons. The history weight therefore reaches maximum on a one- or
two-game scoring sample — the model chases last Saturday's touchdowns in
exactly the weeks the file's own docstring warns about. **24.7% of rows
that use the history term; 93% of week-2 rows.** This is the one proposal
a verifier upheld: mechanism real, lines cited correctly, numbers
replicate within noise.

### 6. The published AUC is not the board's number
`CFB_TD_AUC = 0.675` is the fitter's chain. The shipped board chain,
paired on identical rows, ranks at **0.6662** (bootstrap CI on the gap
[+0.0101, +0.0156]). Separately, the board does not sort on the model
probability at all — it sorts on `longshots.calibrated_prob`, which is
the market-shrunk number.

### 7. Early season is materially worse and the board does not say so
Weeks 1-4 AUC **0.6274** against weeks 9+ **0.6687**. Today's board is in
exactly that regime. Related: the fit has never graded a single row built
the way the board builds them in September — `samples()` takes prior only
from within the season, so the cross-season path is unmeasured.

### 8. Smaller, all measured
* The 0.15 share floor binds on **40% of rows** (65.7% of QBs); where it
  binds the opportunity signal is discarded entirely.
* `cfbstats.week_modes` keys on the bare week string, and ESPN restarts
  the week counter for the postseason — 58 bowl games pool into bucket
  "1" and are stored as **false zeros**, poisoning the held-out season.
* The QB gets no game script at all, and a wind penalty labelled "passing
  touchdowns suppressed" — but `anytime_td` is rushing and receiving only.
* `boards.guide('cfb')` prints "Built on the same 0.72 AUC ranking" — the
  NFL figure — directly under a college line saying 0.68.
* Two drops in `build_cfb_td_longshots` `continue` without incrementing
  the census, so the funnel cannot be reconciled.

## The honest summary

The board was thin for a stack of reasons that compound: probabilities
deflated by a units mismatch, then a floor set near the model's ceiling,
then a calibration prior pushing a third of the survivors back under it,
then a row cap sized for a different league. The two ingest joins were
returning nothing at all, which is fixed.

What is NOT established is which fix to make first. Three of the four
attacked proposals did not survive. Re-run the verification before
changing the chain.
