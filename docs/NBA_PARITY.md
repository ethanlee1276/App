# The NBA on the NFL's level — the checklist

Ethan, 2026-10-20: *"make sure nba is ready to go. We need most likely and
edge bets being posted and recorded ... look at what we use for nfl data and
tool wise and make sure NBA has the same shit. We need matchup details and
all that shit. We need reports for nba and key matchups and breakout
players."*

Every NFL tool and data source, and where the NBA stands. **Done** means
built, tested and running in `nba_build.py` (the same build makes the WNBA
board). **Different** means basketball does the same job its own way, and
the page says how. **Not possible** means the data or the idea does not
exist for basketball. **Not yet** is a real gap, with the reason. Items
marked *(10-20)* were built in this round.

## The picks: posted, recorded, settled

| NFL tool | NBA | How |
|---|---|---|
| Edge picks, staked and journaled | Done | Recorded every build; settled from the box scores the nightly job stores |
| Most Likely, on paper | Done | `likely.build`; the matchup scan's leans now help choose the side *(10-20)* |
| One board, four checks, tiers | Done | `likelyboard.attach`; its matchup check reads the scan and the model ("scan+model") *(10-20)* |
| Matchup picks per game | Done *(10-20)* | `matchpicks.build(sport="nba")`: points, rebounds, assists, threes and the combos, on the read's side where our number agrees, at a real sportsbook price, 20+ minutes a game; journaled as `matchup_prop` |
| Pick of the Day | Done | `engine/potd`, one hook for every sport |
| Settled within minutes of the final | Done | Every league |
| Board corrections that learn on their own | Done | `likelycal` refits every league after each settle; NBA calibration and player memory on top |
| One bet never argued both ways | Done *(10-20)* | `python3 -m engine.contradictions --sport nba` reads Edge, Most Likely, the one board, matchup picks and the reads against each other |

## The projection, measured on two full seasons *(11-04)*

The NFL's numbers got better by measuring every idea on games the model
never saw. `docs/NBA_LAB.md` does that for the NBA: the league's own
play-by-play for 2024-25 and 2025-26, every idea fitted on one season and
judged on the next.

| NFL tool | NBA | How |
|---|---|---|
| Play-by-play read into who was on the field | Done *(11-04)* | `engine/nba/stints`: who was on the floor every second, from the substitutions, and every box score it derives matches the final. Research for now; the box already downloads this play-by-play for the shot charts |
| A rate's luck taken out (the NFL's touchdown and catch-rate regressions) | Done *(11-04)* | `engine/nba/shooting`: points and threes from shot volume at his long-run percentages, shrunk toward the league's. Threes 1.68% closer, points 0.99%, the points combos 0.6–0.9%. The pick shows the step "Shooting, luck taken out" |
| A spread fitted to the player, not one size for all | Waiting *(11-04)* | `hoops.NBA.sd_power`: variance = a × projection^c, 0.8–2.1% better on Brier in seven markets. The weekly deep refit runs `nbalabcheck.py` itself and files its verdict; the NBA refit fits on it and then throws the switch (`engine/nba/switches`, runbook KC). `QB_NBA_SPREAD` on the box still decides first |
| The minutes model measured | Done *(11-04)* | Rest and blowout haircuts fitted on two seasons (a back-to-back costs a man who suits up nothing; a blowout 1-5% for a favourite's starters, not 9-14%), the newest games weighted more, a bench player's minutes trimmed 2%: minutes error 6.40 to 6.21 on the season it never saw (`hoops.NBA`) |
| The rotation's news in the number (the NFL's first-game-back and role reads) | Done *(11-04)* | `engine/nba/minutes`: his first game back x0.96 / 0.92 / 0.84 by games missed, his second back x0.96, a minutes jump 40% held, a regular's return taking a quarter of his minutes back from the rest. Each held out both ways; `nbarules.py` asks the box's own seasons every week and the rules follow it (runbook KC). `QB_NBA_ROTATION 0` turns them off |
| The scout's flags on the card (`engine/scout`, `likelyctx.annotate`) | Done *(11-04)* | `engine/nba/scout`: fourteen spots written before measuring, each measured before any model and after ours; the six still over-claimed after our number ride the Edge card and Most Likely's "Why?" as "Scout:" lines, for the side each takes |
| The scout's flags corrected by the record (`likelyctx.fit`, `scouthist`) | Done *(11-04)* | `engine/nba/scoutrecord` rebuilds each settled pick's situation from the stored games; `likelyctx` fits every flag on the NBA's own record (five folds by game, the same bar) and the board applies a proven one, only ever lowering. The game-script flags read the spreads and totals the NBA build keeps from 11-04. No `scouthist` (history-replayed shifts) for the NBA: the lab's two seasons did that job once, by hand |
| Ideas measured and not built | Done *(11-04)* | Back-to-backs and home or away on the rate, last five over last twenty, rebound chances, the referees, and a player's own record with and without a teammate: none helped on the season it never saw. Listed in the changelog as a refusal |

## Offense against defense — the matchup scan

| NFL tool | NBA | How |
|---|---|---|
| Unit rankings for every team | Done *(10-20)* | `engine/nba/teams`: points and points allowed, offense and defense per 100 possessions, pace, shooting (eFG%) both ways, threes both ways, the offensive glass, turnovers both ways. Ranked 1–30 from the stored box scores |
| Tale of the tape on the game page | Done *(10-20)* | The game page's Matchup scan section, and "The matchup" in the report |
| This season leads, last season fills in | Done *(10-20)* | This season counts games / (games + 10) of the blend |
| Key mismatches | Done *(10-20)* | Up to five key matchups a game: one side's offense near the top against the other's defense near the bottom, widest gap first; pace when both teams play fast or both play slow |
| Defense vs position | Different | `engine/hoopsdvp`: what each defense allows in each stat (points, rebounds, assists, threes), read into the projection by a measured share and into the reads. By stat, not by position: the box score names a position for the five starters only |
| Could shine / could struggle / breakout | Done *(10-20)* | `engine/nba/scan`. A breakout needs a role change (minutes, usage or a teammate out) behind a strong case |
| A read on every key player | Done *(10-20)* | The top eight on each team by minutes (12+ a game), plus anyone with a prop on the board |
| Usage on every read | Done *(10-20)* | Minutes a game and usage share, over his last five against the season |
| Every read says its pick, or why there is none | Done *(10-20)* | `gamescan.stamp_picks`, as in football |
| The dashboard's shine / struggle lists | Done *(10-20)* | The same lists as football's, filled from the NBA reads |
| Coverage room, scheme, pass rush | Not possible | Football ideas. Basketball's version is the four factors and defense vs position above |

## Who plays

| NFL tool | NBA | How |
|---|---|---|
| The injury report read by the build | Done | ESPN's injury board. Out and doubtful players are held; questionable players are graded down |
| A player every book took down counts as out | Done | The slate's pulled players, in the build and the scan |
| What a missing teammate opens | Done *(10-20)* | `engine/nba/onoff` measures what his teammates did when he sat; a read counts it only when the logs measured it. A player's own with/without record, from whole games or from every minute the teammate sat, was too noisy to move a number on two full seasons *(11-04, docs/NBA_LAB.md)* |
| The teammate-out step moving the number | Waiting *(11-04)* | `engine/nba/vacancy`: k x the absent regulars' minutes, shared by the room each man has to play more (base x (34 - base), measured held out: minutes 6-8% closer than by base). Holds on the lab's two seasons against the empty slot (k 0.40; minutes 10.3-12.0% closer, points 3.5-3.6% in those games); on once the box saves its own verdict, which the weekly deep refit now does itself (`nbavacancy.py nba --heldout --save`, runbook KC). The card shows the absence either way |
| What if he sits | Done | `engine/nba/whatif`: the record behind each teammate's absence |
| Starting QB change | Not possible | No basketball equivalent; a star out is the teammate rows above |

## The game around the bet

| NFL tool | NBA | How |
|---|---|---|
| Schedule spots (rest, travel) | Done | Back-to-backs, three games in four nights, four in six on the road; in the reads and the report |
| Game script | Done *(10-20)* | A starter facing a spread of 10 points or more gets the blowout line; the points his team is expected to score count in his read |
| Weather, kick physics, altitude | Not possible | Basketball is played indoors |
| Officials | Different | Each game's crew is stored from ESPN's summaries (`engine/officials`). Nothing moves a number until a season of closing totals is stored to test it against. Showing tonight's crew before tip-off is one of the D questions waiting on you. Measured on two full seasons of play-by-play *(11-04)*: the crew's free-throw rate moved no player's points, rebounds or assists on the season it never saw (docs/NBA_LAB.md) |

## The market

| NFL tool | NBA | How |
|---|---|---|
| Kalshi and Polymarket prices | Done | `engine/crowd`, every game |
| The exchange's fair price | Done | `engine/exchangefair` |
| Opening lines kept and compared | Done | `engine/lineopen` |
| Closing lines before tip-off | Done | Every sport |

## Reports and pages

| NFL tool | NBA | How |
|---|---|---|
| A written report on every game | Done | `engine/leaguereport`, NBA sections |
| The matchup and players to watch, in the report | Done *(10-20)* | "The matchup" (the tape and its key matchups), "Players to watch" (breakout watch, could shine, could struggle) |
| What changed, copy, share | Done | Every report |
| Ask reads the report | Done | It now reads the key matchups too *(10-20)* |
| Player charts | Done | Shot chart and the role trend chart |
| Live game page | Done | The court render; the ball moves shot to shot |
| Team page | Done | Every sport |
| Parlay checker, hedge, better number, live chances | Done | Every sport |

## Football's own data

These are football feeds, and the NBA has nothing to match them yet:

- **Next Gen Stats, FTN charting, PFR advanced stats** are football feeds.
  The basketball equivalent would be the NBA's own tracking numbers
  (touches, drives, potential assists). **Not yet:** that would be a new
  source, and it has to be measured before it moves a pick.
- **The practice report and how honest each coach is.** **Not possible:**
  the NBA publishes injury statuses, not practice participation.
- **The drive simulator, touchdown scenarios and red-zone chances.**
  **Not possible:** football only.
- **Rookies translated from their college numbers.** **Not possible:** no
  college basketball data is stored.
- **Player spots: revenge game, contract year, milestones.** **Not yet.**
  The NFL's contracts come from nflverse, and nothing free covers the NBA.
  A revenge game (facing a team he played for) could come from our own
  history, but nobody has measured whether it matters.

## Next, once the box has re-read last season

- **The defense numbers per possession.** `engine/hoopsdvp` counts what a
  defense allows per game, so a fast team's defense reads a little worse
  than it is. Possessions are now stored (step 150), so a per-100 version
  can be measured with `hoopsdvpfit.py`. It replaces the per-game one only
  if it measures better. The lab measured it on two full seasons *(11-04)*:
  per game read as well or better for points, rebounds and assists. For
  threes, the three-point attempts a defense allows per possession added
  0.1% beyond the shooting read: the one per-possession number worth
  trying in `hoopsdvpfit.py`.
- **The floor data on the box.** Store each game's stints from the
  play-by-play the nightly already downloads, so the lab's floor reads can
  be re-measured on our own games.

## How to check it on the box

Step 150 (CS) in `docs/WHEN_YOU_ARE_HOME.md` has the commands: the code
version, the shooting columns, last season's re-read, the team numbers,
what the board carries, one game's report, the contradiction check, and
which NBA markets Most Likely may carry.
