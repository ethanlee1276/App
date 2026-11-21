# Rain, a green quarterback and the lead back — measured (6 November 2026)

Ethan, during Thursday night's Ravens game in Jacksonville, in the rain, with
Baltimore on its third-string quarterback and the board holding Derrick
Henry's rushing-yards under (25 yards ten minutes in):

> "with that rain, I feel like it pushes more towards his over than his
> under. On top of them not having their starting quarterback, they're using
> their third string quarterback right now. So I feel like that would prompt
> their star running back doing better than worse."

Both ideas had been measured once before (September: `engine/wxfit.py`,
`engine/qbfit.py`), on every back pooled. This goes deeper: the lead back on
his own, carries apart from yards, yards per carry, the team's run/pass mix,
the replacement quarterback's experience, and the betting market's closing
total. Data: nflverse's box scores and schedules, 2016-2026 (2026 through
week 9), and the game book's kickoff sky from nflverse's play-by-play.
Every number is a ratio to the player's or team's own earlier games that
season (week 4 on, three games before), over the same ratio in the base
games (domes, or dry, still and above freezing) — the arithmetic every fit
here ships with. "Clears" is the house rule: two standard errors from 1.0,
most seasons the same way, 40+ games.

## Rain

| team-games in rain (146) | multiplier | seasons up / down |
|---|---|---|
| the team's carries | ×1.058 ± .026 — clears | 10 / 1 |
| the backs' carries | ×1.066 ± .029 — clears | 10 / 1 |
| pass attempts | ×0.968 ± .021 | 5 / 6 |
| run share (carries ÷ plays) | ×1.042 ± .022 | 7 / 4 |
| the backs' rushing yards | ×1.057 ± .048 | 8 / 3 |

| the lead back (12+ carries a game before; 99 games) | multiplier | seasons |
|---|---|---|
| carries | ×1.078 ± .042 (×1.064 ± .041 against the board's own form) | 8 / 3 |
| rushing yards | ×1.084 ± .070 (×1.066 ± .069) | 6 / 5 |
| yards per carry | ×1.005 ± .049 | **3 up / 8 down** |
| receptions, receiving yards | ×0.867, ×0.732 (the shipped rain cuts) | |
| his share of the team's backs' carries | the same as on a dry day (−0.009 ± .024) | |

What it says. **Teams run more in rain** — every season but one — and the
lead back keeps his share of it, so his carries go up with the team's. **His
yards do not reliably follow**: per carry he gained less in rain in eight
seasons of eleven, and the yards are too noisy to say either way. Held out
by season, putting the team's rain step on the lead back's carries took
2.6% off their squared error; on his yards it did nothing (+0.1%).

**What changed on the board:** a back's **carries** take the team's
measured rain step, ×1.069 (the fit's own run, 2016-2025: 140 team-games,
nine seasons of ten), at the forecast's chance of rain — the way every rain
cut is applied, so a 70% forecast is 70% of it. His **rushing yards are
left alone**, and the card says why. College reads the same table.
(`engine/wxfit.TEAM_MARKETS`, `engine/weather.RAIN`.)

For Henry's under, that means the history agrees with Ethan on *carries*
(about 6-7% more in rain), not on *yards*.

## The market: the closing total in rain

| team points minus the closing line's implied team total | |
|---|---|
| dry outdoor games (3,157) | +0.27 ± 0.16 |
| domes (1,568) | +0.71 ± 0.23 |
| rain (252) | **−1.96 ± 0.54** — under the dry games in 10 of 11 seasons |
| snow (42) | −0.12 ± 1.28 |
| wind 15+ mph (351) | −0.60 ± 0.49 |

Rain games went about 2.2 points a team (4.5 a game) further under the
close than dry ones. The board's game totals take no weather at all, and
lean almost entirely on the close (`engine/gamecal`). But this reads the sky
**at kickoff**, which nobody knew when they bet: the close may already price
the rain that was forecast and miss only the rain that wasn't. So nothing is
priced yet. The question is asked of the **forecast** on the droplet
(`python3 wxfit.py --totals`, runbook KU): games forecast 60%+ wet at the
kickoff hour (Open-Meteo's archive of its own forecasts, 2022-2025) against
the closing total. If they went under by more than the dry games, by two
standard errors and in most seasons, the board's totals get a rain step;
if not, the close already knows.

## A replacement quarterback

By the replacement's passes in the seasons before (the game's starter is not
the team's established passer):

| replacement | team-games | team carries | pass attempts | the backs' carries | the lead back's carries / yards |
|---|---|---|---|---|---|
| under 50 passes (a third-stringer, a rookie) | 341 | ×1.047 — clears | ×0.937 — clears | ×1.035 | ×1.012 ± .029 / ×1.032 ± .043 |
| 50-299 | 145 | ×0.989 | ×0.978 | ×1.011 | ×0.922 / ×0.902 (51 games) |
| 300+ (a veteran backup) | 341 | ×1.037 — clears | ×1.006 | ×1.070 — clears | ×1.051 ± .029 / ×1.069 ± .043 |

Behind a green quarterback the team does run more and throw less — but the
extra runs are mostly **the quarterback's own** (his and the other non-backs'
carries ×1.10), and the lead back's carries and yards move inside the noise.
The market agrees: those teams scored −0.43 ± 0.44 points against their
implied total, as priced. Behind a veteran backup the backs do get more work
(×1.07), short of clearing for the lead back alone.

**What changed:** nothing in the number. A back's QB-change card now says
it: "Behind a quarterback with almost no passes behind him … teams ran 5%
more and threw 6% less, but mostly on the quarterback's own runs: the lead
back's carries moved +1% and his yards +3%, inside the noise"
(`engine/qbchange.BACKS_BEHIND_GREEN`). The receivers' measured cut behind a
downgrade stands as it was.

**Both together** (rain and a replacement under 300 passes): ten lead-back
games in eleven seasons — too few to say anything.

## Not done here

- **College on its own.** College reads the NFL's table. A college rain
  measurement needs game-day weather history, which the box can fetch with
  its college-data key; the sandbox cannot. It is the next step on Ethan's
  word.
- **Live.** Henry's 25 yards in ten minutes is a live read; the board's
  pregame number is what this measures. The live tracker's pace is
  separate.

Scripts: `engine/wxfit.py` (team carries, `totals_by_forecast`), `wxfit.py
--totals`; the research runs that produced the tables above are not part of
the build (they read nflverse's files directly).
