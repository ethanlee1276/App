"""The closing numbers college football is graded against.

`engine.sources.cfbfastr` backfilled 3,132 FBS games and stored
``spread=None, total=None`` on every one, because that feed carries
scores and Elo and writing a 0.0 would have read as a pick'em on three
thousand games. The cost ran everywhere: `engine.gamecal` could not
measure college football's market haircut, `engine.cfbtdfit` had no
implied team total to grade the touchdown model's game script against,
and nothing college the site prices had ever been compared with the
number a bettor could actually have taken.

The file was in the same repository the whole time. These tests pin the
three things about its shape that will otherwise produce a number that
looks right and is not.

Run directly: `python3 tests/test_cfblines.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfblines as C

GAMES = {"401": {"home_name": "Penn State", "away_name": "Notre Dame"}}


def _row(**kw):
    row = {"game_id": "401", "season": "2024", "week": "16",
           "market_type": "spread", "abbr": "Penn State", "lines": "-1.5",
           "odds": "", "opening_lines": "", "book": "DraftKings"}
    row.update(kw)
    return row


def _both(home, away, book="DraftKings"):
    return [_row(abbr="Penn State", lines=str(home), book=book),
            _row(abbr="Notre Dame", lines=str(away), book=book)]


def _total(value, book="DraftKings"):
    return [_row(market_type="total", abbr="over", lines=str(value), book=book),
            _row(market_type="total", abbr="under", lines=str(value), book=book)]


# --- the home side ----------------------------------------------------
def test_the_stored_spread_is_the_home_teams_number():
    out = C.parse_lines(_both(-1.5, 1.5), GAMES)
    assert out["lines"]["401"]["spread"] == -1.5


def test_the_home_side_is_found_by_this_games_own_school_name():
    """Not by a name table. `abbr` holds the school on modern rows and a
    real abbreviation on old ones, and the schedule already stored which
    school was at home in THIS game."""
    swapped = {"401": {"home_name": "Notre Dame", "away_name": "Penn State"}}
    out = C.parse_lines(_both(-1.5, 1.5), swapped)
    assert out["lines"]["401"]["spread"] == 1.5


def test_a_row_matching_neither_school_is_skipped_not_guessed():
    out = C.parse_lines([_row(abbr="Ohio State")], GAMES)
    assert out["lines"] == {}
    assert out["skipped"]["spread side matched neither school"] == 1


def test_a_game_we_never_ingested_is_skipped():
    out = C.parse_lines([_row(game_id="999")], GAMES)
    assert out["lines"] == {}
    assert out["skipped"]["game not ingested"] == 1


# --- the guards -------------------------------------------------------
def test_a_book_whose_two_sides_do_not_cancel_is_dropped():
    """They are the same number with opposite signs. When they are not,
    the pair is not what it claims and half-reading it would store a
    spread nobody quoted."""
    out = C.parse_lines(_both(-1.5, 7.5), GAMES)
    assert "401" not in out["lines"]
    assert out["skipped"]["the two sides of the spread did not cancel"] == 1


def test_a_one_sided_quote_is_still_usable():
    out = C.parse_lines([_row(abbr="Penn State", lines="-3.0")], GAMES)
    assert out["lines"]["401"]["spread"] == -3.0


def test_an_away_only_quote_is_not_stored_as_the_home_number():
    out = C.parse_lines([_row(abbr="Notre Dame", lines="3.0")], GAMES)
    assert "401" not in out["lines"]
    assert out["skipped"]["no home-side spread from this book"] == 1


def test_an_impossible_spread_is_refused():
    out = C.parse_lines(_both(-120.0, 120.0), GAMES)
    assert "401" not in out["lines"]


def test_a_total_outside_any_plausible_range_is_refused():
    out = C.parse_lines(_total(400.0), GAMES)
    assert "401" not in out["lines"]


# --- the close, and only the close ------------------------------------
def test_an_opener_is_never_substituted_for_a_missing_close():
    """An opener in a column labelled "close" is exactly the kind of
    number that reads as measured and is not."""
    out = C.parse_lines([_row(lines="", opening_lines="-7.5")], GAMES)
    assert out["lines"] == {}
    assert out["skipped"]["no closing number from this book"] == 1


# --- many books -------------------------------------------------------
def test_books_are_combined_by_median_not_mean():
    """One book leaving a stale number up moves a mean and cannot move a
    median past its neighbours."""
    rows = (_both(-1.0, 1.0, "A") + _both(-1.5, 1.5, "B")
            + _both(-2.0, 2.0, "C") + _both(-20.0, 20.0, "Stale"))
    out = C.parse_lines(rows, GAMES)["lines"]["401"]
    assert out["spread"] == -1.75
    assert out["spread_books"] == 4


def test_the_book_count_rides_along_as_evidence():
    out = C.parse_lines(_total(45.5, "A") + _total(46.5, "B"), GAMES)
    assert out["lines"]["401"]["total"] == 46.0
    assert out["lines"]["401"]["total_books"] == 2


def test_a_total_reads_the_over_row_and_ignores_the_under():
    out = C.parse_lines(_total(45.5), GAMES)
    assert out["lines"]["401"]["total"] == 45.5


def test_a_market_with_no_usable_quote_does_not_borrow_the_others_game():
    out = C.parse_lines(_total(45.5), GAMES)
    assert "spread" not in out["lines"]["401"]


def test_the_season_filter_is_honoured():
    out = C.parse_lines(_both(-1.5, 1.5), GAMES, seasons=[2023])
    assert out["lines"] == {}
    assert out["skipped"]["season not requested"]


def test_moneyline_rows_are_read_for_nothing_and_break_nothing():
    rows = _both(-1.5, 1.5) + [_row(market_type="money_line", lines="",
                                    odds="-115")]
    out = C.parse_lines(rows, GAMES)
    assert out["lines"]["401"]["spread"] == -1.5


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
