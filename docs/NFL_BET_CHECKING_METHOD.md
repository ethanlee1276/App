# Ethan's NFL Bet checking method, and where it lives on the site

Ethan's Claude project "NFL Bet checking" (exported 2026-11-14) holds the
master instructions, the slate log (the cards and post-mortems from 1 October
to 12 November) and 55 game chats from 9 September to 12 November. On
2026-11-15 they asked for the project's reports and how they work to be built
into the game reports, the website and how the Most Likely bets are selected.
On 2026-11-20 they pasted the current instructions, **"NFL Prop Bot — Master
Instructions v3.1"**, with: "Those instructions should be used alongside what
we've already talked about in finding our most likely picks and game report
picks with all of our data ... These instructions should not be replacing
anything."

This page maps the method to where the site does it. The first table is v3.1,
section by section. The tables under it are the 14 November mapping (the
"Full Master Instructions", 27 rules), which still stands. It also says what
the site does differently, and why.

## v3.1 (20 November 2026), section by section

| Section | What it says | On the site |
|---|---|---|
| Mission | A pick is a disagreement with a price; honest targets inside −250: single legs 60–68%, two-leg parlays 37–45%, three-leg 25–30%; show the real joint chance; never force a play | Every ticket shows its joint chance, fair price and take-it-at price. A game with no pick says "No qualifying plays at current lines" and names the closest three. The boards stay likelihood-first, as their own messages asked (below); see "The price grade" for why Green, Yellow and Red are not on the cards |
| 0. Start of every card | Rebuild the comps engine and the board from the project's toolkit docs | Theirs to run. The toolkit docs (`claude/data-toolkit.md`, `claude/data-toolkit-matchup.md`) and the season audit were not in the paste, so the comps tables are known here only as the summary in §3 |
| 1. Hard gates | −250 at the heaviest; one book a ticket; two legs by default, three only when asked; touchdown tickets apart; tickets on a game win together; kept off parlays: backup backs' yardage, quarterback rushing overs that depend on scrambles, quarterback rush-attempt unders, game totals in prop tickets | −250 caps every row and leg (`likely.HEAVIEST_PRICE`). Tickets win together (`gameparlays.choose`). Touchdown pairs are their own tickets, and prop tickets carry player props only (true since step AAH, 21 November: until then a Most Likely touchdown pick or moneyline could ride a prop ticket, and 28 touchdown legs and 4 moneylines did on the NFL's Friday board; `gameparlays.SCORERS_APART`, `GAME_LINE_MARKETS`). **Added 2026-11-20** (`gameparlays.off_parlays`): no parlay leg for a backup back's yardage (a back behind the lead carrier with under 8 carries a game), a quarterback's rush-attempt under, or a quarterback's rushing over where the charting has at least half the carries as scrambles. Three-leg tickets are posted because they asked the site for them (19 and 20 November). One book a ticket is a preference, not a gate: since step AAB each ticket names the one book that has every leg at its number or says none in our pull does (`gameparlays.one_book`), and since step AAJ a ticket one book prices whole is chosen first (`gameparlays.book_ranker`); a ticket no one book has can still post, and says so |
| 1. Their guardrails | No Lions unders; avoid Jets and Justin Fields; no CeeDee Lamb unless asked; no elite-quarterback passing-yard unders; no fragile unders | Kept for their own bets; the boards serve every member. The record holds the unders it has proven (`likelyboard.NFL_UNDER_CAUTIONS`, tight-end and receiving-yards unders) |
| 2. How a leg gets its number | Comps base rate, spot and matchup adjustments (capped −10/+12), then a haircut: 30% toward the market's no-vig chance and never more than 6 points above it; a second number from Qellys; take-at price; minimum 64% (SAFE) or 60% (BALANCED) | Our projections and their measured steps make the number. The haircut here is stricter because the record asked for it: an NFL pick is never shown above three books' fair price (`trust_price`, picked on held-out weeks), and a college prop never above its own price (`PRICE_CEILING`). The take-at price is on every pick line. Parlay legs clear 60% (`gameparlays.LEG_FLOOR`; a short game's fill goes down to 50%) |
| 3. Where legs come from | Rungs as a share of the season average (completions 0.82x hits 70%, and so on); Tier 1 volume markets, Tier 2 receptions, Tier 3 yardage as POP | The Most Likely list climbs the alternate ladder for the likeliest rung inside −250 (`likely._best_rung`). The tiers are not adopted as a ranking: on our graded record completions, attempts and carries at the lines we took are the weakest markets, so the record's own check decides (`record_check`) and completions stay benched from stakes. Their tables are about rungs well under the average, which the box can test (decision 4 below) |
| 4. Spot rules | Lifts and cuts by total, spread and trend; no back's carries or rushing on a 7+ underdog; on a 10+ favorite, attempts drop and completions and yards hold | The scout raises each (`dog_run_over` at 7, `low_total_over` at 40, `blowout_over`, `wind_pass_over`). **Changed 2026-11-20**: the big-favorite rule caps pass attempts only (`METHOD_MARKETS["fav_pass_over"]`); it had capped a favorite's completions and yards too |
| 5. Matchup scan | Who is guarding him, and how much each part may move the number; a cornerback matchup explains a receiver's leg and adds nothing; zero weight on touchdowns allowed to a position, streaks, revenge, primetime | The reports' rankings and "Who's guarding who". Our matchup step moves a number only by what was measured (`defensevs`, `hoopsdvp`). **Changed 2026-11-21** (decision 5, answered yes): in football a pass catcher's coverage read explains his catches and receiving yards and counts nothing toward Top; the projection's measured matchup step does (`likelyboard.COVERAGE_READ_SPORTS`, `QB_COVERAGE_READ=on` to undo) |
| 6. Breakout candidates | Definitions and base rates; about a one-in-four shot at best; POP legs at plus money, never the anchor | "Players to watch" names them with the reasons. The framing line (how often even the best spot gets there) is not on the report yet |
| 7. Game script | Four scripts with their chances; what each leg needs | Scripts A to D with their shares (`gamereport.script_blocks`); each ticket says what it needs and how likely (`gameparlays.script_need`) |
| 8. Injuries, roles, weather | Same-day status and replacements; a new starting quarterback with too few attempts to rate: no pass-catcher legs; wind 12+ caution, 15+ major | The injury list, what each absence opens, the news watch. **Added 2026-11-20**: behind a replacement with under 50 passes (`qbchange.card` `unrated`) a catch or receiving-yards pick tops out at Worth a look (`likelyboard.METHOD_NEW_QB`) and is no parlay leg. 15+ mph caps passing overs (`scout.WIND`). **Added 2026-11-21** ("6. Yes"): college's quarterback-change card counts the replacement's passes from college's logs and carries the same mark under 50 (`cfb/qbchange.attempts_of`) |
| 10. Parlay builder | SAFE, BALANCED, POP; one anchor; no more than two tickets on a leg; fair price beside the book's | A leg rides on two tickets of a size at most (`gameparlays.MAX_USES`: two of a game's three-leg tickets and two of its two-leg ones); each ticket shows fair and take-it-at and says when the legs' prices multiplied fall short of it. Each two-leg and three-leg ticket says Safe, Balanced, Pop or a long shot by these bars and names the one book that has every leg (`gameparlays.ticket_class`, `one_book`, step AAB); the dollar stakes are theirs and stay off the site |
| 11. Touchdown module | Base rates by team total; approve at 45% and at or above the price's break-even, or 40% at plus money with EV 6% and undeniable usage; never two pass catchers from one team | `likelyboard.td_rule`. **Changed 2026-11-20**: the fallback now needs a plus price paying 6% over our number (it had passed a red-zone role at any price), and two pass catchers from one team share no touchdown pair (`gameparlays.pair_link`). The 45% clause keeps no price test: see "The price grade" |
| 12. Sides and totals | Stricter edges | The game-bet lanes keep their own bars |
| 13–14. Live, hedge, bankroll | Their own staking | Not the site's to set; My Bets tracks a member's own |
| 15. Output | Ranked picks with book, price, final number, take-at, what it needs, who is guarding the player | The report's card and pick lines, the board's ranking (tier, matchup, chance) |
| 16. Learning loop | Log every leg; a market 8+ points under its rate over 20+ legs drops a tier; one rule a slate | Every pick is journaled and graded. `record_check` is that rule as written: 20 settled picks, 8 points under the claim, and the pick cannot be Top or Strong |

### The price grade (Green, Yellow, Red): on the NBA's and hockey's picks, not football's

v3.1 posts a leg only when its number beats the price (Green), or sits within
two points (Yellow). That needs a number that has earned the right to
disagree with a price. On the site's public receipts it has not, in football:

| Picks shown above their price | Picks | We said | Hit |
|---|---|---|---|
| NFL board picks | 677 | 68.5% | 56.1% |
| College football board props | 617 | 66.9% | 55.1% |

The picks at or under their price hit what we said (NFL 56.6% of 1,670,
college props 58.5% of 908). So where our number ran above the price, the
price was right, and a "Green" label would have marked the picks that missed
by the most. The site's answer is the stricter haircut in §2: show the
price's number, post the take-at price, and let the Edge board carry the
bets that claim a price is wrong.

The NBA's and the NHL's numbers have held up against their prices, and since
step AAB (20 November; they said yes) each of those leagues' player picks
shows its grade (`engine/pricegrade`): on the report's pick card, Report
Picks and the Most Likely card. Public receipts to 20 November, props at −250
or better, each pick once, a chance of 60% or better:

| | Green | Yellow | Red |
|---|---|---|---|
| NBA | 673 hit 62.6%, +2.6% a bet | 399 hit 66.9%, +0.3% | 804 hit 67.5%, −1.6% |
| NHL | 1,010 hit 66.5%, +1.9% | 542 hit 68.8%, +1.9% | 744 hit 66.9%, −2.6% |

A Red-priced pick hit as often as a Green one. What the grade sorted was the
money, and only at 60% or better: under 60% every grade made money (the NBA's
Red-priced picks at 50-60% hit 66.9% where we said 57.3%, 614 of them: our
number ran low there). So v3.1's "Red: never posted, however likely" is not adopted: every
pick stays, the grade is a label about its price, and each card says how
picks at that chance and grade have done on our own record, once 20 have
settled. `QB_PRICE_GRADE=off` turns it off.

### Decisions v3.1 leaves with them

1. **Two legs by default.** Answered yes, 20 November ("we want 3 two-leg
   parlays for each game report as well"): every league's game report posts
   three two-leg prop tickets beside its three three-leg ones, and football
   and hockey keep their scorer pairs (step AAA, `gameparlays.TWO_SPORTS`).
   Started sets when they asked: NBA two-leg 12 of 16, three-leg 6 of 27;
   NHL two-leg 14 of 20, three-leg 22 of 43; NFL three-leg 0 of 3.
2. **SAFE / BALANCED / POP on each ticket**, and one book that prices every
   leg. Answered yes, 20 November; done in step AAB
   (`gameparlays.ticket_class`, `one_book`). Every two-leg and three-leg
   ticket says its class by v3.1's own bars, whatever its size: Safe (every
   leg 64%+, 40%+ together), Balanced (every leg 60%+, 36%+ together), Pop
   (25%+ together), and under that a long shot. Each says why it is not the
   class above. In hockey Safe also needs every leg at a Green price and
   Balanced one, as section 10 says; football's numbers are tied to their
   prices, so its classes stand on the chances alone, and since step AAR (21
   November) so do the NBA's: step AAM put an NBA leg at no more than the
   book's own chance, which almost never clears its price, and the NBA's
   two-leg Safe tickets, every leg Green on our own number, had gone 3 of 18. A three-leg ticket
   is nearly always a Pop, which is what three legs are by v3.1's own targets
   (25-30%). A touchdown pair is not classed. Each ticket names the one book
   that has every leg at its number, or says none in our pull does; it is not
   yet a rule that one must (the heartbeat's `one_book` counts how often one
   does, to decide on). Since step AAE (21 November) the line reads only
   today's quotes, never a sharp book's, and a ticket with a leg whose number
   no book lists any more says it cannot be placed as written, which leg, and
   the nearest number a book has; a ticket not posted before takes no such
   leg. The first NFL board to count them had none. Step AAF fixed one thing
   that kept the line quiet on football: an under's price was lost wherever
   its book also listed that number on its ladder.
3. **The price grade on the NBA and NHL cards.** Answered yes, 20 November;
   done in step AAB (above).
4. **Rungs well under the average.** Their Tier 1 is completions, attempts
   and carries at 0.80x to 0.85x of the average. Ours lose at the lines we
   took. A box run can say how our picks did by rung-to-average, which would
   settle whether completions come off the bench at low rungs.
5. **A cornerback matchup adds nothing.** Answered yes, 21 November ("Yes only
   shit that actually hold"); done in step AAJ. In the NFL and college a pass
   catcher's coverage read no longer backs his catches or receiving yards toward
   Top or ranks him; the projection's measured matchup step decides there, and
   the card says the read explains the pick.
6. **A posted pick whose number the books have left.** Withdrawn the day it
   was written (21 November). I asked whether a parlay leg should follow the
   books to today's number when they leave the number its pick was posted at.
   The count step AAE added read 0 such legs on the NFL's Friday board, two
   days after Sunday's picks went up, so there is nothing to decide now. The
   count stays on the heartbeat (`one_book_legs` `unlisted`), and a ticket
   with such a leg says so.

7. **Hockey's goal scorers on its stat parlays** (new, 21 November). Football's
   touchdown scorers came off the three-leg and two-leg stat tickets, as v3.1
   says. Hockey's goal scorers can still ride its stat tickets beside its
   goal-scorer pairs. v3.1 is football's and hockey's tickets are winning
   (two-leg 14 of 20, three-leg 22 of 43), so I left them; the heartbeat counts
   how many such legs there are (`scorer_legs_on_props`). Answered no, 21
   November: they stay.

Also answered 21 November (step AAJ): a game short of three three-leg tickets
posts fewer rather than take a touchdown leg back ("Fewer so we don't force
anything"); a parlay one book prices whole is chosen first
(`gameparlays.book_ranker`); no college basketball prop is priced off a ladder
alone until they say so; v3.1's parlay rules reach college football in full;
college picks ask 60% (`likely.LANE_MIN_PROB`); the record may raise an NBA or
NHL chance toward its price (`likelycal.RAISE_SPORTS`); and Saturday's college
slate is bought from Friday (`oddsbudget.DAY_BEFORE_ON_TOP`).

## What their own messages add to the instructions

Read across all 213 of their messages in the chats:

- **Hitting matters more than edge.** "I don't care about edge I care about
  what's actually going to happen" (Oct 1). "I care more about what
  genuinely will hit not my rules" (Oct 22). So a rule the graded record
  shows costs hits comes off the board.
- **−250 at the heaviest.** "We want to keep it to like minus 250 and up"
  (Oct 29, Nov 1, Nov 12).
- **Tickets that win together.** "I don't want to run it to where one ticket
  loses and one ticket wins" (Oct 25, Nov 8).
- **Red-zone usage beside each defense's weak spot.** "I want to know that
  next to the Dolphins tight end on the chart" (Nov 8); "line up in order who
  has the best touchdown chances on each team" (Oct 25).
- **Different scorers across touchdown tickets.** "I don't like how you have
  Gordon in almost every single one of them" (Nov 8).
- **The record's best markets.** "look at the NFL record page and seeing
  exactly what categories the most likely bets hit the best in" (Oct 11).
- **Who to look at, and who to avoid, and why** (Nov 1).

## The method, rule by rule

| Rule | What the site does | Where |
|---|---|---|
| 0. Price gate: never a leg worse than −250 | Every Most Likely row, matchup pick and parlay leg is capped at −250. Every pick line now says the price it's worth: "take it at −163 or better", never past −250 | `likely.HEAVIEST_PRICE`, `gamereport.take_at` |
| 0. Script discipline: no RB rushing over on a team likely to trail; no WR volume over when a blowout could take the fourth quarter; no passing over the weather or script works against | The scout flags each one (`dog_run_over`, `blowout_over`, `wind_pass_over`, `fav_pass_over`). A pick carrying one tops out at Worth a look and says which rule | `scout.FLAGS`, `likelyboard.METHOD_AVOID` |
| 1–2. Deep matchup scan; who's guarding whom | Unit ranks, corners with the passer rating they allow, coverage shells, funnels | the report's rankings, "Who's guarding who" |
| 3. Breakout matchups | The matchup reads: breakout, good, tough, avoid | `gamescan` reads, "Players to watch" |
| 4. Injuries, inactives, who replaces whom | The injury list and what each absence opens ("If that player sits, the 19% of DET's targets that player gets go to others") | the report's injuries, "Before kickoff" |
| 5. Usage and role | Target share, targets and carries a game, red-zone work | "How each team plays", the reads |
| 6. Game scripts A–D; prefer props that hold in several | Script A (the favorite controls it), B (the underdog leads), C (a close game) and D (a blowout), each with its share of the simulator's games and who it helps. Then the game's picks ranked by how many scripts they hold in | `gamereport.script_blocks` |
| 7. Weather: 12+ mph caution, 15+ mph a major downgrade | 15+ mph raises `wind_pass_over` on passing and receiving overs, which caps the pick | `scout.WIND` |
| 8. Trenches | Pass protection against the pass rush; the run game against the run defense | "In the trenches" |
| 9. Scheme and funnels | Man/zone, shells, blitz, and where each defense is weakest and strongest by position | the report's identity and coverage lines |
| 10. Red zone; TD props need real scoring opportunity | Red-zone rates and plays, who gets the chances, and each team's touchdown chances ranked beside what the defense allows that position | `gamereport.td_chance_lines` |
| 11. Recent form: last 2 > last 4 > season | The models' own recency weights, measured on our seasons | the projections |
| 12–13. Coaching; past matchups | Coaching tendencies; the last meetings with their lines | the report |
| 14. PES output: hit rate, fair price, EV, volatility, role certainty | Our chance, the fair price and the price to take on every Most Likely row and pick line; boom-or-bust players are flagged | the board's cards |
| 15. Prop priority: volume floors first | Not adopted as a ranking. Our graded NFL Most Likely record has completions, attempts and carries as its weakest markets (52.5%, 49.5% and 51.2% hit) and passing yards as its best (67.7%), so the record's own market check decides | `likelyboard.record_check` |
| 16. Hard filters: no RB receiving over without a route role; no needs-a-bomb yardage over; no unstable role | Flags `rb_route_over`, `boom_bust` (yardage overs), `role_down_over` and `role_up_under` cap a pick at Worth a look | `likelyboard.METHOD_AVOID` |
| 16. Their guardrails (no Lions unders; avoid Jets and Justin Fields; no CeeDee Lamb unless asked) | Kept for their own bets; the boards serve every member and don't follow them | — |
| 17. Two-leg parlay builder (SAFE/BALANCED/POP) | Four three-leg parlays and three touchdown pairs a game, each with its joint chance, fair price, take-it-at price and backups. Built to win together, as their chats ask: no ticket needs the game to go the other way from another. A game that can't fill its tickets that way says which ticket wins in a different game | `engine/gameparlays.choose` |
| 18. TD module: 45%, or 40% with undeniable usage | Every touchdown pick on the board is checked: 45%, or 40% with 30% of the team's red-zone chances. One that falls short tops out at Worth a look. Each touchdown pair says whether both scorers are 40% or better (decision 1 under RUN_NEXT 00f) | `likelyboard.td_rule`, `gameparlays.card` |
| 19–20. Live market; the "I checked" list | Line moves, the opener, prediction-market money, a total moving against the money | "The market" |
| 21. Picks output: ranked, with the maximum playable price | The board ranks by tier, then how hard the matchup backs a pick, then our chance. Every pick line says the price to take it at | the board, `read_pick` |
| 22. Sides and totals need stricter edges | The game-bet lanes keep their own bars | `likely` game lanes |
| 25. Post-mortem: log every leg, update one rule | Every pick is journaled and graded. The record measures each flag and moves a chance only once a flag is proven (`likelyctx`); the held book tracks what holding was worth | the Record page |
| 26. Never force a bet; "No qualifying plays at current lines" with the closest candidates | A read gets a pick only where our number backs it; otherwise the card says why there's no pick. A game with no pick says "No qualifying plays at current lines" and names the closest three with the price each would need | `matchpicks.not_backed`, `gamereport.no_play_blocks` |

## His slate log's rules from losses

| Rule (date) | On the site |
|---|---|
| Model receptions from the 3-game target average, never a 1–2 game trend (Oct 1) | The projections use measured recency weights; `role_down_over` and `role_up_under` flag a role that is moving |
| A reception over outside the top two needs ≥15% target share or ≥5 targets a game (Oct 8) | `thin_target_over`, with the 5-a-game alternative since 2026-11-15; caps the pick |
| QB rush-attempt unders stay off the main card (Oct 8) | `qb_rush_under` since 2026-11-15; caps the pick |
| Shrink our Strong numbers toward the market (Oct 11, after 483-343) | The record's correction (`likelycal`) and the price's correction (`trust_price`) |
| Use the record's best markets (Nov 8) | `record_check`, per market, side and band |

## Why a rule caps a pick instead of removing it

Their own words put hitting ahead of their rules. The scout's flags were written
before anything was measured. The five-season replay proved only two of
them (a player's first game back; pass-attempt unders in projected
shootouts). The board's graded record proved five kinds of unders, and
those are held. A pick that breaks one of their rules therefore stays on the
board, tracked like every pick, but can't be Top or Strong, and its card
says which rule. If the record shows picks breaking a rule hit at their
claim, the rule comes off. If it shows they over-claim, `likelyctx` lowers
their number on its own.
