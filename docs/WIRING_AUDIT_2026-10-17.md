# Wiring audit — every feature, fit and invention, and whether the picks use it right (2026-10-17)

Ethan, 2026-10-17: *"make sure we are wrapping all the features into the
most likely bets and edge bets where it makes sense. just cause we add
features and data and shit and say we did doesnt mean we are using them the
right way so make sure all of our tools and data are being used correctly
and not just the ones you just added but ALL tools and data we were and are
using."*

Two questions, kept apart because they fail differently:

- **Wiring:** does each thing reach the place it belongs (the projection,
  the Most Likely board, Edge, a card), or does it sit unread?
- **Value:** where it does reach, is it read the right way?

## 1. The thirteen inventions, into Most Likely and Edge

They were built as readings on the pick and game pages, each with a bar
set before its first box run. Until today a reading that cleared its bar
would still have waited for someone to wire it by hand. That is how a
passing measurement ends up unread. `engine/ideagate.py` closes that gap.
Each invention reaches the picks at the earliest point it belongs, and
only once its own saved verdict says HOLDS. This is the same rule
likelycal and likelyctx already follow.

| Invention | Where it lands once it holds | Hook |
|---|---|---|
| Rookies (I8) | the prior a thin rookie sample (under four NFL games) is pulled toward: his college line, translated | `sources/nflverse.build_slate` → `form_prior_kind="rookie"` |
| Role change (I10) | the usage bridge's targets and carries follow the detected role, not four flat weeks | `nflusage.volume_roles` × `ideagate.role_ratio` |
| Kick physics (I7) | a kicker's field goals and kicking points, as its own "air" step in the chain | `projection.build_projection` × `ideagate.kick_factor` |
| Drive simulator (I9) | two teammates' parlay legs take the simulated correlation; the doc's clash type and verdict stay | `parlays.relate` (the taxonomy alone is `relate_prior`) |
| Book menus (I1) | Most Likely chance ± the measured excess; an Edge pick refused if it takes the edge away | `likelyboard.build` / `ideagate.edge` |
| Book recipe (I3) | the same, when the outcome recipe sits ≥ 0.75 sd from the line | same |
| Attention (I6) | the same, on a spiked player: under up, over down | same |
| Book copies (I4) | the market check compares our chance with the fair chance, one vote per opinion | `likelyboard.market_check` |
| Practice reports (I5) | holds a listed man under 50% to play off Most Likely and Edge | `likelyboard.held_reason`, `ideagate.edge` |
| Honest ranges (I11) | holds a pick the range puts under even, only where the range was covered AND beat our chance (Brier) held out | same |
| Alt curve (I2), autopsy (I12), risk (I13) | never a number, by design: picks sit at the main line where the curves agree; the autopsy names a step, it is not one; the risk view is My Bets' | — |

**Rules.**

- Menu, recipe and attention can together move one pick's chance by at
  most eight points (`MAX_SHIFT`).
- A posted pick keeps the chance it went up at.
- The journal keeps the first claim (`board_raw_prob`), so the record's
  own fits judge what we said and not this correction.
- The NFL build now writes the readings before its Most Likely board. They
  were written after it, which meant no reading could ever have reached
  the board.

`python3 -m engine.ideagate --sport nfl` prints, gate by gate, whether each
one is applied or waiting on its verdict. Today every gate is waiting: none
has had its box run yet (BX to CC).

## 2. Value: read the right way?

These problems were found while wiring the gates and fixed before any gate
can open:

1. **The air step compared tonight's air with sea-level air.** A kicker's
   own average was built in his usual air, which for a Denver kicker is
   half thin air. A Denver home game would have counted the altitude twice.
   The step now compares with his usual air: half his home stadium's (its
   roof's air, or standard air at its altitude) and half the league's (the
   fit now saves `mean_dev`). It also refuses the 65° placeholder that an
   unforecast outdoor game carries (`Weather.measured`).
2. **The simulator would have been measured against itself.**
   `playsim.prior_rho` asked `parlays.relate` for the pricer's number. Once
   the gate opened, `relate` would have returned the simulation's own
   number, and the held-out test would have compared the simulation with
   itself. It now asks `relate_prior`, the taxonomy alone.
3. **Opposite sides.** The simulated correlation is for two overs. A pair
   on opposite sides now takes it with the sign turned, as a Gaussian
   copula does when one leg is flipped. Without this it would have been
   priced as if both legs ran the same way.
4. **The role ratio reads the share it was measured on.** That share is
   his targets or carries over his team's that week
   (`rolechange.series_from`), not a proxy.
5. **The map was honest about three measurements:**
   - `defoutfit` (a defence missing its starters) was measured and NOT
     applied.
   - `qbscriptfit` retired the spread tilt rather than adding one.
   - `chartfit` and `ngsfit` found no lift, so they are notes on the scan,
     never counted.

## 3. Every fit and measurement in the repo (`engine/wiremap.py`)

There are 65 rows: every fitter in `engine/`, every measurement script at
the top level, and the thirteen inventions.

| Lands | Rows | What it means |
|---|---|---|
| number | 24 | the projection or pricer reads its store, or the measured constant it wrote into the code |
| board | 5 | the Most Likely board reads it (rankfit, yardagefit, scanfit, tdmatchfit, scanblendfit) |
| gated | 10 | the inventions above |
| card | 6 | shown, never a number: alt curve, autopsy, risk, MLB expected stats, play charting, Next Gen Stats |
| report | 14 | a person reads it; what it found is in the code it names, or it found nothing to apply |
| failed | 6 | cbfit, tdinjfit, tdmanfit, tdtop (2026-10-04), cfbbridgefit (10-14), defoutfit (10-12) — unwired on purpose |

**What the check holds** (`python3 -m engine.wiremap --check`, and
`tests/test_every_fit_lands_where_it_says.py`):

- A new fitter cannot be added without a row.
- A row that claims a reader fails if that reader's source never names the
  fit.
- A "gated" row must be one of ideagate's gates.
- Nothing on the number path may import a fit that failed its bar.

**The engine's 445 modules by lane:**

- 268 on the number path
- 71 build-only (cards, the journal)
- 49 reached only by pages and Ask
- 57 command-line only (probes, fitters, chores)

**The data we pull** is `engine/datause`'s job. Its 12 registered signals
each land at least where they were promised; none is short.

**On tonight's boards,** `python3 homecheck.py inputs` lists every step of
the projection that moved no pick.

## 4. For Ethan to decide — not changed here

1. **Game-line edges.** `engine/haircut` measured, 2026-09-19, that the
   model's claimed moneyline edge did not survive in college (2,729 games)
   or the NFL (1,356). Survival was about 0%, with an interval spanning
   zero. The shipped college haircut (35% standard, 50% marquee) assumes
   65% survives. A large enough raw edge still makes an Edge pick. Refusing
   game-line Edge picks outright, or setting the haircut to the measured
   number, is a call about what the site bets, so it is left to you.
2. **The learned multiplier model** (`engine/ml`) is opt-in (`--model`),
   and the box never passes it. The measured steps (defence transfer,
   weather, teammates, quarterback) replaced what it did, so turning it on
   would count those effects twice. It is left off on purpose.
3. **An empty hook.** The usage bridge's `att_usage` is never filled for
   the volume markets (attempts, completions, carries), which have no
   usage bridge. It moves nothing, so it is harmless.

## 5. On the box

Block CD in `docs/WHEN_YOU_ARE_HOME.md` (step 135):

```
cd /srv/qellys && sudo -u qellys python3 -m engine.ideagate --sport nfl
cd /srv/qellys && sudo -u qellys python3 -m engine.ideagate --sport cfb
cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.wiremap
cd /srv/qellys && sudo -u qellys python3 homecheck.py inputs
```
