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
  starter 8%.

## Next

- **Who takes a scratched regular's ice time.** The dataset carries every
  game's scratches and rosters. The NBA's version (vacancy) measured well,
  and hockey's top-six and top-four roles make it a natural fit.
- **The saves model.** `goalie_projection` hasn't been replayed. Shots
  against a backup, a tired team's shots allowed, and the save-rate prior
  (600 shots) are all measurable on these files.
- **Line combinations and the power play** are already read live from
  the shift charts (`engine/nhl/lines`, `xg.power_play`). The lab could
  measure how much of a skater's rate follows his line rather than him.
