# NFL Week 1 readiness audit — 2026-09-02

Branch: `qa/nfl-readiness`. Brief: `NFL_READINESS_PROMPT.pdf` (Ethan). The
question: can this system produce a Week 1 card that is correct, complete,
and has a demonstrated edge? "Ready" is only claimed where a number says
so; everywhere else this log says **unverified** in those words.

Sandbox note: this audit ran in a container whose egress proxy blocks
ESPN, the MLB Stats API and Polymarket, has no `ODDS_API_KEY`, and has a
copy of `data/history.db` (216 MB: NFL logs 2021–2025, the 2026 schedule)
but an empty `odds_history` and a stale local ledger. Everything that
needs live odds or the droplet's harvested closes is marked as such.

## Phase 0 — Inventory

### The NFL system, file by file
| role | file(s) |
|---|---|
| instruction set | `docs/NFL_MODEL.md` (800 lines; §1–14 + Implementation Map + two appendices), `docs/PARLAY_MODEL.md` (520) |
| pipeline | `nfl_build.py` → `engine/pipeline.py` (`build_slate`, `run_pipeline`), driven by `launch.refresh_nfl` every cycle |
| schedule / weekly stats / rosters / snaps / pbp | `engine/sources/nflverse.py` (GitHub release CSVs: schedules, weekly player stats, rosters, snap counts), `engine/sources/nflpbp.py` (play-by-play → rz_car / rz_tgt / i5_car / xfp), `engine/sources/nflpart.py` (participation) |
| depth charts | `engine/sources/depthcharts.py` |
| injuries | `engine/sources/injuries.py` (nflverse practice reports → own-player hold + knock-on), `engine/sources/espninjuries.py` (ESPN current-status board, 10-min TTL), `engine/injuries.py`, `engine/injurymerge.py` |
| odds | `engine/sources/oddsapi.py` (The Odds API; `--odds` paid pull, `--cached-odds` last pull, `--active-odds` narrow), `engine/linemoves.py` (`record_snapshots` → price history for CLV), `engine/oddsbudget.py` |
| weather | `engine/nflwx.py` (kickoff forecasts) |
| projection / pricing | `engine/models.py`, `engine/betting.py` (edge, haircut `temper_edge`, grade, Kelly via `engine/staking.py`), `engine/odds.py` (devig), `engine/devig.py` (market-sum), `engine/calibrate.py`, `engine/quality.py`, `engine/losspatterns.py` (veto) |
| TD model | `engine/touchdowns.py` (Poisson-style: baseline × implied total × opportunity share × matchup × weather × role), `engine/nflusage.py` (measured rz usage, snap shares, volume roles), `engine/tdbook.py` (TD book: shrink + ROI vs harvested prices), `engine/tdfeatures.py` (feature harness), `engine/tdbacktest.py` (walk-forward grader) |
| game bets | `engine/gamebets.py`, `engine/teamrates.py`, `engine/gamebacktest.py` (vs nflverse closing consensus) |
| parlays | `engine/parlays.py` (MAX_LEGS 3, §3 clash taxonomy `relate`, `check_ticket`), `engine/social.py` (shares) |
| bet log / CLV | `engine/ledger.py` (`bets` table: ts, book, odds, line, closing_line, closing_odds, stake, pnl, `_bet_clv`, `_bet_price_clv`, `process_grade`), `engine/clvboard.py`, `engine/maintenance.py` (settle, harvest closes) |
| readiness | `engine/nflready.py` (per-market gates: calibration, tier edge, measured?, settled record) |
| pages | `web/js/app.js` NFL views: recommended (props), game bets, likely, longshots, parlay zone, live, record; `web/data/recommendations.json` |

### Data sources — what, how, how often, reachable here, on failure
| source | provides | fetch | cadence | reachable here | on failure |
|---|---|---|---|---|---|
| nflverse schedules | 2026 schedule, kickoff ET, closing spread/total consensus | GitHub release CSV | every cycle (cached) | **yes** (7,548 rows; 2026 W1 = 16 games) | build exits 2, launcher keeps last board |
| nflverse weekly stats | player-week box scores (targets, carries, yards, TDs) | GitHub release CSV | every cycle | yes for 2021–2025; **2026 has none until W1 is played** | full build exits 2 → launcher's `--games-only` fallback (now guarded so a props board is never downgraded) |
| nflverse rosters / snaps / pbp | 2026 rosters; snap shares; rz usage | GitHub release CSV / nightly ingest | nightly | rosters yes; pbp needs ingest | prior-season carry (`--carry`) |
| The Odds API | prop + game prices, per book | HTTPS, key | budgeted pulls per cycle | **no key here** | `--cached-odds` reads the last paid pull; proxies never overwrite real prices |
| ESPN injuries | current designations | keyless HTTPS | every cycle, 10-min TTL | **blocked here** | page keeps last board; prop hold uses last data |
| nflverse injuries | practice reports (Wed–Fri) | GitHub CSV | every cycle | yes | own-player hold skipped with a warning |
| depth charts | starters / roles | see `depthcharts.py` | every cycle | see Phase 1 | role inferred from usage |
| weather | kickoff forecasts | keyless | every cycle | blocked here | neutral weather |

### Hardcoded season / week / date
- `nfl_build.py` takes `season week` as arguments; the launcher computes them from the schedule (`_current_nfl_week`, nearest game within 7 days, plus a 45-day run-up rule). No hardcoded 2026 in the build path.
- `engine/pipeline.py:127` documents the season-spans-New-Year keying (week 18 of 2025 played in Jan 2026). Correct by design.
- Only literal years in NFL code are in docstrings/examples (`2024 5` usage examples in `nfl_build.py`) and dated notes.
- `engine/playoffs.py` has a POSTSEASON table — checked in Phase 1 for 2026.

## Phase 1 — Week 1 dry run (this sandbox, 2026-09-02 00:03 UTC)

`python3 nfl_build.py 2026 1 --injuries --depth --carry --out …` — the
launcher's exact flags. Exit 0 in 3 minutes. Output: 16 games, 32 teams,
285 props analysed, **0 recommended** (no odds key here → every line is
a proxy → `has_market` false → the forcing rule publishes nothing; the
gate census says so on the payload). 4.6 MB payload with every section
the page reads.

| check | result |
|---|---|
| 2026 schedule loads, correct teams | yes — 272 games, 18 weeks, 32 teams, **every team exactly 17 games**, no team twice in a week |
| kickoffs in Eastern | yes — nflverse `gametime` is ET; the fatigue module's body-clock math depends on it and says so |
| Thu / Sun / Mon split | Week 1 is **Wed 9/9 20:20 (NE@SEA)**, Thu 9/10 20:35 (SF@LA), Sun 9/13 13:00 / 16:25 / 20:20, Mon 9/14 20:15. **The brief says the season opens Thursday 9/10; the feed says Wednesday 9/9.** Logged for Ethan to confirm against the league schedule — not a code defect either way (the build uses the feed) |
| bye weeks | weeks 5–14 carry 13–15 games, weeks 1–4 and 12, 15–18 carry 16 — consistent with 32 teams and 17 games each |
| no 2025 schedule leaking | the 29 "2025" rows dated in 2026 are the 2025 postseason (Jan–Feb 2026), keyed to season 2025 as `engine/pipeline.py:127` documents. Correct |
| rosters reflect 2026 | **0 of 285 board players on the wrong team** against nflverse's 2026 roster (2,800 rows); **0 not on a 2026 roster**; **55 board players changed teams 2025→2026** (Etienne→NO, Pacheco→DET, A.J. Brown→NE, Keenan Allen→IND, Kenneth Walker→KC, Montgomery→HOU, Njoku→LAC, Rachaad White→WAS…) and every one carries a `team change` reset in `carried`. Coach changes reset too (MIA McDaniel→Hafley, BAL Harbaugh→Minter) |
| coaching / coordinator changes | head-coach changes: detected from the schedule feed and applied as sample resets (above). **Coordinator identity: no feed; nothing in code is keyed to a named coordinator**, so there is no stale-coordinator rule to be wrong. The instruction set's §6 names no coordinators either. See Phase 2 |
| injuries & inactives | practice reports (nflverse) → own-player hold at build; ESPN designations every cycle (10-min TTL). A player ruled OUT after the card is built **leaves the board on the next cycle** (≤ ~15 min after ESPN posts). The journaled bet on him is **voided by the settle pass once the whole week is final** (`ledger.settle` no-show sweep, pinned by `tests/test_ledger.py::test_nfl_no_show_voids_only_when_the_week_is_final`) — the book's no-action rule, mirrored. *Correction:* an earlier draft of this row called this a P1 gap; it is not. The one real consequence is timing: a Sunday scratch sits `open` until Monday night's box score lands, so the Record page's open exposure overstates for ~30 hours. Cosmetic |
| depth charts | **P1 — the adapter reads a schema nflverse no longer publishes.** Both the 2025 and 2026 depth-chart files carry `dt, team, player_name, pos_abb, pos_rank, pos_slot`; the adapter filters on a `week` column and reads `club_code / full_name / depth_position / depth_team` — so `index_for_week` and `qb1_map` return **0 rows for 2026 week 1 and for 2025 week 18**. The QB-dependency watch and the knock-on role refinement (`--depth`) have been silently doing nothing. Fixed below |
| odds pulled, timestamped, stored | with a key: `--odds` pulls the intended books, `linemoves.record_snapshots` appends (prop, book, line, both prices, ts, game start) for CLV, and the last paid pull is reused via `--cached-odds`. **Not exercisable here (no key)** |
| renders completely, correct labels, grades match numbers | 285 rows render on the NFL board in the page walk of the QA audit (no JS errors); grades are recomputed from confidence/net edge in `tests/test_qa_numerics.py`. With no odds every grade is Pass and nothing is shown as a pick |

## Phase 2 — Instruction set audit (`docs/NFL_MODEL.md`, read adversarially)

Method: every rule in §1–14 checked against the Implementation Map and
the code it names. Findings, worst first.

**Contradictions (spec vs spec, or spec vs code)**
- **P2 — two grading systems.** §10 says "one 0–100 score, not a
  confidence score *and* a letter grade — two systems that can disagree
  create loopholes." The code has both: `engine/quality.py`'s 0–100
  `quality` (§10's weights, A+/A/B+/Pass) is computed, shown and
  journaled, but the publication gate is `engine/betting._grade` —
  Strong Play / Play / Pass on `confidence ≥ 8.0/6.5` and net edge
  `≥ .020/.010` (+ favourite surcharge) — via `rules.py:74` (`grade ==
  "Pass"` → not recommended). They can disagree exactly as §10 warns.
  Not changed (which one should gate is Ethan's call — Ask Ethan).
- **P3 — §3 Tier 2 minimum edge is stated as +4% in §3 and re-tuned to
  3% in the Implementation Map / `quality.TIER_MIN_EDGE`.** The map
  explains the re-tune (2026-07-29) but §3 was never updated. Doc fix.
- §5 recency weights: spec 45/35/20, code uses fitted window weights
  (≈61% recent / 32% season+career). The map says so; the spec text does
  not. Doc drift, not a defect.
- §3 devig for ATD: spec says additive/Shin; code uses the fitted
  **market-sum** method (`engine/devig.py`, constants fitted on 1,216
  games). A documented, measured deviation — and the right direction
  (see Phase 3: naive normalisation would be wrong for ATD).

**Undefined terms / fuzzy rules (no number in the spec)**
- §4 "moved sharply against you", "steam" — code: `engine/linemoves.py`
  has thresholds; the spec has none.
- §5 Usage Stability: "fluctuates significantly" — code: CV vs the
  market's typical variance (`quality.py`); the spec has no number.
- §7 timing rule ("Friday questionable vs Sunday inactive are different
  bets") — no procedure in code beyond the hold + rebuild cycle.
- §8 Tier 3 "only at clearly outlier prices" — no number; in practice
  Tier 3 props are quarantined to the Long Shots board.
- §9 "acknowledge the conflict" — code kills/flags via the §3 taxonomy;
  the spec never says which pairs are killed vs priced.

**Rules the pipeline cannot execute with the data it has** (decoration
today, all honestly marked 📋/🟡 in the map)
- §6 coordinator identity (no feed; head coach is the proxy) — **no
  coordinator is named anywhere in code or spec, so nothing here can be
  stale.**
- §6 per-receiver alignment (which corner shadows whom).
- §7 referee crew *assignments* (tendencies computable, assignment not
  published in any feed).
- §4 public bet % / money % (not published).
- §13 live betting (blocked by design; `rules.block_live_games`).

**Stale references** — none found: no 2025 player, team, coordinator or
scheme is named in the spec; 2026 league rule changes: nothing in the
spec depends on a rule (kickoff, OT, PI review) that changed.

**Missing who/what/when/where/why** — the spec is unusually complete on
this; the gaps are the undefined numbers above, not missing rationale.

**Sizing** — explicit and implemented: quarter Kelly default, half only
A+/Tier 1, post-haircut probability as input; caps 2u/play, 5u/game,
15u/slate with correlated bets counted together
(`correlation.apply_exposure_caps`, scaled uniformly then floored at
0.1u by dropping); drawdown rule halves stakes after a 10u peak-to-trough
(`ledger.drawdown_factor`). **Missing: max bets per week** (not in spec,
not in code). Bankroll basis is "1u = 1% of bankroll"; the dollar
bankroll is the reader's own setting.

**Parlay** — 3-leg cap in the engine (`MAX_LEGS`), the reader's slip
(`SLIP_MAX`, changed to 3 on 2026-09-01) and the share
(`social.MAX_PARLAY_LEGS`). Conflict definitions, probed with
`engine.parlays.relate` (Phase 3 tests keep these):
- same player over/under, or two markets → **killed** (Type 5)
- QB under + his WR over → **killed** (Type 7, "incoherent")
- two sides of one game → **killed** (Type 1)
- **P1 — both sides of one game TOTAL were NOT killed**: the taxonomy
  had no total-vs-total branch, so Over 45.5 + Under 45.5 in one game
  fell through to the generic same-game pace rule and came back "ok,
  ρ +0.10". Fixed below.
- QB passing TD + his WR anytime TD → **priced, not prohibited**, but at
  the generic same-game floor ρ = +0.10 with `measured=False`. The true
  correlation is far higher (the WR's TD usually *is* the QB's TD). Not
  silently independent — but under-priced. **Ask Ethan: prohibit, or
  measure and price it** (the measurement is buildable from the ingested
  logs: P(WR TD | QB pass TD) by team-week).

## Phase 4 — Is it actually making money?

**The one-line answer: profitability of the NFL PROP board is
unverified as a live record. Every number below is a leak-aware replay
or a paper measurement, stated with its sample size; the live journal
holds no settled NFL bet of the 2025 season on this box, and the 2026
season has not started.**

### What data exists
- Local: nflverse box scores 2021–2025 (≈93k player-week rows per
  season, 1,424 completed games with the schedule's closing spread/total
  consensus), the 2026 schedule. **No harvested prop closes here**
  (`odds_history` empty; the droplet harvests them via `harvest_odds.py`
  and the nightly close capture).
- Ledger: 13 NFL rows, all `open`, all 2026-W01 — a stale local build.
  Zero settled NFL bets, zero with a close. No 2025 bet history exists
  anywhere in the repo (the site journals from build day forward).

### Game lines — replayed here, walk-forward, vs nflverse's closing consensus (n = 1,184 games with a close + team history)
Ratings from games strictly before each game; production pricing; settled
by final score. ROI is **at the close** (the bet is against the closing
number — beating it is beating the field):

| market | bets | hit | ROI | note |
|---|---|---|---|---|
| total | 232 | 48.3% | **−7.5%** | projection 3.18 pts off the close; 449 games refused as not credible |
| spread | 188 | 53.3% | +2.6% | 4.05 pts off the close; 578 refused; +2.6% on 188 is inside noise (SE ≈ ±7 pts) |
| team total | 403 | 49.7% | −4.3% | line split from total+spread; 1,078 refused |
| moneyline | 161 | 41.0% | −5.1% | Brier 0.2336 vs 0.2475 base rate (mild skill); favourites −22.6% (51), dogs +8.9% (110) |

Verdict: **no demonstrated edge on any game market.** `engine/nflready`
records the same replay from 2026-08-30 with the production gates
grading *no* bet above Pass; the live board's game bets from before the
shrink was measured were voided (2026-08-30). Game lines are NO-GO for
real money on this evidence.

### Player props — measured on the droplet against REAL closes (recorded in `engine/yardagefit.py`, 2026-08-30; not re-runnable here)
Walk-forward, split by week, priced against the book's own two sides
(vig paid):

| market | bets | hit | ROI | 95% CI (≈ ±5 pts SE) |
|---|---|---|---|---|
| receptions | 304 | 55.6% | **+4.5%** | roughly [−2%, +18%] |
| rec_yds | 344 | 49.7% | −6.9% | roughly [−17%, +3%] |
| rush_yds | 838 joined closes | — | "no measured edge" (market shut on the board) | — |
| pass_yds | 266 closes | — | too thin | — |

Verdict, in the brief's words: **receptions shows a positive number on
~300 bets that is not statistically distinguishable from zero**; rec_yds
and rush_yds show none and are shut on the live board. At 55% against
−110 it takes on the order of a thousand bets to say much. **This is
noise-compatible, not proven.**

### Calibration — TD model, replayed here (walk-forward, 2021–2025, 22,099 player-weeks)
| band | n | claimed → landed |
|---|---|---|
| 0–10% | 9,002 | 5.9% → 8.4% |
| 10–18% | 5,596 | 13.8% → 18.0% |
| 18–28% | 4,451 | 22.6% → 30.0% |
| 28–40% | 2,254 | 32.9% → 38.9% |
| 40–60% | 772 | 46.1% → 55.3% |

Brier 0.1460 vs 0.1602 always-guess. **Systematically conservative** in
every band (the fitted correction in the store, T=1.12 b=+0.20, is what
the board applies). AUC 0.7210 (`engine/tdfeatures`). Top of board (95
slates): the #1 most-likely scorer landed 67.4% claiming 60.0%; top-5
60.2% claiming 53.4%, 95% band [+2.1%, +11.3%] — real. **ROI unknown
here**: no prices in this sandbox; on the droplet `python3 -m
engine.tdbook --roi` prices the same rows against harvested ATD odds
(Ask: paste that output).

### Not measurable here (and what it would take)
- Prop ROI at bet price vs at close, CLV in probability points, share
  beating the close, drawdown, flat vs Kelly — need the droplet's
  `odds_history` (harvested closes) and a journal with settled bets.
  The tools exist (`engine/lab.py` → The Lab page; `engine/clvboard`;
  `edge_audit.py`); the 2026 journal will feed them from Week 1.
- Per-week breakdown by market for 2025 — same dependency.

### What is in place to verify from Week 1 (the paper-trading requirement)
Already built and running on the droplet: every recommended pick is
journaled at build time with timestamp, book, price, line, model
probability, devigged fair, EV, stake (`engine/ledger.journal`); prices
are snapshotted per book with game start (`linemoves.record_snapshots`);
closes are captured and CLV (line and price) + process grade computed at
settle; the Record page leads with CLV and refuses to headline an ROI
under 100 bets; the likelihood board journals to its own paper bucket.
**The site does not imply a track record it does not have** — the
Record page's NFL section is empty until bets settle.

## Phase 3 — Model math, verified by hand (`tests/test_nfl_readiness_math.py`, 36 pins, commit 3575cb1)

Every expected value was worked on paper from the documented formula
before the function was called. All 36 pass.

| check | hand number | code |
|---|---|---|
| −110 → probability / decimal | 110/210 = 0.52381 / 1.90909 | same |
| +100 and −100 | both 0.5, decimal 2.0; even money spelled **−100** (Ethan 2026-09-01) | same |
| +600 → 1/7 = 0.142857, decimal 7.0; round-trip +600 | same | same |
| two-way de-vig −110/−110 | 0.5 / 0.5 | same |
| two-way de-vig −130/+110 | 0.565217/1.041408 = **0.542744** | same to 1e-6 |
| one-sided +600 at the documented 6% hold | 0.142857/1.06 = 0.134771 | same |
| ATD market-sum hold, 8 prices summing 3.60 vs 3.20 expected scorers | multiplier 1.125, overround +12.5%; 0.60 → 0.5333 | same |
| thin board (5 prices) / holdless board | **None**, not 1.0 — "no idea" ≠ "no hold" | same |
| power exponent | solves Σpᵏ = 3.20 exactly | residual < 1e-9 |
| power vs proportional | at equal overround the +600 loses MORE under power, the −150 LESS — the margin sits on the long prices, so a naive proportional normalisation over-prices every longshot | holds |
| EV at +600 | p=0.10 → −0.30; p=1/7 → 0.00; p=0.20 → +0.40 | same |
| EV at −110, p=0.55 | +0.05 | same |
| Kelly at −110, p=0.55 | (0.5−0.45)/0.90909 = 0.055 | same |
| Kelly when the price beats the edge | 0, never negative; `kelly_units` 0 | same |
| price ladder | −110 → 1.00u; +600 → 0.35u floor; −300 → 1.25u cap; a bigger Kelly fraction cannot buy a bigger stake at the same price | same |
| grade boundaries | Strong Play at conf ≥ 8.0 & net ≥ .020, Play at ≥ 6.5 & ≥ .010, inclusive; a hair under either → the lower grade | same |
| favourite surcharge at −200 | 0.18 × (0.6667 − 0.55) = 0.021, so .020 net is Pass at −200 and Strong Play at −110 | same |
| 5u game cap: three 2u legs in one game | factor 5/6, 1.67u each | same |
| 15u slate cap: eight 2u bets | factor 15/16, 1.88u each | same |
| 0.1u floor | a 0.11u leg scaled by 5/6 (0.092u) is **dropped**, not rounded to 0.09 | same |
| line CLV | Over 62.5 → close 64.5 = +2.0; the same Under = −2.0 | same |
| price CLV | took +600, closed +500 → +0.0238 (market came to us); took −110, closed +100 → −0.0238 | same |
| 2 / 3 legs at −110 | 1.90909² → **+264**; ³ → **+596** | same |
| independence joint | 0.55² = 0.3025; 0.55³ = 0.166375 | same |
| 4th leg | refused by `parlays.MAX_LEGS`, `check_ticket`, `social.MAX_PARLAY_LEGS`, `SLIP_MAX` — all 3 | same |
| conflict probes | both sides of a spread → kill; both sides of a total → kill (**after 48545ec**); same player O/U → kill; same player two markets → kill/duplicate; QB under + his WR over → kill (Type 7); two independent games → ok, ρ 0 | same |

Not verifiable by arithmetic alone, stated as such: whether the
market-sum constants (`SCORERS_SLOPE`/`BASE`, fitted on 1,216 games) are
right for 2026 is a Week 1 measurement (`--boards` de-vig check, task
#66), not a formula.

## Phase 5 — The anytime-TD model, in depth

**Inputs actually used** (`engine/touchdowns.td_probability`, read, not
the docs): team implied total (from spread + total → expected team TDs);
the player's share of team TDs = blend of his historical TD/game (weight
saturating at 30 games, cap 0.7) with a position baseline scaled by
opportunity share; **pulled 70% toward his xFP share** when the
expected-points model has him (held-out seasons: xFP share orders a TD
better than any other single input, AUC 0.7210 in `tdfeatures`);
red-zone touch share as a ±15% nudge (measured from ingested rz_car /
rz_tgt when present, else inferred and **flagged on the card as the
biggest source of error**); opponent TD-allowed multiplier by position;
weather multiplier (wind/precip on passing TDs); game-script multiplier.
Rate → P(≥1) = 1 − e^(−rate), rate clamped to [0.005, 1.15]. Then the
board applies the fitted calibration (T=1.12, b=+0.20) and the shrink
toward the book's devigged price.

**What it does NOT use, honestly**: snap counts (not ingested), per-
receiver alignment, coordinator identity, goal-line package (the
`i5_car` inside-5 feature exists in `tdfeatures` but is a diagnostic,
not a model term). §5's "usage stability" is a quality-score input, not
a TD-probability input.

**Calibration (Phase 4)**: conservative in every band before the fitted
correction; Brier 0.1460 vs 0.1602 base. Top-1 on 95 replayed slates
67.4% vs 60% claimed, top-5 [+2.1%, +11.3%] — the model **ranks** who
scores. Whether that ranking beats the **price** is the question the
brief asks and this sandbox cannot answer: no ATD prices are stored
here. On the droplet `python3 -m engine.tdbook --roi` prices the same
rows against harvested closes and prints the answer per depth band with
its bootstrap interval, and `engine/longshots` already measured the
+455…+800 band as the one where the book charges roughly double the
consensus hold (task #65). **Top-10 Week 1 edges: cannot be listed.**
There is no Week 1 ATD menu yet (books post it Tuesday–Wednesday) and no
key here; the first real menu is the check (task #66).

**Scratched / inactive**: the own-player hold refuses to publish a player
with a concern-or-worse designation at build; ESPN designations re-poll
every 10 minutes and a player ruled OUT leaves the board next cycle; a
journaled bet on a player who never appears in a fully final week is
**voided** by the settle sweep (Phase 1 row, corrected). What is NOT
handled: a late scratch after the reader has already bet — that is the
book's void, and the site says nothing about it (fine: it cannot).

**Parlay interaction**: `anytime_td` is in `parlays.EXTREME_MARKETS` —
**no engine ticket ever carries an ATD leg** (§4.3/§8.4). The reader's
slip can: `check_ticket` runs the clash taxonomy but does not apply the
extreme-market ban, so a person can build ATD + ATD or ATD + QB pass-TD.
The QB-TD + WR-TD pair is priced at the generic same-game floor ρ=+0.10,
`measured=False` (Phase 2) — **under-priced, and the warning the slip
shows for it says "+0.10", which understates the dependence**. Ask
Ethan (below) whether the slip should refuse ATD legs the way the engine
does, or price the pair from the ingested logs.

## Phase 6 — Defects, worst first

| sev | what was wrong | status | commit |
|---|---|---|---|
| P1 | depth-chart adapter read a schema nflverse stopped shipping → 0 rows for every 2025/2026 chart; QB-dependency watch and knock-on role refinement silently off | **fixed**, real 2026 file: 1,968 entries, 32 QB1s; legacy schema still read; 6 new pins | 579df52 |
| P1 | both sides of one game total were not a parlay kill (fell through to "ok, ρ +0.10") | **fixed**, kill/duplicate + slip refusal, pinned | 48545ec |
| P2 | two grading systems (quality 0–100 vs Strong Play/Play/Pass) — the gate is the letter grade, the card shows the score; they can disagree exactly as §10 warns | **not changed — Ask Ethan** which one gates | — |
| P2 | QB pass-TD + his WR anytime-TD priced at the generic ρ +0.10, unmeasured | **not changed — Ask Ethan** (prohibit vs measure) | — |
| P2 | the reader's slip does not apply the engine's extreme-market ban (ATD legs allowed on a person's ticket, never on the model's) | **not changed — Ask Ethan** | — |
| P3 | §3 rule 6 said Tier 2 +4% while `TIER_MIN_EDGE` enforces +3% since 2026-07-29 | **fixed** (doc) | 1194c27 |
| P3 | `maintenance.run_if_due`'s Wednesday deep-refit gate read the wall clock while every other weekday gate reads its `today` parameter — on a real Wednesday the suite's fake July days spawned the real fitters against the box's history.db and hung 15 min (found by this audit's suite run) | **fixed**, pinned; production unchanged | d4c354d |
| P3 | Week 1 opens **Wednesday 9/9 20:20 NE@SEA** in the nflverse schedule; the brief says the season opens Thursday 9/10 | **not a code defect** — the build uses the feed; Ethan to confirm against the league schedule | — |
| P3 | max bets per week: not in the spec, not in the code (caps are per play / game / slate) | **not changed — Ask Ethan** | — |
| — | "DNP-void gap" flagged P1 in the Phase 1 draft | **withdrawn**: the no-show void exists and is tested; only the ~30-hour open-exposure timing remains, cosmetic | — |
| — | Phase 3 hand-computed pins (36) | added | 3575cb1 |

Nothing was removed or simplified; no threshold was tuned to fit a
backtest; every number above names its sample.

## Phase 7 — Verdict for Week 1

**Code correctness: GO.** The pipeline builds the 2026 Week 1 slate end
to end on the launcher's own flags (16 games, 285 props, 0 wrong-team
players, every team-change reset, injuries on a 10-minute pull, depth
charts now actually read, closes and CLV captured at settle, no-shows
voided). The arithmetic matches the hand working in all 36 places
checked. The two defects found that could have changed a card are fixed
and pinned.

**Demonstrated edge: NO-GO for real money on game lines; NOT PROVEN on
props; UNKNOWN on anytime-TD prices.**
- Game lines: −7.5% (totals, 232), +2.6% (spreads, 188, inside noise),
  −4.3% (team totals, 403), −5.1% (ML, 161) against closes, walk-forward.
  The production gates already grade none of these above Pass.
- Props: receptions +4.5% on 304 bets, 95% CI roughly [−2%, +18%] —
  noise-compatible; rec_yds/rush_yds no edge, shut on the board.
- ATD: the model ranks scorers (top-5 landed 60.2% claiming 53.4%,
  CI [+2.1%, +11.3%]); against the price it is unmeasured in this
  sandbox. **Too-good check:** nothing here is too good — the one
  positive number (receptions) is within its own error bar.

**What that means for the site on 9/9–9/14:** publish the card as
built — the forcing rule, the own-player hold and the Pass gates are
doing their job — with the honesty copy that is already on every page
(no track record implied; the Record page's NFL section stays empty
until bets settle). Paper-trade Week 1 through the journal that already
exists; the CLV and hit numbers from one real week are the next input,
and this audit should be re-run against them.

**Ask Ethan (money / policy decisions — nothing here was decided for you):**
1. Which grade gates publication: `quality` 0–100 (§10's single score)
   or Strong Play/Play/Pass (`betting._grade`)? Today the letter grade
   gates and the score is shown.
2. QB pass-TD + his WR anytime-TD on one ticket: prohibit, or measure
   P(WR TD | QB pass TD) from the ingested logs and price it?
3. Should the reader's slip refuse anytime-TD legs, as the engine's own
   tickets do (§4.3/§8.4)?
4. A max bets-per-week cap: number, or none?
5. Bankroll basis, Kelly fraction and which books the Week 1 card
   prices against — the code defaults (1u = 1%, quarter Kelly, the
   ODDS_API book list) stand until you say otherwise.
6. Confirm the Wednesday 9/9 opener (NE@SEA) against the league
   schedule; the card will build for it either way.
7. On the droplet, paste `python3 -m engine.tdbook --roi` and the
   Week 1 `--boards` de-vig line once the ATD menus post — those are
   the two numbers this audit could not produce.
