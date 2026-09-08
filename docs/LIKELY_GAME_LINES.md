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
| NFL | **0.677** (1,356 games) | 0.504 | 0.496 | 0.500 |
| CFB | **0.752** (2,729 games) | 0.496 | 0.503 | 0.492 |
| NFL, the market's own de-vigged moneyline | **0.722** (1,420 games) | — | — | — |
| CFB, the market's own de-vigged moneyline | **0.791** (3,011 games) | — | — | — |

**The moneyline rows rank on the market's number (2026-09-07).** The
last two rows were measured the same day on this box's stored closes:
the book's de-vigged moneyline against the result, every scored game
with a price, ties out. The market ranks winners better than the model
in both leagues, so `likely.from_game_bet` orders a moneyline row on
the book's de-vigged number for its side (`prob_source: "market"`),
keeps the model's number on the card, and says so on the row. A
sharp-anchored card ranks on its own probability, which is the sharp
book's fair. Spreads, totals and team totals have no market figure and
are what they were. The model's credibility bar still refuses a row
whose model disagrees with the book by more than we credit, because
the card prints that number. `likely.GAME_RANK_MARKET` holds the
figures and `tests/test_likely_ranks_on_market.py` re-measures them.

The floor is `likely.MIN_RANK_AUC` (0.60). The model can say who wins
and cannot say who covers: spreads, totals and team totals test as a
coin flip against the close on both leagues. That is not a surprise (the
close already contains the ratings, and the market's own de-vigged
moneyline ranks NFL winners at 0.718 on the same 1,181 games), and it
decides the board.

The NFL row was re-measured on 2026-09-07. Its first figures came off a
walk that was not one: an NFL `period` is a week number that repeats
every season, and two readers assumed it was unique. The walk sorted on
it alone, so it priced each season's second week having already seen
every later season's first; and the schedule closes were keyed by it
alone, so a same-week rematch a season apart shared a key and 65 games
were graded against another year's line. Ordered by season and then
week, and joined by season, the same games gave 0.633 / 0.481 / 0.471 /
0.482 — lower on every market, and no market on a different side of
the floor.

The row above is one step further: the NFL measured on the ratings the
build actually ships (`gamerank.measure_nfl`, the college precedent),
not on the plain cumulative walk, which rates a 2025 team on its
2021-25 average. The shipped rating ranks winners better than the
stale one — and its disagreement with the close is still worth nothing
(docs/NFL_MONEYLINE_ARITHMETIC.md).

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

The college walk (`gamerank.measure_cfb`) rebuilds the production
opponent-adjusted ratings before every date from an in-memory table
that holds only the past, so its figure is the build's own model; the
plain-ratings walk had put the moneyline at 0.708. Not replayed: the
recruiting prior blended in before week four and the FCS exclusion that
needs the live team map, so it is still a floor, a higher one.

## The raw claim on a market-ranked row (2026-09-08)

Ethan, 2026-09-08: "we have player props just barley any money money
lines are touchdown crap." The moneyline half of that was this bar.

`likely.engine_credible` refuses a row whose raw model claim sits more
than `MAX_CREDIBLE_EDGE` (ten points) from the book's de-vigged number —
the Gelof guard, written for a prop whose 96% raw claim had been shrunk
to 73% against a price that could not be real. A football moneyline row
ranks on the market's number (above), so its claim IS the market's; the
bar was still asked of the model's own rating, and refused the row
whenever that rating sat more than ten points from the book.

Measured 2026-09-08 on this box's NFL closes, on the ratings the build
ships (`python3 -m engine.gamerank --sport nfl --raw-bar`):

    quoted, scored, non-tie games with a four-game rating         1,356
    favourites the board could carry (fair >= 55%, price >= -250)   681
    …the raw bar would refuse                                        207   30%
    the market's number on the rows kept:     claimed 61.4%  landed 64.3%
    the market's number on the rows refused:  claimed 61.4%  landed 62.3%
    refused minus kept, landed-vs-claimed, 95% by game     [-9.8%, +5.7%]
    refused rows by size of disagreement:
        10-15 pts  n=120  claimed 61.1%  landed 63.3%
        15-20 pts  n= 54  claimed 61.7%  landed 61.1%
        20-30 pts  n= 30  claimed 61.9%  landed 60.0%
        30+ pts    n=  3  claimed 63.7%  landed 66.7%

And college, the same day, on the production opponent-adjusted walk
(`--sport cfb --raw-bar`, 2,729 quoted games):

    favourites the board could carry                              1,066
    …the raw bar would refuse                                        401   38%
    the market's number on the rows kept:     claimed 62.2%  landed 60.2%
    the market's number on the rows refused:  claimed 64.0%  landed 63.8%
    refused minus kept, 95% by game                        [-4.3%, +7.8%]
    by size of the disagreement: 10-15 pts +0.4 · 15-20 -4.8 · 20-30 +8.3 · 30+ -9.2 (n=14)

The market lands where it claims on the games the model disputes, at
every size of dispute, in both leagues. `engine.gamecal` had said the same of this model
from the other side: the slope of its disagreement against the close is
−0.057 ± 0.135, nothing, and the moneyline haircut it measures prices
the card at the market. A bar that removed three eligible favourites in
ten and changed nothing measurable was a shelf a third empty.

So `engine_credible` answers True for a row whose `prob_source` is
"market". The model's own rating stays on the row (`engine_raw_prob`);
the row's note prints it as the model's and says why it does not bar;
the card's hero tile is labelled "Market" with a "Model" tile beside it
(`likelyOwnReadTile`); `showableLikelyRow` no longer hides the row; and
the board lint prints the disagreement as OWN READ rather than RAW GAP.
A row that ranks on the model's number (a sport with no market figure)
is held to the bar exactly as before, and so is every prop row.

Re-measure on the droplet, whose harvest joins more closes than the
schedule alone:

```
cd /srv/qellys && python3 -m engine.gamerank --sport nfl --raw-bar
cd /srv/qellys && python3 -m engine.gamerank --sport cfb --raw-bar
```

## The number the board ranks on is a real book's (2026-09-08)

The board ranks football moneylines on the market's de-vigged number
(`GAME_RANK_MARKET`, above). That number was being computed from the
SHOPPED pair — the best price per side across every book we request —
which is the right number to bet and the wrong one to de-vig, because
the two halves come from different books and the hold between them is
nobody's hold.

Measured on this box's college line history, 11,366 games with two or
more books quoting both sides (median eleven books a game):

| | |
|---|---|
| hold on one book's own pair | 3.64% |
| hold on the shopped pair | 0.67% |
| the shopped pair is an outright **arbitrage** | 24.4% of games |
| de-vigged P differs from a real book's by >1 point | 28.4% |
| …by >2 points | 7.9% |

A quarter of the time the "market implied" figure was de-vigged from a
pair that sums to less than one. And the 0.722 the board ranks against
was measured on the SCHEDULE's single consensus pair (this box's
`odds_history` is empty, so `close_for` fell through to it) — so
production was ranking on a different quantity than the one measured.

`oddsapi.consensus_h2h_fair` de-vigs each book's own two-sided pair and
takes the median, renormalised; the shopped best stays the price, named
by its book (`best_h2h_books`). The sharp book is left out because it
has its own path — `price_moneyline_sharp` prices a soft number AGAINST
it, and folding it into the consensus would make the anchor and the
anchored share a number.

**The trade, stated.** The median is not steadier than what it replaces:
on two books it is their mean and on three it snaps to the middle one,
so an added book can move it several points against a tenth of one for
the shopped number. The case is bias, not variance — every book added
can only thin the shopped pair, so that error grows with the size of the
payload rather than describing the game, while this one is sampling
noise on real quotes. A ranked number survives noise; it does not
survive a bias that moves with how many books a pull returned.

## Every game price says which book is posting it, per side (2026-09-08)

Ethan, twice in one day: "I don't want you too stop working until we
display the right lines and prices the books show." The moneyline was
named first because it was what he screenshotted and what the board ranks
on. The spread and the total were still publishing a shopped price under
no name, and the college board was doing something worse than that.

**Why the side matters.** The best price on the Over and the best on the
Under sit at different books far more often than they sit at one, and so
do the two sides of a spread — that is the same fact that made the
shopped de-vig wrong. So the resolvers are keyed by side:

| market | resolver | keyed by |
| --- | --- | --- |
| moneyline | `oddsapi.best_h2h_books` | team abbreviation |
| spread | `oddsapi.best_spread_books` | team abbreviation |
| total | `oddsapi.best_total_books` | `over` / `under` |
| team total | — | nothing quotes it |

A team total is derived from the game total and the spread rather than
read off a menu, so no book posts it and none is named. Naming one would
put a real book against a number it never offered.

**Two rules each resolver inherits from the price it names**, because a
name that follows different rules than the number is a lie about the
number:

* the same book filter — the sharp reference is skipped, since nobody
  here can bet it, so it is never the answer to "where do I get this";
* the same published line. A book off the consensus number quotes
  neither side of it and names neither side, and where no book is at the
  line the parsers publish -110 — a price nobody is offering, which gets
  no book's name at all.

**One walk per market.** `_total_quotes` and `_spread_quotes` return
`(point, price, book title)`, and both the parser and the resolver read
them. Two separate walks over one payload can pick two different books
for one price, and a card showing the right price under the wrong book is
the failure this whole line of work has been chasing.

**The college defect this closed.** `cfb_build._books_for` looked each
market up on ONE fixed side — the home spread, the Over, the home
moneyline — and handed that name to every card in the market. Its own
docstring had the reason that was wrong: "naming the wrong book is worse
than naming none — it sends you to a window that isn't quoting that
price." An Under card printed the Over's book; an away spread printed the
home side's. It is retired, replaced by `_book_for_side`, which asks the
shared resolvers for the side the card actually took. One rule now names
both leagues.

## The moneyline and the spread, read together (2026-09-08)

Ethan, with two screenshots side by side — his sportsbook and our page:

    his book   DAL -3   ·  DAL -162 / NYG +136
    our board  NYG ML -218, 66% likely, "the likely side"

"Also the money lines we are showing on the most likley page is
completely wrong."

That card is wrong on its own terms. The spread on the game makes
Dallas the favourite; the moneyline on the same card makes the Giants a
66% favourite. Two numbers, one card, opposite conclusions — and until
now nothing read them together, because a moneyline card carried the
h2h pair and nothing else. The two feeds that fill them are different
(the schedule's spread, the odds pull's h2h), so they can and do drift
apart.

This is the third report of this class. 2026-09-03: "The lines on the
most likely best bet page ... are completely wrong so we are giving bad
bets", and "A lot of the money lines and shit are wrong." Both were
answered with freshness stamps (`priced_at`, `lines_priced_at`), which
say a price is OLD and cannot say a price is WRONG.

**Measured before it was barred.** On this box's 1,424 stored NFL closes
carrying both a closing moneyline and a spread, the book's de-vigged
P(home) against its own spread through the sport's win curve
(`gamebets.spread_win_prob`):

| | |
|---|---|
| median disagreement | 0.036 |
| 99th percentile | 0.102 |
| 99.9th percentile | 0.113 |
| largest in five seasons | 0.118 |
| games where the two named a different favourite | 0 of 1,424 |

A book prices both markets off one opinion, so they never cross over and
sit within about a tenth of each other. `likely.SPREAD_COHERENCE` is
0.15 — above every disagreement five seasons of closes contain — and a
moneyline further than that from its own game's spread is refused with
its own census line. Both builds now stamp the game's spread onto every
card they price (`pipeline._finish_bet`, `cfb_build.to_game_bet`), an
unposted line staying None rather than becoming a zero, and the board
lint flags the same pair on an older board file.

**What it does not catch, stated plainly.** The other screenshot had MIN
-1.5 with our board showing MIN ML -220 against the book's -125. Those
two numbers of ours agree with each other — 0.083 apart, ordinary — so
this bar passes it. That card is a price that is merely OLD, and age is
a different question with a different answer (§8f of the droplet
checks). The guard is not advertised as covering it, and
tests/test_spread_ml_coherence.py pins that it does not.

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

* The `likely` book now carries game rows. `ledger.likely_report`
  already cuts the book per market (`by_market`), and the weekly
  maintenance log prints the game markets' lines beside each sport's, so
  whether moneylines, spreads or totals drag or lift the calibration is
  read off the record rather than guessed.
* MLB: run the droplet command above and read the printed line before
  expecting a baseball moneyline on the board.

## The alternate ladder (2026-09-07)

Ethan, with the census in hand — 303 NFL prop rows, 215 under the
floor, 49 with no real price, none shown: "i prefer to do whatever
gives us props and picks every single day ... we need to be showing
most likley props period."

A main line is hung where the book thinks the coin is fair, so the
calibrated number at it sits near 50% — the fitted mixture puts a
62-yard projection at 40% over 62.5 — and a board that asks for 55% at
a price no heavier than −250 could show nothing at main lines however
good the model. The same books hang the same stat at other numbers,
and that is where a 60–70% event is for sale.

* The NFL and college event pulls buy the four `_alternate` markets
  (`oddsapi.ALT_ODDS_TO_MARKET`). They are parsed with their own map
  onto `Prop.alt_lines` and never into `Prop.lines`, because line
  shopping takes the lowest line on the board and a ladder in the
  shopped field would hand every card its cheapest rung as "the line".
  The sharp book's rungs ride as `Prop.alt_sharp_lines`. An NFL event
  call is twelve markets now (`oddsbudget.credits_per_event`), a
  college one nine.
* `likely._best_rung` holds every rung to the bars the main line is
  held to, AT THE RUNG'S OWN NUMBERS: the mixture's probability at
  that line (or the sharp book's de-vigged fair there when the market
  has no fit, and nothing when it has neither), the 55% floor, the
  −250 cap, a price a book could post, and the credibility bar against
  the rung's own de-vigged price. Best price per (line, side) across
  the bettable books; sharp-book rungs price and are never shown.
  Highest probability wins, the main line wins when it is the likelier
  number, and a rung stands in when the main line fails its own bars.
* The row's `line` / `side` / `odds` / `model_prob` are the rung's, so
  the journal grades the rung itself. `rung` says "alt" or "main";
  `main_line` / `main_odds` / `main_book` ride beside an alt row and
  the card says which book number it stands next to. `implied_prob`
  is the rung's fair; `fair_prob` and `engine_raw_prob` stay the main
  line's, so the engine's pre-shrink claim is judged where it was
  made. No EV on a rung.

Nothing about the floor, the cap or the credibility bar moved.
