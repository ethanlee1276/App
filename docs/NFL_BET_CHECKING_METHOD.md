# Ethan's NFL Bet checking method, and where it lives on the site

Ethan's Claude project "NFL Bet checking" (exported 2026-11-14) holds the
master instructions ("NFL Prop Bot — Full Master Instructions", 27 rules),
the slate log (the cards and post-mortems from 1 October to 12 November) and
55 game chats from 9 September to 12 November. On 2026-11-15 he asked for
the project's reports and how they work to be built into the game reports,
the website and how the Most Likely bets are selected. This page maps each
part of the method to where the site does it. It also says what the site
does differently, and why.

## What his own messages add to the instructions

Read across all 213 of his messages in the chats:

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
| 4. Injuries, inactives, who replaces whom | The injury list and what each absence opens ("If he sits, his 19% of DET's targets go to other players") | the report's injuries, "Before kickoff" |
| 5. Usage and role | Target share, targets and carries a game, red-zone work | "How each team plays", the reads |
| 6. Game scripts A–D; prefer props that hold in several | Script A (the favorite controls it), B (the underdog leads), C (a close game) and D (a blowout), each with its share of the simulator's games and who it helps. Then the game's picks ranked by how many scripts they hold in | `gamereport.script_blocks` |
| 7. Weather: 12+ mph caution, 15+ mph a major downgrade | 15+ mph raises `wind_pass_over` on passing and receiving overs, which caps the pick | `scout.WIND` |
| 8. Trenches | Pass protection against the pass rush; the run game against the run defense | "In the trenches" |
| 9. Scheme and funnels | Man/zone, shells, blitz, and where each defense is weakest and strongest by position | the report's identity and coverage lines |
| 10. Red zone; TD props need real scoring opportunity | Red-zone rates and plays, who gets the chances, and each team's touchdown chances ranked beside what the defense allows his position | `gamereport.td_chance_lines` |
| 11. Recent form: last 2 > last 4 > season | The models' own recency weights, measured on our seasons | the projections |
| 12–13. Coaching; past matchups | Coaching tendencies; the last meetings with their lines | the report |
| 14. PES output: hit rate, fair price, EV, volatility, role certainty | Our chance, the fair price and the price to take on every Most Likely row and pick line; boom-or-bust players are flagged | the board's cards |
| 15. Prop priority: volume floors first | Not adopted as a ranking. Our graded NFL Most Likely record has completions, attempts and carries as its weakest markets (52.5%, 49.5% and 51.2% hit) and passing yards as its best (67.7%), so the record's own market check decides | `likelyboard.record_check` |
| 16. Hard filters: no RB receiving over without a route role; no needs-a-bomb yardage over; no unstable role | Flags `rb_route_over`, `boom_bust` (yardage overs), `role_down_over` and `role_up_under` cap a pick at Worth a look | `likelyboard.METHOD_AVOID` |
| 16. His guardrails (no Lions unders; avoid Jets and Justin Fields; no CeeDee Lamb unless asked) | Kept for his own bets; the boards serve every member and don't follow them | — |
| 17. Two-leg parlay builder (SAFE/BALANCED/POP) | Four three-leg parlays and three touchdown pairs a game, each with its joint chance, fair price, take-it-at price and backups | `engine/gameparlays` |
| 18. TD module: 45%, or 40% with undeniable usage | Every touchdown pick on the board is checked: 45%, or 40% with 30% of his team's red-zone chances. One that falls short tops out at Worth a look. Each touchdown pair says whether both scorers are 40% or better (decision 1 under RUN_NEXT 00f) | `likelyboard.td_rule`, `gameparlays.card` |
| 19–20. Live market; the "I checked" list | Line moves, the opener, prediction-market money, a total moving against the money | "The market" |
| 21. Picks output: ranked, with the maximum playable price | The board ranks by tier, then how hard the matchup backs a pick, then our chance. Every pick line says the price to take it at | the board, `read_pick` |
| 22. Sides and totals need stricter edges | The game-bet lanes keep their own bars | `likely` game lanes |
| 25. Post-mortem: log every leg, update one rule | Every pick is journaled and graded. The record measures each flag and moves a chance only once a flag is proven (`likelyctx`); the held book tracks what holding was worth | the Record page |
| 26. Never force a bet | A read gets a pick only where our number backs it; otherwise the card says why there's no pick | `matchpicks.not_backed` |

## His slate log's rules from losses

| Rule (date) | On the site |
|---|---|
| Model receptions from the 3-game target average, never a 1–2 game trend (Oct 1) | The projections use measured recency weights; `role_down_over` and `role_up_under` flag a role that is moving |
| A reception over outside the top two needs ≥15% target share or ≥5 targets a game (Oct 8) | `thin_target_over`, with the 5-a-game alternative since 2026-11-15; caps the pick |
| QB rush-attempt unders stay off the main card (Oct 8) | `qb_rush_under` since 2026-11-15; caps the pick |
| Shrink our Strong numbers toward the market (Oct 11, after 483-343) | The record's correction (`likelycal`) and the price's correction (`trust_price`) |
| Use the record's best markets (Nov 8) | `record_check`, per market, side and band |

## Why a rule caps a pick instead of removing it

His own words put hitting ahead of his rules. The scout's flags were written
before anything was measured. The five-season replay proved only two of
them (a player's first game back; pass-attempt unders in projected
shootouts). The board's graded record proved five kinds of unders, and
those are held. A pick that breaks one of his rules therefore stays on the
board, tracked like every pick, but can't be Top or Strong, and its card
says which rule. If the record shows picks breaking a rule hit at their
claim, the rule comes off. If it shows they over-claim, `likelyctx` lowers
their number on its own.
