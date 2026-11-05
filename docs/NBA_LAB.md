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

## Twenty games is not enough for a rate

The board reads every per-minute rate from his last twenty games for the
club. Twenty games is about 600 minutes for a starter: some 20 blocks for
a forward, 15 steals for a guard, so a hot or cold fortnight moves the
number as much as a real change does. The read now goes past the twenty
(`engine/nba/rates`): his older games (his last sixty, any club) join it at
a weight a minute, and some minutes of the league's rate for his role
(starter or bench) are added, so a man with a thin twenty leans on what a
man like him does:

    rate = (V20 + w x V_old + kappa x league) / (M20 + w x M_old + kappa)

Fitted on one season and judged on the other, both ways (every player-game
of 10+ minutes with 5+ earlier games for his club, 40,327 of them; his rate
times the minutes he played):

| Stat | w, kappa (both seasons) | Squared error, 2024-25 / 2025-26 held out | Through the board's minutes (priced rows) | Thin twenty (under 400 min) |
|---|---|---|---|---|
| Steals | 0.75, 400 min | **+4.5% / +4.4%** | +3.3% / +3.3% | +6.7-7.3% |
| Turnovers | 0.3, 100 | **+3.3% / +3.4%** | +2.3% / +2.4% | +5.9-6.2% |
| Blocks | 0.5, 100 | **+2.7% / +4.0%** | +2.2% / +3.3% | +3.2-5.6% |
| Rebounds | 0.5, 25 | **+2.0% / +3.2%** | +1.3% / +2.1% | +2.9-5.7% |
| Assists | 0.3, 25 | **+1.6% / +2.4%** | +1.0% / +1.7% | +2.8-4.9% |
| Rebounds + assists | (the two parts) | +1.9% / +2.8% | +1.1% / +1.8% | |

How far back to read was chosen the same way (40, 60 or 82 games: 60, the
shooting read's own reach). AS CHANCES, through the fitters' own walk (the
board's projection priced at a half point under his last eight games'
average, Brier with a temperature fitted on one half of the games and
judged on the other): steals 0.7-1.3% better, blocks 1.1-1.5%, turnovers
0.9-1.2%, rebounds 0.7%, assists 0.6%, rebounds + assists 0.5%, PRA and
points + rebounds 0.1%, points + assists 0.0%, and as much with the
temperature fitted before the change as after it, so the board gains from
its first build, not only once the weekly refit has run.

A twenty that never once recorded the stat (a guard's blocks) had a rate
of nothing, and the board called the under a certainty; it now takes the
read past the twenty as its rate (`rates.lift_zero`).

POINTS AND THREES ARE LEFT ALONE. Read the same way (his shots a game past
the twenty, the makes as the shooting read has them), points landed 0.8% /
1.4% closer as a number and 0.1% WORSE as a chance, after a refit as well;
threes moved 0.3%. The shooting read (above) keeps them. The combos'
points stay the shooting read's, their rebounds and assists are read past
the twenty.

On the box: on by itself (`QB_NBA_RATES`; the heartbeat's
`nba_switches.rates`), and the weekly deep refit asks the box's own stored
seasons the same question every week before the NBA's fitters
(`nbarates.py --save`, runbook KD): if a season big enough disagrees about
any of the five stats, it turns itself off. On the lab's seasons that check
reads rebounds +2.1% / +2.4%, assists +1.7% / +1.8%, steals +4.6% / +3.7%,
blocks +2.6% / +3.2%, turnovers +3.4% / +2.8%: HOLDS.

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
- **The absent man's shots to the stars** (2026-11-04). With his minutes
  shared by room (above), the stars' points in fresh-absence games are
  already right: the top third of teammates by share of the club's points
  runs -0.00 a game against the board, the bottom third +0.23. Handing his
  share of each stat to the teammates who play, in proportion to their own
  share raised to a power (the power and the amount fitted on one season,
  judged on the other): points +0.33% / +0.18%, assists +0.36% / +0.18%,
  rebounds and threes nothing, and the best power was 0 or 1 (equal shares
  or a flat bump), never "to the stars". Too small to move a number.
- **The other club short-handed** (2026-11-04). The opponent's fresh
  absences (its absent minutes, or the absent men's share of the stat, or of
  steals and blocks) as a step on every player's number, on top of a defence
  read: our players did slightly WORSE against a short-handed club in every
  market. That is the game script: a short-handed opponent makes a bigger
  favourite and a blowout, which the board's own spread prices and the lab
  held neutral. Under 0.35% everywhere. Not built.

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

### Fixed: the alternate rungs carry their own correction *(11-04)*

The walk now prices every game twice: at its practice line, as before,
and raw at the rungs Most Likely lives on, the half-point lines one and
one and a half curve-widths either side of his projection (the board's
own width, whichever spread is on; `hoopsreplay.ladder_lines`). The
weekly refit's temperature fit (calibrate.py) fits those rungs as their
own key, `<market>@ladder`, beside the market's own, with the same
fitter (`calibrate.fit`: a temperature or a curve, whichever wins its
held-out slice) and the same 200-sample floor. A rung on the board is
priced through it (`pipeline.rung_probs`); the main line keeps the
market's key, and a rung with no ladder key takes its market's
correction exactly as before (`calibrate.ladder_key`).

Measured with that production fitter on the replica (the walk's 30,000
most recent games a market and their 49,000-120,000 rungs; each half's
games fit both keys and the other half is judged; Brier on the rungs
against no correction at all; first half fitting / second half fitting):

| Market | The market's own key on the rungs | The ladder key on the rungs | Rungs called 70%+: said / landed, own key → ladder key |
|---|---|---|---|
| Points | +15.0% worse (T 1.56) / level (T 1.00) | **1.6% / 2.6% better** | 78.7 / 90.2 → 89.1 / 89.9 |
| Rebounds | +1.6% (T 1.12) / level | **0.7% / 0.3%** | 86.3 / 90.6 → 90.6 / 90.8 |
| Assists | +5.3% (T 1.26) / +4.3% (T 1.20) | **1.3%** / level | 81.4 / 89.9 → 90.4 / 90.0 |
| Threes | level / level (T 1.00) | **0.9% / 0.5%** | 85.8 / 88.2 → 88.6 / 88.1 |
| PRA | +7.4% (T 1.32) / +11.5% (T 1.46) | **2.2% / 1.7%** | 82.9 / 90.6 → 91.0 / 91.1 |
| Points + rebounds | +7.8% (T 1.34) / +7.8% (T 1.36) | **2.0% / 2.2%** | 82.6 / 90.4 → 90.5 / 90.7 |
| Points + assists | **+64% (a curve)** / +13.1% (T 1.54) | **2.5% / 2.5%** | 71.5 / 89.5 → 90.4 / 90.4 |
| Rebounds + assists | **+53% (a curve)** / +5.0% (T 1.24) | **1.9% / 2.6%** | 72.3 / 94.9 → 91.1 / 91.1 |
| Turnovers | +0.2% / +1.1% (T 1.08) | **1.6% / 1.5%** | 84.1 / 88.4 → 88.6 / 88.4 |
| Steals | level | 0.1% / 0.1% | 87.4 / 88.1 → 88.5 / 88.0 |
| Blocks | level | level / 0.2% | 86.1 / 86.4 → 87.5 / 85.8 |

The near-line correction made the ladder worse in 14 of the 22 fits; the
ladder key made it better in 20 and left it level in the other two. Two
of the near-line fits chose a curve, and a curve learned near 50% has
nothing to say about 85%: on points + assists it flattened the ladder so
far that half the rungs the raw model called 70%+ fell under 70%
(rebounds + assists: three in four), and the rest claimed 71.5% while
landing 89.5%. That is Most Likely's NBA board in one line: picks that
land about 90% shown as 72-86% chances, so too few clear a tier and fewer
still reach its top. Read the other way, the ladder key is the wrong
correction at the line itself (worse there than the market's own in 17
of the 22 fits, by up to 6.1%), which is why the main line keeps its key.
Steals and blocks barely move either way.

Nothing to run: the next weekly refit fits both keys (runbook KF), and
until it has, every rung prices exactly as it did.

## Who starts tonight *(11-05)*

The board reads a man's minutes from his last twenty games whatever he
did in them, and his role from his newest one: started, or came off the
bench. On the replica's two seasons, every priced player-game (15+ minutes
a game over his last ten) through the board's own projection, the vacancy
at k 0.40 and a regular's return included:

| His newest game → tonight | 2024-25: share of games, miss (played − ours) | 2025-26 |
|---|---|---|
| Bench → started | 4.6%, **+3.6** min | 4.9%, **+3.6** |
| Started → bench | 4.7%, **−4.2** | 4.9%, **−3.8** |
| Bench → bench | 34.2%, −1.9 | 35.3%, −1.8 |
| Started → started | 56.5%, −0.0 | 54.9%, −0.2 |

The one game in eleven where he does the other thing carries a sixth of
the board's squared minutes error. Knowing tonight's five outright (the
oracle: each role's miss fitted on the other season as a shift) takes
**6.0% / 5.5%** off the minutes error over every priced game and
**1.2% / 0.9%** off points, against a level-only shift fitted the same
way. The five is confirmed half an hour before the tip, after most of the
board's prices are posted, so the question was how much of that is known
earlier. A good deal of it:

| Before the tip | 2024-25 | 2025-26 |
|---|---|---|
| Bench last game, one of his club's last five not playing tonight: started | 27.5% | 27.0% |
| Bench last game, the five all playing: started | 3.1% | 3.3% |
| Started last game, a regular back who started before he sat: to the bench | 19.6% | 18.8% |
| Started last game, nobody like that back: to the bench | 6.1% | 6.7% |

And his own starts lately say which way his base is wrong: a man back on
the bench who started half or more of his last ten played 2.6-4.0 minutes
under the board (his base still carries the starter's minutes), and a man
who started his newest game after mostly coming off the bench played over
it (a base made partly of bench games).

THE RULE (engine/nba/starters), six terms fitted by least squares on the
board's miss beside a level the calibration owns, and applied without the
level, through the vacancy's slot (its caps included):

| Term | Who | Minutes (fitted on both) |
|---|---|---|
| `bench_after_starts` | bench last game, x the share of his last ten he started | −3.83 |
| `bench_one_out` | bench last game, one of his club's last five ruled out | +0.89 |
| `bench_two_out` | ... two or more of them (on top) | +1.41 |
| `start_after_bench` | started last game, x the share of his last ten he did not start | +1.22 |
| `start_one_back` | started last game, a regular back who started before he sat | +0.58 |
| `fill_in_one_back` | ... x the share of his last ten he did not start (on top) | −3.19 |

THE BAR, written before the run: each season held out in turn (the six
fitted on the other), and the squared error of minutes AND points over
every priced game lower with the rule than with the level alone, in both.
HELD, through the board's own projection:

| Held out | Minutes, every priced game | Points | In the games it moves (46%) | Points Brier at the fitters' line |
|---|---|---|---|---|
| 2024-25 | **1.72%** | **0.34%** | 3.43% / 0.96% | 0.2434 → 0.2428 |
| 2025-26 | **1.28%** | **0.35%** | 2.31% / 0.81% | 0.2428 → 0.2421 |

So about a third of what the confirmed five is worth is in the board now.

ITS OVERLAP WITH THE VACANCY. Both give a bench man minutes when a starter
sits, so they were fitted together: the six at each vacancy k on a grid,
each season held out. A lower k leaves more to the six (k 0.25: minutes
2.0% / 1.7% off, points 0.19% / 0.23%) and k 0.40 the most on points
(0.30% / 0.35%, minutes 1.4% / 1.3%) — points are what is bet, so the six
run at the vacancy's own k, which the box keeps fitting (nbavacancy.py).
The coefficients fitted on either season alone sit close to these
(`bench_after_starts` −3.1 / −4.6, `fill_in_one_back` −2.6 / −3.8, the
others within 0.3).

ITS OVERLAP WITH HIS SECOND GAME BACK. A second game back after two or
more missed is often a role change too (in his first game back he came off
the bench, or started in another man's place), and with the new rule on,
nbarules.py's own measure of the x0.96 haircut fell to +0.29% / −0.02% on
points with the vacancy off: a failed bar by a hair, which would have
switched the rotation's three rules off on a box whose vacancy is not
holding. Refitted beside the new rule on a grid (0.96, 0.97, 0.98, 1.0),
the haircut is x0.97: the most off in both seasons with the vacancy on
(points +0.53% / +0.31%), and within 0.07% of the best with it off
(+0.35% / +0.15%). Every rule's bar holds in every season, both ways.

Measured, and not built:

- A base read only from his games in his newest game's role: 5.7-8.0%
  WORSE on minutes. One game in eleven the flag is wrong, and then that
  base is off by the whole gap between his two roles (6.6-7.5 minutes);
  the board's base across both roles is a hedge worth keeping.
- A logistic chance he starts (Brier 0.093-0.098 → 0.064-0.067 against
  his newest flag) mixing his two role bases: −0.1% to +1.1% on minutes,
  0.2-0.3% on points, under the six terms.
- A bench-wide level (−0.8 minutes for every bench man, 0.3% more on
  minutes): left out. The replay holds the spread at zero, so a bench
  man's base still carries his blowout minutes with nothing tonight to
  answer them; the board's blowout norms answer them on the real board.

On the box: `nbarules.py` (the weekly refit's `nba_rules` piece) replays it
on the box's own seasons in its own column and files its own verdict
(engine/nba/switches `starters`), apart from the rotation's three. Runbook
KG prints it.

## Next

- Done 2026-11-05 (runbook KG): who starts tonight, read before the tip —
  the injury report on his club's last five, a starter coming back, his
  own starts lately — moves his minutes (above).
- The confirmed five: the rest of the oracle's 5.5-6.0% (minutes) and
  0.9-1.2% (points) needs tonight's lineup, confirmed about half an hour
  before the tip, and a board rebuild after it. Neither the league's
  daily lineups page nor ESPN's game summary is reachable from the lab;
  a read-only probe on the box comes first, then the rebuild's timing
  against when picks post.
- Done 2026-11-04 (runbook KF): the alternate rungs carry their own
  correction, fitted at the rungs by the weekly refit (above); the main
  line keeps the market's.
- Done 2026-11-04 (runbook KD): rebounds, assists, steals, blocks and
  turnovers are read past his last twenty games (above), checked on the
  box's own seasons every week.
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
- The Lab's weekly replay prices with the inherited spreads, not the ones
  the board uses; handing it `hoops_fit`'s would make its NBA numbers the
  board's.
- The floor data on the box: store each game's stints from the play-by-play
  the nightly already downloads, so the lab's floor-based reads can be
  re-measured on our own games and the page can show on/off numbers.
- Threes allowed per possession in the defence step (above).
