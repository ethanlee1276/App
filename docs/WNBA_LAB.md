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

## Next

- **The WNBA's spread.** The NBA lab's variance = a × mean^c (`sd_power`)
  was measured on NBA play-by-play. The WNBA still prices with one CV per
  stat. These box scores can fit and judge the same curve.
- **Calibration.** The WNBA board is `calibrated=False` and has been on
  probation since it launched. Next season's graded picks are what open
  that.
