# The draft plan and the any-platform draft assistant

Ethan, 2026-09-02: "add like a list for best draft orders of players or
something so users can see who they should draft in what round and shit
like that. We need a tool to help users in their draft while they are
doing it. Make sure we use all our data available."

## What was already there

- **Draft kit** (`engine/fantasy_draft.py`): last season's volume run
  forward into expected points per game, valued over the best freely
  available player at the position (VORP), tiered at real cliffs,
  auction dollars beside it. Rookies and anyone who missed the year sit
  at the market's draft rank with the board's points at that rank and
  are marked as the market's number, not ours (`engine/draftmarket.py`).
- **Consensus ranks** (`engine/fantasy_ranks.py`): our board, Sleeper's
  own board, the room's actual picks, and anything the reader imports,
  folded into one order with the disagreements shown.
- **Live Sleeper draft** (`engine/fantasy_pick.py`, `/api/draftadvice`):
  paste a draft link; every pick crosses off; the advice says who will
  not survive to your next pick, measured from how far off consensus
  the room has actually been reaching.
- **Mock draft**, **auction values**, **lineup optimiser**, **trades**,
  **waivers and streamers**, the **player dossier**.

## What was missing, and what shipped

**A plan by round.** Nothing said, before the draft, "from seat 7 of 12:
this round a receiver, next round the last tier-two back, the tight end
in four, the quarterback in eight." `engine/draftplan.py` builds it from
the same three inputs the live advice reads: the kit's VORP, the
consensus draft order, and the seat's pick numbers. For each of your
picks it asks of every available player "how likely is he still to be
there" (`fantasy_pick.survival`, the room's measured reach when there
are picks to measure it from and the stated prior when there are not)
and takes the player with the best value-times-survival, filling
starting slots first (QB, RB, RB, WR, WR, TE, FLEX by default), never a
third quarterback or tight end. Each round carries the plan, the
stretch (the best toss-up if the room lets him fall), two fallbacks,
and the players worth more who will already be gone. The summary adds
up the planned starting lineup.

**A draft on any platform.** The Sleeper advice reads a pick feed; ESPN,
Yahoo and an in-person draft have none. The assistant card takes the
picks a person marks by hand — type a name, mark it Gone or Mine — and
`POST /api/draftplan` returns the advice for the pick on the clock
through the same `fantasy_pick.advice` the Sleeper room gets, plus the
plan for every pick after it. Marked picks live in the browser and
survive a phone going to sleep mid-draft. Nothing is stored server-side.

**Value and reach on the board.** `draftplan.annotate_rounds` stamps
every board row with the round our value would take him in and the
round the consensus does: a player the market takes a round or more
later than we would is a value; one it takes a round or more earlier
is a reach.

## The data it uses, and what it cannot see

Used: five seasons of ingested NFL game logs (targets, carries,
receptions, expected fantasy points from play-by-play, red-zone usage,
snap share), the 2026 schedule for byes, Sleeper's players feed for
current teams, rookies and the market's draft order, the injuries page
for tags on every name, and the consensus ranks.

Not used, and said so on every response: camp news, a Friday injury, a
coaching change's effect on a specific player (the offseason section
lists the changes; nothing re-projects on them), and the tendencies of
one seat in your room. The plan is greedy, one round at a time, and it
calls itself a plan rather than a promise.

## Running it

- The page: Fantasy → Around the league → Draft kit. The plan controls
  (league size, seat, rounds, snake or linear) sit above the board; the
  assistant card sits beside the Sleeper card.
- The endpoint: `POST /api/draftplan` with
  `{teams, slot, rounds, type, slots, order:[{player, mine}]}`;
  returns `{advice, plan, slots, board_rounds}`.
- Tests: `tests/test_draftplan.py`, `tests/test_draft_assistant.py`.
