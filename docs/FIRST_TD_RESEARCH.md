# Who scores the first touchdown?

Ethan, 2026-10-31: *"I only want our long shot picks to be stuff like first
basket score for NBA or first touchdown score for NFL ... use all of our data
and tools to figure out how we can figure out who would be the best, most
likely, first touchdown scorer for each game. Now, obviously, if we go by the
most likely scorer for each game, it's just going to be the person with the
lowest odds to score the touchdown first. But that's not what we want to be
selecting."*

**Short answer:** the first touchdown comes down to two things we can
measure before kickoff. First, which team: the favourite, by about as much
as the spread says. Second, which player on that team: his share of its
carries and targets, more than his touchdown history. Our number from those
two is honest on games it never saw. The likeliest scorer is rarely worth
betting, though, so the board picks players whose price is longer than our
chance says it should be.

Everything here comes from the nflverse play-by-play the NFL model already
reads: 1,467 regular-season games, 2021 through week 8 of 2026. Each model
is fitted on 2021–2024 and scored on 2025–2026, games it never saw.
`python3 tools/first_td_study.py` reruns every number.

## What a first touchdown looks like

| | |
|---|---:|
| games with a touchdown | 99.3% |
| first touchdown by an offence (pass or run) | 94.8% |
| by a defence or a return | 5.2% |
| in the first quarter | 69% |
| on the game's opening drive | 24% |
| scored by the favourite | 58.9% |
| scored by the team that received the opening kickoff | 57.3% |

## Which team

The lines carry most of it. A logistic fit on the home team's edge in
implied points (logit = 0.073 + 0.478 × edge / 7) scores 0.6654 on the
held-out games, against 0.6931 for a coin. A 7-point favourite at home
scores the first touchdown about 63% of the time.

**Who receives the opening kickoff matters, but you can't know it at build
time.** Teams' history of receiving or deferring predicts nothing (held-out
0.6965, worse than a coin), because the coin toss decides most of it. Once
the toss is known, adding the receiving team takes the fit to 0.6550, the
biggest single improvement in this study. A first-touchdown price that
doesn't move after the toss would be a real chance. That's a live-betting
question for later, not something a pre-game board can use.

## Which player

For every team that scored an offensive touchdown, how well does each
measure, taken only from games before that one, pick out who scored the
team's first? Lower is better (log loss over the team's players, 704
held-out team first touchdowns):

| his share of the team's... | held-out |
|---|---:|
| touchdowns (what a price built off anytime-touchdown odds leans on) | 2.369 |
| carries + targets | 2.145 |
| **two-thirds carries + targets, one-third touchdowns** | **2.086** |

Volume beats touchdown history clearly, and the blend beats both. Touchdowns
are rare and lumpy: a receiver who scored twice in three weeks isn't twice
as likely to score next week. Carries and targets are what a coordinator
hands out on purpose, and they hold up week to week. (Season to date, last
season at half weight; every player gets a small floor, chosen on the
training seasons.)

## The whole model, checked

His chance = his team's chance of scoring the first touchdown × 94.8% (an
offence scoring it) × his share. On 7,309 held-out player-games:

| we said | scored first | games |
|---|---:|---:|
| under 2% | 2.0% | 781 |
| 2–5% | 2.8% | 3,762 |
| 5–8% | 6.3% | 1,799 |
| 8–12% | 11.3% | 674 |
| 12–18% | 15.6% | 262 |

Log loss 0.1852, against 0.1998 for the touchdown-share shortcut.

## Why the likeliest scorer isn't the pick

Our top player in each held-out game scored the first touchdown 12.9% of
the time (we said 13.5%). Books price that player at about +450 to +600,
which works out to 15–18%, and the first-touchdown market's total margin
runs 25–35%. Backing the favourite every week loses steadily, and so would
a board that ranks by price.

So a pick is a player whose price is longer than our chance says it should
be:

- an expected return of **10% or more** at the best price we can bet;
- our chance **4% or more** (below that the number can't tell a real chance
  from noise);
- a price between **+250 and +2500**;
- **one pick a game**, ranked by expected return, never by price.

On a night when nothing clears that, the board says so. Under the picks,
every quoted player is listed by our chance with the price beside it, so
"who do we think scores first" is always answered, even when no price is
worth taking.

## What it costs and how it's graded

- The first-touchdown market is one more market on each NFL odds call
  (26 credits an event instead of 25).
- Picks go to the Long Shots book on paper at 0.1 units and are graded off
  the play-by-play's first scorer once the game ends. A defence's or
  return's first touchdown loses every player pick, the same as at the book.

## College and the NBA

- **College football** uses the same idea, but its fit has to come from
  college games. The app's college play-by-play is ESPN's, and that version
  of this study comes next. Until then, college Long Shots stay on anytime
  touchdowns.
- **NBA first basket** needs its own version: who wins the opening tip, who
  takes the first shots, and how often they go in. The box keeps every NBA
  shot with its game clock, so the first made basket of each game can be
  counted there. That study and its board come next.
