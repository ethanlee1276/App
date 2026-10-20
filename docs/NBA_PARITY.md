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
| What a missing teammate opens | Done *(10-20)* | `engine/nba/onoff` measures what his teammates did when he sat; a read counts it only when the logs measured it |
| The teammate-out step moving the number | Different | The card shows it (the lineup card). It moves the number only once `engine/nba/onoff` passes its edge test |
| What if he sits | Done | `engine/nba/whatif`: the record behind each teammate's absence |
| Starting QB change | Not possible | No basketball equivalent; a star out is the teammate rows above |

## The game around the bet

| NFL tool | NBA | How |
|---|---|---|
| Schedule spots (rest, travel) | Done | Back-to-backs, three games in four nights, four in six on the road; in the reads and the report |
| Game script | Done *(10-20)* | A starter facing a spread of 10 points or more gets the blowout line; the points his team is expected to score count in his read |
| Weather, kick physics, altitude | Not possible | Basketball is played indoors |
| Officials | Different | Each game's crew is stored from ESPN's summaries (`engine/officials`). Nothing moves a number until a season of closing totals is stored to test it against. Showing tonight's crew before tip-off is one of the D questions waiting on you |

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
  if it measures better.

## How to check it on the box

Step 150 (CS) in `docs/WHEN_YOU_ARE_HOME.md` has the commands: the code
version, the shooting columns, last season's re-read, the team numbers,
what the board carries, one game's report, the contradiction check, and
which NBA markets Most Likely may carry.
