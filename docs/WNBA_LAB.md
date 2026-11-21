# The WNBA lab — six seasons of box scores against the NBA's measured pieces

Ethan, 2026-11-05: *"Go through nfl and CFB and nba and mlb and wnba and
nhl ... make sure we have all the tools and data we can be using like how
we just added for nba."*

The WNBA board is built by the NBA's own code (`nba_build.py` with the
league `wnba`, `engine/hoops.WNBA`). On 2026-11-04 the NBA lab measured
the minutes model's pieces on two NBA seasons. The WNBA kept them switched
off, since nobody had measured them on WNBA games: the role jump, his
first and second games back, a regular's return, the starting five's
news, and the NBA's weights on his recent games. This lab measures them
on the WNBA's own seasons.

## The data

Every regular-season WNBA box score of 2021 to 2026: 17,163 player-games
of players with 15+ minutes a game and 5+ games for their club first,
across 88 club-seasons. The files are sportsdataverse's public
`wehoop-wnba-data` player boxes on GitHub, which carry starters, minutes,
points, rebounds and assists. This is research only; the live site does
not read them.

## How each piece was judged

Every player-game is projected through the board's own code. The rows
are `nbarules.cases`, the box's own check of the NBA rules, built from
these clubs, and each projection runs through `engine/nba/pipeline.project`
with the WNBA's tuning. Each variant is scored on its own season-wide
level, because the calibration downstream owns the board's overall
level and a rule must not take credit for it. All six WNBA seasons are
out of sample for values fitted on the NBA. The NBA's bar applies: the
squared error of minutes and of points must both fall, in every season.

## What held up, and is on the board

Minutes RMSE / points RMSE, season by season:

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| As shipped | 6.317 / 5.958 | 5.887 / 5.719 | 5.769 / 6.136 | 5.960 / 5.897 | 5.802 / 5.933 | 5.578 / 5.993 |
| + the starting five's news | 6.207 / 5.942 | 5.786 / 5.711 | 5.684 / 6.123 | 5.863 / 5.889 | 5.728 / 5.931 | 5.477 / 5.982 |
| + his first game back | 6.174 / 5.933 | 5.772 / 5.707 | 5.637 / 6.112 | 5.832 / 5.882 | 5.694 / 5.924 | 5.458 / 5.975 |
| + the NBA's recency weights | **6.121 / 5.930** | **5.716 / 5.703** | **5.576 / 6.108** | **5.769 / 5.878** | **5.652 / 5.923** | **5.420 / 5.974** |

Each step is better than the one before in every season, minutes and
points both. Together they cut minutes error by 2.6% to 3.3% and points
error by 0.2% to 0.5%, every season.

- **The starting five's news** (`STARTER_NEWS_NBA`). Before the tip, the
  board reads the injury report on each club's last starting five, the
  returning regulars, and each player's own starts. The NBA's
  coefficients are used in minutes, as fitted. Scaled to a 40-minute
  game (×40/48) they did worse on minutes in every season.
- **His first game back** (the NBA's table: 1 game missed ×0.96, 2–4
  ×0.92, 5 or more ×0.84).
- **His newest games weighted harder**: 0.60, 0.25, 0.15 for the last
  five, games 6–10 and the rest. That is the NBA's measured set. The
  WNBA spec's 0.40, 0.30, 0.20 read players too slowly; 0.50, 0.30,
  0.20 sat in between.

## Measured, and left off

On top of those three:

| | Points worse in |
|---|---|
| A role that jumped (×1.2 the seven before, 40% of the way) | 2021 and 2026 |
| The same at 20% of the way | 2026 |
| The same at ×1.3 | 2021, 2023, 2026 |
| His second game back (×0.97) | 2023 and 2024 (minutes mixed too) |
| A regular's return (a quarter of his minutes given back) | 2022, 2023, 2025, 2026 (minutes mixed too) |

Every one moved minutes the right way in most seasons, but none held on
points in all six, so all stay off for the WNBA. The board's switches
are the NBA's (`engine/nba/switches`: `rotation`, `starters`). If the
NBA's own verdict turns one off, the WNBA's goes off with it.

## The spread that follows the projection (built, behind the NBA's switch)

The WNBA priced every prop with one CV per stat, the box's own fit: the
median of each player's game-to-game spread. That gives a 5-point bench
line and a 25-point star line the same relative width. The NBA lab
replaced it with variance = a × projection^c (`hoops.NBA.sd_power`). This
measures the same curve on the WNBA's own games.

Every player-game above, for points, rebounds, assists, threes, PRA and
the three two-stat combos (122,600 stat-games), was projected by the
board's own code at the shipped tuning. For each judged season, the
curve was fitted on the season before it: the squared miss around the
projection, by tenth of the projections, a line through the logs (the NBA
lab's fit). It was judged against the CV the box's own rule sets from the
same season's logs. Overs were priced at lines from half the projection
to one and a half times it, through the board's own pricer
(`engine/nba/prob.p_over`).

Brier change, judged season by season (negative is better):

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| Points | −1.10% | −1.20% | −1.93% | −1.10% | −1.49% |
| Rebounds | −0.45% | −0.96% | −1.67% | −0.76% | −1.74% |
| Assists | −1.79% | −1.06% | −1.85% | −2.14% | −2.30% |
| PRA | −1.25% | −1.47% | −2.43% | −1.94% | −2.13% |
| Pts+Reb | −1.28% | −1.19% | −2.19% | −1.65% | −1.82% |
| Pts+Ast | −1.29% | −1.67% | −2.33% | −2.03% | −1.88% |
| Reb+Ast | −0.89% | −1.32% | −1.90% | −1.43% | −1.59% |
| Threes | −0.59% | −0.03% | −0.18% | +0.72% | +0.26% |

Better in every judged season in seven markets. Threes were worse in two
of five, so they keep their CV, as the NBA's do.

The ends of the curve are where it matters. One CV per stat called few
points overs 80% or more (42 to 664 a season), and they hit 69% to 80%.
The new curve called 1,654 to 2,753 a season at about 85%, and they hit
82% to 85%.

On Most Likely's kind of over (lines under 0.8 of his projection), one
CV said too little in every market: rebounds 68–70% for overs that hit
74–76%, assists 66–68% for overs that hit 73–75%, PRA 76–78% for overs
that hit 80–81%. The curve's average landed within about 2 points of
what hit in most markets and seasons. Points is the exception. There
the CV said 71–73% for overs that hit 72–75%, and the curve said 76–77%,
1 to 4 points too high; the combos with points ran 2–3 points high in
2024 and 2025. Correcting that is the refit's calibration's job, one
more reason the spread waits for it.

**The values** are the fit on all six seasons:

| | a | c | its CV at a projection of 3 / 8 / 15 / 25 |
|---|---|---|---|
| Points | 5.927 | 0.735 | 1.22 / 0.65 / 0.44 / 0.32 |
| Rebounds | 1.407 | 0.987 | 0.68 / 0.41 / 0.30 / 0.23 |
| Assists | 1.447 | 0.845 | 0.64 / 0.36 / 0.25 / 0.19 |
| PRA | 8.429 | 0.650 | 1.38 / 0.71 / 0.47 / 0.33 |
| Pts+Reb | 6.847 | 0.711 | 1.29 / 0.68 / 0.46 / 0.33 |
| Pts+Ast | 6.308 | 0.711 | 1.24 / 0.66 / 0.44 / 0.32 |
| Reb+Ast | 2.114 | 0.833 | 0.77 / 0.43 / 0.30 / 0.22 |

**Why it waits for the NBA's switch.** The board's stored calibration was
fitted on the CV spread, so the spread goes on with a refit, never
before one (`prob.spread_on`, `engine/nba/switches`). The WNBA reads the
NBA's switch. The weekly refit fits the WNBA after the NBA
(`engine/deepfit.PIECE_ORDER`), so in the round where the NBA's verdict
turns the spread on, the WNBA's calibration is refitted on it too. The
WNBA plays again in May, long after that is settled.

**Replayed through the board itself.** To be sure the production code
does the same, the six seasons were loaded into a copy of the box's
`player_game_logs` and `nbalabcheck.py --league wnba` was run against it
(three and a half minutes). That is the board's own replay, at the spread
the build fits from those logs: one CV per stat, points 0.83, rebounds
0.80, assists 0.92 (each player's spread across all his seasons, wider
than one season's). On Most Likely's kind of over (lines at 0.5, 0.65 and
0.8 of his projection, about 52,000 overs a market) the Brier was lower
in all seven markets, by 2.5% (points) to 5.1% (PRA). The CV called 24
points overs 80% or more, and 46% of them hit; the new spread called
13,533 at 85%, and 83% hit. Near the line it was lower in five markets
and level in two (points and Reb+Ast, inside the check's half-percent
slack). Its verdict: `wnba spread: ready for the refit`.

**On the box.** The same command reads the box's own stored WNBA games,
through today's stored calibration and raw (runbook step KM). It files no
verdict: the switch is the NBA's.

## Next

- **Calibration.** The WNBA board is `calibrated=False` and has been on
  probation since it launched. Next season's graded picks are what open
  that.
