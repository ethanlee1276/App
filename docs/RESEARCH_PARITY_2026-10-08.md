# Research parity — Buccaneers @ Cowboys, 2026-10-08

Ethan pasted four outside write-ups of tonight's game ("here 4 researches
for tonights nfl game. look at where it is looking and the site isnt and
make sure we are hitting all the marks"). This is every angle the four
used, against what the site computes, and what was built from it.

**Built tonight (free data, measured before it moves a number):**

| # | Angle the research used | Site before | Now |
|---|---|---|---|
| 1 | "Dallas has allowed a league-high 188 rushing yards to quarterbacks — Dart 54, J. Daniels 69, Lamar 50" | A QB rushing prop read **no defence at all** (`stat_for("QB","rush_yds")` was None; the number used nothing) | `defensevs.STATS["qb_rush_yds"]`: rated per defence, shown on the QB rushing pick card ("rushing yards to QBs" beside the run defence), said in the scan read ("DAL gives up 47 rushing yards to quarterbacks a game — the 1st-most of 32"). **Not in the number** until `python3 defensefit.py` on the box measures it (runbook step 13) |
| 2 | Post-mortem rule: "reception overs outside a team's top-2 targets need 15%+ target share" | No flag; target share shown in usage only | `scout.FLAGS["thin_target_over"]` on the card, read from the scan's usage; a **note until the record proves it** (likelyctx fits every flag on the journal, held out) |
| 3 | "Tampa altered its entire offense around Daniels — 31 runs vs 36 dropbacks, 4.2 air yards per target, 8 carries for 55" | QB-change card: who starts, his yards an attempt vs the starter's | `qbchange.shape_words`: the team's pass rate in his starts (against the usual starter's), his carries and rushing yards a game, his air yards an attempt |
| 4 | "Inactives come out about 6:45 PM ET — confirm Otton and Godwin are active" | Kickoff only | The NFL game page says "inactives 6:45 PM ET" (90 min before kickoff) while the game is ahead |
| 5 | "Lamb works the short and intermediate zones"; "Egbuka's deep targets against Porter"; "4.2 air yards per target" | Target depth was computed for the xFP model only (red zone / deep / short value buckets) and never said | Every target counted by air yards — short (under 10), intermediate (10–19), deep (20+) — per receiver (`tgt_short/mid/deep` rows) and per defence-week (`team_units` short/mid/deep targets and yards). The defence is ranked in each zone like every unit; the card says "58% of his targets are short throws (under 10 air yards); TB ranks 24th of 32 against them, allowing 6.9 yards a target". Registered in `engine/scanfit` as the `depth` signal — **shown, not in the number**, until the box's run measures it (runbook step 13) |

**Already on the site** (the research's angle → where it lives):

| Angle | Where |
|---|---|
| Who is out, and who steps in for a defender (Melifonwu for Winfield, Barham for Overshown) | injuries board; `gamescan.coverage_room` names the sub and the weakest starter left |
| QB change, the replacement, his sample | `qbchange` card on every row of that team |
| Unit ranks: scoring, EPA, success, explosive plays, pressure, YPC, third downs, red-zone TD rate | `gamescan` units (S1), the tale of the tape |
| Blitz rate vs pressure generated | FTN charting (`blitz_rate` on the scan) + pressure per dropback |
| Pass rate over expectation | `sources/nflpbp` (`pass_oe` per play) in the units |
| Defence vs position: WR/TE/RB yards, catches, TDs; QB yards, TDs, attempts, completions, INTs | `defensevs.STATS`, every pick card and scan read; in the number where measured (`TRANSFER`) |
| Target share, targets/carries a game, carry share, red-zone usage | scan usage (`USAGE_RATES`), red-zone chances, goal-line usage |
| Target depth (short / intermediate / deep) | built tonight — row 5 above |
| Game script from spread/total: trailing teams stop running, favourites sit on leads, shootouts, low totals, blowouts | `scout.FLAGS` (dog_run_over, dog_pass_under, fav_pass_over, fav_run_under, shootout_under, low_total_over, blowout_over) |
| First game back, thin sample, boom-or-bust, short week, wind | `scout.FLAGS` |
| NGS tracking: completion over expected, YAC over expected, separation, cushion | scan tracking lines (free data #2, #6) |
| Game logs and the hit rate at the line ("22, 26, 25, 32") | pick page logs, `recent_values`, hit rate |
| Line movement on the prop (FD 56.5 → 51.5) and the game (10 → 8.5), sharp money | `linemoves` opened → now on cards and the game page; sharp witness; prediction-market money split |
| Fair price and the price to take ("max −250") | price to take on every Most Likely row |
| Per-book prices, the best price, alt lines | Bet it sheet (best price, your book), alt-line note |
| Joint hit rate of the parlay with correlation ("about 38%, fair +165") | the slip: correlation tax, capped at three legs, contradicting legs refused |
| Staking ($10–15 vs $25–30) | Bankroll page |
| Indoor venue — weather a non-factor | `weather.dome` |
| Catch rate, RB targets | usage; the pick page |

**Cannot be done with free data** (said so, not faked):

| Angle | Why |
|---|---|
| Which corner covers which receiver; shadow assignments (Porter on Egbuka; Lamb vs rookie slot Keionte Scott) | Alignment data is PFF/charting-only. The scan has coverage room and the weakest starter left, not man-on-man pairs |
| Coverage shell rates ("single-high 2nd-highest", "two-high shell", "Cover 3 ~70% zone") | No free coverage-shell source |
| PFF matchup grades and projections | Paid |
| Yards after contact ALLOWED by a defence (1.73, best) | Not in nflverse/PFR free tables |
| "Completing over 80% when kept clean" | Pressure-split completion rate is PFF/NGS-only per QB |

Also built the same night: the three zones on the game page's tale of
the tape ("Short throws allowed … 24th"), and the QB-change card's
offence shape gained where the ball goes under him — "in his starts 73%
of the team's targets were short throws (under 10 air yards) and 7% deep
(20+) — Mayfield's starts: 50% short, 18% deep" (the offence side of the
same `team_units` columns, over his start weeks).

**Next if wanted:** the depth signal's box run (`engine/scanfit`) — if
it passes the bar, the zone matchup joins the number for receivers.
