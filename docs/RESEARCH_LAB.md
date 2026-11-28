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
| `research/exp1_lines_box.py` | EXP-001c (the models at the books' real NFL lines; runs on the box) |
| `research/exp4_college_two_stage.py` | EXP-004 (EXP-001 replicated on college) |
| `research/exp5_symbolic_residuals.py` | EXP-005 (searched equations for the direct model's misses) |
| `research/exp6_shrink_b.py` | EXP-006 (EXP-005's shrink on the two-stage model; read at season end) |
| `research/thinmarket_box.py` | EXP-R06 (a market chance for the board's thin picks; runs on the box) |
| `engine/fieldcurve.py`, `fieldcurvefit.py` | the market's curve from main lines, and the spread law it reads |
| `research/exp7_mlb_strikeouts_box.py` | EXP-007 (MLB: a starter's strikeouts, batters faced first; runs on the box) |
| `research/exp7b_mlb_strikeout_lines_box.py` | EXP-007b (those strikeout models at the books' own lines; runs on the box) |
| `research/exp4c_college_lines_box.py` | EXP-004c (the college results at the books' own lines; runs on the box) |
| `research/exp8_nba_shape_box.py` | EXP-008 (NBA: a shape built from his minutes against the board's spread; runs on the box) |
| `research/exp9_nhl_shape_box.py` | EXP-009 (NHL: a shape built from his ice time against the board's own count; runs on the box) |
| `research/box_round.py` | every read-only box run above, in order, in one command (never a holdout) |
| `tests/test_research_lab.py` | the lab's tests (also `test_thin_market.py`, `test_mlb_strikeouts_lab.py`, `test_college_lines_lab.py`, `test_nba_shape_lab.py`, `test_mlb_strikeout_lines_lab.py`, `test_nhl_shape_lab.py`, `test_box_round.py`) |

`python3 research/registry.py` prints the ledger; `--sources` prints the
data matrix.

---

## Session 3 report (2026-10-19), in the spec's Part 13 format

Built while Ethan was away ("Yeah keep building. I'm not home so just
save all code for when I'm home"). Seven new tests, two protocol
amendments and one correction. None has read real data yet: each one runs
on the box or waits on games, and every bar below was committed before
that.

### 1–2. Research questions and why they matter

- **EXP-R06, the board's thin picks.** On the box's first full board
  under the price rule, 133 of 230 NFL player picks had no three-book
  field at their own line. They are mostly alternate rungs, which books
  hang one-sided. Those picks keep our chance unjudged, and they are where
  our chance can run furthest from the middle. Can the books' main lines
  price them?
- **EXP-006.** Is the two-stage model's receptions centre too wide in the
  same way EXP-005 found the direct model's was, so that the two gains
  add?
- **EXP-007, MLB's first experiment (backlog B8).** Is a starter's
  strikeout count better forecast as batters faced times a strikeout rate
  than directly? The spec calls for a program per sport, and it forbids
  assuming an NFL finding transfers.
- **EXP-004c.** Do the college results (B on receptions, H on rushing)
  hold at the books' own lines? A line is where a bet is made.
- **EXP-007b.** The same question for MLB: do EXP-007's strikeout models
  hold at the books' own lines?
- **EXP-008, NBA (backlog B9).** The NBA board's centre is already
  minutes times a per-minute rate, but its spread is a fixed share of
  that centre: a 38-minute night and a 24-minute night are the same
  width. Does a shape built from his minutes price better at the same
  centre?
- **EXP-009, NHL.** The hockey board went live this month with written
  priors for its spreads: shots and blocks as wide as each skater's own
  game-to-game variance shrunk toward 1.25, points a Poisson. Nothing
  has tested them. At the board's own centre, does a shape built from
  his ice time price better?
- **One read, not a read per run (EXP-001b, EXP-001c).** Deciding at
  whichever run first looks good is optional stopping, and it inflates
  false passes.

### 3–6. Methods, equations and variables

- **EXP-R06.** Each book's main line is two-sided, so de-vigged it pins
  that book's centre m_b. It does so under a measured shape: variance =
  PHI × mean, read as a negative binomial for counts and a gamma for
  yards (`engine/fieldcurve`). The field's centre is the median over
  three books or more, and it gives the chance at the pick's own line.
  The test is pricetrust's rule and bar, imported unchanged:
  shown = ours − w·max(0, ours − market − T).
- **EXP-006.** B′ is B moved to m′ = m_B + c0 + c1·m_B. The line was
  fitted on 2017–2025 and printed before any scored game: +0.4919 −
  0.18155·m_B. The score is CRPS(B′) − CRPS(B) on receptions.
- **EXP-007.**
  - A is the site's MLB form blend of his strikeouts, with the training
    pool's shape.
  - B: batters faced = his starts' age-weighted batters faced plus a
    residual drawn from the training starts' own pool (early exits
    included, no assumed curve). Then strikeouts | batters faced ~
    Binomial(bf, p), with p his season rate shrunk toward the league's by
    k batters, k fitted.
  - H is A's mean with B's shape.
  - The score is CRPS on 0–15 strikeouts.
- **EXP-004c.** P(over L) from A, B and H, all fitted on 2025, each
  recalibrated by a logistic at the proxy line. L is the line most books
  hang among each book's last quote before kickoff. C is the books'
  de-vigged consensus there. The score is log loss.
- **EXP-007b.** EXP-007's A, B and H, fitted on its training starts and
  recalibrated the same way (A*, B*, H*), each priced at the line most
  books hang before the start. C is the books' de-vigged consensus there.
  The score is log loss, on EXP-007's holdout starts only.
- **EXP-008.** One centre for both shapes: his rate per minute times his
  role's base minutes (the board's own arithmetic). S is the board's
  shape exactly (`engine/nba/prob`), at the cv the live build measures by
  its own rule (`engine/hoops_fit`), on the training window only. C
  takes his minutes from the training games' own spread around the base,
  then a count with mean rate × minutes and variance PHI × mean. The
  score is CRPS.
- **EXP-009.** One centre: the board's own projection, as the NHL walk
  computes it (a test holds the centre, the spread and the position
  priors equal to the walk's). S is the board's own count. C draws his
  ice time from the training pool of actual over projected ice time,
  then a count given it with variance PHI × mean. N, described only, is
  the board's count with one refitted spread per stat. The score is
  CRPS.

### 7. Data and its verified availability

- **The spread law, measured (`fieldcurvefit.py`, 2022–25).** Within a
  player-season, a game's variance is a constant multiple of its mean.
  The multiple is PHI = 1.19 for receptions, about 20 in every yards
  market, and 1.77 for pass attempts. It holds across low, middle and high
  means in every market but rushing attempts.
- **Line stores.** The box's line snapshots keep every book's main line,
  both sides, with the game's start. Alternate ladders live only in
  `alt_curves`, and only since 2026-10-16. College snapshots begin
  2026-09-30.
- **odds_history's college props** come from the prop tape: players on an
  injury report, kept only when the number moved. That is not a
  representative sample on its own, so EXP-004c reads both stores.
- **College completeness.** 2025's play file held 886 of 888 major-college
  games. Every completed 2025 game has its real kickoff in the mirror's
  schedule; none is still marked "time TBD".
- **MLB.** The box's play-by-play table holds the seasons the chart
  backfill has read, likely 2026 alone. EXP-007 prints its coverage
  against the season's regular-season finals.
- **MLB lines.** odds_history's MLB rows are mostly the nightly close
  harvest, taken at 23:00 UTC. Until 2026-09-30 that harvest also stored
  games already under way, at their live prices, and its rows carry no
  start. The play table keeps dates, not first pitches. So a quote with
  no start counts for a start only from an earlier day, or before 11 a.m.
  Eastern on the day itself. Snapshot rows carry their start and are
  placed exactly. Both stores keep main lines only.
- **NHL.** The box's logs hold 2023–26; the league's API is now in the
  source ledger (SRC-NHL-API). At the box's scale (900 skaters, three
  seasons), EXP-009 ran in 42 seconds here and peaked at 218 MB.
- **NBA.** The board's volatile-role gate is off for the NBA (on for
  the WNBA). The live build refits its spreads from every season the box
  holds; EXP-008 uses the same rule on its training window only, and the
  test checks the two agree on the same rows.

### 8–10. Implementation, evaluation design, success criteria

| experiment | bar committed in | read |
|---|---|---|
| EXP-001b, EXP-001c amendments (one read) | `3ba10078` | before any decision row existed |
| EXP-R06 | `e6601811` | on the box (round five) |
| EXP-006 | `c0941ca4` | once, at the regular season's end |
| EXP-007 | `7544b1ca` | on the box: validation first, holdout once |
| EXP-004c | `97563ef1` | on the box: development now; decision as weeks 9+ complete |
| EXP-008 | `6db6e64a` | on the box: validation first, holdout once |
| EXP-007b | `0242e2ee` | on the box: development now; the decision once, on EXP-007's holdout starts |
| EXP-009 | `ce5be82c` | on the box: validation first, holdout once |

Each bar's strictness was tried on made-up data where the truth is known:

| test | passes where it should | passes where it should not |
|---|---|---|
| EXP-R06 | 33 runs of 40 | 1 of 40 |
| EXP-007 (B v A) | 19 leagues of 20 | 0 of 20 |
| EXP-008 (C v S, three stats) | 19 stat tests of 30 (points 10 of 10) | 0 of 30 |
| EXP-007b, Q2 (H* v A*: the shape at the line) | 17 leagues of 20 | 1 of 20 |
| EXP-007b, Q1 (B* v A*: the whole model at the line) | 19 of 20 | 13 of 20, on its centre (below) |
| EXP-009 (C v S, three stats; 90 skaters a league) | 9 stat tests of 30 (shots 5 of 10) | 1 of 30 |

Two guards keep EXP-007's holdout to one honest read. It is not read
until the table holds plays for 98% of every season's regular-season
finals, so the rows cannot change afterwards. It is not read while the
fitted shrink sits on its grid's edge, which would need a written
amendment first. EXP-007b reads under the same two guards.

EXP-007b's two questions are not equally strict, and the table shows why.
Where a league's strikeouts come from the pitcher's mean whatever his
batters faced, Q1 still passed in 13 of 20. B's pooled season rate is a
steadier centre than the form blend: its squared error on the decision
starts was 3–9% lower, in leagues of both kinds. At one line the centre
counts for more than the shape. So a Q1 pass says B* prices the line
better, not that batters faced is the reason. Q2 shares A's centre, so it
is the shape test at the line.

EXP-009 carries a described arm for a related reason. Where the board
set a spread too narrow or too wide, any refit can beat it, not only one
built from ice time. N refits the board's spread with one number per
stat, and C − N says which it was. In made-up leagues where the board's
own spreads were the truth, N still beat S on shots in 5 of 10. The
board's 1.25 is the spread around a player's true mean; a forecast's
spread also carries the error in its own centre (the refit read
1.27–1.37 there). If C advances and C − N holds zero, the simpler N is
what a paper test tries; that rule was written before any run.

One correction, made before any real data was read. EXP-004c's text says
each book's last two-sided quote counts. Its code kept each book's last
quote of any kind, so a later one-sided quote dropped that book from the
consensus. The code now does what the text says (`0242e2ee`), and
EXP-007b does the same; both are tested.

### 11–12. Results (measured) and uncertainty

No decision this session: every new test waits on the box or on games.
What was measured:

- **The live rule's own counts** (Ethan's paste, 2026-10-17): 230 player
  picks checked; 26 with no book quote; 133 with under three books at the
  line; 71 with a field; 35 above it and moved, 16 of them posted.
- **EXP-006's fitted line** is a slope of −0.18155. B's receptions centre
  is too wide as well, a little more than A's (EXP-005: −0.154). Whether
  shrinking it adds is the test.
- **EXP-001b:** 0 of 192 regular-season games after the freeze are final
  yet.

### 13. Limitations and failure modes

- **EXP-R06.** One spread per market; rushing attempts breaks the law at
  the extremes. A book's main line may come from a different model than
  its alternates.
- **EXP-007.** Likely one season, so the one-season split. Openers count
  as starts. Opponent lineup, park and umpire are in neither model.
- **EXP-004c.** Development is short, because college snapshots start
  2026-09-30. The snapshot file has no sport field, so a quote is placed
  only within six hours of the college kickoff its own start names (an
  NFL namesake plays a day apart). There is one fitting season.
- **EXP-007b.** A quote with no start counts only from an earlier day,
  or before 11 a.m. Eastern on the day. That drops most of the nightly
  harvest's same-day quotes, so many of its lines are the day before's.
  It decides on the same starts as EXP-007's holdout, so the two reads
  are not independent.
- **EXP-009.** The centre is the walk's: a neutral opponent and no
  power-play step, so tonight's opponent, goalie and special teams are
  in neither shape. Playoff games feed projections, as they feed the
  live board. PHI by moments mixes the centre's error into the spread.
- **EXP-006.** One season of rows. The line is fitted on the seasons B
  trains on.
- **EXP-008.** The centre leaves out tonight's spread, rest, vacancy and
  defence dials, which neither shape has. PHI by moments mixes the rate's
  own estimation error into the count's spread.

### 14. Novelty assessment

| item | class |
|---|---|
| EXP-R06 (a variance law used to extend a market's price to lines it does not quote) | 4 |
| EXP-006 | 2, shrinkage combined with the compound model |
| EXP-007 | 4 |
| EXP-004c | 4 |
| EXP-008 | 4 |
| EXP-007b | 4 |
| EXP-009 | 4 |

Still no new mathematics.

### 15. Decisions

| item | decision |
|---|---|
| EXP-R06 | implemented. A pass goes to Ethan with its w and T, never straight to the board |
| EXP-006 | preregistered; read once at season end |
| EXP-007 | implemented; validation read first, then the holdout once |
| EXP-004c | implemented; development now, decisions as college weeks 9+ complete |
| EXP-008 | implemented; validation read first, then the holdout once. An advance goes to Ethan, then to a paper board |
| EXP-007b | implemented; development now, the decision once, after EXP-007's validation paste is checked |
| EXP-009 | implemented; validation read first, then the holdout once. An advance goes to Ethan with C − N beside it |
| EXP-004c correction | its code now keeps each book's last two-sided quote, as its text says |
| EXP-001b, EXP-001c | amended to one read before any decision row was read |

### 16. Next highest-value experiment

**EXP-001c's decision** is still first: NFL receptions at real lines, the
first complete weeks after the freeze to reach 300 rows. It is the
earliest read that says whether any distribution gain survives at the
book's number.

Then, from the box:

1. EXP-007's, EXP-008's and EXP-009's validation pastes, and EXP-007b's
   development numbers; each holdout follows once that paste looks
   sound.
2. EXP-004c as the college weeks complete.
3. EXP-R06 as thin picks settle.

Built since: **EXP-007b**, the strikeout models at the MLB lines the box
holds, deciding on EXP-007's holdout starts, once. B9 (NBA) is now EXP-008.

---

## Session 2 report (2026-10-17, evening), in the spec's Part 13 format

### 1–2. Research questions and why they matter

- **EXP-R05, wired.** Ethan said yes to pricetrust's pass on the NFL one
  board. Does the rule keep helping on picks made after it went live? That
  is the only test a live change can still fail.
- **EXP-004.** Does EXP-001's opportunities-first model hold in a second
  sport? The spec forbids assuming an NFL finding transfers.
- **EXP-005.** Can a small, searched equation explain the direct model's
  misses (spec 5.1 symbolic regression, 5.4 residual discovery)?

### 3–6. Methods, equations and variables

- **R05 (live):** shown = ours − w·max(0, ours − market − T), with w = 1,
  T = 0 on the NFL one board. Market = each book's quote at the pick's own
  line, both sides, de-vigged, median of ≥ 3 books. This is pricetrust's
  number, computed at build time (`engine/likelyboard.trust_price`).
- **EXP-004:** EXP-001's models A, B and H, imported unchanged and fed
  college player-games by the site's own parser. P(Y|X) = Σ_o P(Y|o,X)
  P(o|X) with O ~ NegBin; H is A's centre with B's shape.
- **EXP-005:** r = y − μ_A, r̂ = c0 + c1·g. g runs over every one- and
  two-term formula (1,680) in six pre-game quantities: A's centre, B's
  centre, age-weighted opportunities, production per opportunity, week
  and opportunities so far. Four functions are allowed (x, √x, log(1+x),
  1/(1+x)) and four operators (+ − × protected ÷). Choice is by validation
  error × (1 + 0.01·complexity).

### 7. Data and its verified availability

- College play-by-play, 2022–2026, cached and read here.
- **Measured this session:** the share of college incompletions that name
  their target is 45% (2022), 38% (2023), 21% (2024), 78–84% by week
  (2025) and 92% (2026). Every rushing play names its runner. Recorded in
  `research/sources.json`.
- So the college receiving test runs only on 2025→2026, and rushing on
  2022–26. A target count whose meaning moves between seasons would test
  the feed, not the model.

### 8–10. Implementation, evaluation design, success criteria

Every test's bar, splits and multiplicity correction were committed before
its holdout was read:

| experiment | committed before the holdout | holdout read in |
|---|---|---|
| EXP-004 | `0ad7173c` | `b036253e` |
| EXP-005 | `bc72d027` | `edeb0fce` |

- **Score:** CRPS on EXP-001's grids.
- **Uncertainty:** player-season-clustered bootstrap, Bonferroni within
  each family (97.5% or 98.33% intervals).

### 11–12. Results (measured) and uncertainty

| experiment | test | holdout | difference [CI] | decision |
|---|---|---|---|---|
| EXP-004a | H v A, college rushing yards | 2025–26, 5,635 games | −0.1905 [−0.2455, −0.1366] | **ADVANCE** |
| | B v A, college rushing yards | same | −0.1523 [−0.3386, +0.0205] | INCONCLUSIVE |
| EXP-004b | B v A, college receptions | 2026, 1,738 games | −0.0271 [−0.0525, −0.0019] | **ADVANCE** |
| | B v A, college receiving yards | 2026, 1,718 games | −0.2116 [−0.6368, +0.1891] | INCONCLUSIVE |
| EXP-005 | shrink A's centre, NFL receptions | 2024–26, 4,343 games | −0.0067 [−0.0108, −0.0024] | **ADVANCE** |
| | the same, NFL rushing yards | 2024–26, 1,519 games | +0.0059 [−0.1140, +0.1306] | REJECTED |
| | NFL receiving yards | (search) | nothing beat no correction | REJECTED |

What the runs say together:

1. **Receptions replicate across sports, and the gain is shape, not
   centre.** Two-stage beat direct by −0.0271 in college and −0.0270 in
   the NFL. In both sports it was *worse* at a line-like threshold and in
   mean error. A bettor prices at a line, which is why EXP-001c (real
   lines) is the test that matters.
2. **The hybrid wins college rushing as a preregistered test.** It is the
   same idea EXP-001b waits to test on NFL games after the freeze.
3. **The search found shrinkage, not a new formula.** Out of 1,680 shapes,
   the complexity price chose the plainest: the direct model's centres are
   spread about 15% too wide. That held on unseen receptions games, and
   held up where noise was planted in the tests. It points the same way as
   pricetrust and EXP-003b: our numbers run too extreme.
4. **None of this moves a pick.** The only live change is the one Ethan
   approved: the NFL board at the market's price.

### 13. Limitations and failure modes

- College targets before 2025 are short (most incompletions are
  unnamed). Even 2025→2026 carries a ten-point jump in naming into the
  holdout, which was stated before the run.
- EXP-005's holdout includes 2024–25, which were read before as
  EXP-001's holdout for A against B. They were never read for A's misses
  against these quantities, and the search read none of them.
- The 2026 slices are a few weeks only.
- The rushing-yards result shows why the score was fixed in advance:
  squared error fell while the distribution got worse.

### 14. Novelty assessment

| experiment | class |
|---|---|
| EXP-004 | 4, an out-of-sport replication of an established method |
| EXP-005's chosen equation | 5, rediscovered shrinkage |
| the search procedure | 4 |

Still no new mathematics. The spec says to report that rather than dress
it up.

### 15. Decisions

| item | decision |
|---|---|
| EXP-R05 | **wired** (NFL board), re-tested prospectively on `trust_from` |
| EXP-004 receptions (B) and rushing (H) | **advance** to college real lines |
| EXP-004 rush B and rec_yds B | **investigate** (inconclusive) |
| EXP-005 receptions | **advance**: does it add to B? |
| EXP-005 rushing and receiving yards | **reject** |

### 16. Next highest-value experiment

**EXP-001c's decision rows** (NFL receptions at real lines, games after
today). This is the test that says whether any of the distribution gains
survive at the number a book actually hangs. The box script now prints its
pace.

Then:

1. **EXP-004c:** the same at the college lines the box holds.
2. **EXP-006:** B with and without the EXP-005 shrink on NFL receptions,
   preregistered, scored on games after the freeze.

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
| EXP-003b our picks vs the market (box, 1,804 held-out picks, 7 weeks) | correction vs ours / vs market; blend vs market | log loss: ours 0.6849, corrected 0.6921, market 0.6790, blend 0.6845; every comparison FAILS its bar | **REJECTED**: the market at pick time beats our shown chance |
| EXP-001c real lines (box, development) | receptions / rec_yds / rush_yds at the books' consensus line | log loss, model vs market: receptions B* 0.6993, A* 0.6908, market 0.6837; rec_yds B* 0.7002, market 0.6933; rush_yds B* 0.7037, market 0.6937 (3,433 props) | waiting: the market beats every model so far; games after 2026-10-17 decide |
| EXP-R05 pricetrust (box) | lean our chance toward the price | NFL one-board: 0.6966 → 0.6852, 199 picks, every week better (w 1.0); MLB Most Likely paper: 0.6901 → 0.6895; Edge NFL and MLB fail | **PASSES on two books: Ethan's call** |
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
4. **On our own published picks, the market's price is the better
   forecast.** Over 1,804 held-out picks, our shown chances averaged 0.572,
   the market's 0.547, and 0.538 hit. Neither a learned correction nor a
   blend beat the market alone. That is the overclaim pricetrust.py was
   built to test a fix for.
5. **The closing total is close to unbeatable on public features.** Its
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

**EXP-001c, built after the box audit.** It prices EXP-001's models,
recalibrated, at the lines the books actually hung, against the de-vigged
market (`research/exp1_lines_box.py`).

- The box already holds 2025 and 2026 NFL props from 16 books, so it
  needs no harvest and no credits.
- 2025 and pre-freeze 2026 are development data, because 2025 was
  EXP-001's holdout and has been read once.
- Games after 2026-10-17 decide it, with the bar written in the script
  before its first run.

---

## Task 1 — data audit

### What the site already owns (the most important finding)

**Counted on the box, 2026-10-17** (`research/audit_box.py`):

- **NFL props are already stored, 2025-09-07 to today.** odds_history
  holds 1.49M NFL rows from 16 books over 332 games. That includes
  receptions on 305 games, receiving yards on 311, rushing yards on 306,
  passing yards on 272 and anytime TD on 279.
- **MLB:** 742k rows since 2026-06-01. **College:** 159k rows since
  2026-08-29. **NHL:** props only, since 2026-10-15; no NHL game lines are
  stored yet.
- **Line snapshots:** `line_history.jsonl` has 3.28M quotes from 15 books,
  2026-08-16 to today.
- **Journal:** about 28,300 settled picks and 32,366 sealed forecasts. The
  market's fair price is journaled only on the Edge book (NFL 246, MLB
  631, CFB 5). That is why EXP-003b now rebuilds it from the snapshots.
- **Outcomes:** NFL 2021–26, MLB 2021–26, NHL 2023–26, NBA 2024–25, WNBA
  2021–26 and CFB 2022–26 player logs, plus 811 UFC fights.

So **the 2025 and 2026 NFL seasons need no historical purchase.** A 2023
harvest would only add development data.

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
| B1 | Calibrate EXP-001 receptions | — | — | — | **built into EXP-001c** (logistic recalibration fitted on 2023–24) |
| B2 | Harvest NFL props | — | — | — | **not needed**: the box already holds 2025–26 |
| B3 | Score A, B and calibrated B at real lines against the de-vigged book | — | — | box | **EXP-001c, implemented**; decides on games after 2026-10-17 |
| B4 | Canonical participant table with aliases (gsis / ESPN / book spellings) | — | medium | have ids | every journal row maps to one id; a test that fails on a new unmapped name |
| B5 | Store each pick's feature vector at decision time (feature_snapshots) | — | medium | own | a pick can be re-priced from its stored features alone |
| B6 | EXP-001b scored weekly | games | none | auto | the preregistered bar |
| B7 | EXP-003b on the box (amended: market chance rebuilt from snapshots) | Ethan runs it | none | journal + line history | the bar in the script |
| B8 | MLB first experiment: two-stage strikeouts (batters faced × K rate) vs direct | — | medium | MLB Stats API on the box | **EXP-007, implemented**; validation read first, then the holdout once |
| B9 | NBA: minutes × per-minute rate, minutes from rotation/injury state | — | — | box history | **EXP-008, implemented**: the board's centre is already this; the test is the shape |
| B10 | UFC: fight-time distribution × striking rate for significant-strike props | data audit of per-fight stats | large | needs a per-fight stats source | coverage verified first |
| B11 | College: the EXP-001 protocol on cfbfastR (verified 2022–26) | — | small | have it | **done: EXP-004** (receptions B and rushing H advance) |
| B12 | EXP-001c decision rows (NFL receptions at real lines) | games after 2026-10-17 + nflverse stats | none | box | 300 receptions rows; the bar in the script |
| B13 | EXP-004c: college B (receptions) and H (rushing) at real college lines | — | — | box (line snapshots + odds_history) | **EXP-004c, implemented**; one read per question on weeks 9+ |
| B14 | EXP-006: B with and without EXP-005's shrink, NFL receptions | — | — | have it | **preregistered**; read once at the regular season's end |
| B15 | pricetrust prospective: the NFL board's rule re-tested on `trust_from` | four weeks of picks after 2026-10-17 | none | box | every held-out week no worse, pooled better — or the switch goes off |
| B16 | Canonical participant table (B4) feeding every join above | — | medium | have ids | as B4 |
| B17 | EXP-007b: strikeouts at the MLB lines the box holds (odds_history from 2026-06-01) | — | — | box | **EXP-007b, implemented**: decides on EXP-007's holdout starts, once |
| B18 | EXP-R06: thin board picks priced from the main lines | settled weeks of thin picks | none | box | pricetrust's bar, one read; a pass goes to Ethan |
| B19 | EXP-009: NHL shots, points and blocks, a shape built from ice time against the board's count | — | — | box | **EXP-009, implemented**; validation first, holdout once |

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

0. **Done: the NFL board shows the market's number where ours ran above
   it** (your "yes nfl board").
   - Off switch, no deploy needed: `sudo ./deploy/setenv.sh QB_PRICE_TRUST
     off`, then `sudo systemctl restart qellys`.
   - The journal keeps our pre-price chance (`trust_from`), so pricetrust.py
     re-tests the rule on picks made from today on.
   - One consequence follows your 10-07 rule: a pick the price puts under
     50% is held back unless the matchup read backs it. It still rides on
     paper in the Held bucket.
1. **MLB Most Likely paper** passed pricetrust too, by less (0.6901 →
   0.6895). Recommended: not yet. Give it more weeks.
2. **No credits needed.**
3. **SQLite stays** (recommended) or the lab moves to Postgres.
4. **Vendor samples:** still not needed.

### Box commands (round five)

The same list, in order, is block CP of `docs/WHEN_YOU_ARE_HOME.md`.
Every line is read-only. `research/box_round.py` runs lines 2 to 8 in one
command, each in its own process and under its own heading, and never
passes `--holdout`.

```
cd /srv/qellys && git log --oneline -1
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/thinmarket_box.py
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp1_lines_box.py | tail -20
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp7_mlb_strikeouts_box.py
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp7b_mlb_strikeout_lines_box.py
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp4c_college_lines_box.py
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp8_nba_shape_box.py
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp9_nhl_shape_box.py
```

1. The box has today's code.
2. EXP-R06. It says NOT YET until three held-out weeks of settled thin
   picks exist.
3. EXP-001c. Run it Tuesday or later.
4. EXP-007, validation only. The holdout (`--holdout`) is read once, after
   this paste has been checked.
5. EXP-007b, development only; its decision (`--holdout`) reads EXP-007's
   holdout starts at the books' lines, once.
6. EXP-004c. Development numbers now; each question decides as the
   college weeks after the freeze complete.
7. EXP-008, validation only. Its holdout (`--holdout`) is read once,
   after this paste has been checked, as EXP-007's.
8. EXP-009, validation only, the same way.

At the NFL regular season's end (January), EXP-001b and EXP-006 read once:

```
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp1_two_stage.py --prospective
cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp6_shrink_b.py
```
