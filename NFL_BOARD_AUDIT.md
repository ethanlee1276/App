# NFL board audit — edge bets and Most Likely (2026-09-02)

Ethan: "dive deep into making sure the nfl bets for edge bets and most
likely bets are perfect and following everything we have and make sense
... Some of them seem weird so I wanna make sure. Especially the most
likely bets."

The live boards are built on the droplet from feeds this sandbox cannot
reach (no Odds API key; ESPN, nflverse release assets and qellys.com are
blocked), and the local copy of `web/data/recommendations.json` is the
locked preseason shell with zero rows. So this audit has two halves: what
the code says every row must satisfy — read end to end and fixed where
it did not — and a tool that reads the rows the site is actually showing
and asks the same questions of each one, for Ethan to run on the droplet.

## What the Most Likely board is, in the code

`engine/likely.py build()` takes **every evaluated prop row** (recommended
or not) plus the touchdown value picks and the touchdown watch, keeps a
row only if its market has a measured ranking AUC ≥ 0.60 (anytime TD
0.721, receptions 0.770, rush yds 0.761, rec yds 0.733, pass yds 0.691),
shows the **mixture-calibrated** probability where a fit exists (else the
model's), and refuses a row that: has no probability; sits under 30%; is
priced by a proxy; carries a price no book could post; is heavier than
**−250**; or disagrees with the book's de-vigged number by more than 10
points. (Until 2026-09-02 it also refused every **under**; the cap was
what answered the −1200 rows that rule was aimed at, and unders are bets
again — see `docs/LIKELY_GAME_LINES.md`, which also covers the game
cards the board now ranks: moneylines, by measurement, and nothing
else.) It sorts by probability and nothing else, caps
at 40 rows, and the page shows three per shelf on the home page. The top
ten are journaled to the `likely` book at a flat 0.1u, zero dollars.

## Finding 1 (P1, fixed): the injury hold never reached this board or the touchdown watch

`rules.apply_rules` holds a Questionable / Doubtful / Out player — sets
`recommended=False` with "listed OUT — hold until inactives confirm
status". That took him off the **edge board only**. The Most Likely board
reads the same row, never looks at `recommended`, and the row carried no
field with the designation at all. The touchdown watch (`td_watchlist`)
was built straight from the prop menu with no injury read whatsoever.
So a back ruled out on Friday could sit at the top of "who is most
likely to hit" on Sunday with a live price beside him — while the
Recommended page, correctly, showed nothing on him. That is the exact
shape of "weird" Ethan is describing, and it is the one defect visible
from code alone.

Fixed on both paths:
- `pipeline._rec_to_dict` stamps `injury_status` on every prop row from
  the rules decision's own `health` check, so the two pages cannot
  disagree about the same player.
- `likely.admissible` refuses any row with a designation: "listed OUT —
  held until inactives confirm", counted in the board's census.
- `touchdowns.td_watchlist` reads `player_injury_status` for each
  candidate, carries it as `injury_status` with the hold sentence in its
  caveats, and the likelihood gate refuses it.
- Pinned: `tests/test_likely.py` (5 tests), `tests/test_td_board.py` (1).

## What the code says the other rows must satisfy (checked, no defect found)

- **Overs only, price cap −250, floor 30%, credibility ±10 pts** — one
  gate (`admissible`) on both makers, pinned already.
- **Probability shown vs raw** — the card says "Calibrated for this
  market's shape — the model's raw read was N%" whenever the mixture is
  used. The mixture needs ≥3 recent games and a fitted store; otherwise
  the raw number stands and says so.
- **Game script** — the same `game_script` object the prop card and the
  Fantasy page carry rides on every likely row since 2026-09-02.
- **Ranking only, never EV** — sort key is probability; EV is shown on a
  bettable row and hidden on a rank-only one.
- **Dedupe** — one row per (player, team, market). A player CAN appear
  on several shelves (receptions, rec yds, anytime TD). That is by
  design and it can read as repetition; the lint counts it.
- **Edge board gates** (`betting.evaluate_prop` → `rules.apply_rules`):
  real market price; credibility; calibration reliability; loss-pattern
  veto; tier edge bar (2.5% / 3.0% / 6.0%); max juice; injury hold; wind
  block on deep markets; grade floor 70 → B+; stake by the price ladder
  capped by grade (2u / 1u / 0.5u); exposure caps 5u a game, 15u a slate;
  Tier 3 TD picks only at outlier prices. Game bets: shared normal model,
  quality ceiling 75 (B+), `credible` False → Pass.

## The tool: `engine/boardlint.py`

Reads the published payload and the injuries page, prints every row on
the three boards with its numbers, and beside each the checks it fails.
Every flag is a question for a human, printed with enough of the row to
answer it. Most Likely: HELD, CHALK, UNDER-FLOOR, GAP, PROJ<LINE (and
PROJ>LINE on an under),
HISTORY (a 60%+ row whose recent games cleared the line less than a
third of the time), SCRIPT against the side, ROLE misfit (a QB on a
receptions line), REPEAT, RANK-ONLY, STARTED. Recommended props: HELD,
WARNED, REFUSED, BAR, GRADE, CAP, EV, PROXY, GAP, PROJ vs SIDE, SCRIPT,
BOTH SIDES, STARTED. Game bets: CREDIBLE, QUALITY above 75, GRADE, CAP,
EV, PROXY, WARNED, STARTED. Read-only; 15 pins in
`tests/test_boardlint.py`.

### Run on the droplet (after the pull lands)

```
cd /srv/qellys
python3 -m engine.boardlint                 # flagged rows only
python3 -m engine.boardlint --all           # every row with its numbers
python3 -m engine.boardlint --sport cfb
```

Paste the output back. The rows with flags are the "weird" ones with
the reason attached; the rows without flags but that still look wrong
are the next thing to read, and the `--all` print carries the numbers
to read them by.

## Still to check on the live rows (needs the paste)

- Whether the top of the Most Likely board is dominated by low-line
  receptions overs near the −250 cap (allowed by the rules; may read as
  chalk).
- Week 1 projections carried from 2025 logs for players who changed
  teams or roles — the reset rule truncates to post-change games where
  it can and reports "held" where the sample is too thin; the payload
  does not carry that flag per row, so the lint cannot see it.
- Whether the mixture is fitted on the droplet for all three yardage
  markets (`prob_source` on each row says which number is shown).
