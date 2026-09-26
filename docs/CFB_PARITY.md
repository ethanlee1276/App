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
| Starting QB out, benched or back | Different | Usual starter from college passing logs, this week's from the passer the books priced. **Shown, not priced**: the NFL's receiver effect was measured on NFL games; college has not been measured |
| Teammate out, what it opens | Done | The scan names who is out and what his share opens ("30% of the catches to go around") |
| Teammate-out lineup step moving the number | Not measured | The NFL's step is measured on NFL data (`engine/teammates`). College stays unpriced until it is measured the same way |

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
