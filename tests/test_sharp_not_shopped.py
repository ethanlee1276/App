"""The sharp reference is never quoted as the price to take.

`oddsapi.SHARP_BOOKS` says it in its own comment — "Books a user can
actually bet at (Pinnacle doesn't take US action); the sharp reference
must never be quoted as the price to take" — and four of the five price
parsers in that module enforce it. `parse_event_scorers` did not, and
its quotes are the ENTIRE anytime-touchdown market in both football
leagues: college shops them through `best_scorer_price`, the NFL turns
them into SportsbookLines at 0.5 and shops them through
`best_over_line`. A sharp book runs a thinner margin, so on a favourite
its price is by construction the highest American number on the board
and wins either shop outright.

The half of this that is easy to get wrong in the other direction: the
parser must KEEP the sharp book, because `devig.board_fair` takes the
median de-vigged price across every book that quoted the player and a
sharp book belongs in that median. The refusal is about which price we
tell someone to TAKE, and nothing else. Both halves are pinned here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import booksharp, linemoves                     # noqa: E402
from engine.models import SportsbookLine                    # noqa: E402
from engine.odds import (best_over_line, best_under_line,    # noqa: E402
                         is_sharp_book)
from engine.sources import oddsapi                          # noqa: E402


def test_the_premise_the_bug_rests_on():
    """A sharp book is REQUESTED on every event pull, so it is in every
    payload. Without this the leak below could not happen and the guard
    would be dead code."""
    assert "pinnacle" in oddsapi.DEFAULT_BOOKS
    assert "pinnacle" in oddsapi.SHARP_BOOKS


def test_matched_on_the_title_not_only_the_key():
    """Quotes carry BOOK_TITLES display names; SHARP_BOOKS carries API
    keys. A strict comparison answers False forever."""
    assert is_sharp_book("Pinnacle")
    assert is_sharp_book("pinnacle")
    assert is_sharp_book("  PINNACLE ")
    assert not is_sharp_book("FanDuel")
    assert not is_sharp_book("DraftKings")


def test_an_absent_book_is_not_sharp():
    """A row with no book name is a different problem; calling it sharp
    would drop it from the shop for the wrong reason."""
    assert not is_sharp_book("")
    assert not is_sharp_book(None)


def test_one_predicate_not_three():
    """`linemoves._is_sharp` and `booksharp.compare_to_the_list` each
    carried their own copy. Three that must agree is a drift waiting to
    happen, and the drift reads as a finding about the market."""
    import inspect
    assert linemoves._is_sharp("Pinnacle") is is_sharp_book("Pinnacle")
    assert linemoves._is_sharp("FanDuel") is is_sharp_book("FanDuel")
    for mod in (linemoves, booksharp):
        src = inspect.getsource(mod)
        assert "is_sharp_book" in src, f"{mod.__name__} grew its own copy again"
        assert "SHARP_BOOKS = {" not in src, \
            f"{mod.__name__} re-inlined the fallback set"


# --- the college shop -------------------------------------------------------
def _q(book, yes, no=None):
    return {"book": book, "yes_odds": yes, "no_odds": no}


def test_scorer_shop_skips_the_sharp_book_even_when_it_pays_more():
    """The whole shape of the bug: the sharp price wins `max` and is
    unbettable."""
    got = oddsapi.best_scorer_price(
        [_q("Pinnacle", -240, 190), _q("DraftKings", -300, 230),
         _q("FanDuel", -320, 245)])
    assert got["book"] == "DraftKings", got
    assert got["yes_odds"] == -300


def test_scorer_shop_still_takes_the_best_bettable_price():
    """The guard must not cost the shop its job."""
    got = oddsapi.best_scorer_price(
        [_q("DraftKings", -300), _q("FanDuel", -260), _q("BetMGM", -285)])
    assert got["book"] == "FanDuel", got


def test_a_player_only_the_sharp_book_quotes_is_not_dropped():
    """Falling back is deliberate. Returning None would delete the
    player, and a deleted player reads as a market nobody quoted — the
    failure that arrives looking like an ordinary empty result."""
    got = oddsapi.best_scorer_price([_q("Pinnacle", -240, 190)])
    assert got is not None
    assert got["book"] == "Pinnacle"


def test_scorer_shop_still_refuses_a_corrupt_price():
    """The dead-zone filter predates this guard and outranks it: -97 is
    not a price any book posted, sharp or soft."""
    assert oddsapi.best_scorer_price([_q("DraftKings", -97)]) is None
    got = oddsapi.best_scorer_price([_q("DraftKings", -97), _q("FanDuel", -300)])
    assert got["book"] == "FanDuel"


def test_corrupt_sharp_and_real_soft():
    """Both filters at once, in the order that matters."""
    got = oddsapi.best_scorer_price([_q("Pinnacle", 50), _q("BetMGM", -300)])
    assert got["book"] == "BetMGM", got


def test_scorer_shop_returns_none_on_nothing():
    assert oddsapi.best_scorer_price([]) is None
    assert oddsapi.best_scorer_price(None) is None


# --- the NFL shop -----------------------------------------------------------
def _ln(book, line, over, under=None):
    return SportsbookLine(book=book, line=line, over_odds=over,
                          under_odds=under)


def test_over_shop_skips_the_sharp_book_at_the_same_number():
    got = best_over_line([_ln("Pinnacle", 0.5, -240, 190),
                          _ln("DraftKings", 0.5, -300, 230)])
    assert got.book == "DraftKings", got
    assert got.odds == -300


def test_over_shop_falls_back_when_only_the_sharp_book_quotes():
    got = best_over_line([_ln("Pinnacle", 0.5, -240, 190)])
    assert got.book == "Pinnacle"


def test_over_shop_still_prefers_the_lower_line():
    """Shopping the NUMBER outranks shopping the price, and the guard
    must not reorder that."""
    got = best_over_line([_ln("Pinnacle", 0.5, -200, 160),
                          _ln("FanDuel", 1.5, +130, -160),
                          _ln("BetMGM", 0.5, -260, 200)])
    assert got.book == "BetMGM", got
    assert got.line == 0.5


def test_under_shop_skips_the_sharp_book_too():
    got = best_under_line([_ln("Pinnacle", 0.5, -300, 210),
                           _ln("Caesars", 0.5, -320, 195)])
    assert got.book == "Caesars", got


def test_under_shop_falls_back_when_only_the_sharp_book_quotes():
    got = best_under_line([_ln("Pinnacle", 0.5, -300, 210)])
    assert got.book == "Pinnacle"


# --- and the half that must NOT change --------------------------------------
def _payload():
    return {"bookmakers": [
        {"key": "pinnacle", "markets": [{"key": "player_anytime_td", "outcomes": [
            {"description": "Cam Jones", "name": "Yes", "price": -240},
            {"description": "Cam Jones", "name": "No", "price": 190}]}]},
        {"key": "draftkings", "markets": [{"key": "player_anytime_td", "outcomes": [
            {"description": "Cam Jones", "name": "Yes", "price": -300},
            {"description": "Cam Jones", "name": "No", "price": 230}]}]},
    ]}


def test_the_parser_still_reports_the_sharp_book():
    """`devig.board_fair` takes the MEDIAN de-vigged price across books,
    and the sharp book belongs in that median. Filtering here instead of
    at the shop would make the consensus worse while fixing the price —
    the plausible wrong fix, pinned against."""
    got = oddsapi.parse_event_scorers(_payload())
    quotes = got[(oddsapi.normalize_name("Cam Jones"), "anytime_td")]
    books = {q["book"] for q in quotes}
    assert "Pinnacle" in books, books
    assert "DraftKings" in books, books


def test_the_devig_input_keeps_both_books():
    """End to end through the college hold measurement: the sharp board
    reaches `board_fair`, and the shop still refuses its price."""
    from engine.cfb.tds import game_fairs
    quotes = {}
    for (norm, _mkt), qs in oddsapi.parse_event_scorers(_payload()).items():
        quotes.setdefault(norm, []).extend(qs)
    seen = set()
    real = __import__("engine.devig", fromlist=["board_fair"]).board_fair

    def spy(by_book, *a, **kw):
        seen.update(by_book)
        return real(by_book, *a, **kw)

    import engine.devig as devig
    devig.board_fair = spy
    try:
        game_fairs(quotes, spread_home=-14.0, total=52.0)
    finally:
        devig.board_fair = real
    assert "pinnacle" in seen, seen
    shopped = oddsapi.best_scorer_price(
        quotes[oddsapi.normalize_name("Cam Jones")])
    assert shopped["book"] == "DraftKings", shopped


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
