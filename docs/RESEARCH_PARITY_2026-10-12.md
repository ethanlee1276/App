# Research parity — Bills @ Rams, Monday Night Football, 2026-10-12

Ethan pasted four outside write-ups of tonight's game: "compare to what we
have and see where we agree and disagree and what we are getting right and
wrong. Then fix shit." This covers each report's angles and legs against
what the site computes, what was wrong with ours, and what was changed.

**How the comparison was made.** Every number the reports quote was checked
against our own 2026 logs (nflverse, weeks 1–4). The week-5 NFL build was
run here on the same feeds the box reads, but without book prices. Every
leg the reports built or cut was then priced at its exact line with the
board's own derivation (`legcheck.py`, `likely._prob_at`). The box will
differ a little, because it has prices, the injury report and its own
calibration fits. Run `legcheck.py` there to see the box's version.

## Their facts are right

Every game-log number in the four reports matches our data:

- **Adams:** 26 and 32 yards with Nacua; 195 and 137 without him.
- **Kyren Williams:** 65, 97, 158 and 147 scrimmage yards.
- **Stafford:** 15, 22, 30 and 32 completions.
- **Allen:** 29, 31, 26 and 33 attempts, and 7 rushing TDs.
- **Cook:** 57, 135, 154 and 75 rushing yards.
- **Kincaid:** 225 yards in the first two games, 45 in the last two.

We also agree on the venue: SoFi is a dome in our stadium table, so no
weather adjustment, which is what reports 1 and 2 say. Report 3 quoted an
outdoor forecast. The roof makes it irrelevant.

## Where we agreed before any change

| Leg | Theirs | Ours |
|---|---|---|
| Nacua 6+ catches | R1 76% | 78% |
| Nacua over 6.5 catches | R2 63% (FD −160) | 67% |
| Stafford 21+ completions | R1 71% | 69% |
| Stafford 250+ passing yards | R2 68% | 65% |
| Kyren 50+ rushing yards | R3 "high", DK −311 | 79% (a −311 price needs 76%; past our −250 cap anyway) |
| Allen 200+ passing yards | R3 "high", DK −349 | 80% before the fixes, 69% after (−349 needs 78%; past the cap) |
| Nacua 70+ receiving yards | R3 "high", DK −276 | 71% — under the 73% the price needs. Report 3 is wrong to call this a bet |

## Where we disagreed — and who was right

Our widest gaps against the market and the reports were all on players
whose 2026 games were played in unusual circumstances:

| Player | Our projection | Market | What the reports knew that we didn't |
|---|---|---|---|
| Davante Adams, rec yds | **90.5** | 64.5 | Two of his four games came without Nacua (195, 137); with him, 26 and 32 (R2). Our form read all four as normal. |
| Keon Coleman, rec yds | **61.6** | 36.5 | His 63- and 116-yard games came when DJ Moore left early (31% and 39% of the snaps); in 2025 he averaged 34 (R3, R4). |
| Kyren Williams, catches | **5.8** | ~3.5 | Six and ten catches the last two weeks; 2.1 a game in 2025. Every report anchors on last season; we did not after week 3. |
| Kyren Williams, rush+rec | **122.6** | 91.5–97.5 | Same. |
| Stafford, attempts | **41.2** | 36.5–37.5 | 55 and 51 attempts in two catch-up games; 35 a game in 2025. |
| James Cook, rush yds | **95.8** | 75.5 | The Rams allow 3.8 yards a carry. Cook's 2025 (95 a game) agrees with us, so this one is the matchup, not the form. |

**They were right on five of the six.** Our model chased the last two or
three games and forgot last season once a player had three games this
year. It also had no idea a teammate coming back changes anything. Those
are the fixes below. Cook is the sixth: there the gap is the matchup, and
we still differ (below).

**Where we stay apart:**
- **Allen's attempts.** We have 29.7 against a 32.5 line; report 1 said 68%
  for 30+, we say 51%. His logs are 29, 31, 26 and 33, and he threw 28.8 a
  game in 2025. Report 1 itself conceded "closer to 62–65%". The market's
  extra attempts come from Buffalo being an underdog. **Measured the same
  day** (`qbscriptfit.py`), on the board's base of form, last season and
  the defence step. An underdog quarterback does not throw for more:
  attempts against the spread got worse in two held-out seasons, and
  completions failed the older, unseen seasons. The old script tilt
  (+0.4% a point on an underdog's passing yards, catches and receiving
  yards) made every season 2022–2025 worse, and 2017–2021 agreed, so it
  was retired. We stay at our number.
- **Cook's rushing.** We still have 90.5. Our matchup step reads the Rams'
  run defence and moves him less than the market does.
- **Adams 60+ (report 4, 67%).** We now say 52%. Reports 1 and 2 cut Adams
  for the same reason we now do.
- **Kincaid 50+ (report 4, 65%).** We say 50%. Report 1 calls the Rams'
  tight-end coverage the league's best (2.9 yards a target), and his last
  two games were 38 and 7 yards. We side with report 1.
- **Three legs the fixes moved further from the reports.** These are
  Stafford's 21+ completions (report 1, 71%) and 250+ yards (report 2,
  68%), and Kyren's 15+ receiving yards (report 4, 76%). We had them at
  69%, 65% and 85%. With last season in the blend we now say 62%, 57% and
  67%. Stafford's 55 and 51 attempts came in two catch-up games, and his
  2025 brings his completions to 23.1, beside the market's 23.5. Kyren's
  2.1 catches a game in 2025 now weigh against his last two games. Where
  the median sits we are with the market. The chances at the alt rungs
  are the board's own derivation, and the box redoes them with its fits.

## What was fixed (pushed today, live on the next build)

1. **His own last season, from week 4 on** (`engine/carry.SEASON_PRIOR_GAMES`,
   `seasonpriorfit.py`). The form is now pulled toward the player's 2025
   per-game number by w = n/(n+k), through `compute_form`'s existing shrink.
   The bar was set before the run: every season, held out, must improve.
   k was fitted on three seasons and squared error measured on the fourth:

   | Market | k | 2022 | 2023 | 2024 | 2025 |
   |---|---|---|---|---|---|
   | Receiving yards | 6 | +7.8% | +6.5% | +5.1% | +5.6% |
   | Catches | 4 | +4.9% | +5.3% | +4.6% | +4.2% |
   | Rushing yards | 2 | +3.4% | +2.2% | +2.7% | +2.9% |
   | Carries | 1.5 | +2.2% | +2.1% | +2.1% | +1.2% |
   | Passing yards | 10 | +9.4% | +7.0% | +11.0% | +1.2% |
   | Pass attempts | 10 | +12.2% | +6.3% | +9.6% | +4.5% |
   | Completions | 8 | +9.5% | +5.6% | +9.5% | +4.0% |
   | Rush + rec yards | 2 | +2.5% | +1.3% | +2.4% | +3.1% |
   | Pass + rush yards | — | +8.9% | +7.8% | +9.9% | −1.6% (fails, not applied) |

   Three details matter. It applies only to a player at least as involved
   this season as the measured population (15 receiving yards a game, 1.5
   catches and so on). A man whose role has shrunk isn't pulled back to
   last season's job: the first build had Jauan Jennings going from 3.1 to
   27.2, which the bar never covered. Last season is read the way the
   board reads a season: a quarterback's real games only. A first run that let backups'
   relief appearances in failed the passing markets in 2024. And the pick
   page says it: "4 games this season, so the blend is pulled 60% toward
   56.4 — his own per-game number last season — as measured on 2022–2025."

2. **A teammate back** (`engine/teammates.back`, `matefit.py --back`). With
   nobody at his position out tonight, every game of his that a teammate
   ranked with him missed is divided by the lift we already measured for
   that absence. A WR's yards run ×1.22 the first game the man ahead of him
   misses and ×1.10 after. The form is then taken again. This adds no new
   number, plus one residual the shipping rule passes: a back's catches
   ×0.903 when the back behind him has returned. A teammate counts as
   back once he has played the team's last game. "Not on the injury
   report" isn't "playing": Ronnie Rivers, active once all year, would
   otherwise have counted. Each season was held out in turn. Running
   backs' rushing improved +2.6%, +6.0%, +1.4% and +1.5%. Receivers' catches
   improved +1.0%, +0.3%, +0.4% and +0.7%. A tight end's catches went the
   wrong way in two seasons, so it isn't applied. The card says it:
   **Teammate back** — "Puka Nacua back at WR — 2 of his 4 games this
   season came without him."

3. **Two broken joins in the teammate step**:
   - The snap file writes "D.J. Moore" and every other feed "DJ Moore".
     The two never matched, so Moore ruled out tonight would have reached
     nobody. Fixed, along with D.K. Metcalf.
   - The snap file calls Cincinnati's backs "HB", so the Bengals had no
     running backs in the order at all. Fixed.

**Tonight's projections, before → after** (local build, both fixes):

| Player | Market | Before | After | Market line |
|---|---|---|---|---|
| Davante Adams | rec yds | 90.5 | **63.9** | 64.5 |
| Kyren Williams | catches | 5.8 | **3.9** | ~3.5 |
| Kyren Williams | rec yds | 45.7 | 28.0 | — |
| Stafford | attempts | 41.2 | **36.2** | 36.5–37.5 |
| Stafford | completions | 25.2 | **23.1** | 23.5 |
| Keon Coleman | rec yds | 61.6 | **44.3** | 36.5 |
| James Cook | rush yds | 95.8 | 90.5 | 75.5 |
| Josh Allen | attempts | 30.7 | 29.7 | 32.5 |

Report-by-report, each leg at its own line, ours after the fixes:

| Leg | Report | Theirs | Ours |
|---|---|---|---|
| Nacua 6+ catches | R1 | 76% | 78% |
| Kyren 75+ rush+rec | R1 | 72% | 80% |
| Stafford 21+ completions | R1 | 71% | 62% |
| Allen 30+ attempts | R1 | 68% | 51% |
| Stafford 250+ pass yds | R2 | 68% | 57% |
| Nacua over 6.5 catches | R2 | 63% | 67% |
| Allen anytime TD | R2 / R1 | 57% / ~48% | on the box (needs the scorer quotes) |
| Rams moneyline | R2 | 60% | on the box's game board |
| Allen 200+ pass yds | R3 | high (−349) | 69% |
| Kyren 50+ rush yds | R3 | high (−311) | 78% |
| Nacua 70+ rec yds | R3 | high (−276) | 71% |
| Coleman 40+ rec yds | R3 / R4 | moderate / 65% if Moore out | 54% |
| Kyren 15+ rec yds | R4 | 76% (−203) | 67% |
| Adams 60+ rec yds | R4 | 67% | 52% |
| Kincaid 50+ rec yds | R4 | 65% | 50% |

## Their angles we already had

The 10-08 parity doc maps most of them: the dome, injuries and who
steps in, unit ranks (EPA, success, explosives, pressure, red zone), pass
rate over expectation, defence against each position (including RB
receiving, where Buffalo is 30th), game script from the spread and total,
first game back (Nacua's isn't, he played week 4), Kalshi/Polymarket game
prices and money split, the opening line against now, the −250 price cap,
correlation on the slip, alt rungs on yards and catches, the QB touchdown
model (goal-line work and the measured quarterback scale), and the
questionable-teammate note ("if Moore sits…").

## Their angles we don't have, and why

| Angle | Verdict |
|---|---|
| Alt rungs on completions, attempts and rush+rec yards (all of report 1's card) | We buy alternates for yards and catches only, so the board can price 21+ completions but has no book price to seat it. The Odds API documents alternate keys for these too (unproven from here); they would cost three or four more credits a game (22 now). **Your call**: say yes and I'll add them behind the same drop-and-retry guard. |
| A teammate who left a game early (Moore, weeks 2 and 4) | Our "left early" rule compares him with his own median. With two short games in four, his median is low and nothing is flagged. Last season's anchor now covers most of it (Coleman 61.6 → 44.3). |
| A defender out (Ed Oliver, Dee Alford, Quentin Lake) | **Measured the same day** (`defoutfit.py`): starters (60%+ of snaps) listed Out or Doubtful, against what the defence gives up beyond its rating. Every market got worse in at least one held-out season, so it is not in the number; the injury board shows who is out. Re-run once 2026 is complete. |
| Quarterback against man or zone (Allen +0.36 EPA vs man, +0.17 vs zone) | Coverage comes from nflverse's participation file, which publishes a season behind. Last season's split could be measured; not done today. |
| Kalshi player-prop contracts (R2: "Kalshi 68.5¢" on Stafford 250+) | We read Kalshi's game, spread and total series only. Kalshi is blocked from this sandbox; `kalshiprops.py` is the box probe (runbook step 33). |
| Ticket and money splits (Circa via VSiN) | No free feed. We don't scrape. |
| Referee crew (Scott Novak, most penalties) | Report 4 found no reliable trend either. Not built. |
| Coach trends ("Under 29-14 as a home favourite under McVay") | Not measured, and not worth a number on its own. |

## Known limits of today's fixes

- ~~The calibration replay builds its slates without last season.~~ Fixed
  the same day: `propcal` replays with `carry=True`, as the live board
  builds.
- ~~The usage bridge reads only this season.~~ Measured and fixed the same
  day for catches, receiving yards and rushing yards (`bridgefit.py`);
  passing yards failed 2025 and keeps its bridge as it was.
- Measured with the form's default curve; a market whose curve the
  formfit adopted runs a slightly different blend underneath.
