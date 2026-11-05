# The NHL lab — three seasons of box scores against our hockey model

Ethan, 2026-11-05: *"Go through nfl and CFB and nba and mlb and wnba and
nhl and pollymarkwt and crypto and make sure we have all the tools and data
we can be using like how we just added for nba and have had for nfl."*

Until today every NHL constant was a plain prior, written down on
2026-10-03 and never measured: the model's own docstring said so. This is
the NBA lab's method for hockey. Every skater-game of two full seasons is
priced through the board's own model, using only the games before it.
Each knob is fitted on one season and judged on the other, and only what
held up both ways changed.

## The data

- **Every regular-season NHL box score of 2023-24, 2024-25 and 2025-26**
  (3,936 games): the skater, goalie and team box scores and game info
  from sportsdataverse's public `fastRhockey-nhl-data` files on GitHub.
  This is research only; the live site does not read them. 2023-24 only
  warms up the history; 2024-25 and 2025-26 are scored.
- The league's own API (api-web.nhle.com) cannot be reached from the
  sandbox, and the shift charts and scratches in the same dataset weren't
  needed for these questions. Who takes a scratched regular's ice time
  is the next one (below).

## How each idea was judged

Every skater-game with three or more earlier games, 468,205 of them over
the two scored seasons, five markets each. Each is projected by
`model.skater_projection` and priced by `model.skater_prob`. The inputs
are his games strictly before that one, the previous season's league
rates as the prior, and every team's profile as of that morning, with
`team_profiles`' season blend. Each is scored at a ladder of lines, where
Most Likely prices: shots 0.5 to 4.5, blocks 0.5 to 2.5, points 0.5 and
1.5, assists and goals 0.5. The score is log loss. Game lines were
replayed the same way through `team_lambdas` and `game_probs`: moneyline,
puck line, and totals at 4.5, 5.5, 6.5 and 7.5.

## What held up, and is on the board

**The memories** (`RATE_HALF_LIFE`, `TOI_HALF_LIFE`, `RECENT_GAMES`). A
skater's per-60 rate now reads a 30-game half-life (was 12). His ice time
reads a 3-game one (was 6). Both come from up to 60 games (was 40). Rates
are noisy and need a long memory; ice time follows a coach's latest line
card and needs a short one. Fitted on 2024-25 and judged on 2025-26, every
market was better:

| | Fit, 2024-25 | Held out, 2025-26 |
|---|---|---|
| Before | 0.42843 | 0.42394 |
| After | 0.42652 | 0.42235 |

The prior minutes (120), the shot dispersion, the opponent's shrinkage
and cap, and the shooting prior were swept the same way and none cleared
the bar, so they stay. The shot-quality window stays at 40 games
(`XG_WINDOW`): the lab has no expected goals to measure it on.

**A team's strength, believed slowly** (`TEAM_PRIOR_GAMES` 15 → 100,
`TEAM_HALF_LIFE` 25 → 40). Each season's own best shrinkage was 70 and
150 games, and 100 sits between. With no team strength at all, every team
average, the game lines were clearly worse (0.640 and 0.633), so the
strengths carry signal. They were just believed far too fast. Moneyline,
puck line and totals log loss, averaged, with the back-to-back factors
below:

| | 2024-25 | 2025-26 |
|---|---|---|
| Before | 0.63428 | 0.63166 |
| After | 0.63077 | 0.62866 |

All three markets improved in both seasons. Home ice stays 1.04: 2024-25
wanted 1.06 and 2025-26 wanted 1.02, and each season's choice did worse on
the other. The overtime split (0.52) is flat. A slower early-season blend
than Ethan's helped 2024-25 slightly and tied 2025-26, so his schedule
stays.

One more number worth knowing: the moneyline's log loss is 0.666 and
0.688, close to a coin's 0.693. Our team model alone barely beats a coin
at picking winners. The board already pulls every game-line chance toward
the no-vig price (`temper`), which is why that matters less than it
sounds.

**Back-to-backs, the game** (`B2B_FACTOR` 0.97 → 0.93, new
`B2B_OPP_FACTOR` 1.04). The measure is goals actual ÷ model on 568
tired-versus-rested games, against the rested games' own ratio. That
ratio is 1.04 because finals count overtime and the shootout winner.

| | 2024-25 | 2025-26 | Pooled |
|---|---|---|---|
| The tired side | 0.894 | 0.962 | **0.929** |
| Its rested opponent | 1.053 | 1.032 | **1.042** |
| Both tired | 0.999 | 0.917 | 0.954 |

The first guess, 0.97 on the tired side alone, missed half the effect:
the rested side scores more too. When both sides are tired the two
seasons disagree, so there is no factor.

**Back-to-backs, the skater** (new `B2B_SKATER`, `B2B_SKATER_OPP`). The
same ratio for every skater-game: one whose team is on its second night
("tired"), one whose opponent is ("opp_tired"), pooled over both seasons:

| | Tired | Opp tired | Ships (¾): tired / opp tired |
|---|---|---|---|
| Shots | 0.967 | 1.042 | 0.975 / 1.031 |
| Points | 0.923 | 1.072 | 0.942 / 1.054 |
| Goals | 0.910 | 1.060 | 0.933 / 1.045 |
| Assists | 0.929 | 1.078 | 0.947 / 1.058 |
| Blocks | 1.023 | 0.967 | 1.017 / 0.975 |

Ice time does not move (1.002, 1.000). The legs change, not the minutes:
the tired side shoots and scores less and blocks more, and its rested
opponent does the reverse. The board takes three-quarters of each number.
The full size fitted on 2024-25 overshot 2025-26 in one market (goals,
where 2024-25's effect was the bigger), while three-quarters made every
market better in both directions held out:

| Market | 2024-25 → 2025-26 | 2025-26 → 2024-25 |
|---|---|---|
| Shots | −0.00011 | −0.00003 |
| Points | −0.00007 | −0.00018 |
| Goals | −0.00001 | −0.00010 |
| Assists | −0.00006 | −0.00017 |
| Blocks | −0.00002 | −0.00005 |

These gains look small because only about one skater-game in five is on a
back-to-back. Where they apply, a 2.5% to 6% move shifts a 60% call by one
to three points. Both-tired games disagreed between seasons and get no
factor. Each card on such a night says so: `Rest: EDM on the second night
moves his number -2.5% (measured over two seasons of back-to-backs)`.

**The goalie on a back-to-back.** The probable starter is the goalie with
the most of his team's last ten starts:

| | Starts |
|---|---|
| Rested night | 63.0% |
| Second night of a back-to-back | 36.1% |
| … having started last night | **9.3%** (49 of 527) |
| … having rested last night | 83.1% (250 of 301) |
| The team's other goalie, when the probable started last night | **78.4%** (413 of 527; 79.3% and 77.5% by season) |

The board already treated last night's starter as unsettled: no saves bet
rides on him, and the opposing skaters read his team's goals allowed
instead of his save rate. That rule now has its number. The card also
names who is likely in net (`backup_goalie`: the most of the team's other
recent starts), with *starts about 78% of those nights*. He is still not
"sure", so still no saves bet. The opposing skaters' back-to-back factor
already carries his effect: it was measured with no goalie read, and is
larger on these backup nights (goals 1.073) than on the others (1.037).

**The saves model** (`SAVES_LEVEL` 0.943, `SAVES_SD_SCALE` 1.22, new
`B2B_SAVES` 1.036 and `B2B_SAVES_OPP` 0.974). Every start of the two
seasons (5,183) was priced through `goalie_projection` at a ladder of
saves lines, 19.5 to 33.5. Two things were wrong in both seasons:

- **It ran high.** Goalies made 0.936 and 0.950 of the saves projected.
  A starter does not face every shot his team allows: some nights he is
  pulled, and the empty net takes the rest.
- **Its spread ran narrow.** The misses' squared z averaged 1.55 in both
  seasons, where an honest spread reads 1.0. Saves land about 22% wider
  than the model said, so it was too sure of every saves pick.

A back-to-back moves his shots too, both seasons the same way. His team
on its second night lets more through (1.03 and 1.06 of rested); an
opponent on its second night takes fewer (0.975 and 0.955). Each factor
was fitted on one season and judged on the other. Ladder log loss
change:

| | 2024-25 → 2025-26 | 2025-26 → 2024-25 |
|---|---|---|
| The level | −0.0046 | −0.0185 |
| + the spread | −0.0107 | −0.0214 |
| + the back-to-back (¾) | **−0.0120** | **−0.0216** |

These are the largest gains in the lab, larger than any skater
market's. The pooled values ship. Through the model itself, the misses'
squared z is now 0.98 and 1.00 and the level 0.99 and 1.01. The prior on
his save rate (600 shots) barely mattered (2,400 was 0.0002 better) and
stays: it also sets the opposing goalie's read for every skater's goal
markets, which this lab did not replay. A saves card on a back-to-back
says so: `Rest: EDM on the second night moves his saves +3.6%`.

## On the box

`nhllabcheck.py` (step KK of `docs/WHEN_YOU_ARE_HOME.md`, read-only)
replays the box's own stored NHL games, this season's included, which
these files never had. It prints three things:

- the skater ladder before and after;
- the back-to-back ratios beside the shipped factors;
- the game lines before and after, and the goalie rule's two rates.

On a copy of the box's tables built from this lab's three seasons (every
other date, a neutral opponent, all three seasons), it ran in 38 seconds
and agreed with the lab:

- the skater ladder was better in all five markets (shots −0.0016,
  points −0.0018, goals −0.0008, assists −0.0016, blocks −0.0013);
- the back-to-back ratios leaned the shipped way in 10 of 10;
- the game lines were better (−0.0015 a line, totals the most);
- the named backup started 80% of 727 such nights, and last night's
  starter 8%;
- saves (7,560 starts over all three seasons): log loss 0.56503 →
  0.54909, the misses' squared z 1.58 → 1.02, actual ÷ projected 0.949 →
  1.002.

## Measured, and not built

**Who takes a missing regular's ice time.** An absent regular is a skater
with 16+ minutes a game over his last ten who played in one of his club's
last three games and is not in tonight's box. His teammates in the same
position group read clearly in both seasons. With one forward regular
out, the other forwards played 3.2% more and shot 3.4% more; with two or
more out, 8.6% more ice time and 13.5% more points. Defencemen showed the
same pattern: +2.8% ice time with one out, +5.4% with two.

As a multiplier on every teammate's number, though, it barely moved the
ladder, and it went the wrong way on one season for shots and blocks:

| Fitted on → judged on | Shots | Points | Goals | Assists | Blocks |
|---|---|---|---|---|---|
| 2024-25 → 2025-26 (¾) | −0.00004 | −0.00002 | −0.00003 | −0.00002 | −0.00001 |
| 2025-26 → 2024-25 (¾) | **+0.00008** | −0.00005 | −0.00002 | −0.00000 | **+0.00009** |

The extra ice time goes to the man who moves up a line, not to everyone
in the group evenly, so a flat multiplier is the wrong shape. It stays
off. A second pass would read who moves up from the shift charts' line
combinations (`engine/nhl/lines`), as the NBA's vacancy reads who inherits
the minutes.

## Next

- **Who moves up when a regular is out**, read from the line combinations
  (above: the flat version did not hold).
- **Line combinations and the power play** are already read live from
  the shift charts (`engine/nhl/lines`, `xg.power_play`). The lab could
  measure how much of a skater's rate follows his line rather than him.
