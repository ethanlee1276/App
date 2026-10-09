# Research parity — Buccaneers @ Cowboys, 2026-10-08

Ethan pasted four outside write-ups of tonight's game ("here 4 researches
for tonights nfl game. look at where it is looking and the site isnt and
make sure we are hitting all the marks"). This is every angle the four
used, against what the site computes, and what was built from it.

**Built tonight (free data, measured before it moves a number):**

| # | Angle the research used | Site before | Now |
|---|---|---|---|
| 1 | "Dallas has allowed a league-high 188 rushing yards to quarterbacks — Dart 54, J. Daniels 69, Lamar 50" | A QB rushing prop read **no defence at all** (`stat_for("QB","rush_yds")` was None; the number used nothing) | `defensevs.STATS["qb_rush_yds"]`: rated per defence, shown on the QB rushing pick card ("rushing yards to QBs" beside the run defence), said in the scan read ("DAL gives up 47 rushing yards to quarterbacks a game — the 1st-most of 32"). **Measured 2026-10-09 on the box: b +0.30 ± 0.12 (n 955), held out 2021 −0.10% / 2022 +1.26% / 2023 +0.12% / 2024 +0.09% / 2025 −1.92%, mean −0.11% — fails the bar (two seasons negative), so it stays shown, not in the number** |
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

**The five I first called "paid"** — Ethan: "u really think we have to
pay for this data or is there other ways to get it and maybe use past
game data … seems like it should be free data." He was right about
three of them:

| Angle | Verdict | Where it is now |
|---|---|---|
| Coverage shell rates ("single-high 2nd-highest", "two-high", "Cover 3 ~70% zone") | **Free, and the scan already had it.** nflverse's participation file charts every dropback's coverage (man/zone, Cover 0/1/2/3/4/6/2-man) and pressure; `nflscheme.scheme` turns it into man %, zone %, single-high % (Cover 1 + 3), two-high/open-middle %, blitz %, pressure %. The one catch: nflverse publishes the file a season behind, so in-season these are **last season's tendencies**, and the page says which season. Same coordinator, mostly the same shells | Game page scheme line (now says "single-high (Cover 1/3) NN%" explicitly) |
| Yards after contact ALLOWED by a defence ("1.73, best in the league") | **Free, derivable from past game data** — exactly as asked. PFR's weekly advanced rushing table (nflverse, within the week) gives every rusher's yards before contact, after contact and broken tackles, with the opponent; summed by the defence they came against it is the research's number | `nflscheme.run_contact` / `rushers_contact`; the RB card: "DAL allows 2.90 yards after contact a carry (20th-fewest of 32) and 2.40 before contact (12th-fewest); he averages 3.10 after contact" (last season's until a defence has faced 60 carries). Measurement arm `yac_allowed` in `scanfit.PENDING` |
| "Completing over 80% when kept clean" | **Half free.** PFF counts every pressure; the play-by-play records hits and sacks. So the split the site can build is completion % when NOT HIT against when hit — the free half, and the card calls it that. (Last season's participation file has `was_pressure` per play for the full split, a season behind) | `nflpbp.POCKET_MARKETS` (nightly fold) → `nflusage.pocket_split` → the QB card: "Completes 71% of his throws when not hit and 33% when hit (league 65% / 43%); DAL hits or sacks the passer on 9.1% of dropbacks, 5th of 32". Measurement arm `pocket_fit` (his gap × their pressure) in `scanfit.PENDING` |
| Which corner covers which receiver; shadow assignments (Porter on Egbuka; Lamb vs the rookie slot) | **Not free.** Who lines up across whom comes from the league's tracking data, which is not public (the participation file lists the eleven on the field, not where they stood). What IS free and already on the scan: each corner's own targets, completions, yards and passer rating allowed (PFR), his depth-chart spot (outside / slot), and the defence's man rate — in a man-heavy defence the top corner travels more often, but that is inference, so the card does not say it | coverage room on the game page |
| PFF matchup grades and projections | **Not free** — PFF's grades are its product. The things a grade summarises are the free stats above (rating allowed, separation, cushion, EPA per target), which the scan reads | — |

Also built the same night: the three zones on the game page's tale of
the tape ("Short throws allowed … 24th"), and the QB-change card's
offence shape gained where the ball goes under him — "in his starts 73%
of the team's targets were short throws (under 10 air yards) and 7% deep
(20+) — Mayfield's starts: 50% short, 18% deep" (the offence side of the
same `team_units` columns, over his start weeks).

**Next if wanted:** the depth signal's box run (`engine/scanfit`) — if
it passes the bar, the zone matchup joins the number for receivers.
