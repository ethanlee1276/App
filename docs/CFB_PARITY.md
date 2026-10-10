# College football on the NFL's level — the checklist

Ethan, 2026-09-26: *"look exactly what we did for NFL and make sure every
single thing is done for college football. we want it locked in and ready
to go."*

Every NFL change from the matchup and Most Likely work (tasks 45–133), and
where college stands. **Done** means built, tested and running in
`cfb_build.py`. **Different** means college does the same job from the data
it has, and the page says how. **Not possible** means the data does not
exist for college, and the reason is written down.

## The matchup scan and the reads

| NFL work | College | How |
|---|---|---|
| Unit rankings per team (offence and defence) | Done | CFBD advanced season table ranked across FBS (`gamescan.cfb_ratings`) |
| Tale of the tape on the game page | Done | Same page code, college units |
| This season leads last season, both used | Done | Blended by plays (`CURRENT_SHARE`) |
| Could shine / could struggle / breakout reads | Done | `gamescan.scan_game`, college branch |
| Reads for every key player, not only priced ones | Done | College usage table feeds `key_players` (`gamescan.cfb_usage`) |
| Usage on every read (targets, carries) | Different | College logs catches, not targets. The share is said as **catches** and is never passed off as targets |
| Every read says his touchdown chance | Done | `stamp_touchdowns` from the whole scorer list |
| A read's pick, or why there is none | Done | `stamp_picks` with the board |
| Coverage room, scheme, pass-rush charting | Not possible | No defender files or charting exist for college |

## Touchdowns

| NFL work | College | How |
|---|---|---|
| Touchdowns routed into Most Likely | Done | College scorer board |
| Touchdown value board refusal census | Done | `td_census` |
| Red-zone trips, offence and defence | Different | **Scoring chances**: drives reaching the 40, from CFBD, had and allowed, compared with the league. Raw, not schedule-adjusted, and the card says so |
| Red-zone chances scaled to this week's offence | Different | Scaled by this week's implied total against the points his team scored when the touches were measured (`tds._rz_now`) |
| Touchdown matchup of 8 | Done | A college defence's rank is read as it would sit among 32 (`tdscenarios.rank32`) |
| Touchdown scenarios shelf | Done | Built, journaled (`td_scenario`) and pooled into the board |
| Never a listed or pulled player in a scenario | Done | College injury board and pulled players |

## Matchup picks and the one board

| NFL work | College | How |
|---|---|---|
| Matchup picks per game (touchdowns, yards, catches) | Done | `matchpicks.build`, journaled `matchup_td` and `matchup_prop` |
| Real sportsbook line, juice cap, role floor | Done | Role floor is 2 catches a game where the NFL uses 3 targets |
| One Most Likely board with four checks and tiers | Done | `likelyboard.attach(out, "cfb")`, journaled per tier |
| Record check says its numbers | Done | Same page |
| Novig price only when a sportsbook is close | Done | Props and anytime-TD scorers (`oddsapi.best_scorer_price`) |

## Who plays

| NFL work | College | How |
|---|---|---|
| Injury report read by the build | Done | ESPN college injury board (`injuries.load_cfb_injuries`), which fed only the Injuries page before |
| Listed player's props held | Done | The slate's games carry the injuries; the rules engine's health check holds them |
| Player every book took down treated as out | Done | `pricedplayers.Tracker` in the college quote pull |
| Starting QB out, benched or back | Done | Usual starter from college passing logs, this week's from the passer the books priced. Priced by college's own measured multipliers (`engine/cfb/lineup`, 2026-10-10 — see round 2); x1.00 until college's fit is saved |
| Teammate out, what it opens | Done | The scan names who is out and what his share opens ("30% of the catches to go around") |
| Teammate-out lineup step moving the number | Done | Measured on college's own games (`engine/cfb/lineup`, 2026-10-10 — see round 2); x1.00 until college's fit is saved |

## How to check it on the droplet

After a college build, `data/logs/cfb_build.log` prints each piece:

```
Injuries: N designation(s) on tonight's schools (M out or doubtful)
Pulled by every book before kickoff: N player(s)
QB changes: ...
Matchup scan: N of M game(s), K lean(s) for Most Likely.
Touchdown scenarios: N · matchup picks: M across G game(s)
Most Likely board: N pick(s) — T top, S strong, L worth a look
```

The full board is at `data/built/cfb.json`. The public `web/data/cfb.json`
is the free copy, with the paid picks removed.

## Round 2 — everything the NFL got from 2026-09-27 to 2026-10-09

Ethan, 2026-10-09: *"Our edge picks for college football is 34 for 23, and
we're up eight units ... But our most likely picks for college football is
down 3% ROI ... look at every single tool and every single data point and
every single everything we've added for NFL and add it for college
football."*

**Done today** means built, tested and running for college from the next
build. **Measuring** means the college version is built and runs on the box
under the NFL's own bar; it changes a college number only when college's
own games or record pass it. **Already** means college had it.

### What sets a Most Likely pick's chance

| NFL work | College | How |
|---|---|---|
| The record corrects each maker's chance (likelycal) | Already | Every league, fitted on its own record |
| The board learns by itself on every settle (boardlearn) | Already | Every league |
| A losing pick comes off only when our reads also say no | Already | Every league |
| One bet, one chance (harmonize) | Already | Every league |
| The scout's football flags on every card | **Done today** | College thresholds (`scout.LEAGUE`): shootout 63, grind 48, big dog 17, big favourite 24 / 17, blowout 28, low implied 20. Written before any college measurement |
| The scout's correction from the record (likelyctx) | **Measuring** | College's own record, the NFL's held-out bar, refit on every settle |
| History proves a flag (scouthist: first game back, shootout unders) | **Measuring** | College's stored games, both halves, 100+ each; own store |
| Per-position spread (posspread: tight ends too sure) | **Measuring** | College's player-weeks, the NFL's bar, college's own record veto; own store |
| Touchdowns follow the team total (tdscale) | **Measuring** | The NFL's exponent per position, on college's own replay (`cfbtdfit.run`) against college's average team (26.7), the NFL's bar, college's own store (`cfb_td_implied.json`). Refitted weekly before college's touchdown temperature, which is fitted on top of it. 0 (no change) until a position passes |
| Defence strengths for attempts, completions, interceptions | Done | Measured 2026-10-10 (`python3 cfbmarketfit.py --opp`, held out 2023, 2024, 2025 in turn; needs +0.01 ranking AUC in every season): interceptions ADOPT x1.5 (+0.109) and back rushing yards ADOPT (+0.020), both already in `TRANSFER_CFB`; attempts +0.005, completions +0.002, carries +0.008 — under the bar, so the defence stays out of those numbers, as measured |
| Teammate out, what it opens (lineup step) | **Measuring** | `engine/cfb/lineup`: a catch-ranked depth order off college's logs (carries plus catches for a back), out from ESPN's board and every book's pulled players, the NFL's cases and the NFL's rule (2 SE, 3+ seasons). Applied from the store the fit saves; x1.00 until then |
| Lineup steps on the touchdown board | Done (2026-10-10) | College's scorers are not slate props, so the projection never saw them; `cfb/tds.lineup_step` applies the same two steps on the scoring rate before the price, from college's own store. The NFL shows these on touchdown rows and never prices them (measured as noise there); college's fit adopted RB touchdowns behind a downgrade at quarterback (x0.87), so college prices it |
| New starting QB moves his receivers | **Measuring** | Same module: qbfit's starter and tier on college passing, the change read from the passers the books priced BEFORE pricing, college's own multipliers |

### The price (Ethan's call, 2026-10-09)

The box's loss audit: staked college Most Likely picks claimed 63% and hit
63% at prices that needed 65% — honest numbers, bought too dear (127-76,
-4.1%). Ethan chose **stake only when we cover the price**: a college pick
is staked only when the chance its card shows is at least what its price
needs to break even (`ledger.PRICE_COVER_SPORTS`). Below that it is still
published and graded, on paper, and the card says "Price too high to
stake". The NFL is not in it.

### Data the NFL added

| NFL source | College | Why |
|---|---|---|
| Next Gen Stats (separation, RYOE, CPOE) | Not possible | NFL tracking data; no college equivalent is published |
| FTN charting (blitz, box, play-action, drops) | Not possible | NFL charting only |
| PFR advanced passing and receiving | Not possible | NFL pages only |
| Target depth and depth zones | Not possible | Needs air yards per target; college play-by-play does not carry them reliably |
| Thin-target receiving over (scout flag) | Not possible | College logs catches, not targets, and this checklist never passes catches off as targets |
| Expected QB starters from the news feed | Different | College reads the passer the books priced (C4) |
| Opening lines kept per game | Already | College keeps its line snapshots (lineledger) |
| Interceptions, attempts, completions, carries markets | Already | Q1 and Q4 |

### Box checks for round 2 (read-only)

```
cd /srv/qellys
sudo -u qellys python3 -m engine.scouthist --sport cfb --dry-run 2>&1 | tail -40
sudo -u qellys python3 -m engine.posspread --sport cfb --dry-run 2>&1 | tail -20
sudo -u qellys python3 -m engine.likelyctx fit --sport cfb --dry-run 2>&1 | tail -30
```

The first prints, for both leagues' stored games, the share each game-script
threshold catches (college's numbers should catch about the share the NFL's
catch of NFL games), then what history proves for college. The second says
which college position widths would be adopted. The third says whether
college's record can prove a flag yet. None of them saves anything.
