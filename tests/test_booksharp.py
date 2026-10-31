"""Which books are actually sharp — measured, not asserted.

NFL_MODEL §4's sharp-book hierarchy is a hand-written LIST today:
`oddsapi.SHARP_BOOKS`, everything in it equal, everything outside it
worth nothing. Which book is sharp is the most repeated claim in this
industry and the least often checked, and we do not have to trust it —
every snapshot the movement engine writes records what each book said and
when, and the closing consensus is the nearest thing to truth available.

Run directly: `python3 tests/test_booksharp.py`
"""

import inspect
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import booksharp as bs                            # noqa: E402
from engine import linemoves                                  # noqa: E402


def _snap(ts, prices, player="P", market="rec_yds", side="over", line=24.5,
          start=None):
    """One snapshot as the journal writes it (`linemoves.record_snapshots`):
    a row per book, every row at the snapshot's one time."""
    field = "under_odds" if side == "under" else "over_odds"
    rows = []
    for b, o in prices.items():
        row = {"ts": ts, "player": player, "market": market, "book": b,
               "line": line, field: o}
        if start is not None:
            row["start_ts"] = start
        rows.append(row)
    return rows


def _series(n, sharp_odds, slow_odds, close):
    """n series where `sharp` sits at the close early and `slow` does not."""
    rows = []
    for i in range(n):
        p = f"P{i}"
        rows += (_snap(1000, {"sharp": sharp_odds, "slow": slow_odds}, player=p)
                 + _snap(1100, {"sharp": sharp_odds, "slow": slow_odds}, player=p)
                 + _snap(2000, {"sharp": close, "slow": close}, player=p))
    return rows


def test_the_book_that_sat_at_the_close_early_scores_better():
    """The whole measurement in one case: -110 all along against a -110
    close is perfect foresight; -150 all along is 15 points of error."""
    m = bs.measure(_series(12, -110, -150, -110))
    assert m["sharp"]["mae_pts"] < m["slow"]["mae_pts"]
    assert m["sharp"]["mae_pts"] == 0.0
    assert m["sharp"]["weight"] > m["slow"]["weight"]


def test_a_book_below_the_series_floor_is_not_ranked():
    """Three props quoted once is not a hierarchy. `weight` is None rather
    than a small number, because a small number still sorts."""
    m = bs.measure(_series(3, -110, -150, -110))
    assert m["sharp"]["weight"] is None
    assert m["sharp"]["mae_pts"] == 0.0        # still MEASURED, just unranked


def test_accuracy_ranks_and_lead_only_reports():
    """A twitchy book moves first every time by reacting to noise and
    reverting. Ranking on lead would put it top; ranking is on accuracy."""
    rows = []
    for i in range(12):
        p = f"P{i}"
        # `twitchy` moves first and moves WRONG; `steady` never moves
        # and is already at the close.
        rows += (_snap(1000, {"twitchy": -110, "steady": -120}, player=p)
                 + _snap(1050, {"twitchy": -200, "steady": -120}, player=p)
                 + _snap(2000, {"twitchy": -120, "steady": -120}, player=p))
    m = bs.measure(rows)
    assert m["twitchy"]["lead_rate"] == 1.0, m["twitchy"]
    assert m["steady"]["mae_pts"] < m["twitchy"]["mae_pts"]
    assert m["steady"]["weight"] > m["twitchy"]["weight"]


def test_an_impossible_price_is_not_a_price():
    """`-5` is not a 95% favourite, it is a corrupt row. Prices inside
    ±100 do not exist in American odds and must not reach the error."""
    assert bs._implied(-5) is None
    assert bs._implied(0) is None
    assert bs._implied(None) is None
    assert bs._implied(-110) is not None


def test_one_book_cannot_define_the_truth_it_is_graded_against():
    """The close is the MEDIAN across books in the last snapshot. With a
    single book quoting, it would grade itself as perfect every time."""
    rows = _series(12, -110, -150, -110)
    m = bs.measure(rows)
    # `slow` is 15 points off a close it half-owns; if the close were its
    # own price this would be 0.
    assert m["slow"]["mae_pts"] > 5


def test_the_comparison_names_a_book_we_call_sharp_that_is_not():
    """The finding that would actually change something."""
    m = bs.measure(_series(12, -110, -150, -110))
    # Name the WORSE book as sharp and the comparison should catch it.
    m2 = dict(m)
    c = bs.compare_to_the_list(m2)
    assert c["n_ranked"] == 2
    assert c["measured_sharpest"][0] == "sharp"


def test_the_report_says_so_when_there_is_no_history():
    """An empty measurement must not render as a table of nothing."""
    out = bs.report([])
    assert "No snapshot history yet" in out


def test_the_journals_own_rows_are_measured():
    """THE CARD THAT NEVER RANKED A BOOK (the 2026-10-30 audit). It read a
    "books" map and an "odds" price that no writer has ever produced, so
    every row the journal holds read as no price, `measure` came back empty
    and the chores never wrote bookreport.json. These rows come from the
    journal's own writer, so the reader cannot drift from it again."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "line_history.jsonl"
        for ts, sharp, slow in ((1000, -110, -150), (1100, -110, -150),
                                (2000, -110, -110)):
            props = [NS(player=f"P{i}", market="points", lines=[
                NS(book="sharp", line=24.5, over_odds=sharp, under_odds=-110),
                NS(book="slow", line=24.5, over_odds=slow, under_odds=-110),
                NS(book="proxy", line=24.5, over_odds=-110, under_odds=-110)])
                for i in range(12)]
            linemoves.record_snapshots(props, ts=ts, path=path)
        m = bs.measure(linemoves.stream_history(path))
        doc = bs.payload(linemoves.stream_history(path))
    assert m["sharp"]["weight"] > m["slow"]["weight"], m
    assert m["sharp"]["mae_pts"] == 0.0 and m["slow"]["mae_pts"] > 3, m
    assert m["sharp"]["series"] == 24, "both sides of twelve props"
    assert "proxy" not in m, "a proxy line is not a book"
    assert [b["book"] for b in doc["books"] if b["ranked"]] == ["sharp", "slow"]


def test_a_price_after_the_start_is_not_the_close():
    """The journal keeps pulling once a game is under way, and those prices
    are in play. A close taken from them grades every book against a live
    number — here, one where the game has turned."""
    rows = []
    for ts, a, b in ((1000, -110, -150), (2000, -110, -110), (3000, 300, 300)):
        for i in range(12):
            rows += _snap(ts, {"a": a, "b": b}, player=f"P{i}", start=2500)
    m = bs.measure(rows)
    assert m["a"]["mae_pts"] == 0.0, "the close is the last price BEFORE the start"
    assert m["b"]["mae_pts"] > 5


def test_another_line_is_another_market():
    """A price at 24.5 says nothing about one at 25.5; comparing them would
    score a book for posting a different number rather than a worse one.
    And a line only one book still quotes has no close to grade it by."""
    rows = []
    for ts in (1000, 1100, 2000):
        for i in range(12):
            rows += _snap(ts, {"a": -110, "b": -110}, player=f"P{i}", line=24.5)
            rows += _snap(ts, {"c": -150}, player=f"P{i}", line=25.5)
    m = bs.measure(rows)
    assert m["a"]["mae_pts"] == 0.0 and m["b"]["mae_pts"] == 0.0
    assert "c" not in m


def test_the_same_line_next_week_is_another_series():
    """Same player, market and line, two games: one series would grade the
    first game's prices against the second game's close."""
    rows = []
    for start, close in ((5000, -110), (90000, -200)):
        for ts, b in ((start - 4000, -150), (start - 3900, -150), (start - 3000, close)):
            rows += _snap(ts, {"a": close, "b": b}, player="P", start=start)
    m = bs.measure(rows)
    assert m["a"]["series"] == 2
    assert m["a"]["mae_pts"] == 0.0, "each game graded by its own close"


def test_a_fight_is_read_once():
    """record_fight_snapshots writes each fighter with the opponent's price
    as the under, so reading both sides would count every price twice."""
    fights = [{"a": "Fighter A", "b": "Fighter B", "commence": None,
               "books": {"x": (-150, 130), "y": (-140, 120)}}]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "line_history.jsonl"
        for ts in (1000, 2000):
            linemoves.record_fight_snapshots(fights, ts=ts, path=path)
        series = list(bs._closed_series(linemoves.stream_history(path)))
    assert len(series) == 2, "one series per fighter, not four"


def test_memory_holds_only_the_games_not_yet_played():
    """The journal is read once, in time order, and a game's series is
    handed over as soon as the stream passes its start — not held to the
    end, which is every price in the window at once."""
    seen = []

    def rows():
        for ts in (1000, 1100, 2000):
            yield from _snap(ts, {"a": -110, "b": -120}, player="early", start=2500)
        seen.append("past the first start")
        for ts in (3000, 4000):
            yield from _snap(ts, {"a": -110, "b": -120}, player="late", start=9000)
        seen.append("the end")

    it = bs._closed_series(rows())
    first = next(it)
    assert seen == ["past the first start"], seen
    assert [ts for ts, _ in first] == [1000, 1100, 2000]
    assert first[-1][1] == {"a": -110, "b": -120}, "one snapshot, both books"


def test_the_card_is_four_weeks_read_from_just_before_them():
    """The chores read the window (plus the week a line can be open before
    its game), never the whole journal; a series that closed before the
    window is read and not scored."""
    src = inspect.getsource(bs.payload)
    assert "stream_since(" in src and "load_history()" not in src
    asked = []
    real = linemoves.stream_since
    linemoves.stream_since = lambda ts, path=None: asked.append(ts) or iter(())
    try:
        doc = bs.payload(now=10_000_000.0)
    finally:
        linemoves.stream_since = real
    assert asked == [10_000_000.0 - (bs.WINDOW_DAYS + bs.RUN_IN_DAYS) * 86400]
    assert doc["window_days"] == bs.WINDOW_DAYS == 28
    rows = []
    for start in (5000, 900000):
        for ts in (start - 4000, start - 3000):
            rows += _snap(ts, {"a": -110, "b": -110}, player="P", start=start)
    assert bs.measure(rows, since=500000)["a"]["series"] == 1


def test_nothing_here_prices_anything():
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "booksharp.py"), encoding="utf-8").read()
    assert "hit_prob" not in src and "stake" not in src
    assert "THE_INFORMATION_TEST" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
