"""A hold is what you pay, and nobody pays an arbitrary book.

WHAT THIS WAS FOUND CHASING. #65's spike survived its error bar and then
survived the void-bet filter: after dropping every player-week the logs
record as zero snaps, the 0.10-0.18 raw band — +456 to +900, where the
touchdown longshot board lives — still charged 33.9% +/-7.1% against
11.8% across the rest of the board, z = +2.8 on 872 rows. The +900-and-
longer band, by contrast, collapsed from 13.7% to 0.8%: that is where the
scratches were, not here.

So the next question is what "the market" meant in that sentence.

`db.closing_odds_by_date` keeps the LAST row per (player, date). One
harvest writes every book at a single `taken_at`, so among those rows the
survivor is whichever SQLite hands back last. Every hold this module has
ever printed is an arbitrary book's hold — and books disagree most
exactly where the longshots are: a soft +900 and a sharp +650 on the same
man are four points of implied probability apart.

That is not a rounding detail. It is the difference between "the market
charges 34% here" and "one book we happened to read charges 34% here,
and the board does not bet that book".

Run directly: `python3 tests/test_devigshop.py`
"""

import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as DB                             # noqa: E402
from engine import devigfit as D                        # noqa: E402


# --- the accessor -------------------------------------------------------
def _store(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(DB.SCHEMA)
    conn.executemany(
        "INSERT INTO odds_history "
        "(sport, taken_at, event_id, home, away, player, market, book, "
        " line, over_odds, under_odds) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [("nfl", t, "e1", "KC", "DEN", p, "anytime_td", b, None, o, None)
         for t, p, b, o in rows])
    conn.commit()
    return conn


def test_every_book_survives_not_whichever_sorted_last():
    conn = _store([("2025-09-07T15:00:00", "a smith", "dk", 550),
                   ("2025-09-07T15:00:00", "a smith", "fd", 700),
                   ("2025-09-07T15:00:00", "a smith", "mgm", 600)])
    got = DB.closing_odds_all_books(conn, "nfl", "anytime_td")
    quotes = got[("a smith", "2025-09-07")]
    assert sorted(q["over_odds"] for q in quotes) == [550, 600, 700]


def test_a_stale_snapshot_does_not_linger_beside_a_fresh_one():
    """The point of a CLOSE is that it is the last price. A morning quote
    sitting in the same list as an afternoon one would let a bettor
    "shop" a number that was gone by kickoff."""
    conn = _store([("2025-09-07T12:00:00", "a smith", "dk", 400),
                   ("2025-09-07T15:00:00", "a smith", "dk", 550),
                   ("2025-09-07T15:00:00", "a smith", "fd", 700)])
    quotes = DB.closing_odds_all_books(conn, "nfl", "anytime_td")[
        ("a smith", "2025-09-07")]
    assert sorted(q["over_odds"] for q in quotes) == [550, 700]


def test_each_day_is_its_own_close():
    conn = _store([("2025-09-07T15:00:00", "a smith", "dk", 550),
                   ("2025-09-14T15:00:00", "a smith", "dk", 300)])
    got = DB.closing_odds_all_books(conn, "nfl", "anytime_td")
    assert got[("a smith", "2025-09-07")][0]["over_odds"] == 550
    assert got[("a smith", "2025-09-14")][0]["over_odds"] == 300


def test_the_one_quote_accessor_is_left_alone():
    """A second accessor rather than a wider return, because the
    one-quote-per-key contract is what the existing backtest joins are
    built on — the reasoning `calibrate.load_curves` already gives."""
    conn = _store([("2025-09-07T15:00:00", "a smith", "dk", 550),
                   ("2025-09-07T15:00:00", "a smith", "fd", 700)])
    single = DB.closing_odds_by_date(conn, "nfl", "anytime_td")
    assert isinstance(single[("a smith", "2025-09-07")], dict)


# --- the table ----------------------------------------------------------
def _board(seed=2, n=3000, soft=0.75):
    """A board where one book quotes `soft` shorter implied — that is,
    LONGER odds — on the longshots only. The market charges the same
    everywhere; one book on the screen is generous."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        p = rng.choice([0.05, 0.14, 0.22, 0.35, 0.55])
        best = p * (soft if p < 0.18 else 0.97)
        rows.append({"season": 2024, "week": "1", "market": p, "best": best,
                     "books": 3, "book": "soft", "played": True,
                     "scored": int(rng.random() < best * 0.92)})
    return rows


def _cut(lines, band="0.10-0.18"):
    for ln in lines:
        if ln.strip().startswith(band):
            return float(ln.split()[4].rstrip("%")) / 100.0
    raise AssertionError(f"{band} not in\n" + "\n".join(lines))


def test_a_spike_that_is_one_books_loading_shrinks_when_you_shop():
    """THE DISCRIMINATING TEST. Nothing about the true probabilities
    changes between these two tables — only which price on the screen is
    used to measure the toll."""
    rows = _board()
    arbitrary = _cut(D.haircut_lines(rows))
    shopped = _cut(D.best_price_lines(rows))
    assert arbitrary > 0.15, arbitrary
    assert shopped < 0.10, shopped


def test_a_spike_the_whole_market_charges_survives_shopping():
    """The other direction, or the test above proves nothing. When every
    book quotes the same longshot price, shopping cannot help and the
    toll is the market's."""
    rows = _board(soft=1.0)
    assert _cut(D.best_price_lines(rows)) > 0.03, \
        "a market-wide loading must not vanish just because we looked twice"


def test_the_longest_price_is_the_one_taken_not_the_average():
    """A bettor takes the best number on the screen, not the mean of the
    screen. Averaging would understate what shopping is worth and read as
    the market being tighter than it is."""
    import inspect
    src = inspect.getsource(D.collected)
    assert "min(priced, key=lambda pq: pq[0])" in src


def test_the_original_column_still_means_what_it_meant():
    """`market` stays whichever book sorted last, so every number this
    module has printed since it shipped is still comparable. A silent
    redefinition would make the old runs and the new ones look like a
    change in the market."""
    import inspect
    src = inspect.getsource(D.collected)
    assert "market = priced[-1][0]" in src


def test_the_book_count_is_reported_because_one_book_proves_nothing():
    got = "\n".join(D.best_price_lines(_board()))
    assert "books per player-date" in got
    assert "quoted by only one" in got


def test_a_single_book_harvest_says_the_table_is_empty_of_meaning():
    """Two identical tables read as two answers agreeing, which is the
    strongest claim from the weakest evidence."""
    rows = [dict(r, books=1, best=r["market"]) for r in _board()]
    got = "\n".join(D.best_price_lines(rows))
    assert "says nothing yet" in got


def test_rows_with_no_per_book_prices_refuse_instead_of_guessing():
    rows = [{"market": 0.14, "scored": 0, "played": True} for _ in range(50)]
    got = "\n".join(D.best_price_lines(rows))
    assert "no per-book prices" in got
    assert "what the market actually charged" not in got


def test_the_full_report_shops_only_rows_that_could_be_lost():
    """Void bets and one-book pricing are two different distortions and
    correcting one must not smuggle the other back in."""
    import inspect
    assert "best_price_lines(played_rows(rows))" in \
        inspect.getsource(D.report_lines)


# --- the fit, and what it must not be wired into -------------------------
def _weeks(seed=4, weeks=12, per=400, soft=0.75):
    rng = random.Random(seed)
    rows = []
    for w in range(1, weeks + 1):
        for _ in range(per):
            p = rng.choice([0.05, 0.14, 0.22, 0.35, 0.55])
            best = p * (soft if p < 0.18 else 0.95)
            rows.append({"season": 2025, "week": str(w), "market": p,
                         "best": best, "books": 6, "book": "x",
                         "played": True,
                         "scored": int(rng.random() < best * 0.96)})
    return rows


def test_the_fit_is_redone_on_the_price_the_board_actually_bets():
    """`odds.best_over_line` shops across books — its own docstring calls
    it "the 'shop for the best number' step every sharp bettor does" — so
    the published pick carries the LONGEST price on the screen. A de-vig
    fitted on some other book is fitted on a price nobody was offered."""
    got = "\n".join(D.shopped_fit_lines(_weeks()))
    assert "refitted on the SHOPPED price" in got
    assert "must not be wired into a board that shops" in got


def test_the_shopped_hold_is_far_smaller_than_the_arbitrary_one():
    rows = _weeks()
    loose = D.compare(rows)["m"]
    tight = D.compare(D.shopped(rows))["m"]
    assert tight < loose, (tight, loose)


def test_the_overround_is_summed_not_averaged_over_bands():
    """An overround is a ratio of summed probabilities. Averaging five
    band percentages weights 300 longshots the same as 800 favourites,
    which is how a table that reads flat produces a headline that does
    not."""
    rows = ([{"market": 0.50, "scored": 1} for _ in range(100)]
            + [{"market": 0.10, "scored": 0} for _ in range(100)])
    # summed: 60.0 implied against 100 hits -> 0.60
    assert abs(D.overall_hold(rows) - 0.60) < 1e-9
    assert D.overall_hold([]) is None
    assert D.overall_hold([{"market": 0.2, "scored": 0}]) is None


def test_the_line_says_which_way_the_assumption_errs():
    """"Close" is not the same claim as "cautious", and the board prices
    real money off the difference."""
    got = "\n".join(D.shopped_fit_lines(_weeks()))
    assert "the board assumes" in got
    assert ("cautious, and close" in got
            or "the book charges more than we assume" in got)


def test_the_conflict_with_board_hold_is_recorded_not_smoothed_over():
    """`devig.board_hold` reports 22-35% on the same menus. Four to five
    times apart, different denominators, and only one of them can be
    wrong. A module that quietly reports the friendlier number is worse
    than one that reports the disagreement."""
    assert "board_hold" in D.shopped_fit_lines.__doc__
    from engine import longshots as L
    import inspect
    src = inspect.getsource(L)
    head = src[:src.index("ONE_SIDED_HOLD = 1.06")]
    assert "board_hold" in head
    assert "expected distinct" in head


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
