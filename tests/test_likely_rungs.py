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


def test_a_passing_yards_rung_is_priced_by_the_model_when_no_mixture_fits():
    """Ethan, 2026-09-15: "I didn't see any passing yard props." The
    yardage fit declined passing yards, so `display_prob` has nothing for
    it, and the ladder's only other source was a sharp book hanging the
    same alternate number — almost never. The rung is priced the way the
    main line was: the projection's own normal, held to every bar."""
    row = _row(market="pass_yds", market_label="pass_yds", line=279.5,
               projection=285.0, hit_prob=0.53, raw_prob=0.54,
               recent_values=[301, 244, 312, 268])
    row["proj_std"] = 45.0
    row["alt_lines"] = [_ln("DK", 264.5, -180, 150), _ln("DK", 299.5, 150, -180)]
    row["alt_sharp_lines"] = []
    assert display_prob("pass_yds", 285.0, 264.5, row["recent_values"], fits=FITS) is None
    rung = K._best_rung(row, "pass_yds", fits=FITS)
    assert rung is not None, "the ladder could not price a passing-yards rung"
    assert rung["line"] == 264.5 and rung["side"] == "over" and rung["source"] == "model"
    assert 0.66 < rung["prob"] < 0.69, rung           # P(N(285, 45) > 264.5)
    # And the full maker takes it, as a model-sourced row.
    got = K.from_prop(row, _always, fits=FITS)
    assert got is not None and got["line"] == 264.5 and got["prob_source"] == "model"
    # No spread on the row: nothing to price, nothing invented.
    row["proj_std"] = 0
    assert K._best_rung(row, "pass_yds", fits=FITS) is None


def test_a_sharp_anchored_row_prices_its_ladder_from_the_markets_centre():
    """Ethan, 2026-09-10 and 2026-09-15: one passing-yards prop. The raw
    passing model sits well above the book — here 250 against a 234.5
    line the sharp book calls a coin flip — so the main line fails the
    credibility bar, every over rung fails it by the same margin, and
    every under rung is under the floor. The edge board already trusts
    the sharp book at the main line (`sharp_anchored`, `hit_prob`); the
    ladder now hangs the model's width on that centre and reads the
    rungs off it."""
    alts = [_ln("DK", 199.5, -240, 185), _ln("DK", 224.5, -135, 105),
            _ln("DK", 249.5, 115, -150), _ln("DK", 274.5, 230, -310)]
    raw = _row(market="pass_yds", market_label="pass_yds", line=234.5,
               projection=250.0, hit_prob=0.50, raw_prob=0.66, fair_prob=0.50,
               recent_values=[230, 260, 245, 210], alt_lines=alts,
               alt_sharp_lines=[], sharp_anchored=False)
    raw["proj_std"] = 45.0
    # Not anchored: the model's own centre, and no rung survives its bars.
    assert K._best_rung(raw, "pass_yds", fits=FITS) is None
    assert K.from_prop(raw, _always, fits=FITS) is None
    # Anchored: the same width on the market's centre prices a rung.
    row = dict(raw, sharp_anchored=True)
    assert abs(K._anchored_mean(row, 45.0) - 234.5) < 1e-9
    rung = K._best_rung(row, "pass_yds", fits=FITS)
    assert rung is not None and rung["source"] == "anchored", rung
    # Highest probability wins: under 249.5 at −150 reads 0.63 on the
    # anchored curve (P(N(234.5, 45) < 249.5)) against a 0.56 fair, ahead
    # of over 224.5 at 0.59. Both cleared every bar; neither did before.
    assert rung["line"] == 249.5 and rung["side"] == "under", rung
    assert 0.62 < rung["prob"] < 0.64, rung
    got = K.from_prop(row, _always, fits=FITS)
    assert got is not None and got["line"] == 249.5 and got["prob_source"] == "anchored"
    # The build's raw-claim bar judges the main line's raw number (0.66
    # against 0.50) and would refuse this row; a rung carrying the
    # market's own claim passes it, the way a market-ranked card does.
    assert K.admissible(got) == "", K.admissible(got)
    assert K.admissible(dict(got, prob_source="model")) != ""
    # The anchor reads the main line's own side: an UNDER row at 0.60
    # puts the centre below the line.
    under = dict(row, side="under", hit_prob=0.60)
    assert K._anchored_mean(under, 45.0) < 234.5
    # No anchor without a width, and none for a row the edge board did
    # not anchor.
    assert K._anchored_mean(row, 0.0) is None and K._anchored_mean(raw, 45.0) is None


def test_a_row_with_no_model_number_still_reads_a_sharp_rung():
    """A prop the model could not price (no projection this week) used
    to skip its ladder outright. A sharp book hanging the alternate
    needs no model, so the rung is read."""
    row = _row(market="pass_yds", market_label="pass_yds", line=234.5,
               projection=None, hit_prob=None, raw_prob=None,
               recent_values=[], alt_lines=[_ln("DK", 199.5, -240, 185)],
               alt_sharp_lines=[_ln("Pinnacle", 199.5, -225, 190)])
    row["proj_std"] = 0
    got = K.from_prop(row, _always, fits=FITS)
    assert got is not None and got["line"] == 199.5 and got["prob_source"] == "sharp", got
    assert got["raw_prob"] is None


def test_the_funnel_counts_the_ladder_and_where_its_rungs_went():
    """"One passing-yards prop" could not be told apart from "no ladder
    was bought" on the page. The per-market funnel now says how many rows
    carried a ladder and what became of the rungs."""
    kinds: dict = {}
    bullish = _row(market="pass_yds", market_label="pass_yds", line=234.5,
                   projection=250.0, hit_prob=0.50, raw_prob=0.66, fair_prob=0.50,
                   recent_values=[230, 260, 245, 210],
                   alt_lines=[_ln("DK", 199.5, -240, 185), _ln("DK", 174.5, -400, 290)],
                   alt_sharp_lines=[], sharp_anchored=False)
    bullish["proj_std"] = 45.0
    bare = _row(player="B Back", alt_lines=[], alt_sharp_lines=[])
    K.build([bullish, bare], sport="nfl", fits=FITS, census_by_kind=kinds)
    mf = kinds["prop"]["markets"]
    assert mf["pass_yds"]["laddered"] == 1 and mf["rush_yds"]["laddered"] == 0
    lad = mf["pass_yds"]["ladder"]
    assert lad.get("heavier than the cap") == 1, lad          # the −400 rung
    assert lad.get("disagrees with the rung’s own price") == 1, lad   # over 199.5
    assert not lad.get("priced")
    assert mf["pass_yds"]["shown"] == 0
    # The same row anchored: its rung prices, and the ledger says so.
    kinds2: dict = {}
    anchored = dict(bullish, sharp_anchored=True,
                    alt_lines=bullish["alt_lines"] + [_ln("DK", 249.5, 115, -150)])
    K.build([anchored], sport="nfl", fits=FITS, census_by_kind=kinds2)
    lad2 = kinds2["prop"]["markets"]["pass_yds"]["ladder"]
    assert lad2.get("priced") == 1 and kinds2["prop"]["markets"]["pass_yds"]["shown"] == 1, lad2


def test_a_rung_the_maker_priced_itself_is_read_before_any_fit():
    """Baseball rows carry `rung_probs` — P(over) at each rung from the
    curve that priced the main line (engine/mlb/betting.rung_probs).
    Ethan, 2026-09-15: "MLB most likely bets are only showing hits and
    total bases. There is no ... pitchers props." A strikeout main line
    sits at the median; the rung under it is where a likely number is
    for sale, and no football mixture or normal knows the shape of a
    count of five."""
    row = _row(market="strikeouts", market_label="strikeouts", line=5.5,
               projection=5.6, hit_prob=0.51, raw_prob=0.52,
               recent_values=[7, 4, 6, 5, 8, 3, 6],
               alt_lines=[_ln("DraftKings", 3.5, -210, 165), _ln("FanDuel", 4.5, -140, 115)],
               alt_sharp_lines=[], rung_probs={"3.5": 0.71, "4.5": 0.60})
    rung = K._best_rung(row, "strikeouts", fits=None)
    assert rung is not None, "the pre-priced ladder was not read"
    assert rung["line"] == 3.5 and rung["side"] == "over", rung
    assert rung["source"] == "model" and abs(rung["prob"] - 0.71) < 1e-9, rung
    # The pricer's number, not a fit's: with the pre-priced entry gone
    # and no mixture, no spread and no sharp rung, nothing is invented.
    row["rung_probs"] = {}
    assert K._best_rung(row, "strikeouts", fits=None) is None
    # And the whole maker takes the rung on a main line under the floor.
    row["rung_probs"] = {"3.5": 0.71, "4.5": 0.60}
    got = K.from_prop(row, _always, fits=None, sport="mlb") if K.rankable("strikeouts", "mlb") else None
    if got is not None:
        assert got["line"] == 3.5 and got["prob_source"] == "model"


# ── the derivation and the choice are separate ──────────────────────

def test_the_choice_is_the_head_of_the_derivation():
    """`rungs` is EVERY priced number on the ladder that clears the floor
    and its own credibility bar; `_best_rung` is one VIEW of it — the
    likeliest, which is the Most Likely board's question.

    THEY EXIST APART because the Pick of the Day asks a different
    question of the same ladder: what clears an EV floor at a price
    inside an even-money band. That is not the likeliest rung, and a
    second walk of the ladder to find it would be a second set of
    probabilities to keep honest."""
    row = _row()
    got = K.rungs(row, "rush_yds", fits=FITS)
    assert got, "the fixture's ladder priced nothing"
    best = K._best_rung(row, "rush_yds", fits=FITS)
    assert best == max(got, key=lambda c: c["prob"]), (best, got)


def test_the_derivation_comes_back_likeliest_first():
    """A caller with its own bars walks it in a sensible order, and the
    caller that wants one can take the head.

    THE LADDER IS HANDED IN BACKWARDS ON PURPOSE. The default fixture
    lists its rungs low-number-first, which is already descending by
    probability — so the sort was a no-op on it and deleting the sort
    passed. A test that only holds when the input happens to arrive in
    the right order is not testing the sort."""
    backwards = _row(alt_lines=[_ln("DraftKings", 75.5, 150),
                                _ln("FanDuel", 50.5, -155),
                                _ln("DraftKings", 50.5, -160),
                                _ln("FanDuel", 40.5, -230),
                                _ln("DraftKings", 40.5, -240)])
    got = K.rungs(backwards, "rush_yds", fits=FITS)
    assert len(got) > 1, "one rung cannot show an ordering"
    assert got == sorted(got, key=lambda c: -c["prob"]), got
    # And the head really is the likeliest, which is what `_best_rung`
    # hands the Most Likely board.
    assert got[0] == K._best_rung(backwards, "rush_yds", fits=FITS)


def test_a_ladder_with_nothing_on_it_is_an_empty_list_not_None():
    """The two readers want different empties: `_best_rung` answers None,
    `rungs` answers []. A None here would make every caller guard."""
    assert K.rungs(_row(alt_lines=[]), "rush_yds", fits=FITS) == []
    assert K._best_rung(_row(alt_lines=[]), "rush_yds", fits=FITS) is None


def test_every_rung_carries_what_a_second_reader_needs():
    """A caller with its own bars needs the price, the number, the side,
    the book, the probability AT that rung and the rung's own de-vigged
    fair. Anything it has to recompute is a derivation in two places."""
    got = K.rungs(_row(), "rush_yds", fits=FITS)
    assert got, "the fixture's ladder priced nothing"
    for c in got:
        assert set(c) >= {"line", "side", "book", "odds", "prob", "fair",
                          "source"}, c
        assert 0.0 < c["prob"] < 1.0, c
        assert isinstance(c["odds"], int), c


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
