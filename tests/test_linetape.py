"""CLV stops being a number and becomes a line you can look at.

Ethan, 2026-08-20: "Applying the same tape to sportsbook lines — open →
now, with our pick's entry marked — turns CLV from a number on a page
into something you can see. The data is already collected."

It is. `lineledger.record()` runs inside both live builds and writes one
row per distinct MINUTE a number was observed — props, moneylines,
spreads and totals through one table shape, at no API cost, because the
prices were already in memory. Nothing had ever read it back.

WHY CLV DESERVES THE PICTURE. It is the only evidence about the PROCESS
that arrives before the results do, which makes it the most load-bearing
number on the site — and as "+0.34 pts" it is inert.

PLOTTED IN PAYOUT SPACE, NOT AMERICAN POINTS, and that is the one design
decision worth defending. American odds are neither linear nor continuous
at the origin: -110 → +110 is a big move, +110 → +330 is bigger, and
-101 → +101 is almost nothing while the labels jump 202. Drawing the raw
numbers would put the largest visual step where the least happened.
Profit-per-unit is monotone across the boundary, so the shape means what
it looks like it means. `_better` uses the same conversion, which is why
the best-price rule does not silently prefer -101 over +101.

Verified on a controlled fixture (two books, six minutes, -110 drifting
to +105): the tape picks the better book at every minute, the summary
reports drift in payout space, and a market never seen returns an empty
series rather than a flat line.

And on a live render, five cases: drifted our way, moved against us, flat,
one point, and no tape at all — the last two draw nothing, because one
point is not a line.

Run directly: `python3 tests/test_linetape.py`
"""

import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, linetape                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
NOW = dt.datetime(2026, 8, 20, 20, 0, tzinfo=dt.timezone.utc)


def _conn(series, player="A Hitter", market="hits"):
    c = db.connect(":memory:")
    rows = []
    for i, books in enumerate(series):
        at = (NOW - dt.timedelta(minutes=len(series) - 1 - i)
              ).strftime("%Y-%m-%dT%H:%M:00Z")
        for book, odds in books.items():
            rows.append({"sport": "mlb", "taken_at": at, "event_id": "g1",
                         "home": "NYY", "away": "BOS", "player": player,
                         "market": market, "book": book, "line": 1.5,
                         "over_odds": odds, "under_odds": -odds})
    db.upsert_odds_history(c, rows)
    return c


def test_the_tape_comes_back_oldest_first():
    c = _conn([{"dk": -110}, {"dk": -105}, {"dk": 100}])
    t = linetape.line_tape(c, "mlb", "A Hitter", "hits", now=NOW)
    assert [p["over_odds"] for p in t] == [-110, -105, 100]
    assert t[0]["at"] < t[-1]["at"]


def test_it_keeps_the_price_a_bettor_could_have_taken():
    """With no book named the tape is the BEST number at each minute — the
    one the pick was priced against. Averaging venues would draw a line
    nobody could have bet."""
    c = _conn([{"dk": -110, "fd": -125}, {"dk": -108, "fd": 100}])
    t = linetape.line_tape(c, "mlb", "A Hitter", "hits", now=NOW)
    assert [p["over_odds"] for p in t] == [-110, 100]
    assert [p["book"] for p in t] == ["dk", "fd"]


def test_the_best_price_rule_survives_the_sign_boundary():
    """THE BUG THIS AVOIDS IS SILENT. A numeric comparison makes -101 beat
    +101, which is backwards, and would quietly pin the tape to the worst
    quote on the board every time a market crossed even money."""
    assert linetape._better(101, -101) is True
    assert linetape._better(-101, 101) is False
    assert linetape._better(150, 120) is True
    assert linetape._better(-110, -140) is True
    assert linetape._better(None, -110) is False
    assert linetape._better(-110, None) is True


def test_one_point_is_not_a_line():
    c = _conn([{"dk": -110}])
    rows = [{"player": "A Hitter", "market": "hits", "odds": -110}]
    assert linetape.attach_tapes(c, rows, "mlb", now=NOW) == 0
    assert "line_tape" not in rows[0], \
        "a single quote was hung on a row as if it were a series"


def test_a_market_we_never_watched_gets_nothing():
    c = _conn([{"dk": -110}, {"dk": -105}])
    assert linetape.line_tape(c, "mlb", "Nobody", "hits", now=NOW) == []
    s = linetape.move_summary([])
    assert s["drift"] is None and s["n"] == 0


def test_the_entry_is_carried_not_inferred_from_the_first_point():
    """The tape starts when RECORDING started, which is not the instant
    the bet was placed. Inferring the entry from point one would mark the
    wrong line on the chart and quietly restate our own CLV."""
    c = _conn([{"dk": -140}, {"dk": -125}, {"dk": -110}])
    rows = [{"player": "A Hitter", "market": "hits", "odds": -120, "line": 1.5}]
    assert linetape.attach_tapes(c, rows, "mlb", now=NOW) == 1
    assert rows[0]["tape_entry"]["odds"] == -120, \
        "the entry was overwritten with the first observed price"


def test_drift_is_measured_in_payout_space():
    """-110 → +110 must not read the same as +110 → +330."""
    c = _conn([{"dk": -110}, {"dk": 110}])
    a = linetape.move_summary(linetape.line_tape(c, "mlb", "A Hitter", "hits", now=NOW))
    c2 = _conn([{"dk": 110}, {"dk": 330}])
    b = linetape.move_summary(linetape.line_tape(c2, "mlb", "A Hitter", "hits", now=NOW))
    assert b["drift"] > a["drift"] > 0, (a["drift"], b["drift"])


def test_both_builds_attach_the_tape():
    for name in ("mlb_build.py", "nfl_build.py"):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert "linetape.attach_tapes" in src, f"{name} does not attach a tape"


def test_the_chart_converts_before_it_plots():
    """The front end must do the same conversion, or the picture argues
    with the number beside it."""
    assert "function oddsPayout(" in APP
    fn = APP[APP.index("function lineTapeSVG("):]
    fn = fn[:fn.index("\n}\n")]
    assert "oddsPayout(" in fn, "the SVG plots raw american odds again"


def test_the_chart_marks_our_entry():
    fn = APP[APP.index("function lineTapeSVG("):]
    fn = fn[:fn.index("\n}\n")]
    assert "stroke-dasharray" in fn, "the entry line is gone"


def test_a_window_it_cannot_compute_is_omitted_rather_than_printed():
    """Caught by a malformed fixture in review: an unparseable stamp made
    the caption read "last NaNm · 6 quotes" to a reader, which is worse
    than saying nothing about the window."""
    fn = APP[APP.index("function lineTapeHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "isFinite(t0) && isFinite(t1)" in fn, "the NaN guard is gone"
    assert 'win ? `last ${win}' in fn, \
        "an empty window is printed instead of being dropped"


def test_the_reading_is_a_comparison_not_an_opinion():
    flat = " ".join(APP.split())
    for phrase in ("The price drifted our way", "The price moved against us",
                   "The number has not moved since we took it"):
        assert phrase in flat, f"lost the derived reading: {phrase}"


def test_gaps_are_never_bridged_silently():
    """The build runs on a timer and the odds budget paces the paid pulls,
    so a flat stretch is a stretch nobody sampled."""
    flat = " ".join(APP.split())
    assert "never an interpolation" in flat, \
        "the caption no longer tells the reader the gaps are real"


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
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
