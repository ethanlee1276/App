# College basketball on the NBA's level — the checklist

Ethan, 2026-11-13: *"we need to add college basketball, so go add college
basketball, add the most likely picks and edge bets and the live page and
all that. Obviously look at NBA, look at all the tools and resources and
data points we use for NBA, and obviously put that towards college
basketball. And don't stop working until you've added every single tool and
feature that we have for NBA onto college basketball. Make sure we use the
renders that we use for NBA. Make sure we're pulling headshots."*

Every NBA tool and data source, and where college basketball stands. College
is the basketball build's third league (`nba_build.py --league cbb`,
`engine/hoops.CBB`), so most of this list is the NBA's own code running on
college's games. **Done** means built, tested and running for college.
**Different** means college does the same job its own way, and says how.
**Not possible** means the data or the idea does not exist for college.
Measured numbers are in `docs/CBB_LAB.md`.

## The picks: posted, recorded, settled

| NBA tool | College | How |
|---|---|---|
| Edge picks, journaled | Done | On probation, as every new league starts: journaled and graded in public, nothing staked until the record clears the promotion bar (`engine/promotion`) |
| Most Likely | Done | `likely.build`, gated per market by the rank fitter; until the box has fitted college's, the tab says nothing is measured yet |
| One board, four checks, tiers | Done | `likelyboard.attach`, the NBA scan's read ("scan+model") |
| Matchup picks per game | Done | `matchpicks.build(sport="cbb")`, the basketball markets |
| Pick of the Day | Done | `engine/potd`, every league |
| Game bets (moneyline, spread, total) | Done | Every Division I game, in the same three-credit request the NBA's game lines use |
| Market scan (stale lines, arbs, middles, low holds) and sharp value | Done | The shared build |
| Live picks and the live Pick of the Day | Done | The shared build |
| Settled from the box scores | Done | The nightly ingests every Division I final (`engine/maintenance`, November to April) |
| Board corrections that learn on their own | Done | `likelycal`, the calibration, player memory and the weekly refit pieces run per league |
| One bet never argued both ways | Done | `python3 -m engine.contradictions --sport cbb` |
| Fantasy points tonight | Done | `fantasy_cbb.json` |

## The projection

| NBA tool | College | How |
|---|---|---|
| Minutes first, then the rate | Done | A 40-minute game of two halves, five fouls |
| The starting five's news, his first game back | Done | Measured on five college seasons: minutes better every season, points never worse; his first game back takes 15-17% off the minutes error in the games it touches |
| The newest games weighted harder | Done | 0.60 / 0.25 / 0.15, the best of four weightings on college |
| A role jump, the second game back, a regular's return | Different | Measured on college and left off: each failed on points in some season (as for the WNBA) |
| Shooting, luck taken out | Done *(11-13)* | Points 0.4-0.5% closer, threes 1.2-1.3%, every season held out, on college's own percentages |
| Rates read past his last twenty | Done *(11-13)* | Rebounds 0.6-0.8% closer, assists 0.5-0.7%, on college's own role rates |
| The spread that follows the projection | Done, behind the NBA's switch | College's own curve: Brier better every judged season in seven markets; threes keep one width |
| One width per stat before the box fits its own | Done *(11-13)* | College's measured widths (points 0.78), not the NBA's starting 0.30 |
| The margin's spread | Done | Fitted from the box's own college games once 200 are stored (`hoops_fit`) |
| The blowout curves, rest | Different | The WNBA's until college's own picks are graded; the replay has no lines to measure them against, and college rarely plays on consecutive days |
| What a missing teammate opens, the vacancy step | Done | The shared reads; the vacancy step follows the NBA's verdict |
| Defense vs position | Done | `engine/hoopsdvp`, the WNBA's measured transfer |
| The combos (P+R, P+A, R+A), steals, blocks, turnovers as markets | Different | Priced for the NBA only: each is another market on every event the odds pull buys. College prices points, rebounds, assists, threes and PRA on its five games a night |
| The scout's flags | Done *(11-14)* | Measured on five college seasons by a bar written before the run (docs/CBB_LAB.md, "The scout"): seven warnings on college's cards (a teammate sitting, his first game back, a minutes drop or jump, two straight days, a regular's return, a man barely into his season); a projected blowout and shootout refused; college's graded record learns the same flags |

## Offense against defense

| NBA tool | College | How |
|---|---|---|
| Unit rankings, the tale of the tape, key mismatches | Done | `engine/nba/teams` and the scan, off college's stored box scores (field goals, free throws, offensive rebounds, turnovers) |
| Could shine / could struggle / breakout | Done | `engine/nba/scan` |

## Who plays

| NBA tool | College | How |
|---|---|---|
| The injury report read by the build | Done | ESPN's college injury lists, where a school reports one; most publish nothing, and the minutes come from recent games |
| Rosters with headshots | Done | Each school's ESPN roster, read by team id for tonight's priced schools, so a namesake at another school never lends a face; every player who appears in a box score gets his ESPN headshot |
| What if he sits | Done | `engine/nba/whatif` |

## The game around the bet

| NBA tool | College | How |
|---|---|---|
| Schedule spots | Different | Rest and the blowout watch. No arena table for 365 schools, so no trip or altitude line (the module draws none rather than guess) |
| Game script | Done | The blowout line on a big spread |
| Officials | Done | Each final's crew is stored, as for the NBA; nothing moves a number |

## The market

| NBA tool | College | How |
|---|---|---|
| Kalshi and Polymarket prices | Done | `engine/crowd`, by each exchange's own college names (Kalshi's KXNCAAMBGAME, Polymarket's ncaab); a night they list no college market shows none |
| Opening lines kept, closing lines, CLV | Done | Every sport |
| Prediction-market flow | Done | Its own NCAAB chip |

## Reports and pages

| NBA tool | College | How |
|---|---|---|
| A written report on every game | Done | On the games the board prices, naming the school as a reader does ("Duke has") |
| Ask reads the board | Done | "ncaab", "college basketball", "college hoops" and "march madness" find it |
| Player charts | Done *(11-13)* | The shot chart on the college court (a 12-foot lane, the three-point line at 22 feet 1.75 inches), by half, against college's own zone percentages; the matchup view against tonight's defense; the role chart |
| Live game page | Done | The court render, two halves, the play feed |
| Game page, team page, standings | Done | Standings by conference with the overall record |
| Parlay checker and parlays | Done *(11-14)* | The Parlays page's two-leg tickets from college's own Edge and Most Likely picks (`engine/twoleg`), same-game and two-game, every one tracked and none staked while college is on probation; the same-game link reads the published priors until college's own games measure one. The checker screens a slip with a wider blowout spread |
| Alerts, follows, push | Done | Every league |
| Lab replay | Done | Once the box holds college's seasons |

## The NCAA tournament

The NBA's two season-long pages have one college analog, the NCAA
tournament:

| NBA tool | College | How |
|---|---|---|
| The NBA Cup's page (the race) | Done *(11-14)* | `engine/ncaarace`, the Race page: the field if the season ended today, the bubble, every conference's race, each school's chances and games at our price, the games that swing the bubble; from Selection Sunday the bracket off the scoreboard. Ratings adjusted for every opponent (`engine/cbbratings`) and a stand-in for the committee, both measured (docs/CBB_LAB.md, "The tournament model") |
| Futures (title odds against our simulation) | Done *(11-14)* | The race's own run on the Futures page: projected record, the automatic bid, the field and the title, beside the books' best title price (`futures_build.py cbb --odds`, one credit) |
| Long Shots (the NBA's first basket) | Not possible | The books post first-basket props on NBA games, almost never on college ones, and our first-basket model was measured on the NBA's play-by-play |

## Not possible for college

- **On/off, lineups, stints and tracking**: the NBA's floor data and
  tracking numbers come from the league's own feeds; there is no free
  college equivalent.
- **Weather, altitude by arena**: indoor, and no arena table (above).

## How to check it on the box

Runbook step OT (`docs/RUN_NEXT.md` item 00a): the probe of every ESPN
college endpoint we read, two seasons of college box scores (which also
stores every shot for the shot chart), and what is stored.
