# Most Likely: unders and game lines

Ethan, 2026-09-02: "One thing I wanna add with the most likely to hit
page is all I see us is doing overs, but we have no unders, and we also
have no money lines or spreads or totals or anything like that. So we
need to dive deeper because there is more bets that we can salvage and
look into and use data for."

Two faults, one rule. The likelihood board's founding rule is that a
market appears only once the model has been **measured** to rank it (an
AUC over ingested history, not an argument), and every row answers to
one bar, `likely.admissible`: a probability of at least 30%, a real
book price no heavier than −250, and a number within 10 points of the
book's own de-vigged figure.

## Unders

The board refused every under from 2026-09-01 to 2026-09-02. The ban went
in beside the −250 price cap, aimed at the first MLB night's rows
(unders at −300 to −1800). The cap is what actually answered that
complaint, since every one of those rows is heavier than −250; the under
rule swept the bettable unders out with them.

An under needs no second measurement. An AUC is symmetric under the
complement: flip every probability and every outcome and it is
unchanged, so a market whose over ranks at 0.77 ranks its under at 0.77.
Pinned in `tests/test_likely_gamelines.py`.

What changed:

* `likely.admissible` no longer refuses on side. Cap, floor, credibility
  and the injury hold apply to an under exactly as to an over.
* `likely.from_prop` shows the under's own probability. The mixture is
  P(over); an under row shows its complement, with the raw model number
  beside it as before.
* The page's render gate (`showableLikelyRow`) keeps the price cap and
  drops its under filter.
* `engine/boardlint.py` stops flagging UNDER and instead flags an under
  whose projection sits above its line (PROJ>LINE), the mirror of the
  over check.

## Game lines: measured first

`engine/gamerank.py` measures whether the model **ranks** game outcomes.
It replays the same walk `engine/gamebacktest.py` runs (ratings from
games strictly before each date, the production pricers, the stored
closes) and keeps, for every quoted game, the probability the pricer put
on its side and whether that side won. The AUC of those pairs is the
board's question: does a higher number mean a more likely winner?

Measured 2026-09-02 on this repo's history (NFL 2021–25, CFB 2022–25):

| sport | moneyline | spread | total | team total |
|---|---|---|---|---|
| NFL | **0.641** (1,181 games) | 0.491 | 0.497 | 0.513 |
| CFB | **0.708** (2,016 games) | 0.517 | 0.512 | 0.492 |

The floor is `likely.MIN_RANK_AUC` (0.60). The model can say who wins
and cannot say who covers: spreads, totals and team totals test as a
coin flip against the close on both leagues. That is not a surprise (the
close already contains the ratings, and the market's own de-vigged
moneyline ranks NFL winners at 0.714), and it decides the board.

The first cut shipped moneylines alone and kept the rest off. Ethan,
the same day: "I only see money lines in the best bets. I don't see team
totals over or unders, I don't see player unders, I don't see spread
bets, I don't see anything like that I just asked you to do." His call,
and the measurement's job became to be printed on each row rather than
to gate it.

So:

* **Ranked:** NFL and CFB moneylines, via `likely.GAME_RANK_AUC`. The
  shelf's "ranks at" figure is theirs.
* **Shown as leans:** spreads, totals and team totals, via
  `likely.GAME_RANK_MEASURED`. Each row carries `ranked` False, its own
  measured figure, and a `rank_note` the card prints: the model's lean
  at this number, sorting these across games measured at 0.49 against
  the close, a coin flip, so the percentage is a read on this game and
  not a ranking. The list shows "lean" beside the market and the shelf
  header counts them.
* **Capped apart:** player rows keep `likely.LIMIT` (40) and game rows
  get `likely.GAME_LIMIT` (20), then the survivors share one probability
  order. Five cards a game across a Sunday is eighty 50–60% leans, and
  a single cap would have pushed every player row off.
* **The likely side, on every market:** every two-way card now carries
  the other side's price (`other_odds` from `gamebets._game_bet`), so a
  card backed from the short end on price flips to the side the same
  numbers say lands more often: the other team and the mirrored number
  on a spread, the other side of a total or team total, the favourite
  on a moneyline.
* **Never measured stays off:** a market with no figure at all has
  nothing to say.
* **MLB:** nothing yet. The MLB game history lives only on the droplet,
  so the measurement runs there and writes into the rank store
  `likely.rank_auc` reads first (`rankfit.STORE`):

```
cd /srv/qellys && python3 -m engine.gamerank --sport mlb          # print
cd /srv/qellys && python3 -m engine.gamerank --sport mlb --save   # into the store
```

  The weekly maintenance pass runs `gamerank.measure_and_store` for
  MLB, NFL and CFB beside the prop rank fitter, so the shelf turns on
  by itself once the run-rating model's moneyline clears the floor. A
  sub-floor number is stored too (it is what stops a shelf being
  claimed by prose); a market the box can no longer support retires its
  own entry; a market that could not be measured at all leaves the
  store alone.

The college figure is a floor on the production model: the replay uses
the plain ratings, not the opponent-adjusted map the live CFB board
prices with.

## How a game card reaches the board

`likely.from_game_bet` takes the card the edge board already built
(`gamebets._game_bet`, `gamebets.moneyline_to_dict`, `to_game_bet` in
`cfb_build.py`): `win_prob` is the model's probability of the side taken,
`fair_prob` the book's de-vigged number for it. The row is marked
`kind: "game"`, carries the pick label as its `player` ("DET ML"), and
carries home, away, market, side and line verbatim so the page opens the
game-bet page by the same id the edge card uses (`gameBetId`).

**The likely side, not the priced side.** The edge card backs whichever
side has the edge, and on a moneyline that is the dog more often than
not: the first end-to-end run put "CHI ML +190, 37%" on a board called
Most Likely with the 63% favourite nowhere on it. A moneyline is
two-way with no push, so the other side is 1 minus the card's
probability at the other price, and both prices now travel on the card
(`MoneylineRec.home_odds`, `MoneylineRec.away_odds`, on the model path
and the sharp-anchored path). When the card's pick sits under 50% the
row is built for the favourite, marked `flipped`, with a first reason
saying which side the edge board backed and why this one is listed. A
dog card from a payload without the other price is refused rather than
shown as likely. The row carries the card shape (`win_prob`,
`fair_prob`, `edge`, `grade` "Likely", zero stake) so the game-bet page
can draw a flipped row the edge board never published; the page looks
it up in the likelihood list when it is not among the edge cards.

Refused before the bar: an in-play card (`live`), a college conditional
waiting on a starter (`conditional`), a card with no real market. A card
the edge board marked not credible arrives with a Pass grade and is
refused again on the numbers by `likely.admissible`.

All three builds hand their cards over: `pipeline._likely_board` for
the NFL, `cfb_build.py` and `mlb_build.py` at their likely-board call.
The rows share the one list and the one sort key (probability), and land
on a **Game lines** shelf at the end of the football and baseball shelf
specs in `engine/boards.py`. The shelf names all four game markets; only
moneylines ever reach it today. Its figure ignores a measured sub-floor
market (the droplet's store will hold the spread's 0.49 beside the
moneyline's 0.64, and a market that never puts a row on the shelf is
not the weakest row under its header).

## Journal

`ledger.log_most_likely` journals game rows to the `likely` book in the
exact shapes `ledger.log_recommendations` writes for the same markets,
so the existing settle path grades them with no new code: a moneyline is
the team at OVER 0.5, a total the matchup key at its line, a spread the
team at the negated number, a team total the team at its number. Flat
0.1u, zero dollars, top ten of the board, as before.

## What to watch

* The `likely` book now carries moneylines. `ledger.likely_report`
  reads them with everything else; a per-market cut of that book is the
  next thing to add if the moneyline rows drag or lift the calibration.
* MLB: run the droplet command above and read the printed line before
  expecting a baseball moneyline on the board.
