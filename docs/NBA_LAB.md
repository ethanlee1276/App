# The NBA lab — what two full seasons of play-by-play say about our picks

Ethan, 2026-11-04: *"work on the nba most likely and edge bets. Let's find
and invent more tools and data and sources to make better picks ... look at
how we kept looking for data and tools and resources for nfl to make better
picks and let's do that for nba. I know we are missing stuff."*

The NFL got better by measuring every idea on games the model never saw
before it moved a number. This is the same for the NBA: a lab with two full
seasons of the league's own play-by-play, every idea fit on one season and
judged on the next, and only what held up on the board.

## The data

- **Two full regular seasons of the NBA's own play-by-play**, 2024-25 and
  2025-26 (1,230 games each), in exactly the format our build already reads
  from cdn.nba.com. Taken from a public dataset on GitHub
  (`shufinskiy/nba_data`, the `cdnnba_2024` and `cdnnba_2025` files) for
  research only: the live site does not read it.
- **`engine/nba/stints.py`**, new: rebuilds who was on the floor every
  second from the substitutions. 2,459 of the 2,460 games rebuilt clean.
  Every team's floor time is exactly five players for the whole game,
  overtimes included, and the box scores it derives sum to every final
  score. From the floor it also counts what a box score cannot: each
  player's rebound chances (misses while he was on), his teammates' made
  shots while he was on (assist chances), the possessions he played, garbage
  time, and the officials who called each foul. The box already downloads
  this play-by-play every night for the shot charts; this is the rest of it.

## How each idea was judged

Every player-game with 10+ minutes and 5+ earlier games for his club, about
15,000 a season. The prediction is the board's own shape: his per-minute
rate times minutes, with only games BEFORE the one being predicted. Rate
ideas were judged with the minutes he actually played, so a better rate
cannot hide behind a minutes guess. Constants were chosen on 2024-25 and
the score is 2025-26, which the fit never saw.

## What held up, and is on the board

**Shooting, luck taken out** (`engine/nba/shooting.py`, on). Points and
threes rebuilt from shot volume at the player's long-run percentages, not
his last twenty games' makes. Threes are his attempts a minute times a 3P%
over his last 60 games, shrunk toward the league's by 250 attempts. Points
are twos, threes and free throws, each make rate shrunk the same way (150,
250 and 50 attempts). Error on 2025-26, the production module itself:

| Market | Closer by |
|---|---|
| Threes | 1.68% |
| Points | 0.99% |
| Pts+Ast | 0.86% |
| Pts+Reb | 0.64% |
| PRA | 0.56% |

Attempts are a player's role and his coach's choice; makes are that plus
luck. Twenty games is about 100 threes for a starter, and a 3P% over 100
attempts swings ±5 points on luck alone. A board priced on raw makes calls
a hot shooter's over an edge the market has already discounted. The pick
page shows it as its own step, "Shooting, luck taken out".

## What held up, and waits for one check on the box

**The spread that follows the projection** (`hoops.NBA.sd_power`, behind
`QB_NBA_SPREAD=1`). One CV per stat gives a 5-point bench line and a
28-point star line the same relative width. The box fits that CV as the
median of every player's game-to-game spread, garbage-time nights and all,
which makes it wide: 0.72 for points on these two seasons (`hoops_fit`
on the replica below). The truth around our projection runs from about
1.0 at a 4-point projection down to 0.39 at 20. Variance = a ×
projection^c, fit on 2024-25, judged on 2025-26 at lines from half the
projection to one and a half times it:

| Market | Brier | Overs on lines well under him (Most Likely's bets): said → happened, before → after |
|---|---|---|
| PRA | −2.07% | 76.5% → 80.3% said; 80.3% happened |
| Pts+Ast | −1.97% | 74.2% → 78.0% said; 77.7% happened |
| Pts+Reb | −1.73% | 75.4% → 78.8% said; 78.6% happened |
| Points | −1.72% | 72.0% → 75.8% said; 75.0% happened |
| Assists | −1.69% | 65.8% → 71.6% said; 72.3% happened |
| Reb+Ast | −1.13% | 75.7% → 78.7% said; 78.4% happened |
| Rebounds | −0.82% | 70.6% → 74.7% said; 75.1% happened |

Threes stay on their CV (+0.3% Brier, no better). It waits because the
stored calibration curves were fit on the CV spread, probably to stretch
its too-wide probabilities. Switching the spread on without a refit could
stretch them twice. `nbalabcheck.py` measures it on the box's own games
and closing lines, through today's calibration and raw. The runbook step
(JY) turns it on together with an NBA refit.

## Replayed through the board itself

The lab's numbers come from its own scripts. To be sure the production
code does the same, the two seasons were loaded into a copy of the box's
`player_game_logs` and `nbalabcheck.py` was run against it: the board's own
replay (`engine/hoopsreplay`: its projection, minutes model, clamp and
gates), at the spreads the build fits from those logs (points 0.720,
rebounds 0.697, assists 0.891, PRA 0.588). No calibration was stored
there, so its two reads are the raw one. About seven minutes.

- **Shooting:** projections closer in 5 of 5 markets (points 6.422 →
  6.393, threes 1.398 → 1.387, PRA 8.140 → 8.120), and the Brier lower in
  all five. Smaller than the lab's 1.0-1.7% because the board's projection
  carries its minutes guess, which the lab held fixed to judge the rate.
- **The spread, near the line:** Brier lower in 6 of 7 markets on
  half-point lines, rebounds level.
- **The spread, on Most Likely's kind of over** (lines at 0.5, 0.65 and 0.8
  of his projection, about 85,000 overs a market): Brier lower in all 7, by
  1.1% (rebounds) to 4.1% (PRA). Points: the new spread called 18,602 overs
  80% or more (85.8% on average) and they hit 85.4%; today's spread called
  those same overs 74.0%, never more than 77.7%. Assists: 8,218 overs at
  85.3% that hit 84.0%, against 66.8%. Where it is off: points overs in the
  middle, called 65% and 75%, hit 61% and 72%. That is what the refit's
  calibration is for, and why the switch waits for it.

**Two things the replay itself got wrong, found on the way:**

- **The replay priced with the inherited spreads, not the fitted ones.**
  `hoopsreplay.replay` used `hoops.NBA`'s defaults (0.30 for points) while
  the board prices with `hoops_fit`'s (0.72). The fitters' walk already
  used the fitted ones. The replay takes a `tune` now, and the check hands
  it the board's; the Lab's weekly replay still uses the defaults (next).
- **Half the replay's lines were whole numbers.** With no closing line
  stored, the line was his recent average rounded, a whole number half the
  time. A rebound or assist count lands on a whole number about one time
  in five (758 of 4,442 rebound lines), the push is dropped from the score,
  and the board's chance never counted a push. On those lines alone the new
  spread looked 2.5% worse for rebounds and assists; on half-point lines it
  was level. The check scores half-point lines only, and the replay's line
  is always a half point now (the same fix as the calibration's, below).
  Rerun that way the verdict is the same: ready for the refit.

## The minutes model, measured (the game script)

Ethan, 2026-11-04: *"I want to make sure we're picking the right bets,
reading the right scripts, picking the right models ... everything's tuned
in."* Minutes are most of a prop's outcome, and the board's minutes model
(`engine/nba/minutes`) carried a written spec's numbers for rest and
blowouts that had never been checked. Every player-game of both seasons
went through the board's own minutes code: each game's rest label from
`nba_build.rest_from`, and for blowouts his minutes by his club's FINAL
margin, read through the board's own margin ~ Normal(spread, 11.5), so no
historical spreads were needed (the history database stores none for the
NBA, and no free source has them). Players who would carry props (15+
minutes a game), fitted on 2024-25, judged on 2025-26:

| Minutes model | Error on 2025-26 |
|---|---|
| As built (the spec) | 6.404 |
| Rest measured | 6.314 |
| + blowouts measured | 6.263 |
| + the newest games weighted more (0.60 / 0.25 / 0.15) | 6.228 |
| + a bench player's minutes trimmed 2% | 6.209 |

- **Rest.** A man who suits up on a back-to-back or a third game in four
  nights plays about his usual minutes, 0.99-1.03 of them (both seasons the
  same). The spec cut 4-8%, on a third of the schedule, which is an under
  lean. A long break (no game in six days) costs about 4%. Every
  back-to-back was labelled "home" by the build, so the road haircuts never
  ran; with one measured value for both, the label no longer matters.
- **Blowouts.** Starters play about 6% over their usual in close games and
  9-14% under it in 25-30 point blowouts. Through the spread, a favourite's
  starters lose 1% at 6 points and 5% at 15, not the spec's 2% and 14%; the
  underdog's share of the haircut measured 0.58-0.70 (0.6 stands); rotation
  bench players gain nothing, where the spec gave them up to +20%.
- **The stats.** Rate times these minutes, judged on 2025-26: points 0.81%
  closer, rebounds 0.80%, assists 0.72%, PRA 1.32%, and the average miss
  roughly halved.
- **Pace** (`engine/nba/context.env_factor`, tonight's total against the
  league's average) helps by 0.1-0.2%. Read against the totals of his own
  recent games instead (his rate already carries his club's pace), 0.02-0.04%
  more: real, too small to need the pre-game totals the box does not store.

The WNBA inherits the measured haircuts (it has no sample of its own) and
keeps its own recency weights.

## The scout, and the rotation's news

Ethan, 2026-11-04: *"I don't know much about NBA, so I want to make sure
we're picking the right bets."* The football scout (engine/scout) names the
spots a football person hesitates in; `engine/nba/scout` is the same for
basketball: fourteen situations (a starter's over in a projected blowout,
an under in a projected shootout, an over on a back-to-back, an under while
a regular teammate sits, an over the night one returns, a minutes jump, a
minutes drop, his first game back, a hot three-point run, games that swing
widely, a man barely into his season, a line far from his last five), with
every threshold written down before any was measured.

**How each was measured.** Every game a man of 15+ minutes a game played,
5+ games for his club first, both seasons; counted as a book settles it (a
man who played two minutes is action; my first pass kept only 10+ minute
games, which leans to the over and was thrown out). At a half-point line
off his last five: first BEFORE ANY MODEL (does the flagged side hit less
than the same side unflagged?), then AFTER OURS (do flagged picks hit less
than our number said, against unflagged picks on the same side?).

**What it found** (after our number, flagged against unflagged, 2024-25 /
2025-26; before the new rules):

| Flag | Before any model | After ours |
|---|---|---|
| under, a regular teammate sits | -6.8% / -6.3% | -7.2% / -6.6% |
| over, a regular returns | -4.7% / -4.4% | -4.0% / -3.8% |
| under, his minutes just jumped | +2.6% / +1.9% | -3.7% / -4.3% |
| over, his minutes just dropped | +1.4% / +1.1% | -4.8% / -5.5% |
| over, his first game back | -4.8% / -3.6% | -6.1% / -5.5% |
| under, a projected shootout (total 236+) | -3.9% / -3.6% | -2.2% / -3.4% |
| over, a hot three-point run | -6.0% / -7.1% | +4.7% / -1.5% |
| over, a starter in a projected blowout | +1.6% / +1.4% | +2.3% / +3.0% |
| over, a back-to-back | +0.2% / +1.6% | -1.2% / +1.1% |
| games that swing widely (either side) | — | -1.3% / -1.4% |

Most of what goes wrong after our number is MINUTES the board did not
read, so four candidate minutes rules were written, each with its bar set
before its run: fitted on one season (beside a level factor, because the
calibration downstream corrects the board's overall level and a rule must
not take credit for it), judged on the other, kept only if the squared
error of minutes AND points fell in the games it touches in both seasons.

| Rule (the board's value) | Minutes, 2024-25 / 2025-26 held out | Points |
|---|---|---|
| First game back, 1 missed (x0.96) | -1.3% / -2.4% | -0.5% / -1.0% |
| First game back, 2-4 missed (x0.92) | -5.3% / -7.9% | -1.4% / -2.3% |
| First game back, 5+ missed (x0.84) | -19.7% / -35.2% | -8.2% / -8.6% |
| Second game back after 2+ missed (x0.96) | -0.3% / -2.6% | -0.4% / -0.7% |
| A role that jumped: base 40% to the newest three | -7.0% / -4.8% | -1.6% / -1.7% |
| A regular's return: a quarter of his minutes back | -1.2% / -2.4% | -1.0% / -0.5% |
| A role that dropped (0.2-0.4 toward the newest three) | **+0.6%** / -5.0% | **+0.5%** / -1.5% |
| Teammates' rate up when a regular sits | fitted 0 both ways | — |

(Negative is better.) The drop failed 2024-25 and is not built; the rate
term found nothing to fit. The other four are on (`hoops.NBA`; the WNBA
keeps them off, unmeasured). Together, each season scored on values fitted
on the other (vacancy off, as the board runs until the box saves it):
minutes error 6.17 to 6.09 and 6.20 to 6.11 over every priced game; points
0.6% / 0.6% closer, rebounds 0.5% / 0.7%, assists 0.3% / 0.6%, threes 0.3% /
0.2%, PRA 0.9% / 1.0%; Brier at the half-point line 0.2280 to 0.2272 and
0.2279 to 0.2270. With the vacancy at k 0.30 under them, about the same
again on top of what the vacancy gives (minutes 6.15 to 6.07, 6.21 to 6.12;
PRA 1.0% / 1.2%). `nbarules.py` asks the box's own seasons the same question
at the board's values, read-only (on the replica: every rule better in both
seasons, minutes 1.8-10.1%, points 0.2-2.4%).

**The flags after the rules**, as the board runs them (the four rules on,
the role-drop rule not; teammate-out minutes off / on at k 0.30), and their
verdicts (`scout.VERDICT`):

- **Warnings, on the card** (both seasons the same way):
  - an under while a regular teammate sits: -6.7% / -6.3% with the vacancy
    off, -3.1% / -2.9% with it on;
  - an over after his minutes dropped: -4.1% / -4.8% (-3.9% / -4.7%). The
    drop mostly holds, as the role-drop rule said, but that rule hurt one
    season's squared error, so the card says it instead of the number;
  - an over the night a regular returns: -2.6% / -2.8% (-2.4% / -2.4%),
    after the return rule took out about half of it;
  - an under in a projected shootout: -2.5% / -3.4% (-1.5% / -2.9%);
  - games that swing widely: -0.9% / -1.2% (-0.6% / -1.1%);
  - a man under five games into his season: -1.9% (-1.7%), one season.
  Each card says what it measured, as a "Scout:" line, for the side and
  rung that card takes.
- **Priced**, so the card does not warn twice: his first games back
  (-0.8% / -1.7% after, from -6% before), a role jump (+0.3% / -0.4%), a
  hot shooting run (the shooting read: +3.6% / -2.6%).
- **Refused**, not warnings at all: a starter's over in a projected blowout
  (+2.4% / +3.1%: it hits MORE often than our number says), an over on a
  back-to-back (-0.7% / +0.9%).
- **Unmeasured**: a line far above or below his last five (the seasons hold
  no book lines; at the lab's own line these only mark low counts rounding
  up or down), an over in a projected grind (515 picks in one season, none
  in the other).

**The vacancy, held out on the lab's seasons.** `nbavacancy.py --heldout`
against the replica of the two seasons: k 0.30 fitted on the other season
both ways, minutes 5.8% / 5.3% closer and points 2.7% / 2.5% in fresh-absence
games: HOLDS. The board fills the slot only once the box saves its own
verdict: the weekly deep refit runs that check itself since 4 November
(runbook KC), and the slot fills the week its test holds on the box.

## Who inherits a sitting regular's minutes

The teammate-out minutes (`engine/nba/vacancy`) handed k x the absent
regulars' minutes to the rotation in proportion to each man's own base
minutes, so the stars took the most. On the floor it goes the other way:
a star is already near his ceiling, and the minutes go to the men with room
to play more, the bench and the back of the rotation. Four rules for who
takes them, each fitted on one season (its constant and k) and judged on
the other, against sharing by base minutes on the same 23,690
teammate-games in 2,351 fresh absences (the board's own minutes model,
`nbavacancy.py`'s rows):

| Rule (who takes the minutes) | Minutes, 2024-25 / 2025-26 held out | Points |
|---|---|---|
| Room: base x (34 - base), k 0.40 | **+7.6% / +6.4%** | **+1.3% / +1.5%** |
| A bench man when a starter sits (x4), k 0.30-0.35 | +3.1% / +2.8% | +0.4% / +0.9% |
| A man like him (rebounds, assists, threes a minute) | +0.3% / +0.5% | +0.2% / +0.2% |
| Bench man and a man like him together | +3.1% / +3.2% | +0.7% / +0.9% |

(Positive is better than sharing by base.) Room won both ways with the
same cap and k fitted on either season, and it is on (`vacancy.weight`).
Against the empty slot, the box's own check (`nbavacancy.py --heldout`)
now reads minutes 12.0% / 10.3% closer and points 3.6% / 3.5% in those
games, against 4.7% / 4.2% and 2.3% / 2.1% shared by base minutes. A
verdict filed under the old rule no longer fills the slot (`vacancy.k_for`
reads the rule it was fitted under); the weekly deep refit refits it (runbook
KC). A regular's return still takes its minutes back by base minutes, as
that rule was measured.

## Measured, and not built

The same honesty the NFL's refusals get:

- **A teammate's absence, read from his own with/without history.** When a
  regular sits, his teammates do score more a minute: the board under-reads
  them by 0.4 points a game. But each player's own with/without record,
  from whole games or from every minute the regular sat, is too noisy: it
  cut the bias and lost more in accuracy (points error 1-16% worse). Handing
  the absentee's share of the team's output to everyone left helped
  regulars' absences a little (points 0.41% in those games). With the
  build's own definition of an absence (anyone ruled out who played lately,
  mostly bench players), it fell to 0.07% and overshot. Not built; the
  minutes an absence opens stay with `engine/nba/vacancy`.
- **Officials.** The crew's free-throw rate, from the officials who called
  each foul, moved no player's points, rebounds or assists on a season it
  never saw.
- **Back-to-backs and home or away, on the rate.** Nothing beyond what the
  rate already holds (the minutes model reads rest separately).
- **Last five games over last twenty.** Nothing: the twenty-game rate
  already holds what recent form adds.
- **Rebound chances.** Neither the opponent's miss rate nor his own share of
  the misses moved rebounds beyond what the defence step already reads.
- **The opponent per possession instead of per game.** Per game, which the
  board already uses (`engine/hoopsdvp`), read as well or better for points,
  rebounds and assists. One exception: for threes, the three-point ATTEMPTS
  a defence allows per possession added 0.1% beyond the shooting read. That
  is a candidate for the defence step's own fitter (`hoopsdvpfit.py`).
- **Teammates' shooting luck, for assists** (his assists regress when his
  teammates have shot hot): 0.17%. Small, and it needs the floor data on the
  box. Parked.

## The calibration, fitted near the line and applied everywhere

The NBA's stored corrections are fitted by the deep refit on the fitters'
walk: every game priced at one line, his recent average rounded. Two things
about that, measured on the replica with `calibrate.fit` itself:

- **Half those lines are whole numbers**, where a count pushes and the
  chance never counted the push. On them, rebound overs hit 54.5% where the
  chance said 43.7% (assists: 55.4% against 40.2%); on half-point lines
  53.8% against 52.7%. The fit takes in both, and its lean toward the over
  roughly doubles: rebounds +0.18 where half-point lines alone say +0.08,
  assists +0.22 against +0.14 (log-odds; +0.1 is about 2.5 points at 50%).
  Held out (fitted on 2024-25, judged on 2025-26 at half-point lines), the
  correction fitted the old way was worse than none for rebounds (Brier
  0.2411 against 0.2399 raw), assists (0.2399 against 0.2397) and threes
  (0.2123 against 0.2103), saying rebound overs 56.6% that hit 52.6%.
  Fitted on half-point lines: 0.2396, 0.2385 and 0.2107, rebound overs
  53.9%; better than the old fit in rebounds, assists, threes, steals and
  turnovers, level in points and PRA, 0.0001 worse in blocks. **Fixed
  (`hoopsreplay._naive_line`): the practice line is always a half point**,
  and the next weekly refit fits on it.
- **The temperature is fitted near the line and applied to every line.**
  Near the line the model is over-confident (a projection's gap from his
  recent average is part noise), and the fit pulls every chance toward 50%:
  T = 1.76 for points, 1.68 for PRA on today's spread. On Most Likely's
  kind of over that is the wrong way. Today's spread plus its own fitted
  temperature takes the points ladder's Brier from 0.2113 to 0.2217. With
  the new spread its refit's temperature (1.40) takes 0.2045 to 0.2069:
  the overs it called 85.8% (hit 85.4%) come out 83.7% and hit 91.3%.
  Even so, new spread and refit (0.2069) beat today's spread and
  calibration (0.2217) by a wide margin, which is why the switch is worth
  making before this is fixed.

## Next

- Done 2026-11-04 (runbook KC): the box runs `nbavacancy.py nba --heldout
  --save` (the teammate-out minutes) and `nbarules.py --save` (the
  rotation's rules on its own seasons) itself, every week, right before the
  NBA's refit; the switches follow the verdicts (`engine/nba/switches`).
- A teammate sitting still costs unders 3% after the vacancy: the minutes
  go somewhere specific (his backup, the next man in his position) and the
  shots to the stars, where the vacancy shares both by base minutes. The
  floor data would say who inherits what; the Most Likely record's own
  correction (likelycal) lowers what keeps over-claiming meanwhile.
- Done 2026-11-04 (runbook KB): the record-learning that grades the NFL's
  flags (`engine/likelyctx`, held out, by the board learning every few
  hours) grades the NBA's. `engine/nba/scoutrecord` rebuilds each settled
  NBA Most Likely pick's situation from the stored games, the way the
  board read it: his twenty games before the day for the club he played
  for, his season's games, whether he missed the club's last game, the
  club's rest, a regular who sat and one who came back (read off who
  played, as the lab read them), and the books' last pre-game spread and
  total. Every flag a pick raised is fitted, the card's six and the rest:
  a refused flag the record proves gets its number too. On the lab's
  seasons it reads 1,200 picks in under four seconds. The NBA build now
  keeps each game's spread and total (`engine/lineledger`), so the
  game-script flags can be graded from 4 November on.
- The record so far (4 November): Most Likely 714-373 (65.7%) claimed at
  62.0%, both sides beating their claims, and every market in profit.
  The record's corrections (likelycal by maker and side, likelyctx by
  flag) only ever pull a claim toward its price, so an under-claiming
  board is left alone. Raising a claim the record says is too low is a
  different correction with its own bar, and two weeks is too little to
  set one.
- Done 2026-11-04 (runbook KC): the box runs `nbalabcheck.py --part spread
  --save-verdict` itself every week; on `spread: ready for the refit` the
  NBA's refit fits its calibration with the spread on and only then throws
  the switch, the order runbook JY gave.
  Its "through today's stored calibration" ladder lines show the second
  point above on the box's own corrections.
- The football walk (`logwalk._naive_line`) uses the same whole-number
  line, so the NFL and college count markets (receptions, attempts,
  completions) likely carry the same lean. Football has its own fits and
  its own rules; measure it there before changing it.
- A correction for Most Likely's lines that is not the near-the-line one:
  the walk priced at the ladder's lines too, or a correction that knows
  how far the line is from his projection.
- The Lab's weekly replay prices with the inherited spreads, not the ones
  the board uses; handing it `hoops_fit`'s would make its NBA numbers the
  board's.
- The floor data on the box: store each game's stints from the play-by-play
  the nightly already downloads, so the lab's floor-based reads can be
  re-measured on our own games and the page can show on/off numbers.
- Threes allowed per possession in the defence step (above).
