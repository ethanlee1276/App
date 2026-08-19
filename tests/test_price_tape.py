"""Clicking a recommendation shows how its price has moved.

Ethan, 2026-08-19, with a Polymarket screenshot: "add where we can click
on the trade it's recommending and it will pull up a chart of the live
odds just how Kalshi or Polymarket does it."

Both venues' adapters have written a 10-minute price snapshot on every
refresh since they shipped — `kalshi_snapshots` and `pm_snaps`. Nothing
had ever read them back. This is that read-back, the payload that carries
it, and the rules that keep the chart honest.

THE HONESTY PROBLEM IS SPECIFIC AND WORTH NAMING. Polymarket can draw a
market's whole life because it IS the market. We can only draw what we
watched. So:

  * no interpolation and no backfill — an order book cannot be
    reconstructed, and a smooth line through hours nobody recorded is a
    picture of a market that did not exist;
  * a gap in the record draws as a gap (`connectNulls: false`);
  * fewer than two observed buckets gets NO chart, because one point is
    not a line and a single dot invites "it has been flat";
  * and the caption says the window is ours, so nobody reads the left
    edge as the market's open.

Run directly: `python3 tests/test_price_tape.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import pm_build                                                 # noqa: E402
from engine import predmarket as pm                             # noqa: E402
from engine.db import connect                                   # noqa: E402
from engine.sources import kalshi as kx                         # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
VIS = open(os.path.join(ROOT, "web", "js", "visuals.js"), encoding="utf-8").read()


# --- the read-backs ----------------------------------------------------------
def _kalshi_conn(prices, start=1000.0, step=700.0):
    conn = connect(":memory:")
    for i, p in enumerate(prices):
        kx.store_snapshot(conn, [{"ticker": "T1", "prob": p, "spread_cents": 4,
                                  "volume_24h": 100, "open_interest": 9,
                                  "title": "x"}], now=start + i * step)
    return conn


def test_the_kalshi_tape_comes_back_oldest_first():
    conn = _kalshi_conn([0.50, 0.53, 0.58])
    got = kx.price_series(conn, "T1", hours=24, now=3200.0)
    assert [round(p["prob"], 2) for p in got] == [0.50, 0.53, 0.58]
    assert got == sorted(got, key=lambda p: p["ts"]), "not chronological"


def test_the_window_is_a_window():
    conn = _kalshi_conn([0.50, 0.53, 0.58])
    assert kx.price_series(conn, "T1", hours=24, now=10 ** 9) == [], \
        "an ancient snapshot answered a question about today"


def test_a_market_we_never_watched_has_no_history_rather_than_a_flat_line():
    conn = _kalshi_conn([0.5])
    assert kx.price_series(conn, "NEVER-SEEN", hours=24, now=3200.0) == []


def test_the_polymarket_tape_reads_back_the_same_way():
    conn = connect(":memory:")
    for i, y in enumerate([0.41, 0.44, 0.39]):
        pm.store_snapshot(conn, [{"slug": "s1", "question": "q", "yes": y,
                                  "vol24": 10, "liquidity": 5,
                                  "end_date": "2026-09-01"}],
                          now=1000.0 + i * 700)
    got = pm.price_series(conn, "s1", hours=24, now=3200.0)
    assert [round(p["prob"], 2) for p in got] == [0.41, 0.44, 0.39]


# --- what the build hangs on a row ------------------------------------------
def test_a_row_gets_its_tape_and_an_unwatched_row_does_not():
    conn = _kalshi_conn([0.50, 0.53, 0.58, 0.55])
    rows = [{"ticker": "T1"}, {"ticker": "T2"}]
    assert pm_build._attach_tape(conn, rows, kx.price_series, "ticker",
                                 now=3900.0) == 1
    assert len(rows[0]["tape"]) == 4
    assert rows[0]["tape"][0][0] < rows[0]["tape"][-1][0]
    assert "tape" not in rows[1]


def test_one_observation_is_not_a_line():
    """The rule that keeps a brand-new market from claiming a history. A
    chart drawn through a single dot reads as "it has been flat here",
    which is precisely what one observation cannot tell you."""
    conn = _kalshi_conn([0.62])
    rows = [{"ticker": "T1"}]
    assert pm_build._attach_tape(conn, rows, kx.price_series, "ticker",
                                 now=1500.0) == 0
    assert "tape" not in rows[0]


# --- the board row carries it through ---------------------------------------
def test_the_board_projection_does_not_drop_the_tape():
    """`pmVenueRows` rebuilds every payload row into a board row, and
    anything the projection forgets does not exist downstream. It forgot
    the tape in the first cut, which drew no chart and threw no error."""
    fn = APP[APP.index("function pmVenueRows("):]
    fn = fn[:fn.index("\nconst PM_BOARD_SHOWN")]
    assert fn.count("tape:") >= 2, \
        "a venue's rows lost the price history on the way to the panel"


def test_the_recommendation_itself_is_clickable():
    """The desk's rows ARE "the trade it's recommending", and they were
    the one row shape on the page with no way in."""
    desk = APP[APP.index("function deskSectionHTML("):]
    desk = desk[:desk.index("\nfunction ", 10)]
    assert "_pmPick" in desk, "the recommendation rows open nothing"
    assert "r.ticker ?" in desk, \
        "a weather row with no ticker must not open an empty panel"
    # And the board's own rows, not just their View button.
    row = APP[APP.index("function pmBoardRowHTML("):]
    row = row[:row.index("\nfunction ", 10)]
    assert "kx-row openable" in row and "_pmPick" in row


# --- the honesty rules, in the code that draws ------------------------------
def test_a_gap_in_the_record_draws_as_a_gap():
    tape = VIS[VIS.index('} else if (kind === "tape") {'):]
    tape = tape[:tape.index('} else if (kind === "radar")')]
    assert "connectNulls: false" in tape, \
        "a break in our recording would be drawn as a straight line through it"
    assert "smooth: false" in tape, \
        "a smoothed curve invents prices between the ones we saw"


def test_both_sides_are_drawn_and_labelled_at_the_end():
    """The render shows two lines labelled at the right edge; a binary
    market has two sides and showing one is half an answer."""
    tape = VIS[VIS.index('} else if (kind === "tape") {'):]
    tape = tape[:tape.index('} else if (kind === "radar")')]
    assert "endLabel" in tape
    # One helper, called once per side.
    assert "const line = (" in tape, "the line builder is gone"
    assert "line(yesName" in tape and "line(noName" in tape, \
        "only one side is plotted"


def test_the_caption_says_the_window_is_ours():
    fn = APP[APP.index("function pmTapeHTML("):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "our own tape" in fn
    assert "not when the\n      market opened" in fn or "market opened" in fn
    # And the no-history case says so rather than drawing nothing.
    assert "pm-tape-none" in fn and "long enough" in fn


def test_the_fallback_draws_the_real_series_not_a_placeholder():
    """ECharts is a megabyte loaded lazily. On a slow phone the SVG is
    what a reader gets, so it plots the same two real series to scale."""
    fn = APP[APP.index("function pmTapeSVG("):]
    fn = fn[:fn.index("\nfunction ", 10)]
    assert "var(--good)" in fn and "var(--bad)" in fn
    assert "1 - v" in fn, "the fallback draws only one side"


def test_the_mounts_cannot_cancel_each_other():
    """Found while wiring this up: three enhancement mounts chained bare,
    and the first to throw silently cancelled the rest — the chart never
    upgraded, nothing errored, and the SVG fallback made it look like a
    rendering choice rather than dead code."""
    i = APP.index("async function renderIntel()")
    fn = APP[i:APP.index("\n/* =====", i)]
    assert "for (const mount of" in fn and "try {" in fn, \
        "the intel mounts are chained again"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
