# Qellys Book research lab

Started 2026-10-17 from Ethan's research specification (v1.0). This page is
the lab's front door: what data we have, what has been tested, what was
learned, and what needs Ethan. Everything here was either measured (the
command that produced it is named) or is labelled as untested.

The lab lives in `research/`:

| file | what it is |
|---|---|
| `research/sources.json` | the data audit: every source, VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / UNAVAILABLE |
| `research/registry.json` | the research registry (spec Part 11): every experiment, its prior art, novelty class, results, decision |
| `research/registry.py` | checks both files against their own rules and loads them into the spec's tables |
| `research/schema.sql` | those tables (data_sources, experiments, experiment_results, experiment_decisions) |
| `research/exp1_two_stage.py` | EXP-001 and EXP-001b |
| `research/exp2_interactions.py` | EXP-002 |
| `research/exp3_totals.py` | EXP-003a (game totals against the closing market) |
| `research/exp3_props_box.py` | EXP-003b (our own picks against the market at pick time; runs on the box) |
| `research/audit_box.py` | counts what the box already owns (odds, journal, outcomes) |
| `tests/test_research_lab.py` | the lab's tests |

`python3 research/registry.py` prints the ledger; `--sources` prints the
data matrix.

---

## Session 1 report (2026-10-17), in the spec's Part 13 format

### 1–2. Research questions and why they matter

The site's own loss autopsy names volume as the step most often wrong, so
the first questions were about volume and how a prop's distribution is
built. Then whether matchups add anything, then whether anything beats the
market.

### 3–6. Methods, equations and variables

In the registry, entry by entry, with each one's prior art. In short:

- **EXP-001.** P(Y|X) = Σₒ P(Y|O=o,X) · P(O=o|X). Opportunities are
  NegBin(μ_O, r), where μ_O weights each game by its age. Receptions given
  o are Binomial(o, p). Receiving yards given o is a zero-catch mass plus a
  moment-matched normal. Rushing yards given o is Normal(o·m, o·s²). This
  is compared against the direct model: the board's form mean with a
  learned ratio shape.
- **EXP-002.** y = b0 + b1·μ + b2·A + b3·D, with and without b4·A·D, for
  five interactions chosen for a football reason.
- **EXP-003a.** A totals model, then the model plus a context correction,
  then the de-vigged closing total, then a prespecified blend.
- **EXP-003b.** The same four forecasts on our journaled picks, using the
  market's fair price at pick time.

### 7. Data and its verified availability

See the matrix below and `research/sources.json`. All four experiments that
ran used nflverse files read and counted on 2026-10-17 (VERIFIED).

### 8–10. Implementation, evaluation design, success criteria

Each script's docstring states its bar, written before its first run. The
standard protocol:

- fit on early seasons, validate on the middle, read the holdout once with
  the code frozen;
- bootstrap clustered by player-season (props) or week (totals);
- Bonferroni across the comparisons in each experiment.

EXP-001 had one change before the holdout was read: the shrink grid was
widened because the training fits sat on its edge. The change is recorded
in the script.

### 11–12. Results (measured) and uncertainty

| experiment | subject | holdout result (98–99% clustered CI) | decision |
|---|---|---|---|
| EXP-001 two-stage | receptions | CRPS 1.1746 → 1.1476, diff −0.0270 [−0.0436, −0.0102], n 4,152 | **ADVANCE**: to calibration and real book prices, not to the board |
| | receiving yards | +0.0284 [−0.1491, +0.2252]; worse in validation | REJECTED |
| | rushing yards | −0.2153 [−0.4567, +0.0474] | INCONCLUSIVE |
| EXP-002 interactions | all five | every holdout difference ≥ 0 | **REJECTED** (all five) |
| EXP-003a totals | correction vs baseline | log loss +0.00026 [−0.00504, +0.00641] | REJECTED |
| | anything vs the closing market | the market's log loss is 0.6931; our best blend is 0.6948 | **REJECTED** |
| EXP-R01 bridge window | targets, carries | every 2022–25 season improved; worst season +0.11% (receptions), +0.15% (receiving yards), +0.02% (rushing yards) | WIRED |
| EXP-R02 referees | totals, spreads | correlation −0.02 / −0.01 vs the close | REJECTED |
| EXP-R03 team volume | from the line | +0.5 to +0.9% RMSE | recorded, not wired |

Four observations from the same runs:

1. **The receptions gain is over the whole distribution, not at a line.**
   At a line-like threshold, the two-stage Brier score is slightly worse
   (0.2198 v 0.2165). Its over-chances are also too extreme: the top
   decile said 0.49 and 0.36 happened. It needs calibration before it is
   worth anything to a bettor.
2. **The two-stage shape at the direct model's mean beat both models on
   both yardage markets.** This was noticed after looking, so it is not a
   result. It is preregistered as EXP-001b and will be scored only on
   games played after 2026-10-17.
3. **Training coefficients lie.** Two of the matchup interactions had
   large, "significant-looking" training coefficients (+4.5 and +5.3
   standardised) and made unseen seasons worse.
4. **The closing total is close to unbeatable on public features.** Its
   log loss is about what forecasting 50/50 on every game would score,
   and our baseline is worse than that.

### 13. Limitations and failure modes

- The weekly player file has no row for a player with no stats, so a
  zero-target game is missing for both models alike.
- Yardage given o is a moment-matched approximation; we have no per-target
  data in these files.
- The defence step is left out of EXP-001's two models. It is the same for
  both, so it cannot favour either.
- Closing prices are the market's last word, not prices a bettor could
  reliably take before the close.
- No web literature search was possible from the sandbox, because page
  fetches are blocked. The novelty calls rest on general knowledge and are
  labelled that way.

### 14. Novelty assessment

Nothing here is a new mathematical invention:

- EXP-001 is a new application of an established method (class 4).
- EXP-001b is a new combination (class 2), with its novelty unverified.
- The rest are rediscoveries of known ideas (class 5), tested honestly.

This is the expected state of a first session. The spec's own rule: a new
coefficient is not an invention.

### 15. Decisions

- EXP-001 receptions: **advance**, to a calibration step and then a test
  at real 2024–25 book lines.
- EXP-001b: **investigate**, prospectively.
- EXP-002 and EXP-003a: **reject**.
- EXP-003b: **run on the box**.

### 16. Next highest-value experiment

Price EXP-001's calibrated receptions distribution at real receptions
lines, scored by log loss against the de-vigged book and then by the return
at the prices actually posted.

- Develop it on 2023 lines from The Odds API archive.
- Decide it on 2026 games played after today, against the quotes the site
  already records every pull.

2024–25 cannot decide it: those seasons were EXP-001's holdout and have
been read once. The 2023 lines need one harvest decision from Ethan (see
"Decisions for Ethan").

---

## Task 1 — data audit

### What the site already owns (the most important finding)

- **The Odds API is already paid for.** The site already speaks its
  historical endpoints: `harvest_odds.py` and
  `engine/sources/oddshistory.py` have a cost estimate, a hard credit
  budget, a dry-run mode, skip-what-is-stored, and storage of the
  provider's own snapshot time.
- Per a search summary of the provider's page (the page itself is
  blocked from this sandbox), its history runs:
  - game markets: from 2020-06-06;
  - player props: from 2023-05-03, in 5-minute snapshots;
  - cost: 10 credits per region per market per request, paid plans only.

  So **the 2023, 2024 and 2025 NFL prop seasons are buyable with credits
  we already have a plan for.** Nothing new needs to be bought to start.
- **The journal is the best market dataset we have.** It holds every pick
  with:
  - the price observed when it was posted;
  - our chance;
  - the market's de-vigged fair, on the Edge book;
  - the close and the result;
  - forecasts sealed before the game in a hash chain (`forecast_log`);
  - every later correction in `bets_audit`.

  That is the spec's "prospective paper bets" table, already running.

Run `research/audit_box.py` on the box to count all of it (command at the
bottom).

### Odds providers

None of the four could be read directly from the sandbox, so the facts come
from search summaries and are labelled that way.

| provider | historical player props | timestamps / snapshots | results | status |
|---|---|---|---|---|
| The Odds API | from 2023-05-03 (per its own page, via summary) | 5-minute snapshots, provider timestamp | no (we settle from box scores) | PARTIALLY VERIFIED; **already integrated** |
| SportsGameOdds | vendor FAQ claims historical props, closing lines, alternates, prop outcomes | not confirmed | yes (claimed) | UNVERIFIED; prices conflict across sources |
| ParlayAPI | not confirmed (has a closing-odds endpoint; depth by plan) | not confirmed | not confirmed | UNVERIFIED |
| Flash Props | no documented history (listings describe a live feed) | — | — | UNVERIFIED |

Recommendation: **do not buy anything yet.** Run the free dry-run of a
2024 NFL receptions harvest on our existing plan (command below), decide on
the credits, and request vendor samples only if The Odds API's coverage
turns out to be thin.

### Sports data, per sport (full detail in `research/sources.json`)

| sport | statistics | status | historical odds |
|---|---|---|---|
| NFL | nflverse: weekly player stats 2016–2026 (counted), games with closing lines and referees 1999–2026 (counted), pbp, participation, FTN, PFR, NGS (present) | VERIFIED / PARTIAL | The Odds API from 2023-05 (props); nflverse closing game lines 2006+ |
| MLB | MLB Stats API, Baseball Savant (in production) | PARTIALLY VERIFIED | The Odds API |
| College football | cfbfastR player stats 2022–2026 (counted), CFBD API (key on the box) | VERIFIED / PARTIAL | The Odds API, CFBD lines |
| NBA | ESPN summaries (cdn.nba.com refuses the box) | PARTIALLY VERIFIED | The Odds API |
| UFC | ESPN MMA cards and results | PARTIALLY VERIFIED | The Odds API; weigh-ins not stored |

Licences: none of the free sources' terms were re-read in this audit. Every
entry says so, and Ethan should check the ESPN, MLB and Open-Meteo terms
before any commercial reliance.

## Task 2 — the vendor sample request (to send only if needed)

> Subject: Historical player-prop sample request — research evaluation
>
> We are evaluating historical odds providers for a sports research
> project. Before purchasing, we'd like a small sample in your standard
> delivery format:
>
> 1. NFL, regular-season weeks 10 of 2024 and 10 of 2025, every game:
>    player receptions, receiving yards, rushing yards, passing yards and
>    anytime touchdown, main and alternate lines, every sportsbook you
>    carry, every snapshot from market open to kickoff.
> 2. One MLB date (2025-07-15) for batter total bases and pitcher
>    strikeouts, and one NBA date (2025-01-15) for points, rebounds and
>    assists, same detail.
> 3. One UFC event (moneyline, method of victory, round props).
>
> Please confirm for each record: the observation timestamp, and whether
> it is your capture time or the book's; whether suspended or pulled
> markets appear; whether prices are observed or reconstructed; and
> whether settlement (including push and void) is included.
>
> And for licensing: coverage start dates by sport and market, the books
> covered, bulk download, permanent storage, use in commercial models,
> displaying derived predictions publicly, and price for the NFL seasons
> 2023–2025 player props.

## Task 3 — database and ingestion design

**SQLite, not PostgreSQL, for now.** This is a recommendation for Ethan to
confirm. Every database here is SQLite, the engine is standard library
only, and the droplet has one core. The lab's tables
(`research/schema.sql`) use only types and constraints that move to
Postgres unchanged.

Where each table the spec asks for already lives:

| spec table | here |
|---|---|
| data_sources | `research/schema.sql` data_sources, rows from `research/sources.json` |
| events | `history.db` games (+ each sport's schedule tables); UFC bouts in ufc_fights |
| participants / entity aliases | **gap**: players are keyed by name + team (with nflverse gsis ids in the files). A canonical participant table with aliases is backlog item B4 |
| odds_snapshots | `history.db` odds_history (provider snapshot time, never overwritten: the key includes taken_at) + `cache/line_history.jsonl` (every pull, timestamped) |
| outcomes | `history.db` player_game_logs, games; settlement rules in `engine/ledger` (push, void, partial games) |
| feature_snapshots | **partial**: backtests rebuild features "as of week" (`upto_week`), but nothing stores the feature vector a pick was made from. Backlog B5 |
| experiments, experiment_results | `research/schema.sql`, rows from `research/registry.json` |
| model predictions / prospective paper bets | `ledger.db` forecast_log (sealed, hash-chained) + bets |
| historical corrections | `ledger.db` bets_audit (hash-chained, every change with its reason) |
| ingestion logs | `history.db` ingest_log |

**Already enforced by tests in the suite:**

- odds conversions;
- push/void settlement;
- point-in-time cutoffs: `test_usage_asof`, and the CAST trap on text
  weeks;
- closes taken pregame only;
- the tamper-evident journal;
- timestamps stored from the provider envelope, not the request;
- duplicate pick keys (a unique index).

**Gaps:**

- the canonical entity table (B4);
- stored feature snapshots (B5);
- a general "stale odds" test across feeds. Today it exists for the
  board's freshness, not for research reads.

## Task 4 — the first NFL prop baseline

Defined and measured. It is EXP-001's model A:

- **mean:** the board's own form blend, pulled toward last season where
  the board does that;
- **shape:** the training seasons' pool of y/mean ratios for that market
  and position.

That makes it a learned shape, not an assumed one. The two-stage model B
is the first challenger. On receptions it beats A across the whole
distribution, and both need calibration at a line before either is priced
against a book.

## Task 5 — the three experiments

Run, and recorded above and in the registry. EXP-003b (props against the
market at pick time) is written and tested, and waits on one box command.

## Task 6 — prioritised backlog

| # | item | depends on | effort | data | accepted when |
|---|---|---|---|---|---|
| B1 | Calibrate EXP-001 receptions (isotonic or Platt on training seasons), re-score on the 2024–25 holdout's existing CRPS/Brier | — | small | have it | calibrated Brier at the proxy line ≤ A's on validation, and CRPS still beats A |
| B2 | Harvest 2024–25 NFL receptions / receiving / rushing props, one pre-kick Sunday snapshot | Ethan's credit decision | box time | The Odds API | dry-run cost accepted; rows land in odds_history |
| B3 | Score A, B and calibrated B at real lines: log loss vs the de-vigged book, then return at the posted price. Develop on 2023 lines; DECIDE on 2026 games after the freeze against `line_history` (2024–25 was EXP-001's holdout, read once, so it is no longer untouched) | B1, B2 | medium | B2 + the box's line history | the bar written before the run (as EXP-001) |
| B4 | Canonical participant table with aliases (gsis / ESPN / book spellings) | — | medium | have ids | every journal row maps to one id; a test that fails on a new unmapped name |
| B5 | Store each pick's feature vector at decision time (feature_snapshots) | — | medium | own | a pick can be re-priced from its stored features alone |
| B6 | EXP-001b scored weekly | games | none | auto | the preregistered bar |
| B7 | EXP-003b on the box | Ethan runs it | none | journal | the bar in the script |
| B8 | MLB first experiment: two-stage strikeouts (batters faced × K rate) vs direct | — | medium | MLB Stats API on the box | same protocol as EXP-001 |
| B9 | NBA: minutes × per-minute rate, minutes from rotation/injury state | — | medium | box history | same protocol |
| B10 | UFC: fight-time distribution × striking rate for significant-strike props | data audit of per-fight stats | large | needs a per-fight stats source | coverage verified first |
| B11 | College: the EXP-001 protocol on cfbfastR (verified 2022–26) | — | small | have it | same bar |

## Task 7 — what I can do, and what needs Ethan

**Done in the sandbox:**

- read public files and run experiments on them;
- write code, tests and docs;
- commit to the branch.

**Cannot do here:**

- read vendor pages directly (the sandbox's network refuses them);
- reach ESPN, which is refused from the sandbox;
- touch the box's data;
- spend credits;
- contact vendors;
- accept licences.

**Needs Ethan:**

- running the box commands below;
- any Odds API credit spend beyond a dry-run;
- sending the vendor request, if wanted;
- the SQLite-versus-Postgres call;
- reading the free sources' licence terms.

### Decisions for Ethan

1. **Credits for B2.** Run the dry-run below first. It is free and prints
   the cost.
   - At the documented rate, three markets on one region is about 30
     credits per game-snapshot.
   - A 2024 regular season of Sunday games (about 230 games) is therefore
     roughly 7,000 credits, plus each day's events call. That is an
     estimate; the dry-run's number is the real one.
   - The dry-run below covers September–October 2024 at 17:00 UTC.
     November onward needs a second run with `--hour 18`, because the
     clocks change. The harvester's own warning: a
   careless full-market harvest once emptied a 20,000-credit plan in an
   afternoon, which is why it now has a budget cap.
2. **SQLite stays** (recommended) or the lab moves to Postgres.
3. **Vendor samples:** only if the dry-run shows thin coverage.

### Box commands

```
cd /srv/qellys && git log --oneline -1
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/audit_box.py
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp3_props_box.py
cd /srv/qellys && sudo -u qellys python3 harvest_odds.py nfl --from 2023-09-10 --to 2023-10-29 --weekdays sun --hour 17 --markets receptions,rec_yds,rush_yds --dry-run
```

The last one spends nothing. Paste all four outputs.
