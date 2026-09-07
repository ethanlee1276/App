"""Every refusal in `likely.from_prop` is counted, including the two after the mixture.

Ethan, 2026-09-07, on the NFL Most Likely board: "all i see now is the
tight end props removed. so what changed." The census exists to answer
that question — it counts every reason a maker turned a row away — and
it could not, because the two refusals the MIXTURE creates were bare
`return None`s: a row that cleared the floor on its raw claim and fell
under it once calibrated, and a row the calibration walked away from
the book's number. On a night the board came out empty the census read
"under the likelihood floor: 4" while the other hundred rows left no
trace. Both are counted now, under their own names.

Run directly: `python3 tests/test_likely_census_complete.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import likely as K                               # noqa: E402

#: The real fitted mixtures from 2026-08-30 (see tests/test_likely.py).
FITS = {
    "rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54},
    "rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60},
    "receptions": {"zero": [-0.82, 0.48], "sigma": 0.46},
}


def _always(_market):
    return True


def _row(**kw):
    got = {"player": "A Back", "team": "DET", "opponent": "CHI",
           "market": "rush_yds", "market_label": "rush_yds", "side": "over",
           "line": 45.5, "book": "DK", "odds": -110, "has_market": True,
           "fair_prob": 0.55, "projection": 62.0, "ev_per_unit": 0.03,
           "reasons": ["because"], "recent_values": [40, 60, 55],
           "date": "2026-09-14", "hit_prob": 0.62, "raw_prob": 0.66}
    got.update(kw)
    return got


def test_a_row_the_mixture_pulls_under_the_floor_is_counted():
    """Raw claim 0.62 clears the 0.55 floor; the projection sits ON the
    line, so the calibrated number is a coin flip and the row is refused
    — and the census says so under its own name, not the raw floor's."""
    census = {}
    assert K.from_prop(_row(projection=45.5), _always, fits=FITS, census=census) is None
    assert census == {"under the likelihood floor after calibration": 1}, census


def test_a_row_the_mixture_walks_away_from_the_book_is_counted():
    """Projection 62 on a 45.5 line calibrates to about 0.62; a book
    fair of 0.40 is twenty points away, past what we credit."""
    census = {}
    assert K.from_prop(_row(fair_prob=0.40), _always, fits=FITS, census=census) is None
    assert census == {"disagrees with the market by more than we credit": 1}, census
    # The control: the same row against a 0.55 fair is on the board.
    census = {}
    assert K.from_prop(_row(), _always, fits=FITS, census=census) is not None
    assert census == {}


def test_no_refusal_in_from_prop_is_silent():
    """The structural pin: a maker refuses through `_refuse` or not at
    all. A bare `return None` is a refusal the census cannot see."""
    src = inspect.getsource(K.from_prop)
    assert "return None" not in src, "a silent refusal is back in from_prop"
    assert src.count("_refuse(census,") >= 6


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
