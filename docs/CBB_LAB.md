# The college lab — five seasons of box scores against the NBA's measured pieces

Ethan, 2026-11-13: *"look at all the tools and resources and data points we
use for NBA, and obviously put that towards college basketball ... don't
stop working until you've added every single tool and feature that we have
for NBA onto college basketball."*

The college basketball board is built by the NBA's own code (`nba_build.py`
with the league `cbb`, `engine/hoops.CBB`). It started from the WNBA's
tuning, the nearest basketball measured on its own games: a 40-minute game,
the NBA's measured minutes pieces that held on six WNBA seasons, and the
WNBA's spread curve. This lab asks college's own seasons whether those
numbers describe college, and measures the ones that do not.

## The data

Every Division I regular-season box score of 2021-22 to 2025-26: 284,087
player-games of men with 15+ minutes a game and 5+ games for their school
first, across 3,530 school-seasons (60,848 school-games). The files are
sportsdataverse's public `hoopR-mbb-data` player boxes on GitHub, built from
ESPN's box scores, the same feed the board reads. They carry starters,
minutes, points, rebounds, assists and threes. This is research only; the
live site does not read them.

## How each piece was judged

As the WNBA lab did. Every player-game is projected through the board's
own code: the rows are `nbarules.cases`, the box's own check of the NBA
rules, and each projection runs through `engine/nba/pipeline.project` with
college's tuning. Each variant is scored on its own season-wide level,
because the calibration downstream owns the board's overall level and a
rule must not take credit for it. All five seasons are out of sample for
values fitted on the NBA.

## The minutes pieces: what college inherited holds

Minutes RMSE / points RMSE over every game, season by season:

| | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|---|---|
| **As shipped (the WNBA's pieces)** | **6.182 / 5.656** | **6.197 / 5.687** | **6.133 / 5.758** | **6.156 / 5.747** | **6.146 / 5.828** |
| Without the starting five's news | 6.221 / 5.660 | 6.225 / 5.687 | 6.163 / 5.758 | 6.188 / 5.748 | 6.175 / 5.830 |
| Without his first game back | 6.202 / 5.660 | 6.216 / 5.690 | 6.152 / 5.761 | 6.173 / 5.750 | 6.164 / 5.831 |
| Recent games 0.50 / 0.30 / 0.20 | 6.198 / 5.656 | 6.213 / 5.686 | 6.152 / 5.757 | 6.171 / 5.747 | 6.160 / 5.827 |
| Recent games 0.40 / 0.30 / 0.20 | 6.216 / 5.657 | 6.232 / 5.687 | 6.172 / 5.758 | 6.189 / 5.747 | 6.179 / 5.828 |
| Recent games 0.70 / 0.20 / 0.10 | 6.188 / 5.660 | 6.203 / 5.690 | 6.136 / 5.762 | 6.164 / 5.751 | 6.151 / 5.832 |

- **The starting five's news** (`STARTER_NEWS_NBA`) and **his first game
  back** (the NBA's table, 1 game missed ×0.96, 2-4 ×0.92, 5 or more ×0.84)
  each make minutes better in every season, and points are never worse over
  every game. In the games it touches, his first game back takes 15-17% off
  the minutes error and 5-6% off the points error, every season.
- **His newest games weighted 0.60 / 0.25 / 0.15** reads minutes best of the
  four weightings. 0.50 / 0.30 / 0.20 was a hair better on points
  (0.001 in four seasons) and worse on minutes in all five.

On the NBA's stricter bar (`nbarules.py`: minutes AND points better in the
games a rule touches, every season), the starting five's news makes
minutes 1.6-2.3% better every season and points 0.1% worse in three of
five. It stays on, as the WNBA's does: over every game it is never worse,
and college reads the NBA's switch (`engine/nba/switches`), so the NBA's
weekly verdict turns it off for all three leagues at once.

## Measured, and left off

| | Over every game | In the games it touches |
|---|---|---|
| A role that jumped (×1.2 the seven before, 40% of the way) | minutes better 5/5, points 1/5 | points worse in 4 of 5 |
| The same at 20% of the way | minutes better 5/5, points 4/5 | — |
| His second game back (×0.97) | minutes 0/5 | minutes worse in every season |
| A regular's return (a quarter of his minutes given back) | minutes 5/5, points 3/5 | points worse in 2021-22 |

None holds on points in every season, so all stay off, as they are for the
WNBA.

## The spread that follows the projection

The board prices each prop with one CV per stat until the NBA's spread
switch goes on (`prob.spread_on`); then variance = a × projection^c. The
WNBA's curve was what college inherited. This measures college's own, the
WNBA lab's way: every player-game above, for points, rebounds, assists,
threes, PRA and the three two-stat combos (2,272,696 stat-games), projected
by the board's own code; the curve fitted on one season and judged on the
next against the CV the box's own rule sets from the same season's logs;
overs priced at lines from half the projection to one and a half times it
through the board's own pricer (`engine/nba/prob.p_over`).

Brier change, judged season by season (negative is better):

| | 2022-23 | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|---|
| Points | −1.06% | −1.11% | −1.02% | −1.09% |
| Rebounds | −0.24% | −0.44% | −0.36% | −0.33% |
| Assists | −0.38% | −0.84% | −0.60% | −0.55% |
| PRA | −1.43% | −1.44% | −1.30% | −1.40% |
| Pts+Reb | −1.20% | −1.21% | −1.09% | −1.17% |
| Pts+Ast | −1.40% | −1.37% | −1.24% | −1.32% |
| Reb+Ast | −0.83% | −0.95% | −0.85% | −0.91% |
| Threes | +0.30% | +0.42% | +0.47% | +0.35% |

Better in every judged season in seven markets. Threes were worse in all
four, so they keep their CV, as the NBA's and the WNBA's do.

At the top end: one CV per stat called 480-650 points overs a season 80%
or more, at 81%, and they hit 70-77%. The curve called 34,000-38,000 a
season at about 85%, and they hit 82-83%.

**The values** are the fit on all five seasons, and they are what the board
carries (`hoops.CBB.sd_power`):

| | a | c | its CV at a projection of 3 / 8 / 15 / 25 |
|---|---|---|---|
| Points | 6.021 | 0.738 | 1.23 / 0.66 / 0.44 / 0.32 |
| Rebounds | 1.543 | 0.949 | 0.70 / 0.42 / 0.30 / 0.23 |
| Assists | 1.393 | 0.900 | 0.65 / 0.38 / 0.27 / 0.20 |
| PRA | 9.262 | 0.620 | 1.43 / 0.72 / 0.47 / 0.33 |
| Pts+Reb | 7.766 | 0.674 | 1.34 / 0.70 / 0.46 / 0.33 |
| Pts+Ast | 6.301 | 0.718 | 1.24 / 0.66 / 0.44 / 0.32 |
| Reb+Ast | 2.157 | 0.829 | 0.77 / 0.43 / 0.30 / 0.22 |

Points sit almost exactly on the WNBA's curve (a 5.927, c 0.735); PRA and
the combos run a little wider in college.

## One CV per stat, before the box can fit its own

`hoops_fit` measures each stat's spread from the box's stored games once
ten players have twelve games each, and the board reads that. Before then
it read the starting values in the tuning, which college had from the NBA:
points 0.30, rebounds 0.40, assists 0.43. A college line moves about twice
that, so for its first month every chance on the college board would have
been too sure of itself. The starting values are now college's own, by
`hoops_fit`'s own rule (each player's spread over his games, the median) on
the two seasons the box's backfill stores:

| | Points | Rebounds | Assists | Threes | PRA | Pts+Reb | Pts+Ast | Reb+Ast |
|---|---|---|---|---|---|---|---|---|
| One season (2021-22 to 2025-26) | 0.72-0.74 | 0.69-0.70 | 0.93-0.94 | 1.00-1.02 | 0.58 | 0.61 | 0.66-0.67 | 0.62 |
| **Two seasons pooled (the board's)** | **0.783** | **0.743** | **0.972** | **1.047** | **0.639** | **0.672** | **0.721** | **0.676** |

## The NBA's two reads, on college: both on

The NBA lab measured two reads of a player's rate on the NBA's own seasons
(docs/NBA_LAB.md). Both are the build's own code (`engine/nba/shooting`,
`engine/nba/rates`), and college's box scores store every column they read.
Every player-game above (264,882 from 2022-23 on, each judged season with
the season before's league numbers), projected with and without the read,
each side on its own level. RMSE, season by season:

| | 2022-23 | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|---|
| Points, shooting read | −0.52% | −0.50% | −0.53% | −0.42% |
| Threes, shooting read | −1.27% | −1.25% | −1.16% | −1.20% |
| Rebounds, rates read | −0.83% | −0.60% | −0.61% | −0.56% |
| Assists, rates read | −0.72% | −0.70% | −0.65% | −0.50% |

- **Shooting, luck taken out**: points and threes rebuilt from his shot
  volume at his percentages over his last 60 games (any school), shrunk
  toward the league's, with the NBA's shrinkage. College's league numbers are
  its own: the box's stored college games over the last year once it holds
  enough of them, and 2025-26's until then (3P% 33.8%, 2P% 51.9%, FT% 72.2%,
  `shooting.LEAGUE_FALLBACK_BY`).
- **Rates, read past his last twenty**: rebounds and assists a minute with
  his older games and his role's league rate, the NBA's weights, college's
  own role rates (2025-26: a starter's rebounds 0.156 a minute and assists
  0.074, a bench player's 0.159 and 0.059; `rates.LEAGUE_BY`).

Both are on for college, each under the NBA's switch (`QB_NBA_SHOOTING`, the
`rates` verdict), and each says on the pick what it was measured to do on
college.

## Not measured here

- **The margin's spread** (`margin_sd`, every spread and moneyline chance):
  the box fits it from its own college games once 200 are stored
  (`hoops_fit.fit_margin_sd`), days into the season. Until then it is the
  NBA's 11.5.
- **The blowout curves and the rest buckets**: they key on the game's
  spread, and these box scores carry no lines. College rarely plays on
  consecutive days outside its tournaments.
- **First basket** was measured on the NBA's play-by-play and stays the
  NBA's. (The scout's flags were, until 2026-11-14: below, "The scout".)

## The tournament model

Ethan, 2026-11-14: *"make it like nba cup and shit I want all the features
like this is a complete sport."* The NCAA tournament race
(`engine/ncaarace`, the Race page on college) plays the rest of the season
out: every game left, each conference's tournament, the committee's
selection and the bracket. It rests on three things, each measured here on
the hoopR schedules (`mbb/schedules/parquet/mbb_schedule_{2023..2026}`):
every Division I game of 2022-23 to 2025-26 (6,261, 6,249, 6,299 and 6,318),
with ESPN's neutral-site flag, each conference tournament's billing ("SEC
Tournament - Final") and each NCAA tournament game's seeds.

### The ratings (`engine/cbbratings`)

Points better than an average Division I team on a neutral floor, adjusted
for every opponent, each margin capped; last season's rating counts as a few
games of this one. The home court and the small schools' level, fitted on
each full season:

| | 2022-23 | 2023-24 | 2024-25 | 2025-26 | **Carried** |
|---|---|---|---|---|---|
| Home court (points) | 3.20 | 2.83 | 2.93 | 2.65 | **2.8** (the last three) |
| A school below Division I | −22.1 | −22.8 | −23.7 | −23.9 | **−23.5** |

Then each fortnight's ratings predicting the next fortnight's games, every
Division I game of 2023-24 to 2025-26 (15,945), last season's ratings as the
prior. The margin's miss (RMSE, points) and the winner's Brier at a spread
of 10.75:

| Cap | Last season kept | Worth (games) | RMSE | Nov–Dec | Brier |
|---|---|---|---|---|---|
| 20 | 0.50 | 10 | 12.193 | 13.240 | 0.1890 |
| 25 | 0.65 | 6 | 11.833 | 12.642 | 0.1857 |
| 25 | 0.80 | 3 | 11.700 | 12.379 | 0.1852 |
| none | 0.80 | 6 | 11.732 | 12.396 | 0.1869 |
| 30 | 1.00 | 2 | 11.618 | 12.202 | 0.1856 |
| **30** | **1.00** | **3** | **11.599** | **12.174** | **0.1850** |
| 35 | 1.00 | 3 | 11.593 | — | 0.1852 |
| 40 | 1.00 | 3 | 11.612 | — | 0.1857 |

Fifty-four settings in all. The carried one (cap 30, all of last season's
rating, worth three games) is the best Brier and within 0.006 points of the
best margin; it is 11.50, 11.64 and 11.66 season by season. Keeping all of
last season's number, not shrinking it, read best at every cap: a college
team's level carries over more than its roster turnover suggests.

The spread for a game's chance, the Brier on the same games:

| 10.25 | 10.5 | **10.75** | 11.0 | 11.25 |
|---|---|---|---|---|
| 0.18507 | 0.18501 | **0.18499** | 0.18500 | 0.18504 |

The margins themselves miss by 11.6; the best spread for the chance is a
little narrower, because that miss includes the ratings' own error.

### The committee, stood in for

Each conference's champion is the winner of its tournament's game billed
"Final" or "Championship", through selection Sunday itself: 2026's Atlantic
10 and Ivy finals were played that afternoon, and the America East bills its
event "Playoffs". Read that way, all 32, 31 and 31 champions were found, and
every one was in the field.

The at-large teams are the best by a selection score: our rating plus a
weight for every win above what the bubble's team (the *n*th best) would
expect against the same Division I schedule. Against the 110 teams the
committee took at large in 2024, 2025 and 2026, and how far each of the
sixty-four placed seeds is from the line the committee gave it:

| Bubble | Weight 1.0 | 1.5 | 2.0 | 3.0 |
|---|---|---|---|---|
| 30th best | 104 / 0.73 | 104 / 0.74 | 105 / 0.72 | 105 / 0.78 |
| **45th best** | 104 / 0.67 | **104 / 0.69** | 104 / 0.69 | 105 / 0.77 |
| 60th best | 102 / 0.70 | 102 / 0.69 | 103 / 0.70 | 103 / 0.70 |

The carried stand-in, the 45th best at 1.5, named **104 of 110** and seeded
the field within **0.69** of a line on average. The first pass (a coarser
grid) put it best of 24 at naming and at seeding together; our rating alone,
with no résumé at all, named seven fewer. The committee's rule against
early meetings of conference rivals and its quadrants are not modelled.

### The tournament's own games

The ratings on selection Sunday, each NCAA tournament game on a neutral
floor at a spread of 10.75:

| | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|
| Games | 67 | 67 | 67 |
| Brier | 0.1872 | 0.1433 | 0.1567 |
| The favourite won | 70.1% | 80.6% | 73.1% |

### A dress rehearsal on 2025-26

The race built on 2025-26's own games, as the box will build it:

- **15 January:** 3,434 games played and 2,475 left. The field if the
  season had ended that day had Michigan, Arizona, Duke and UConn as the 1
  seeds. Our ratings played the rest out 2,000 times in 2.9 seconds.
- **12 March:** the conference tournaments under way, the regular season
  done. Each one-bid league's leaders were near even for the bid.
- **The tournament's first weekend:** the bracket was read off the
  scoreboard. That was 68 teams, the First Four's results, every
  first-round result and the Final Four's pairs once the scoreboard listed
  them.

## The scout

The NBA scout's fourteen flags (`engine/nba/scout`: the spots a basketball
person hesitates in, docs/NBA_LAB.md "The scout") were measured on NBA
games only, and college's cards carried none. On 2026-11-14 each was
measured on college's own seasons, the NBA's way, with everything decided
before the run.

**Written first** (committed before the run, `scout.LEAGUE["cbb"]`). Three
game-script thresholds are college's own: a projected blowout is fifteen
points (a favourite of ten is an ordinary college game; the median Division
I final margin is ten points, every season 2022-23 to 2025-26), and a fast
or slow game is read against the league's own usual total at the NBA's
ratios, 1.04 and 0.94 (236 and 214 against an NBA game's usual 227),
because college's scoring moved from 141 to 149 points a game across those
four seasons. The rest are ratios of his own numbers and stay the NBA's.
The bar: a WARNING is under what our number said in every judged season
(200+ flagged picks), under both spreads the board can run (one CV, and the
measured power spread), in at least two seasons, by 1.0% or more on
average; REFUSED is over it in every judged season; PRICED hits less before
any model in every season while our number already takes it out.

**The rows.** Every Division I regular-season game of 2021-22 to 2025-26 a
man of 15+ minutes a game played, five or more games for his school first,
his history running back across seasons at the same school as the board's
twenty games do: 61,505 / 71,300 / 71,765 / 71,969 / 70,947 player-games,
in college's five priced markets, at a half-point line off his last five.
Each projected through the board's own projection at college's tuning
(shooting and the rates reads on, the stand-in spread, total and rest on
the prop, the player memory off). Before any model: the flagged side's hit
rate against the same side unflagged. After ours: on the picks our number
makes (the side it gives 50%+), how far flagged picks fall under what we
said, against unflagged ones on that side.

**The seasons carry no book lines.** The game-script flags read OUR
RATINGS' spread (`engine/cbbratings`, refitted each Monday on the season's
games before it, last season's as the prior) and a total from the two
schools' points for and against, over the four seasons with a schedule
(2022-23 on). A man barely into his season needs last season's games, so
four seasons there too.

**What it found** (after our number, the one-CV spread, teammate-out
minutes off as the board runs; 2021-22 to 2025-26):

| Flag | Verdict | After ours, season by season | Fires on |
|---|---|---|---|
| an under while a regular teammate sits | **warning** | -5.8 / -4.2 / -5.5 / -5.8 / -5.1% (with the teammate-out minutes on: -4.2 / -2.6 / -3.8 / -4.2 / -3.3%) | 11-14% |
| an over in his first game back | **warning** | -8.6 / -8.9 / -9.4 / -12.0 / -11.5%, after the first-game-back minutes rule | 2% |
| an over after his minutes dropped | **warning** | -2.9 / -3.4 / -4.5 / -3.2 / -3.5% | 8-9% |
| an over on the second of two straight days | **warning** | -2.7 / -2.3 / -1.1 / -3.3 / -2.7% | 5% |
| an over the night a regular returns | **warning** | -2.9 / -0.5 / -2.0 / -4.6 / -1.6% | 3% |
| an under after his minutes jumped | **warning** | -1.0 / -0.6 / -1.8 / -1.2 / -1.6% | 16-17% |
| a man under five games into his season | **warning** | — / -1.4 / -1.7 / -2.6 / -4.7% | 5-9% |
| a starter's over in a projected blowout | refused | — / +4.0 / +3.4 / +1.8 / +4.4% | 7-9% |
| an under in a projected shootout | refused | — / +0.1 / +0.3 / +0.5 / +1.1% | 18-27% |
| an over in a projected grind | priced | before any model -2.5 / -0.9 / -1.4 / -2.1%; after ours — / -1.7 / +0.4 / +0.2 / -1.4% | 4-8% |
| a scoring over after a hot three-point run | priced | before -5.2 to -5.9% every season; after -1.2 / -2.2 / +1.5 / +2.3 / +1.4% | 2-6% |
| games that swing widely | mixed | -1.7 to -1.3% at one CV, -0.3 to +0.5% at the power spread | 51-52% |
| a line far from his last five | unmeasured | needs the books' lines | — |

The power spread agrees on every warning (first game back -7.4 to -10.9%,
the rest within a point). College is not the NBA here: the back-to-back
over the NBA refused is a warning (college plays two days running only in
its tournaments); the minutes jump the NBA's role-jump rule priced still
goes wrong (college runs no role-jump rule: it failed on points, above);
his first game back goes wrong by far more than the NBA's even after
college's own first-game-back rule; and the projected shootout the NBA
warns on does not, in any college season. The NBA's swing threshold (a
game-to-game spread of 0.55) catches half of all college player-markets,
and what it found came and went with the spread: not a warning.

**On the board** (`engine/nba/scout.VERDICT_CBB`): the seven warnings reach
college's cards as "Scout:" lines, each sentence saying what college's
seasons measured; a refused, priced, mixed or unmeasured flag never does.
A flag moves no number: college's graded record learns the same flags
(engine/likelyctx, each settled pick rebuilt by engine/nba/scoutrecord with
college's names, seasons and usual total, a regular who sat read off this
season's games so a graduated senior never "sat" an opener), and only a
flag the record proves on games the fit never saw lowers a chance.

## Reproducing it

The scripts are research, not the site: the hoopR player boxes for
2022-2026 (`mbb/player_box/parquet/player_box_{year}.parquet`), loaded into
`nbarules.cases`' shape by school id and athlete id (two players on one
roster can share a name), then the WNBA lab's three runs with college's
tuning: the variants, `nbarules.measure`, and the spread fit and judgement.
The scout: the same boxes with every shot column and the hoopR schedules
(2023-2026, for the ratings' spread and the scoring total), one process per
season — the rows, the situation through `scout.situation` at league
"cbb", the board's projection off and on the teammate-out minutes, the two
spreads' chances, each flag's before and after by the bar above.
