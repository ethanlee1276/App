# The competitive recipe

A living file. It holds a competitive-landscape study of the betting-analytics
market and, against it, a ledger of what this site already does, what it does
partly, what it has not built, and what it has decided **not** to build.

The study is preserved at the bottom, unedited. Everything above it is ours.

## Why it is written this way

A roadmap that only lists what is missing rots in one direction: it never
records the day something got built, so it reads as an indictment forever. A
roadmap that only lists what exists rots in the other: it becomes marketing.
This file carries both columns, and the rule is that **the status column is
evidence, not intention** — every `HAVE` names the file that implements it, so
a claim here can be checked in about ten seconds.

Two entries in the ledger were downgraded while writing it, on exactly that
test. `account_health` is real code, but its published payload is `books: []`
in this repo; that is correct (the checked-in ledger is a one-row fixture, the
real journal lives on Ethan's laptop) and it is also the reason the flagship
pillar cannot be called shipped until it has been seen with data behind it.
Referee/judge assignments read as a feature in `coverage.py` until you read the
line: they are `PARKED`, with "no structured assignment feed" written next to
them.

## Protocol for adding to it

1. New findings append to the study, dated. Nothing already in it gets
   deleted — a claim that turned out wrong is more useful marked wrong than
   removed, because the next study will make the same claim again.
2. Anything actionable becomes a row in the ledger with a status.
3. When a row moves to `HAVE`, it names its file in the same commit that
   builds it. A status change with no file reference is not a status change.
4. Guardrails are not rows. They live in their own section and they are
   decisions, not backlog.

---

## The three pillars

The study's own feature matrix has three columns that are empty across the
entire incumbent field — exchange-native pricing, account longevity, and
public model calibration. Those are the three things worth being good at,
because everything to their left (+EV, arbitrage, prop research, bet tracking)
is now table stakes shipped by a dozen tools at $20/month.

| Pillar | Where we actually stand |
|---|---|
| **Radical transparency** | Furthest along. Calibration buckets with confidence bands, Brier against the de-vigged market on our own picks, era-scoped so a re-tune is judged on its own work, a permanent sweep history in `calibhistory.py`. Completed to the study's spec on 2026-08-03 — see below. |
| **Account longevity** | The engine exists (`account_health`, `engine/ledger.py`) and, since 2026-08-03, scores every signal this journal can honestly see — five of the study's seven — and names the rest on the page. Still buried on the Record page, and still never seen with a real journal behind it. |
| **Exchange-native** | Two venues, two lenses since 2026-08-03: Polymarket read as informed FLOW (public wallets), Kalshi read as PRICE (a CFTC-regulated order book's mid is the market's probability, no vig to strip), with a cross-market board putting the exchange's number beside the model's. Novig and ProphetX remain absent — both got CFTC designation in June 2026, after this site's exchange work. |

---

## The ledger

Status values: **HAVE** (built, file named) · **PARTIAL** (built, gap named) ·
**MISSING** (not built) · **WON'T** (decided against, reason in Guardrails).

### Table stakes — the commodity layer

| Item | Status | Where |
|---|---|---|
| +EV screen across books | HAVE | `engine/marketscan.py`, Edge Board |
| Arbitrage / middles / low holds | HAVE | `engine/marketscan.py`, `shopping_value.py`, Scanner |
| Line shopping / best price | HAVE | `shopping_value.py` |
| Stale-line detection | HAVE | `stale_lines.py`, `engine/linemoves.py` |
| Prop research (rolling windows, splits) | HAVE | `engine/form.py`, `engine/matchup.py`, Players/Trending |
| Bet tracking + journal | HAVE | `engine/ledger.py` — our own picks, not the user's book account |
| CLV tracked per bet | HAVE | `_bet_clv`, `engine/ledger.py` |
| **CLV kept after the game starts** | HAVE | `closing_line` is a stored column. This is the study's clearest documented competitor gap (Pikkit drops it at kickoff) and we do not have it because we solved it — we have it because we never had a live feed to lose. |
| Season / playoff simulators | HAVE | `engine/futures.py`, `engine/playoffs.py` |
| Parlay construction with correlation | HAVE | `engine/correlation.py`, `engine/parlays.py`, `engine/parlayledger.py` |
| Fractional Kelly staking | HAVE | `engine/betting.py` |
| Risk of ruin / drawdown | HAVE | `engine/ledger.py` |
| Auto-sync of the user's sportsbook accounts | WON'T | credential-sharing — see Guardrails |
| Deep-link to a book's bet slip | MISSING | the study calls this the safe ceiling (Outlier does it). We render prices without a handoff. |
| Promo / free-bet expiry tracking | MISSING | we track no promos |

### Pillar 1 — Account longevity

The study's Stage 1, and the signal list is the study's own.

| Signal | Status | Where |
|---|---|---|
| CLV beat rate | HAVE | `HEALTH_W_CLV`, weight 40 |
| Market concentration | HAVE | `HEALTH_W_CONCENTRATION`, weight 20 |
| Stake-rounding profile | HAVE | `HEALTH_W_STAKES`, weight 13 |
| Volume at one shop | HAVE | `HEALTH_W_VOLUME`, weight 12 |
| Product mix (props vs main lines) | HAVE (2026-08-03) | `HEALTH_W_PROP_MIX`, weight 15. Distinct from concentration, and the test that proves it: a book spread evenly across eight prop markets scores clean on concentration while being exactly the all-props profile that gets limited first. |
| Time-to-bet after a line move | MISSING | **and not honestly computable.** `bets.ts` is when *we* journaled a pick, not when a human placed a bet, and no line-move timestamp is joined per bet. Building this from `ts` would be inventing a number. |
| Promo behavior | MISSING | not tracked, and cannot be — we take no money |
| Deposit/withdrawal ratio | MISSING | same |
| Per-book 0–100 score with named drivers | HAVE | `account_health` returns score, band, drivers, actions |
| Concrete behavioral advice | HAVE | same — round stakes, diversify markets, open a second book |
| Named blind spots on the page | HAVE (2026-08-03) | `HEALTH_BLIND_SPOTS` — four signals, each with why it is missing |
| Seen with a real journal | **NO** | the published payload here is `books: []` |

The honest read: the three remaining signals need data a non-transacting
analytics tool structurally cannot have, which is a fine answer — and as of
2026-08-03 it is *said* on the page rather than quietly omitted, alongside a
fourth we decline to collect on purpose. Device and browser fingerprinting is
listed as out of scope with the reason attached: watching those signals is
how you talk yourself into spoofing them, and that is account fraud rather
than bankroll management.

### Pillar 2 — Exchange-native

| Item | Status | Where |
|---|---|---|
| Polymarket informed flow (public wallets, trade tape) | HAVE | `engine/predmarket.py`, `pm_build.py` |
| Own stored tape, appended every build | HAVE | `engine/predmarket.py` — "a year of tape is the moat" |
| Kalshi order book as a pricing source | HAVE (2026-08-03) | `engine/sources/kalshi.py` — keyless public API, mid-of-book as the fair (no vig to strip), snapshot tape from day one, and a cross-market board on the Prediction Markets page: Kalshi's probability beside the model's, gap in points, only where both exist. Enters as a PRICE, never as flow — `predmarket.py`'s no-trader-identity reasoning still stands and a test forbids the adapter growing wallet-shaped functions. Awaiting first live pull on Ethan's machine. |
| Novig / ProphetX | MISSING | both received CFTC designation in June 2026, after this site's exchange work |
| Cross-market edge: exchange fair value vs traditional book | PARTIAL (2026-08-03) | exchange-vs-MODEL ships (the Kalshi board); exchange-vs-de-vigged-BOOK is the remaining leg, and the inputs (cached book odds) already exist |
| Sporttrade | WON'T | exited sports betting entirely, May–June 2026 |

### Pillar 3 — Radical transparency

| Item | Status | Where |
|---|---|---|
| Calibration buckets, predicted vs realized | HAVE | `calibration()`, `engine/ledger.py` |
| Sample-size confidence band, small n reads "too early" | HAVE | same — ±1.96·√(p(1−p)/n) |
| Brier, model vs de-vigged market, on our own picks | HAVE | `brier_model` / `brier_market` / `brier_edge` |
| Published even when the market wins | HAVE | "a site that hides this number is a tout with a website" |
| Era scoping, so a re-tune is judged on its own picks | HAVE | `calibration_era` |
| Per-league calibration | HAVE | per-sport record payload |
| Permanent sweep history tied to a git SHA | HAVE | `engine/calibhistory.py` |
| Probation → promotion bar | HAVE | 100+ graded, z ≥ 2 |
| **Log loss** | HAVE (2026-08-03) | the study names Brier *and* log loss; only Brier existed |
| **Expected Calibration Error, published** | HAVE (2026-08-03) | ECE existed offline in `engine/backtest.py` and was never in the payload the site reads |
| **Reliability diagram against the diagonal** | HAVE (2026-08-03) | the bucket bars were a table; a reliability diagram is a curve you compare to y=x |
| Calibration by market | HAVE (2026-08-03) | `calibration_splits`, `engine/ledger.py`. A test board with aggregate ECE of 7.4 points covered one market on the diagonal and one twenty points hot. |
| Calibration by time horizon | HAVE (2026-08-03) | same. Buckets at 0 / 1–3 / 4–14 / 15+ days; reports `horizon_degenerate` when fewer than two buckets clear the sample bar, rather than drawing a one-bar chart. |
| Immutable, publicly hashed forecast log | HAVE (2026-08-03) | `forecast_log` table, `seal_forecasts` / `verify_forecast_log`. Each row's hash covers the row and the hash before it; the head is published on the Record page. |
| The self-tuning loop, visible on the site | HAVE (2026-08-03) | `self_tuning_report`, `engine/ledger.py` → "The model tunes itself" on the Record page. The nightly refit, per-market temperatures with plain-language verdicts, markets closed by their own boundary fits, and the ECE trend across commit-stamped sweeps were all real and all invisible — a learning loop nobody can see is indistinguishable from a static model. The section's disclosure states the WON'T below in public: the numbers come from arithmetic over the journal, never a language model. |

### Data differentiators

| Item | Status | Where |
|---|---|---|
| Weather / wind / dome, tied to live game state | HAVE | `engine/weather.py`, `engine/stadiums.py` — the study calls this "genuinely rare" |
| Park factors | HAVE | MLB pipeline |
| MLB plate-umpire effects wired into props | HAVE | `engine/mlb/projection.py` — a wide zone lifts strikeouts, and it is named in the reason string |
| nflverse / Statcast open data | HAVE | `engine/sources/nflverse.py`, `engine/mlb/ml.py` |
| NFL officiating crew tendencies | MISSING | the study's largest named data gap |
| NBA referee tendencies (FT-driven props) | MISSING | same |
| UFC referee & judge assignments | MISSING | `PARKED` in `engine/coverage.py`: "no structured assignment feed" |
| Travel / rest / altitude | PARTIAL | rest/travel built and rendered (`engine/fatigue.py`, wired into `pipeline.py`, `betting.py`, `losspatterns.py`); altitude is a static venue field (`engine/stadiums.py`), not a fatigue-specific adjustment |
| Injury-report latency | PARTIAL | `engine/injuries.py` has the reports, not the latency |
| Published effect sizes for venue adjustments | MISSING | the study's specific ask: don't just show wind, show what wind is worth |

### Portfolio risk (Stage 3)

| Item | Status | Where |
|---|---|---|
| Fractional Kelly | HAVE | `engine/betting.py` |
| Correlation between legs, clash detection | HAVE | `engine/correlation.py`, `engine/parlays.py` |
| Correlation priors backtested against our own history | HAVE | task #52 |
| Risk of ruin | HAVE | `engine/ledger.py` |
| Drawdown-aware staking | PARTIAL | drawdown is tracked and wired into the parlay module; it does not constrain the singles stake vector |
| Covariance matrix across *simultaneous* positions | MISSING | the study's sharpest quant-finance gap: no consumer tool does this |
| Per-game / per-player / per-day exposure caps, auto-enforced | PARTIAL | one-per-slate cap exists for parlays (task #49); no per-player or per-day cap |
| Shrinkage of edge estimates | PARTIAL | the humility clamp tempers edge; it is not a formal shrinkage estimator |
| Tax lots / reporting | MISSING | |

### Responsible gambling

| Item | Status | Where |
|---|---|---|
| Helpline, terms, About page | HAVE | About view, footer |
| "Process over results" framing | HAVE | the `process` metric — lucky wins and unlucky losses are named as such |
| Loss-chasing detection from tracked behavior | MISSING | |
| Reality checks tied to behavior, not the clock | MISSING | the study is specific that calendar-timed nudges are the wrong design |

---

## Guardrails

Decisions, not backlog. Each of these is a **WON'T** with a reason.

* **No automated bet placement.** Prohibited by most sportsbook terms and
  written into some state codes (Michigan Admin Code R. 432.752 bans bot
  play). Deep links are the ceiling, and we have not even built those.
* **No credential sharing.** The SharpSports model has users hand over
  usernames, passwords, security answers and one-time passwords. It defeats
  2FA, violates account-sharing terms, and makes us custodian of the worst
  possible secret. If bet sync is ever built, it is OAuth-style or it is not
  built, and the risk is disclosed on the page.
* **No IP, device or identity spoofing.** This is the ethical line inside the
  account-longevity pillar and it is not a close call: behavioral coaching is
  fine, KYC evasion is fraud. Even Claw Arbs, the one incumbent in this
  category, draws the line in the same place.
* **Prefer exchange public APIs and licensed feeds to scraped odds.** Swish
  Analytics v. OddsJam/OpticOdds survived a motion to dismiss on all five
  claims. Scraping books' proprietary odds is live civil risk.
* **Disclose any affiliate relationship prominently, or take none.** FTC
  endorsement guides require clear and conspicuous disclosure of a material
  connection, and hidden referral revenue would destroy the transparency
  pillar far faster than it would earn anything.
* **No user betting data published.** The flow modules use public on-chain
  and exchange data. They stay that way.

---

## Built the day this file landed — 2026-08-03

Pillar 3 completed to the study's spec, because every input already existed in
the journal and none of it costs an API credit:

* **Log loss** alongside Brier. The study names both, for a reason worth
  writing down: Brier is a squared error and forgives a confident miss more
  than log loss does. A model that says 95% and is wrong loses 0.9 of Brier
  and 3.0 of log loss. Both are strictly proper; publishing only the gentler
  one is a choice.
* **Expected Calibration Error**, in the payload the site reads. It existed
  in `engine/backtest.py` and never reached a page.
* **A reliability diagram** — the bucket bars are a table, and a table does
  not show the one thing that matters, which is the distance from the
  diagonal.

All three are computed against the de-vigged market on the same picks, the
same way Brier already was, so the comparison stays honest.

## Not built today

In the study's own staging, and roughly in the order the study argues for:

1. ~~**Product mix in the longevity score**~~ — built 2026-08-03.
2. ~~**Say what longevity cannot know.**~~ — built 2026-08-03.
3. ~~**Calibration by market and by horizon**~~ — built 2026-08-03.
4. ~~**Immutable hashed forecast log**~~ — built 2026-08-03.
5. ~~**Kalshi as a pricing source**~~ — built 2026-08-03; the
   exchange-vs-book leg of the cross-market edge remains.
6. **NFL and NBA officiating-crew tendencies** (data). The study's biggest
   claimed data edge, and the one whose effect sizes are the least
   independently verified.
7. **Covariance across simultaneous positions** (Stage 3).
8. **Loss-chasing detection and behavior-tied reality checks** (Stage 3).

Deep links, promo tracking, travel/rest and tax reporting are real gaps with
no pillar attached; they are commodity features and they can wait.

## Added 2026-08-03 — game-script simulation, and where AI does not go

Ethan, brainstorming after the Futures build: could the Monte Carlo run
against individual bets, and could the site learn from its own record without
a human in the loop?

**The learning loop already exists**, and it is worth writing down because it
is easy to look at and not see:

* `engine/calibrate.py` fits a temperature `T` nightly against settled
  outcomes, minimising Brier. `T > 1` means the model was over-confident and
  every probability gets pulled toward 50%. One parameter, so it cannot
  overfit a few thousand props the way a flexible curve would.
* `is_reliable()` in `engine/mlb/pipeline.py` **closes a market by itself**
  when its fit is bad, and the census names which ones. No human decides
  that, and the Recommended page says "closed by calibration: Total Bases"
  rather than silently dropping 197 props.
* `engine/calibhistory.py` stamps each sweep with a git SHA, so "are we
  improving" has an answer that ties to a commit.
* The probation → promotion bar (100+ graded, z ≥ 2) is the same idea applied
  to a whole market rather than a probability.

So the self-adjusting architecture is not missing. What is missing is the
piece below.

### BUILT 2026-08-03 — per-game Monte Carlo (`engine/mlb/gamesim.py`)

The engine and its gate. NOT yet wired into pricing — see below.

Props are still priced from closed-form distributions, and this does not
change that or try to. What it adds is the **joint**: the chance two props in
the same game both land, which a per-prop distribution structurally cannot
produce.

**The design is an inversion.** Building a new batter-versus-pitcher model
would have produced a second set of marginals disagreeing with the first, and
a page showing two numbers for one question has a defect rather than a
feature. So the per-plate-appearance outcome table is solved backwards out of
the projections the pricing engine already produces — given a hitter's
projected hits, total bases and home runs plus his lineup spot's plate
appearances, exactly one table reproduces all three. The sim therefore agrees
with the pricing engine by construction, leaving the joint as the only new
information, which is the only new information wanted.

**The gate.** `reconcile()` checks the simulated marginals against the
projections, and nothing downstream may read a joint from a sim that fails
it. Measured: worst relative error 2.9% against a 6% tolerance. There is a
test that deliberately breaks the sim to prove the gate can fail.

**The correlation is anchored, not invented.** A simulation produces whatever
dependence its parameters imply, so a correlation read off one is worth
nothing unless the parameter came from outside the simulation. The first
working version held every rate fixed across trials, so the only shared
channel was lineup turnover, and it produced phi ≈ +0.034 — against a target
of +0.115 implied by `parlays.py` MEASURED["lineup_stack"], fitted on 27,613
real games. About a third of the truth. Adding the shared game latent that
`parlays.py` already names (game script, pace, tonight's starter, tonight's
zone) closes it, and its width was swept against that measurement rather
than chosen.

Three corrections worth keeping, since all three were mine:

* The chosen width was first justified as "0.30 fails the reconciliation
  gate." It failed a gate comparing a flat relative tolerance, which is
  accidentally strict on rare markets — a 0.05-per-game home-run rate moves
  several percent between seeds. Once the gate learned to forgive the
  sampler's own noise, 0.30 passed, and the real reason to decline it is
  doctrine: 0.30 OVERSTATES the measured dependence and `parlays.py` is
  explicit that understating is the direction to be wrong in.
* The inversion is exact per plate appearance, which is not the same as
  exact per game — reaching base gives the whole lineup another turn, so the
  shared shock drifts counting stats upward, measured at 7%. The rates are
  now fitted rather than derived.
* And the fit itself was wrong, which the live slate is what found. The
  step was `target/simulated` — came in 10% light, scale up 10% — which
  assumes a linear response, when the entire reason the fit exists is that
  the response is not linear. Scaling a hitter's reaching rates lengthens
  the inning, which hands the whole lineup another turn, so the response to
  `k` is nearer `k**(1+eps)` and a full-gain step overshoots by about `eps`
  times the error it was correcting. `eps` grows with how often the lineup
  reaches, so this was invisible on an average order and severe on a good
  one: a lineup half again league average went into the fit 24.3% hot and
  came out 5.6% COLD, corrected past the target and left there. The step is
  now damped (`FIT_DAMP`), which carries the sweep that set it.

**What the live slate was worth.** Three separate defects, none of which the
synthetic lineup could have shown, and only the third was in the sim:

1. the harness graded raw per-market projections instead of the coherent
   triple `run_mlb_slate` actually prices, so a hundred-odd hitters a night
   were dropped as "not valid baseball" and two thirds of the league got no
   verdict at all (10 lineups reconciled, not 30);
2. short orders were simulated at the length the feed supplied, cycling 9/8
   too fast and inflating every remaining hitter's plate appearances ~12%
   (`pad_to_nine`);
3. the overshoot above.

Worst relative error across the league went 0.189 → 0.087 as the first two
landed. The third is verified against synthetic orders spanning the range
that failed — the container has no route to statsapi.mlb.com — so the
league-wide number after it is Ethan's next `sim_reconcile.py` run, not a
figure recorded here in advance.

**The fit was also measuring too coarsely to act on what it measured.**
Each round takes its step from a SAMPLED mean, so it scales a hitter's
whole table by that round's sampler error along with the correction — and
the last round's is never re-measured, so it ships. The error is relative,
which makes it worst on the thinnest projections, i.e. the bottom of a real
order. `sim_diagnose.py` on the live dump returned the same cause for all
four survivors: re-fitting at more trials a round took them from
−0.066/+0.106/−0.063/−0.068 to −0.016/+0.016/−0.037/−0.031, every one
inside the gate. Sweeping trials per round against true post-fit bias found
one plateau from 16,000 up and 8,000 as the only row off it — and only on
the thin lineup, which is exactly the shape that was failing. `FIT_TRIALS`
doubles to 16,000, which buys the whole available improvement.

**And a bug in the inversion, found by arithmetic rather than by a run.**
`rates_from_means` called a triple consistent up to three bases per non-HR
hit, which is true of baseball and false of this table: a single is one
base and a double is two, so an order of nothing but doubles reaches 2.0,
and only triples pass it — but triples are a league constant here because
they are too rare to infer per hitter. With doubles capped at every
remaining non-HR hit the solve tops out at `2 + TRIPLE_SHARE` = 2.022.
Everything between that and 3.0 was admitted as valid baseball and then
under-delivered silently: 19% light on total bases at 2.5 bases per hit,
30% at 2.9. Those triples are now flagged like every other impossible one
and routed at the projection engine.

Stated precisely, because it would be easy to oversell: this changes
nothing on the live path today. `reconcile_triple` already caps total bases
at 1.9 per non-HR hit, comfortably under 2.022, so every triple arriving
through pricing was already inside the corrected bound — and the signatures
of the four live failures do not match this one anyway. The gap was for
callers inverting raw projections directly, and it is closed now rather
than left to be rediscovered if that cap ever moves.

### The finding that outlived the gate — thin samples had no floor

Across three live runs the gate kept failing on hitters whose projected
per-game hits, over the plate appearances their batting spot gets, implied
batting averages no hitter can have: Cortes **.014**, Foscue **.030**,
Peters **.060**, Lopez **.053**, Walton **.078**. Those are the numbers the
BOARD prices from, so this outlives the reconciliation entirely.

The cause is that every look-back window in `compute_form` is an average of
the SAME games, so weighting them differently cannot rescue a short log —
and `MLB_WINDOW_WEIGHTS` gives "career" a weight of zero, leaving nothing
underneath. A .250 hitter with three quiet games projected at **.000**.

That zero was correct for what `career_avg` actually was: MLB built it as
the mean of the same fifteen logs the blend was about to weight — an anchor
made out of the thing it was supposed to anchor. So the fix needed a real
number first, and the gameLog response already contained one:
`parse_game_log` was truncating season-to-date at fifteen games, and
parsing the cached response a second time costs no request. `career_avg`
now spans the season and carries `career_games` alongside it.

The blend then shrinks toward it by how thin the window is, `w = n/(n+k)`.
Measured, in implied batting average:

| case | was | now |
|---|---|---|
| hitless 3 games, .250 regular | .000 | .177 |
| the Cortes shape (1-for-4) | .085 | .182 |
| 1-for-6 | .048 | .145 |
| regular, 15 logged, on form | .216 | .234 |
| season no longer than the window | .078 | .078 (stands down) |

`k = 8` is half a form window and is scoped to the defect. The textbook
empirical-Bayes value for batting rates is nearer 40 — within-player
variance over between-player variance — which would leave every MLB hitter
at a quarter his own form and three quarters his season line, replacing the
recency curve §6 specifies on an argument nobody has run against this
book's record. That is a bigger claim than this fix is making, and it is
worth measuring before it moves.

Two things deliberately NOT done: no other sport was re-priced (NFL, CFB,
NBA and WNBA carry the same gap, and that is a separate decision), and
`k` was not fitted against real logs, because the build container's history
DB carries NFL only.

**And a fourth finding the gate produced rather than suffered.** With the
overshoot gone, 26 of 30 live lineups reconcile and the four that do not
share something the sim did not cause: the offending hitter is projected
for a batting average no hitter can have. Carlos Cortes at 0.055 hits a
game over 3.8 plate appearances is **.014**; Justin Foscue is .030; Taylor
Ward is .122. Those are the numbers the BOARD prices from, so this matters
well beyond the reconciliation — and nothing currently excludes them.
`sample_q` in `engine/mlb/betting.py` shades confidence for a thin log
(floor 0.3) but confidence weighting cannot repair a central estimate that
is structurally wrong. Open question for Ethan rather than a unilateral
filter, since it changes what reaches the board.

**`sim_diagnose.py`** exists because this took too many round trips. The
gate needs a live feed, so every "what is wrong with those lineups" cost a
run on Ethan's machine, a paste, a guess here, and a change. Three of those
guesses were confidently wrong — plate appearances, lineup heterogeneity,
more fitting rounds — and a fourth shipped a fix that had to be reverted
for breaking a lineup nobody had checked. The dump already carried every
hitter's projected means and batting spot, which is a complete input to the
whole chain, so a failing lineup can now be rebuilt and re-run anywhere.
It separates the four causes that call for opposite fixes (the sampler, the
fit's own noise, convergence, a real disagreement), reports the
single-rescale signature that distinguishes a fitting problem from a model
one, and flags an impossible projection before it discusses the sim at all.

### BUILT 2026-08-05 — the sim reaches pricing (`engine/mlb/simjoint.py`)

Task #60, opened when the Monte Carlo was built and shut until the gate
passed all thirty live lineups.

**What it replaces.** The Parlay Zone prices a pair through a Gaussian
copula that needs one number per pair. For two bats in one lineup that
number was `MEASURED["lineup_stack"]` — +0.186, honestly fitted on 27,613
games, and *the same for every pair*. The leadoff hitter and the number two
bat back to back, so one reaching is literally what gives the other his
extra turn; leadoff-and-eight share far less. A league average prices both
identically, and the ticket a bettor is offered is one specific pair. The
sim deals both legs out of the same simulated innings, so it observes the
dependence rather than assuming it — the only new information it was ever
built to produce.

**The gate is the whole precondition.** Every lineup is reconciled first,
and one that fails contributes nothing: its pairs keep the prior, silently.
A sim that cannot reproduce the projections it was inverted from has no
standing to describe their joint.

**The translation is solved, not assumed.** The sim reports P(both legs
win); the copula speaks latent correlation. Those are different numbers at
these marginals, so `solve_rho` bisects `joint_two` — quoting phi as rho
would have been a silent error.

**Conservatism is inherited, not re-argued.** `parlays.py` says understating
correlation is the direction to be wrong in. The naive move is to clamp the
sim's number down again — but `ENV_SD` is already 0.25 where 0.30 fits the
measurement better, chosen because 0.25 misses low. Clamping here would pay
the same toll twice.

**What it declines.** Strikeouts, outs and every game line (the sim does not
tally them); UNDER legs (the joint of two complements is not the complement
of the joint); two legs on different teams; any lineup under six projected
hitters; and any solved rho more than 0.35 from the prior — 27,613 games
against one night's model, so a gap that size is a finding to chase rather
than a number to bet. Cost stays proportional: only lineups that two
candidate legs actually share are simulated at all.

### BUILT 2026-08-03 — the blind-spot miner (`engine/losspatterns.py`)

The next rung of the self-tuning ladder. The temperature refit learns one
dial per market; the miner learns WHERE the misses cluster: every graded
bet is sliced by side, price band, stated-probability band, horizon and
book, within each market and pooled per sport. A slice is a finding only
when the model's own stated probabilities missed reality (calibration z,
never raw win rate — win rate would flag every honest longshot bucket)
AND it survives Benjamini–Hochberg false-discovery control over every
slice tested. Surviving slices that ran ≥5 points hot close themselves,
and `veto()` blocks new picks landing in them at the same gate where
`is_reliable()` sits — pooled sport-level slices may point ("watch") but
never convict, because one bad pocket drags a clean aggregate under. The
banding is one definition shared by miner and veto, so enforcement can
never drift from evidence. Re-mined on every settle pass; rendered on the
Record page under "Learning from losses" with the empty state stating the
discipline out loud.

Enforcement wiring today: every sport's engine (`engine/betting.py`,
`engine/mlb/betting.py`, `engine/cfb/pipeline.py`, `engine/nba/pipeline.py`
all call `lp_veto` — see "the ladder extended to every sport" below).
Mining the quarter-million-prop backtest DB rather than just the live
journal is the one remaining named next step.

### BUILT 2026-08-03 — the recency dial (`engine/formfit.py`)

Rung two: the model's own recipe learns, not just its confidence. The
projection's window weights (how much a player's number leans on his last
week vs his long run) came from the spec; now `formfit.py` fits one dial
per market by walk-forward Brier on raw probabilities — 0 is exactly the
spec curve, ±1 the hot/steady anchors, every stop a normalized blend. One
parameter rather than seven free weights, because seven knobs on one
season of data is an overfitting machine. A move is ADOPTED only when it
beats the spec curve by ≥0.0005 Brier on ≥200 walk-forward samples; ties
break toward the spec; a dial at the grid edge is flagged the way a
boundary temperature is. The fitter passes every candidate curve
explicitly so it can never read the store it is refitting, and the CLI
orders the loop correctly: weights first, then `calibrate.py`, because
the temperature is a correction for the model that will actually run.
Home runs are excluded — the rare-event path already replaced form
blending there. Rendered under "The recipe itself, refit" on the Record
page, including "default kept" rows: a dial the record examined and left
alone is a result.

### BUILT 2026-08-03 — player memory (`engine/playerfit.py`)

Rung three: learn WHO the blend misreads. Per player and market, one
multiplicative correction on the projected mean — the accumulated ratio
of what he produced to what the model projected, shrunk toward 1.0 by
evidence (40 games of prior strength) and clamped to ±15%, with the
clamp re-enforced at read so a hand-edited store cannot be obeyed. The
mechanism must earn adoption per market: applying corrections CAUSALLY
(each game's correction computed strictly from that player's earlier
games — out-of-sample at every row) must beat the uncorrected model's
walk-forward Brier by the standard margin on the standard sample.
"Memory off" ships on the page as a result. The ledger accumulates the
RAW blend's projections — the correction divided back out — or the
memory would learn to correct itself and spiral. Home runs excluded:
the rare-event empirical-Bayes rate already is a per-player learner.

Run order across the ladder's fitters, each shaping the model the next
one measures: `formfit.py` → `playerfit.py` → `calibrate.py`.

### BUILT 2026-08-03 — the ladder extended to every sport

The four rungs stopped being an MLB feature. What changed, per seam:

* **The generic engine** (NFL, and any log sport that adopts it) threads
  ``sport`` through every store lookup. Two latent defects died in the
  process: `evaluate_prop` hardcoded `correction_for("nfl", …)` — harmless
  only while nothing else priced through it and nothing else had a fit —
  and it consulted no `is_reliable` gate at all. It now carries all four
  verdicts, in parity with the MLB gate.
* **The hoops gate** (`engine/nba/pipeline.py`, NBA + WNBA via
  ``tune.key``) applies the temperature before the side is chosen, closes
  boundary-fit markets, vetoes closed slices, and multiplies player
  memory into ``rate × minutes``. **The college gate** does the same for
  its plays. League keys never cross: a WNBA fit cannot touch the NBA.
* **One harness door** — `engine/logwalk.py` walks any generic-engine
  sport forward; `logwalk.walk` picks MLB's own harness for MLB. The
  three deep-fitter CLIs take `--sport` (NFL fits today; its history is
  already in the DB).
* **The journal fitter** (`engine/journalfit.py`) covers sports with no
  deep harness (NBA, WNBA, CFB, UFC): temperatures from journaled claims
  and player memory from journaled (projection, actual), both floor-gated
  at 200 settled bets per market, both run on every settle pass, both
  merge-safe. Temperatures fit ONLY keys with no stored correction —
  post-correction claims would compound — so refits belong to the deep
  fitters or a future since-timestamp composition, and that boundary is
  deliberate.
* **Store hygiene**: all three saves merge instead of replacing (one
  sport's run used to erase every other sport's keys), and
  `correction_for`/`is_reliable` resolve DEFAULT_PATH at call time (the
  frozen-default trap's sixth appearance).

The recency dial fits where a window blend exists (MLB, NFL). The hoops
and college models have no window blend to dial — their models are
minutes×rate and ratings — so rung two is structurally N/A there, stated
rather than faked.

### WON'T — a language model anywhere in the pricing path

Not a capability judgement, a structural one. We just finished publishing a
reliability diagram, Brier, log loss and ECE against the de-vigged close. All
of that rests on the model being **reproducible and temperature-scalable**: we
can re-run a sweep over 295,627 props, fit one parameter, and show the curve
move. A language model in the pricing path cannot be temperature-scaled, does
not reproduce run to run, and cannot be swept historically — so it would take
the one pillar competitors structurally cannot copy and hand it back.

Where it fits instead is explanation, never a number: turning a pick's
existing reason codes into prose. That path cannot move a probability, which
is exactly why it is safe.

**Amended 2026-08-03 — a second sanctioned lane: proposing.** The
hypothesis lab (`engine/hypotheses.py`) lets a language model read the
record's own summary and propose slice INTERSECTIONS worth testing — the
combinations the miner's single-dimension sweep is provably blind to.
Authority never moves: proposals are constrained to the miner's own menu
of dimensions, convicted or acquitted by the same calibration z +
Benjamini–Hochberg tribunal, re-earned every settle pass against the
growing journal (the model saw the data before proposing, so first
confirmations are provisional by construction), and enforced only
through `losspatterns.veto` — the gate every sport's engine already
consults. A confirmed hypothesis acts by becoming ordinary, tested
arithmetic. The API call is one structured-output request to
claude-opus-5 (raw HTTP, stdlib, per project doctrine), key in
gitignored secrets.local; the nightly retest is free. Originally
CLI-invoked only; since 2026-08-04 the propose step also runs itself
weekly from the settle pass (`prose.weekly_lab`) under the same
monthly spend cap as the prose lanes — a recurring manual step is an
operational bug here, and the cap is what made retiring it safe. The
WON'T itself is unchanged: nothing an LLM writes can set a
probability.

**Amended 2026-08-04 — the third and final sanctioned lane: narrating.**
The prose lanes (`engine/prose.py`) are the "explanation, never a
number" path above, built: a nightly postmortem of the graded card and
a weekly brief on what the learning ladder did, each one structured
call writing prose from the arithmetic's own numbers — plus a
CLI-only triage bench that drafts specs for turning the lab's
watchlist ideas into future miner dimensions. Coverage is structural
across every tracked sport (mlb, nfl, cfb, nba, wnba, ufc): the packs
enumerate the sports and validation back-fills any note the model
skipped from the pack's own numbers. Spend is bounded by arithmetic,
not discipline — the automatic lanes stand down for the month once the
ledger (data/llm_spend.json) passes QELLYS_LLM_CAP_USD (default
$5.00), and the export path can only read stores, never call. Three
lanes — propose, narrate, and nothing else — and the WON'T still
stands whole: no LLM output is ever a probability, a stake, or a
gate.

## What to distrust in the study

The study flags its own weak sources and those flags are worth keeping in
front of us, because the numbers most likely to drive a build decision are
the ones with the thinnest provenance:

* Referee effect sizes ("15–20% of penalty yards", "8–12 free throws") come
  from tool-vendor blogs. Item 6 above is the single most expensive thing on
  the list to build and its justification is the least verified. Measure the
  effect on our own data before building the feature, not after.
* Responsible-gambling retention and trust percentages are operator-side
  vendor claims.
* Churn and CAC figures are operator-side and not analytics-tool-specific.
* The "limits sharp bettors 300 wagers earlier" claim is from a marketing
  site.
* Claw Arbs' account-longevity feature is documented only by its own
  marketing.
* The regulatory picture is unsettled — the Kalshi preemption question is at
  the preliminary-injunction stage with a possible circuit split, which is
  precisely the risk sitting under item 5.

---
---

# Source study, preserved unedited

*Received 2026-08-02.*

# Competitive Landscape & Differentiating Feature Opportunities for Qellys Book (EDGEKEEPER)

## TL;DR
- The betting-analytics market is saturated with tools that all sell the same three commodities — +EV feeds, arbitrage scanners, and prop research — but almost none of them defend the one thing every winning bettor eventually loses: their sportsbook accounts. Qellys Book's "Account Longevity" pillar addresses a documented, unsolved pain point that only one obscure competitor (Claw Arbs) even attempts, and none does with published rigor.
- The three highest-value, uniquely-defensible opportunities are: (1) an automated **Account Longevity scoring + protection engine** built on the CLV/stake/timing signals the product already tracks; (2) a genuine **exchange-native pricing and edge layer** for Kalshi/Novig/ProphetX/Polymarket at exactly the moment CFTC-regulated prediction markets are displacing state sportsbooks; and (3) **auditable radical transparency** (permanent calibration, Brier, reliability diagrams, process metric) that competitors structurally cannot copy because they sell picks.
- Biggest constraints to respect: odds scraping is under active litigation (Swish v. OddsJam), credential-sharing (SharpSports model) violates most sportsbook ToS and creates security exposure, automated bet placement is banned by ToS and some state codes, and affiliate-conflict disclosure is an FTC exposure — so the product should lean into being a non-transacting analytics layer and avoid automated placement.

## Key Findings

### The market is crowded and undifferentiated at the core
Every serious competitor now ships the same "five modules" Qellys Book already has (arbitrage, +EV, sharp money, middles, low holds). OddsJam, Unabated, Outlier, RebelBetting, Betstamp, and a swarm of app-store clones (BetterSlip, Oddschecker+, Keen Betting, Juice) all converge on +EV + line shopping + a bet slip deep-link. Pricing has bifurcated into a ~$20/month prop-research tier (Props.Cash, Outlier Premium, Rithmm Core) and a ~$100–200/month sharp tier (Unabated Premium, OddsJam Gold), with a $400+ global/whale tier at the top (OddsJam Platinum/Global). The core pricing engine is now table stakes; differentiation has to come from somewhere other than "we also find +EV."

### The single biggest unmet need is account survival, not edge discovery
This is the strategic wedge. Multiple independent and even sportsbook-sourced statements confirm limiting is pervasive and detection is sophisticated, yet essentially no analytics tool helps the user manage it as a first-class feature.

### Exchanges/prediction markets are the fastest-moving structural shift
The CFTC-regulated prediction-market lane is rapidly displacing the state-licensed exchange model, and tooling has not caught up — creating a genuine first-mover gap.

### Radical transparency is a real, defensible moat because competitors can't do it
Nearly every competitor sells picks or a subscription premised on winning, which structurally disincentivizes publishing honest, permanent calibration.

---

## Details

### 1. Competitive Feature Audit (with pricing, headline feature, gaps)

**OddsJam** — Headline: broadest +EV/arbitrage across 100+ books, polished mobile app, "follow the money" sharp tracking, PrizePicks fantasy optimizer. Pricing: Gold ~$199/mo (40+ US books), Global ~$399/mo, some sources cite $79/mo entry historically. Owned by Odds Holdings, acquired by Gambling.com Group for up to $160M — an initial $80M ($70M cash + $10M in GAMB ordinary shares) plus up to $80M earnout tied to Odds Holdings' performance through 2026; the deal closed Jan 1, 2025, with Odds Holdings projected at ~$26M 2024 revenue and ~$12M adjusted EBITDA (per SBC Americas / Gambling.com Group). Gaps/complaints: very expensive; users report being flagged/removed from arbitrage access after starting; Trustpilot ~3.2 with complaints that "guaranteed" picks lose; no account-longevity protection; picks-quality skepticism.

**Unabated** — Headline: proprietary "Unabated Line" (vig-free fair odds blended per-sport), prop simulator, season simulators, alt-line calculators, private Discord with pros (Captain Jack Andrews). Pricing: ~$49/mo annual entry to ~$132–199/mo Premium. Gaps: steeper learning curve; historically weaker automated alerts vs OddsJam; niche/pro audience.

**Outlier.bet** — Headline: prop research + "traffic light" system, game lines, one-click deep-link bet slip into FanDuel/DK/Caesars/BetMGM/Hard Rock AND exchanges Novig/ProphetX. Pricing: Premium $19.99/mo; Pro (~$99/mo) unlocks +EV feed, arbitrage, sharp book odds. Gaps: prop visualizations less deep than Props.Cash; the differentiating tools are paywalled to Pro.

**Props.Cash** — Headline: deepest prop research (L5/L10/L20, custom rolling windows, DVP grades, "hit rate to odds," home/away, quarter splits, eSports). Pricing: $19.99/mo. Gaps: no +EV, no arbitrage, purely research; no click-to-book; closing line disappears.

**Pikkit** — Headline: automatic bet tracking across books + social feed, bankroll health dashboard (rolling 30/60/90-day ROI), promo/free-bet tracker, SGP line-shopping. Pricing: free + Pro. Gaps: sync glitches (esp. MFA books), missing books (Circa), confusing layout, referral-payout complaints; social features can encourage FOMO/impulse betting; linking makes books aware of usage.

**Betstamp** — Headline: free all-in-one — EV screen, odds comparison, prop research, line-movement tracking, bet tracking, accounting, community picks. Pricing: free + Pro. Gaps: analytics shallower than dedicated tools; jack-of-all-trades.

**Juice Reel** — Headline: auto-sync 300+ books (incl. Kalshi, Novig, ProphetX, offshore), CLV analytics, verified handicapper marketplace ("see the receipts"), copy/follow. Pricing: free + IAP. Gaps: picks-marketplace model; CLV-centric but limited proprietary modeling.

**Rithmm** — Headline: no-code custom AI model builder, backtesting, "Smart Signals," parlay builder, betslip export. Pricing: Core $239.99/yr ($19.99/mo), Premium $999.99/yr ($83.33/mo); Apple listing $29.99/$99.99/mo. Gaps: narrower sport list; evidence layer easier to inspect in-app than publicly; expensive Premium.

**Action Network** — Headline: bet tracking + news/content + sharp "Pro Report," public betting %, umpire/referee assignment pages. Pricing: freemium + Pro subscription. Gaps: content-heavy, media-first; analytics not as sharp as dedicated +EV tools.

**RebelBetting** — Headline: 15+ yr arbitrage/value scanner, ~100 books, profit guarantee (free month if no profit). Pricing: €89–169/mo. Gaps: Euro-book focused (only ~13 US/CA books), prematch focus.

**BetQL** — Headline: AI model picks, player props, line-move alerts, public betting data. Gaps: pick-centric.

The trackers (Pikkit/Betstamp/Juice Reel) collectively expose a shared weakness: closing line value data disappears once games start, and syncing breaks on MFA-protected books.

**Newer entrants / adjacents (2025–2026):** BetterSlip (140+ books, +EV/arb/middles/low-holds + DFS + AI parlays), Oddschecker+ (AI EV, 100M+ weekly projections), Keen Betting, Juice (screenshot→AI EV analysis, Kelly sizing), Bet Hero (Barcelona-built +EV, 400+ books), PropsBot, PlayerProps.ai, Alphascope (Polymarket/Kalshi + news AI forecasts), plus prediction-market whale trackers (Polywhaler, PolyTrack, Polymarket-Insiders, Apify actors).

### Competitive feature matrix (condensed)

| Tool | +EV/Arb | Prop research | Bet tracking/CLV | Exchange-native | Account longevity | Public model calibration | Price/mo |
|---|---|---|---|---|---|---|---|
| OddsJam | ✔ deep | ✔ | ✔ | partial | ✗ | ✗ | $199–399 |
| Unabated | ✔ | ✔ sim | partial | partial | ✗ | ✗ | $49–199 |
| Outlier | ✔ (Pro) | ✔ | ✔ | ✔ deep-link | ✗ | ✗ | $20–99 |
| Props.Cash | ✗ | ✔ deepest | ✗ | ✗ | ✗ | ✗ | $20 |
| Pikkit | ✗ | partial | ✔ auto | ✗ | ✗ (health only) | ✗ | free+ |
| Betstamp | ✔ | ✔ | ✔ | ✗ | ✗ | ✗ | free+ |
| Juice Reel | ✗ | partial | ✔ auto | tracks exch. | ✗ | ✗ | free+ |
| Rithmm | signals | ✔ | ✔ | ✗ | ✗ | ✗ | $20–100 |
| Claw Arbs | ✔ arb | ✗ | ✗ | excludes sharp | ✔ (only one) | ✗ | n/a |
| **Qellys Book** | ✔ | ✔ | ✔ (planned) | ✔ pillar | ✔ pillar | ✔ pillar | TBD |

The matrix shows the whitespace clearly: the three right-most columns — exchange-native, account longevity, and public calibration — are almost entirely empty across the incumbent field, and those are exactly Qellys Book's three positioning pillars.

### 2. Documented User Pain Points (with sources)

- **Trackers drop closing line value at game start.** A Pikkit app review states plainly: "once the game begins, the closing line disappears. This makes it impossible to evaluate whether a bet had positive expected value (EV), since you can't compare your line to the final market consensus." This is a concrete, automatable gap.
- **Syncing breaks on MFA/2FA books and misses books.** Pikkit users report sync glitches, missing books (Circa), and that linking exposes their usage to sportsbooks.
- **"Guaranteed"/AI picks lose and erode trust.** OddsJam Trustpilot complaints ("Garbage every bet they said will hit… all red") and picks skepticism across Rithmm/Juice Reel reviews.
- **Price fatigue.** OddsJam Gold at ~$2,400/yr "before you have placed a single bet" is repeatedly cited as a churn driver.
- **Getting limited is the terminal pain.** XCLSV notes sportsbooks now "profil[e] sharp bettors with AI and limiting them up to 300 wagers earlier than legacy models." Users get limited precisely because the tools that make them +EV also make them detectable.
- **Manual spreadsheet work advanced bettors still do:** correlated-exposure caps across same-game bets, per-game/per-player/per-day bankroll caps, Kelly fractionalization across simultaneous +EV bets, mixing in -CLV "mug" bets to disguise profile, tax reporting, and tracking which promos/free bets expire when. Kelly guides explicitly say traditional Kelly "does not account for correlated bets" and bettors must hand-build exposure caps in Excel.

### 3. Account Limiting — current state (2025–2026)

This is the best-documented and most strategically important finding.

- **Scale (from the books themselves):** At the September 11, 2024 Massachusetts Gaming Commission roundtable, BetMGM's Sarah Brennan said "BetMGM limits approximately 1% of Massachusetts patrons presently" (verbatim confirmed by ESPN), and FanDuel's Cory Fox added that in 2023 only 0.043% of FanDuel's Massachusetts wagers were placed at the player's maximum allowed amount. A separate MGC-commissioned study found that 0.64% of the state's ~2.1 million online wagering accounts (≈13,400 accounts) were limited by operators — and the MGC subsequently moved to approve first-in-the-nation rules on player limits (per Bookies.com). Books frame limiting as "stake factoring" applied only to advantage players.
- **Detection signals (documented):** Closing Line Value is the primary trigger — "consistently beating the final odds before an event starts." Beyond CLV: IP/MAC tracking to link accounts, cookie/browser fingerprinting, bet-timing after line moves, non-round stake sizes ($36.43 flags you), concentration in low-liquidity/niche markets and props, bonus abuse, and fast withdrawals.
- **Liquidity determines speed:** books tolerate sharp action on deep NFL/NBA spreads but limit instantly on college props/niche markets. Limits often start market-specific (props/futures) before spreading; books also share information, so limits propagate across operators.
- **Regulatory attention exists but no protection mandate:** Massachusetts is actively examining and now regulating the practice; Australia has minimum-bet laws. But no US regulation forces books to stop, so the bettor bears the risk.
- **Almost no product addresses it.** The only named product that productizes anti-limiting is **Claw Arbs' "Account Longevity"** feature, which automates six knobs (stake jitter %, round mode, inter-leg delay, minimum spacing, max trades/hour, edge floor) and explicitly excludes sharp venues (Kalshi, Polymarket, Pinnacle). Everything else is advice content published as marketing by +EV tools (Bet Hero, Outlier, XCLSV). Importantly, Claw Arbs itself draws a hard line: its feature "does not fake your IP, spoof your device, or pretend to be a different person. Those are KYC violations." Anti-detect browsers (Multilogin, GoLogin, AdsPower) are repurposed by some bettors but cross into KYC-violation territory.

**Implication:** Qellys Book's Account Longevity pillar is not a slogan — it is a real, under-served category with exactly one weak incumbent and a clear ethical boundary (behavioral coaching = fine; device/identity spoofing = off-limits). The product already tracks the exact signals (CLV percentile, time-to-bet after line move, stake rounding profile, market concentration, product mix, promo behavior, deposit/withdrawal ratio) the books use. That is a defensible, unique asset.

### 4. Exchanges & Prediction Markets (regulatory + tooling)

**Regulatory state (materially affects what's buildable):**
- On April 6, 2026, the Third Circuit (2-1, KalshiEX v. Flaherty) became the first federal appellate court to hold that the CEA likely preempts state gambling laws for sports-related event contracts on CFTC-regulated DCMs. It is a preliminary-injunction ruling (reasonable likelihood of success, not a merits decision); CFTC event-contract rulemaking comments were due April 30, 2026, and a Ninth Circuit argument was set for April 16, 2026 — a possible circuit split.
- State enforcement continues in parallel: Nevada issued a 14-day TRO against Kalshi (March 20, 2026); Massachusetts (Suffolk Superior Court, Jan 2026) enjoined Kalshi sports contracts before it was stayed; the CFTC sued Arizona, Connecticut, and Illinois (April 2, 2026) asserting exclusive jurisdiction.
- **Kalshi** operates in all 50 states under CFTC; **Polymarket** re-entered the US in 2025 via its QCEX acquisition (USDC deposits).
- **Novig** got CFTC DCM approval (~June 16, 2026, fastest in CFTC history per the company), pivoting from a NJ/CO licensed exchange → sweepstakes (42 states) → 50-state prediction market. It raised a $75M Series B (Feb 2026) led by Pantera Capital, with Forerunner Ventures, NFX, Multicoin Capital and Makers Fund; per CNBC (June 16, 2026), Forbes reported the round valued Novig at $500M and brought total raised to over $105M, with Novig citing over $5B cumulative / over $8B annualized volume.
- **ProphetX** received DCM + DCO designation five days before Novig, positioning as "the first sports-native direct-clearing prediction market."
- **Sporttrade EXITED sports betting entirely** — a major change. It wound down its state-licensed exchange (NJ went dark May 25, 2026; AZ/CO/IA/VA ~June 25–26, 2026) to rebuild as a CFTC prediction market (approval still pending). Its own site: "Sporttrade has exited its online sports betting markets."
- **Rebet** is a sweepstakes/social sportsbook (dual-currency: Rebet Coins + Rebet Cash), ~44 states, banned in New York since April 2025 amid a broader sweepstakes crackdown; DraftKings ("DraftKings Predictions," Dec 2025) and FanDuel (with CME Group) are entering the CFTC lane.

**Tooling gap:** For prediction markets, existing tools are almost all Polymarket whale/wallet trackers (Polywhaler, PolyTrack, Polymarket-Insiders, Apify actors, Alphascope) offering insider scoring, wallet P&L, and copy-trading feeds. There is essentially **no tool that treats Kalshi/Novig/ProphetX order books as first-class pricing sources for cross-market +EV/arbitrage against traditional books, or that fair-prices sports event contracts.** This is Qellys Book's Exchange-Native pillar — and it lands exactly as the exchanges become the only "no-limit" venues left. The product's existing Polymarket informed-flow module (large trades, wallet flagging, paper-tracking whether following the money wins) is directly aligned but should be extended to Kalshi and framed as edge validation, not copy-trading.

### 5. Data & Visualization Differentiators (underused sources)

- **Referee/umpire assignment data is the clearest underexploited edge.** Industry commentary claims NFL games show a "15-20% difference in penalty yards depending on the officiating crew" while "fewer than 5% of bettors factor referee tendencies," and that NBA high-foul refs inflate free-throw attempts by 8–12/game and wide-zone MLB umpires suppress strikeouts/runs. Assignment data exists (RefMetrics, Action Network umpire pages, VSiN, Sharp Football) but is rarely wired into prop pricing. Statcast enables per-umpire strike-zone modeling (documented in umpire-bias research). This maps directly onto Qellys Book's prop cards and per-league engines (MLB umpires → strikeout/total props; NFL crews → totals/penalty props; NBA refs → FT-driven props).
- **Weather/venue is already a strength to deepen.** Qellys Book's stadium/park visualizations (wind compass, temp, dome status, park factors) are genuinely rare; almost no competitor visualizes live venue conditions tied to live game state. This should be pushed into explicit prop/total adjustments with published effect sizes.
- **Open-source ecosystems (nflverse, Statcast, and similar) are newly rich and underused** for transparent, reproducible modeling — which pairs naturally with the transparency pillar.
- **Travel/rest, altitude, injury-report latency, and referee crew tendencies** remain mostly manual/anecdotal in consumer tools.

### 6. Model Transparency & Calibration (how to make it defensible)

Best practice from forecasting platforms:
- **Metaculus** publishes Brier scores and, per its FAQ, states: "For questions that resolved in 2021, the Metaculus Prediction has a Brier score of 0.107... slightly lower than the Community Prediction's Brier score of 0.108." It uses strictly proper scoring rules (Brier + log/logarithmic score), Expected Calibration Error, and reliability/calibration diagrams, and distinguishes calibration from resolution/refinement. Superforecaster Brier benchmarks (~0.15–0.25) provide external reference points.
- **Key lessons for a betting tool:** (1) publish **calibration/reliability diagrams** (predicted vs realized frequency), not just win rate; (2) use **proper scoring rules** (Brier and log loss) so the score can't be gamed; (3) note that **calibration alone isn't enough** — a model that says 50% on everything is well-calibrated but useless (resolution/refinement matters), which is why Qellys Book's "process" metric (separating lucky wins from good-bet losses, i.e., CLV-based process vs results) is exactly right; (4) make records **permanent and time-stamped**, ideally with pre-registration so past forecasts can't be quietly deleted; (5) show performance **by time-horizon and by market** (calibration degrades on longer horizons and thin markets).

To make "radical transparency" defensible rather than a slogan, Qellys Book should: publish a live reliability diagram per league; show Brier and log loss with confidence intervals and sample sizes; keep an immutable, publicly hashed forecast log; display the probation→promotion bar as a calibration threshold; and report CLV distribution as the leading indicator (since CLV, not short-run ROI, is the honest proxy for edge). Competitors that sell picks cannot do this without exposing that most picks don't beat the closing line.

### 7. Bankroll, Portfolio & Risk Tooling (quant-finance gaps)

- What exists: Kelly calculators everywhere (including multi-bet/parlay Kelly, ruin probability, Monte Carlo bankroll simulators), Pikkit's rolling ROI dashboard, exposure-cap advice.
- What's missing (and obviously portable from quant finance): **portfolio-level correlated-exposure management.** Kelly guides admit the formula "does not account for correlated bets"; bettors hand-build per-game (3–5%), per-player (2%), and per-day (10–15%) caps in spreadsheets. No consumer tool computes a **covariance/correlation matrix across simultaneous positions** (same-game props, SGP legs, shared-thesis bets) and solves for a portfolio-optimal, drawdown-constrained stake vector.
- Also missing/underdone: **drawdown-aware fractional Kelly** (full Kelly has a ~50% chance of a 50% drawdown), **risk-of-ruin dashboards tied to real bankroll**, **tax-lot/tax reporting**, and **shrinkage of edge estimates** (small edge overestimates → large overbet). Qellys Book's newly specified parlay module with correlation math and clash detection is the right foundation; extend it into a full portfolio risk layer.

### 8. Responsible Gambling as a Feature

- Regulatory direction: RG is shifting "from a customer service requirement to a data-compliance obligation," with pan-European "markers of harm," affordability checks, deposit limits, reality checks, and behavioral monitoring becoming standard. Reality checks are moving from optional to mandatory in several markets.
- Commercial evidence (from operator-side vendors, treat as directional): claims that RG tools correlate with higher trust and retention (e.g., vendor-cited figures around ~20% higher trust and materially higher retention, and ~78% of European players preferring visible RG features). These are vendor claims, not independent studies, so present cautiously.
- Opportunity: because Qellys Book is an analytics tool that takes no money, RG can be a genuine, non-conflicted product feature (the "we keep you betting" thesis literally aligns with sustainable, non-harmful play) rather than a footer disclaimer. Reality-check nudges, loss-chasing detection from tracked behavior, and a "process over results" framing are natural. No evidence surfaced that RG-as-feature hurt an analytics tool commercially; the risk is purely that heavy-handed nudges annoy sharps.

### 9. Business Model & Retention

- Monetization across the category is subscription (tiered $20 research / $100–200 sharp / $400 whale) plus, for some (Juice Reel, Pikkit, Betstamp), a free tier + picks-marketplace/affiliate revenue.
- Retention/churn: sports-betting audiences churn hard. Operator-side data (directional, not analytics-tool-specific) shows only ~4% of bettors stay loyal to one platform >1 year, ~40% go dormant after their first bet, and CAC is high ($250–800+). For tools specifically, the cited churn drivers are price fatigue, losing picks, and getting limited (which ends the use case entirely).
- Retention lever unique to Qellys Book: **if the product literally extends the user's betting life (account longevity), it directly attacks the biggest churn cause** — the user getting limited and quitting. That is a retention story no pick-seller can tell. Transparency (honest record) also builds the trust that pick-sellers erode.

### 10. Legally / Practically Constrained (attractive but risky)

- **Scraping odds is under active litigation.** Swish Analytics sued OddsJam/OpticOdds (complaint surfaced Dec 28, 2024 via gaming attorney Daniel Wallach, San Francisco Superior Court) for scraping proprietary odds off licensees "including FanDuel, bet365, and others," ~$100M+ claimed; the case survived a motion to dismiss on all five claims. Swish's position: scraping is "a violation of the terms of service of these sportsbooks." Gambling.com Group responded the claims are "entirely without merit... we intend to vigorously defend" (SBC Americas, Jan 2, 2025). Building on scraped odds carries real civil risk; prefer licensed feeds or exchange APIs (Kalshi/Polymarket public APIs are cleaner).
- **Official-league-data mandates are in flux.** Per the NFL/Genius Sports press release, "Genius Sports powers over 98% of the legalized U.S. sports betting market with official NFL data," and it is the NFL's exclusive distributor of official play-by-play and Next Gen Stats data through the end of the 2027-28 season; states (TN first in 2019, then IL/MI/VA) mandated official data — but Tennessee REPEALED its mandate effective July 1, 2025. Data licensing is expensive and politically contested.
- **Automated bet placement is prohibited** by most sportsbook ToS and is written into some state codes (e.g., Michigan Admin Code R. 432.752 bans "bot" play). Do not build auto-placement; deep-links (like Outlier) are the safe ceiling.
- **Credential-sharing (SharpSports model) is risky.** SharpSports' ToS has users hand over usernames, passwords, security Q&A, and one-time passwords, granting authority to "act on your behalf." This typically violates sportsbook account-sharing ToS, defeats 2FA, and its Chrome extension is rated "High" risk impact. If Qellys Book offers bet sync, disclose the risk, prefer official/OAuth-style links where available, and treat credential storage as a serious security liability.
- **Affiliate-conflict disclosure is an FTC exposure.** The FTC Endorsement Guides require "clear and conspicuous" material-connection disclosure near the endorsement. A tool claiming objectivity while earning referral revenue must disclose prominently; the 2024 Consumer Reviews rule adds civil penalties for fake/manipulated reviews. This directly conflicts with the "radical transparency" brand if referral revenue is hidden — so make any book referral relationships explicit.
- **Sharing/publishing users' book account data** raises privacy (CCPA/GDPR) obligations; the informed-flow/whale modules should use public on-chain/exchange data (as they do) and avoid exposing identifiable user betting data.

## Recommendations

**Stage 1 — Ship the wedge nobody else has (0–3 months).** Build the **Account Longevity Score** as the flagship, using signals already tracked (CLV percentile, time-to-bet after line move, stake-rounding profile, market concentration, product mix, promo behavior, deposit/withdrawal ratio). Output a per-book 0–100 "limit risk" score with specific, ethical, behavioral recommendations (round stakes, vary timing, diversify markets, add recreational-looking bets) — explicitly excluding any IP/device/identity spoofing. This is the "we keep you betting" thesis made concrete, it's defensible (only Claw Arbs attempts it, without transparency), and it directly attacks the #1 churn cause. Benchmark to change course: if <15% of active users engage the score weekly, the framing is wrong — simplify to a single "you're betting too sharp on Book X" alert.

**Stage 2 — Own the exchange-native + transparency moats (3–9 months).** (a) Extend the pricing engine to treat Kalshi/Novig/ProphetX order books as first-class fair-value sources and surface cross-market edges vs traditional books; extend the Polymarket informed-flow module to Kalshi. This lands as exchanges become the only no-limit venues. (b) Publish a **live reliability diagram + Brier + log loss per league**, with sample sizes, an immutable timestamped forecast log, and the probation→promotion bar shown as a calibration threshold. Benchmark: if published calibration shows systematic miscalibration (reliability curve far off diagonal) in any staked league, move it back to probation automatically — and say so publicly.

**Stage 3 — Portfolio risk + responsible-gambling layer (9–18 months).** Build the correlated-exposure portfolio engine (covariance across simultaneous positions, drawdown-constrained fractional Kelly, per-game/player/day caps auto-enforced) on top of the parlay correlation module. Add reality-check/loss-chasing nudges as a genuine feature. Benchmark: tie RG nudges to tracked behavior, not calendar time, and A/B test that they don't materially raise churn among sharps before making them default-on.

**Cross-cutting guardrails:** Do not build auto-placement. Prefer exchange public APIs and licensed feeds over scraped odds given Swish v. OddsJam. If offering bet sync, disclose credential-sharing risk and prefer safer linking. Disclose any book referral relationships prominently to protect the transparency brand and FTC posture.

## Caveats

- **Numbers hedged or vendor-sourced:** referee/penalty effect sizes ("15–20%," "8–12 free throws"), RG retention/trust percentages, and churn/CAC figures come from tool-vendor blogs, operator-side vendors, or advocacy content, not peer-reviewed or independent studies — directional, not authoritative. The "300 wagers earlier" AI-limiting claim is from a tool marketing site.
- **Claw Arbs "Account Longevity"** is documented only via the vendor's own marketing; its claim to be the only/best such tool is self-serving, though the underlying tactics are corroborated broadly.
- **The affiliate "$100k+ FTC fines against betting affiliates" claim** (encountered in research) came from an affiliate-marketing vendor blog and is uncorroborated by a primary FTC source — treat as unverified.
- **Regulatory situation is fast-moving and unsettled:** the Kalshi preemption question is at the preliminary-injunction stage with a possible circuit split; outcomes could materially change what exchange-native tooling is legal state-by-state. Sporttrade's exit and Novig/ProphetX's approvals are very recent and could shift again.
- **Pricing figures vary by source and state** (e.g., OddsJam quoted at $79–$399 across sources; Rithmm at $19.99–$99.99 depending on billing channel) — treat checkout as authoritative.
- Where a competitor "gap" is inferred from reviews rather than the vendor's own docs, it may already be partially addressed in a newer release.
