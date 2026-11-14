"""The price on a longshot card is one the reader can actually take.

Ethan, 2026-09-08: "You need to work non stop till you solve the issues
with the book prices being wrong for nfl."

THE DEFECT. `oddsapi.SHARP_BOOKS` says it in its own comment — "Books a
user can actually bet at (Pinnacle doesn't take US action); the sharp
reference must never be quoted as the price to take." `engine.odds`
enforces that for yardage props: `best_over_line` drops sharp books
before it shops, and falls back to the whole field only when nothing
bettable is left.

Three boards never went through that function. Each picks its price with
a bare `max(lines, key=over_odds)`:

    engine/pipeline.py      the NFL anytime-touchdown board
    engine/mlb/pipeline.py  the home-run longshot board
    nba_build.py            the NBA prop board

And `parse_event_scorers` does not filter sharp books either, so a
Pinnacle anytime-TD quote reaches `prop.lines` like any other. On a
LONGSHOT that is the worst possible combination: the sharp book runs the
thinnest margin, so on a +600 dog it is frequently the LONGEST price on
the board — which is exactly what `max` is looking for. The card then
prints a book Ethan does not have an account with, beside a number no
book he can reach is offering. To him that is simply a wrong price, and
he has now reported wrong prices four times in a week.

THE DE-VIG IS NOT TOUCHED, the same doctrine `best_over_line` already
carries: `devig.board_fair` takes the median de-vigged price across
every book that quoted the player, and the sharp book belongs in that
median. The refusal is only about which price we tell someone to TAKE.

Run directly: `python3 tests/test_longshot_book_takes_action.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.models import SportsbookLine                       # noqa: E402
from engine import odds as O                                   # noqa: E402


def _ln(book, over, under=None, line=0.5):
    return SportsbookLine(book=book, line=line, over_odds=over,
                          under_odds=under if under is not None else -over)


# --- the shared helper ------------------------------------------------------
def test_the_sharp_book_is_dropped_before_the_shop():
    lines = [_ln("DraftKings", 550), _ln("Pinnacle", 700), _ln("FanDuel", 600)]
    got = O.bettable_lines(lines)
    assert [ln.book for ln in got] == ["DraftKings", "FanDuel"], got


def test_a_market_only_the_sharp_book_quotes_still_returns_a_line():
    """The same fallback `best_over_line` uses, for the same reason:
    dropping the player instead would turn a bad price into an empty
    board, and an empty board is the failure that reads as an ordinary
    result. The caller's own gate is what refuses to price it."""
    lines = [_ln("Pinnacle", 700)]
    assert O.bettable_lines(lines) == lines


def test_an_empty_list_stays_empty():
    assert O.bettable_lines([]) == []


def test_the_name_is_matched_loosely_like_everywhere_else():
    """Quotes carry display names and SHARP_BOOKS carries API keys; the
    loose match in `is_sharp_book` is the one definition, and this helper
    must not grow a second, stricter one."""
    assert O.bettable_lines([_ln("pinnacle", 700), _ln("DK", 500)]) == \
        [_ln("DK", 500)]


# --- the three boards -------------------------------------------------------
def test_the_nfl_touchdown_board_does_not_quote_the_sharp_book():
    """THE CARD ETHAN IS LOOKING AT. Pinnacle at +700 is the longest
    price here, so an unfiltered `max` names it and prints a number he
    cannot bet.

    Driven through `_long_shots`, the function the board actually calls,
    rather than through the helper alone: the helper being right and the
    board not calling it is precisely the state this file found."""
    from engine.models import (ANYTIME_TD, Team, DefenseProfile, Prop, Game,
                               GameLog, Weather)
    from engine.data_loader import Slate
    from engine.pipeline import _long_shots
    teams = {"DET": Team("DET", "DET", DefenseProfile("DET")),
             "NO": Team("NO", "NO", DefenseProfile("NO"))}
    game = Game(home="DET", away="NO", weather=Weather(), date="2026-09-14",
                kickoff="2026-09-14T17:00:00Z", total=44.0, spread=-3.0)
    prop = Prop(player="A Longshot", team="DET", opponent="NO", position="RB",
                market=ANYTIME_TD,
                logs=[GameLog(week=w, opponent="X", value=1) for w in range(1, 6)],
                career_avg=0.4, vs_opponent_avg=None,
                lines=[_ln("DraftKings", 550), _ln("Pinnacle", 700),
                       _ln("FanDuel", 600)])
    slate = Slate(date="2026-09-14", teams=teams, games=[game], props=[prop])
    picks, watch = _long_shots(slate)
    rows = list(picks) + list(watch)
    assert rows, "the touchdown board produced no row at all"
    books = {(r.get("book") or "") for r in rows}
    assert "Pinnacle" not in books, books
    assert books == {"FanDuel"}, books
    assert all(int(r.get("odds") or 0) == 600 for r in rows), rows


def test_the_home_run_board_does_not_quote_the_sharp_book():
    from engine.mlb.models import MLBProp, MLBGame, MLBGameLog
    from engine.mlb.data_loader import MLBSlate
    from engine.mlb.pipeline import _long_shots as hr_long_shots
    game = MLBGame(home="LAD", away="SF", park="LAD", date="2026-09-14",
                   kickoff="2026-09-14T17:00:00Z")
    prop = MLBProp(player="A Slugger", team="LAD", opponent="SF", position="OF",
                   market="home_runs",
                   logs=[MLBGameLog(game=g, opponent="X", value=0)
                         for g in range(1, 6)],
                   career_avg=0.2, vs_pitcher_avg=None, lineup_spot=3,
                   lines=[_ln("DraftKings", 380), _ln("Pinnacle", 460),
                          _ln("FanDuel", 400)])
    slate = MLBSlate(date="2026-09-14", games=[game], props=[prop])
    picks, watch, _diag, pool = hr_long_shots(slate)
    rows = list(picks) + list(watch) + list(pool)
    assert rows, "the home-run board produced no row at all"
    books = {(r.get("book") or "") for r in rows if r.get("book")}
    assert "Pinnacle" not in books, books
    assert books == {"FanDuel"}, books


def test_the_nba_prop_board_does_not_quote_the_sharp_book():
    import nba_build
    lines = [_ln("DraftKings", -110, -110, line=24.5),
             _ln("Pinnacle", 100, 100, line=24.5),
             _ln("FanDuel", -105, -108, line=24.5)]
    got = nba_build.best_two_way(lines)
    assert got is not None, "the NBA board found no line at all"
    _line, over, under, book = got
    assert book == "FanDuel", book
    assert over == -105, over
    assert under == -108, "the sharp book's under was shopped too"


def test_a_board_only_the_sharp_book_quotes_still_draws_a_row():
    """The fallback, through a real board rather than the helper alone."""
    import nba_build
    got = nba_build.best_two_way([_ln("Pinnacle", 100, 100, line=24.5)])
    assert got is not None, "the shelf went empty instead of showing the price"
    assert got[3] == "Pinnacle", got


# --- and the measurement is left alone --------------------------------------
def test_the_devig_still_sees_every_book():
    """`board_fair` takes the median de-vigged price across everyone who
    quoted the player, and the sharp book belongs in that median —
    dropping it there would make the consensus worse, not better. The
    refusal is about the price we tell someone to take and nothing
    else."""
    import inspect
    src = inspect.getsource(__import__("engine.devig", fromlist=["x"]))
    assert "is_sharp_book" not in src, \
        "the de-vig started refusing the sharp book's price too"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
