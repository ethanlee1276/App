"""The Most Likely board picks its number from the book's alternate ladder.

Ethan, 2026-09-07, with the census in hand (303 prop rows, 215 under
the floor, none shown): "i prefer to do whatever gives us props and
picks every single day ... we need to be showing most likley props
period."

A main line is hung where the book thinks the coin is fair, so the
calibrated number at it sits near 50% and a board asking for 55% at a
price no heavier than -250 could show nothing. The same books hang the
same stat at other numbers, and that is where a 60-70% event is for
sale. `likely.from_prop` now judges every rung of the ladder by the
same bars it holds the main line to — at the rung's own numbers — and
shows the likeliest of them, with the main line beside it.

Run directly: `python3 tests/test_likely_rungs.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import likely as K                               # noqa: E402
from engine.odds import devig_two_way                        # noqa: E402
from engine.yardagefit import display_prob                   # noqa: E402

#: The real fitted mixtures from 2026-08-30 (see tests/test_likely.py).
FITS = {
    "rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54},
    "rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60},
    "receptions": {"zero": [-0.82, 0.48], "sigma": 0.46},
}


def _always(_market):
    return True


def _ln(book, line, over, under=0):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _row(**kw):
    """A published rush-yards row: main line 62.5 at -110, projection 62,
    so the main number calibrates to a coin flip and the ladder is the
    only place anything likely lives."""
    got = {"player": "A Back", "team": "DET", "opponent": "CHI",
           "market": "rush_yds", "market_label": "rush_yds", "side": "over",
           "line": 62.5, "book": "DK", "odds": -110, "has_market": True,
           "fair_prob": 0.50, "projection": 62.0, "ev_per_unit": 0.01,
           "reasons": ["because"], "recent_values": [55, 71, 48, 66],
           "date": "2026-09-14", "hit_prob": 0.56, "raw_prob": 0.58,
           "alt_lines": [_ln("DraftKings", 40.5, -240), _ln("FanDuel", 40.5, -230),
                         _ln("DraftKings", 50.5, -160), _ln("FanDuel", 50.5, -155),
                         _ln("DraftKings", 75.5, 150)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got


def _p(line, row=None):
    row = row or _row()
    return display_prob("rush_yds", row["projection"], line, row["recent_values"], fits=FITS)


def test_the_likeliest_rung_under_the_cap_is_shown_at_its_best_price():
    census = {}
    row = K.from_prop(_row(), _always, fits=FITS, census=census)
    assert row is not None, census
    assert census == {}
    # The main number calibrates under the floor; 40.5 is the likeliest
    # rung and FanDuel's -230 beats DraftKings' -240 for it.
    assert _p(62.5) < K.MIN_PROB and _p(40.5) > _p(50.5) > K.MIN_PROB
    assert (row["line"], row["side"], row["book"], row["odds"]) == (40.5, "over", "FanDuel", -230)
    assert row["model_prob"] == round(_p(40.5), 4) and row["prob_source"] == "mixture"
    assert row["rung"] == "alt"
    assert (row["main_line"], row["main_odds"], row["main_book"]) == (62.5, -110, "DK")
    # Judged against the rung's own de-vigged price, not the main line's.
    fair_over, _ = devig_two_way(-230, 0)
    assert row["implied_prob"] == round(fair_over, 4)
    assert row["fair_prob"] == 0.50 and row["engine_raw_prob"] == 0.58
    assert row["ev_per_unit"] is None
    # …and it clears the one bar for every row.
    assert K.admissible(row) == "", K.admissible(row)


def test_a_rung_heavier_than_the_cap_is_never_the_pick():
    """A 35.5 rung at -280 is likelier still (0.77 against a 0.70 fair,
    inside the credibility bar), and it is chalk."""
    fair, _ = devig_two_way(-280, 0)
    assert _p(35.5) > _p(40.5) and abs(_p(35.5) - fair) <= K.MAX_CREDIBLE_EDGE
    row = K.from_prop(_row(alt_lines=_row()["alt_lines"] + [_ln("DraftKings", 35.5, -280)]),
                      _always, fits=FITS)
    assert row["line"] == 40.5 and row["odds"] == -230


def test_the_main_line_wins_when_it_is_the_likelier_number():
    """An under at 80.5 on a 62 projection is likelier than any over rung
    the book left on the ladder."""
    base = _row(side="under", line=80.5, odds=-215, fair_prob=0.68, hit_prob=0.66,
                alt_lines=[_ln("DraftKings", 70.5, -105), _ln("FanDuel", 40.5, -230)])
    # The 40.5 over rung clears every bar on its own; the under is
    # likelier and keeps the row.
    assert K.MIN_PROB < _p(40.5, base) < 1.0 - _p(80.5, base)
    row = K.from_prop(base, _always, fits=FITS)
    assert row is not None
    assert (row["rung"], row["line"], row["side"]) == ("main", 80.5, "under")
    assert row["model_prob"] == round(1.0 - _p(80.5, base), 4)
    assert row["implied_prob"] == 0.68 and row["ev_per_unit"] == 0.01


def test_a_rung_stands_in_when_the_main_line_fails_its_own_bars():
    """The main number can be LIKELIER than the rung and still not
    belong on the board — here a 76% under against a book fair of 52%
    is past what we credit. The rung that clears every bar is the row."""
    base = _row(side="under", line=80.5, odds=-115, fair_prob=0.52, hit_prob=0.60,
                alt_lines=[_ln("FanDuel", 40.5, -230)])
    assert 1.0 - _p(80.5, base) > _p(40.5, base) > K.MIN_PROB
    assert not K._credible(1.0 - _p(80.5, base), 0.52)
    row = K.from_prop(base, _always, fits=FITS)
    assert row is not None, "the rung was refused with the main line"
    assert (row["rung"], row["line"], row["side"], row["odds"]) == ("alt", 40.5, "over", -230)


def test_an_under_rung_is_priced_on_its_own_side():
    base = _row(alt_lines=[_ln("DraftKings", 75.5, 175, -220)])
    row = K.from_prop(base, _always, fits=FITS)
    assert row is not None and row["rung"] == "alt", row
    assert (row["line"], row["side"], row["odds"]) == (75.5, "under", -220)
    assert row["model_prob"] == round(1.0 - _p(75.5), 4)
    _, fair_under = devig_two_way(175, -220)
    assert row["implied_prob"] == round(fair_under, 4)


def test_a_market_with_no_fit_prices_a_rung_from_the_sharp_pair_or_not_at_all():
    """Passing yards has no mixture here. A rung the sharp book quotes
    two ways is priced from that pair; a rung it does not is skipped."""
    base = _row(market="pass_yds", market_label="pass_yds", line=250.5,
                projection=255.0, hit_prob=0.56, raw_prob=0.56, fair_prob=0.52,
                alt_lines=[_ln("DraftKings", 220.5, -140), _ln("DraftKings", 200.5, -200)],
                alt_sharp_lines=[_ln("Pinnacle", 220.5, -150, 125)])
    row = K.from_prop(base, _always, fits=FITS)
    assert row is not None
    fair_over, _ = devig_two_way(-150, 125)
    assert (row["rung"], row["line"], row["prob_source"]) == ("alt", 220.5, "sharp")
    assert row["model_prob"] == round(fair_over, 4)
    # Without the sharp pair there is no number for a rung: the main
    # line, at its raw claim, is what shows.
    row = K.from_prop({**base, "alt_sharp_lines": []}, _always, fits=FITS)
    assert row is not None and row["rung"] == "main" and row["line"] == 250.5


def test_a_rung_that_disagrees_with_its_own_price_is_skipped():
    """A book posting 40.5 at +100 says 50%; the mixture says far more.
    That gap is our error more often than a discovery, at a rung as at
    a main line."""
    base = _row(alt_lines=[_ln("DraftKings", 40.5, 100), _ln("DraftKings", 50.5, -160)])
    row = K.from_prop(base, _always, fits=FITS)
    assert row["line"] == 50.5, row


def test_sharp_and_proxy_books_never_show_as_a_rung():
    base = _row(alt_lines=[_ln("Pinnacle", 40.5, -220), _ln("proxy", 40.5, -220),
                           _ln("DraftKings", 50.5, -160)])
    row = K.from_prop(base, _always, fits=FITS)
    assert (row["line"], row["book"]) == (50.5, "DraftKings")


def test_without_a_ladder_nothing_changes():
    census = {}
    assert K.from_prop(_row(alt_lines=[]), _always, fits=FITS, census=census) is None
    assert census == {"under the likelihood floor after calibration": 1}
    row = K.from_prop(_row(alt_lines=[], projection=85.0, fair_prob=0.55),
                      _always, fits=FITS)
    assert row is not None and row["rung"] == "main" and row["main_line"] == 62.5


def test_the_card_names_the_rungs_main_number():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("function likelyCard(")
    body = app[i:i + 9000]
    assert 'r.rung === "alt"' in body
    assert "Alternate line" in body and "main number is ${r.main_line}" in body
    assert "priced from the sharp book" in body


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
