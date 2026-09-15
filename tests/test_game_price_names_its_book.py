"""A game price the board cannot attribute to a book is not a price.

Ethan, 2026-09-09, with FanDuel and DraftKings open beside our board.
His books:

    GB  +105   /  MIN  -125        (MIN -1.5)
    DAL -162   /  NYG  +136        (DAL -3)

Our Most Likely board, same two games, same kickoffs:

    MIN ML -220        "Moneyline · best"
    NYG ML -218        "Moneyline · best"

"The moneylines are still the wrong book price. FanDuel and draft kings
show the lines in the screenshot yet we show a different line. That's
wrong and needs to be fixed now."

THE WORD "best" IS THE TELL, and it is a thing this code did on purpose:

    "book": row.get("book") or "best"

with a comment saying "a game card carries no book name on the NFL
path". That stopped being true when the moneyline, the spread and the
total each learned to name the book posting the side taken — but the
fallback outlived the comment, so a card that reached the board with no
book printed a book called "best" beside a real-looking price.

A made-up name is worse than no name. It tells a reader the number was
checked against a book, when in fact nothing checked it: the price and
its source parted company somewhere upstream, and -220 rode onto the
page against a market at -125 wearing an attribution nobody could
follow.

So the board stops inventing the name, and `admissible` refuses the row.
This is a TRUTH bar — the number is unverifiable, not merely
unattractive — so the reserve pass does not relax it. A shelf that
empties under it is a shelf reporting that the prices could not be
sourced, which is both honest and a diagnosis; the alternative is
publishing a moneyline that is wrong by ninety-five cents on the dollar.

TEAM TOTALS ARE EXEMPT and that is why the bar names its markets rather
than asking "is the book field empty". A team total is DERIVED from the
game total and the spread, so no book quotes it and none can be named —
`pipeline._finish_bet` says so in its own comment. Holding a derived
number to a bar about quoted ones would empty a shelf Ethan asked for
(2026-09-02) on a technicality.

Run directly: `python3 tests/test_game_price_names_its_book.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                                  # noqa: E402


def _card(**kw):
    """An NFL moneyline card as `pipeline._finish_bet` publishes one."""
    d = dict(bet_type="moneyline", market="moneyline", market_label="Moneyline",
             has_market=True, home="MIN", away="GB", team="MIN", pick="MIN",
             pick_is_home=True, pick_label="MIN ML", side="", line=0.0,
             matchup="GB @ MIN", win_prob=0.66, fair_prob=0.62, edge=0.04,
             odds=-165, home_odds=-165, away_odds=140, book="DraftKings",
             ev_per_unit=0.05, confidence=6.0, stake_units=0.5,
             grade="B", credible=True, headline="MIN ML", reasons=[],
             recommended=True, live=False, date="2026-09-13",
             kickoff="2026-09-13T20:25:00+00:00")
    d.update(kw)
    return d


# --- the fabricated name is gone -------------------------------------------
def test_the_board_no_longer_invents_a_book_called_best():
    row = K.from_game_bet(_card(book=""), "nfl")
    if row is not None:
        assert (row.get("book") or "") != "best", row.get("book")
        assert not (row.get("book") or "").strip(), row.get("book")


def test_the_word_best_is_not_written_anywhere_as_a_book_name():
    """Pinned on the source, because the fallback was three characters
    and reads as harmless every time someone's eye passes over it."""
    src = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()
    i = src.index("def from_game_bet(")
    body = src[i:src.index("\ndef ", i + 10)]
    # CODE ONLY. The comment above the line quotes the old expression to
    # explain what was removed and why, so a naive scan of the whole body
    # finds it in the very sentence saying it is gone.
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert 'or "best"' not in code, "the invented book name is back"


# --- the bar ----------------------------------------------------------------
def test_an_unattributed_moneyline_is_refused_with_the_true_reason():
    """THE CARD IN THE SCREENSHOT. A -220 nobody is posting does not go
    on the page just because the model has an opinion about it."""
    census = {}
    got = K.build([], game_bets=[_card(book="")], census=census)
    assert got == [], got
    assert census == {"no book is posting this price": 1}, census


def test_the_same_bar_covers_the_spread_and_the_total():
    for mkt, extra in (("spread", {"line": -1.5}),
                       ("total", {"side": "OVER", "line": 46.5, "team": ""})):
        census = {}
        card = _card(book="", market=mkt, bet_type=mkt,
                     market_label=mkt.title(), **extra)
        got = K.build([], game_bets=[card], census=census)
        assert got == [], (mkt, got)
        assert "no book is posting this price" in census, (mkt, census)


def test_a_named_book_still_ships_exactly_as_before():
    """The bar must bite on the missing name and nothing else."""
    got = K.build([], game_bets=[_card(book="FanDuel")])
    assert len(got) == 1, got
    assert got[0]["book"] == "FanDuel", got[0]["book"]


def test_a_team_total_is_exempt_because_no_book_quotes_one():
    """Derived from the game total and the spread. `_finish_bet`: "A TEAM
    TOTAL GETS NO BOOK, and that is the honest answer rather than a
    gap." Refusing it here would empty a shelf on a technicality."""
    card = _card(book="", market="team_total", bet_type="team_total",
                 market_label="Team total", side="OVER", line=24.5)
    census = {}
    got = K.build([], game_bets=[card], census=census)
    assert "no book is posting this price" not in census, census


def test_the_markets_the_bar_covers_are_the_ones_books_post():
    assert K.BOOK_POSTED_GAME_MARKETS == ("moneyline", "spread", "total")
    assert "team_total" not in K.BOOK_POSTED_GAME_MARKETS


# --- and the reserve cannot talk its way past it ----------------------------
def test_the_reserve_does_not_relax_it_even_with_the_page_empty():
    """"We need picks" is not a reason to publish a price no book is
    posting. The floor is the owner's to overrule; this is not."""
    census = {}
    got = K.from_game_bet(_card(book=""), "nfl", census=census,
                          floor=K.RESERVE_MIN_PROB)
    assert got is None, got
    assert census == {"no book is posting this price": 1}, census


def test_the_bar_is_scoped_to_the_sports_that_name_their_books():
    """MLB game cards have never carried a book name — `MLBGame` has no
    such field — so the bar would empty a shelf that is in season on the
    strength of a defect measured somewhere else. Same defect, same fix
    owed, but not discovered by Ethan on a live board tonight."""
    assert K.BOOK_NAMED_SPORTS == ("nfl", "cfb")
    assert "mlb" not in K.BOOK_NAMED_SPORTS
    census = {}
    got = K.from_game_bet(_card(book=""), "mlb", census=census)
    assert "no book is posting this price" not in census, census


def test_an_empty_shelf_under_this_bar_stays_empty():
    """End to end: the reserve runs because the game shelf is empty, and
    finds the same rows refused for the same reason."""
    census = {}
    got = K.build([], game_bets=[_card(book=""), _card(book="", team="GB",
                                                       pick="GB",
                                                       pick_is_home=False,
                                                       pick_label="GB ML")],
                  census=census)
    assert got == [], got
    assert not any(r.get("reserve") for r in got), got


# --- and the edge board's gate is a deliberate hold, not an oversight ---
def test_the_edge_board_gate_is_held_back_on_purpose_and_says_so():
    """The Most Likely board refuses an unattributed football price; the
    edge board does not yet withdraw `recommended` for the same thing.

    That asymmetry is a decision, not a gap someone forgot. Applying the
    rule to `_finish_bet` as well would ALSO strip the recommendation
    from every NFL game bet on a build where the books happen to be
    missing — and whether that is the droplet's state could not be
    checked from here. One unverified swing the night before Week 1 is
    enough. Pinned so the reasoning is found by whoever notices the
    inconsistency, rather than "fixed" blind."""
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    i = pipe.index("def _finish_bet(")
    body = pipe[i:pipe.index("\ndef ", i + 10)]
    assert "THE EDGE BOARD DOES NOT YET GATE ON A MISSING NAME" in body
    assert "Task #207" in body, "the hold has no follow-up recorded"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
