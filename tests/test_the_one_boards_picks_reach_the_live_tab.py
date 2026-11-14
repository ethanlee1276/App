"""The one board's picks on the Live tab's Most Likely panel, once each.

Ethan, 2026-09-28, PHI@CHI in the first quarter, with the Live tab open:
"We are definitely missing bets on the most likely live bets here." The
Most Likely page draws the one board (engine/likelyboard), which journals
every pick it posts to its own book — category `board`. The tracker read
only the two books the older Most Likely shelves journal to (`likely`,
`likely_live`), so a pick only the board posted — a matchup pick, a
touchdown scenario — was on the page before kickoff and gone after it.

The board's book now rides with the tracker everywhere it reads (the
shared tracker, the MLB build, the MLB sweat), and a wager journaled in
two books is drawn once: staked first, then the Most Likely book's paper
row, then the board's copy. Fixture journal in memory — never the box's.

Run directly: `python3 tests/test_the_one_boards_picks_reach_the_live_tab.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                                   # noqa: E402
from engine.livepicks import (BOARD_BOOK, LIVE_LIKELY_BOOKS, TRACKER_CATEGORIES,  # noqa: E402
                              attach_tracker, one_row_per_wager)

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _journal():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ledger._BETS_TABLE)
    for col in ("closing_odds INTEGER",):
        try:
            conn.execute(f"ALTER TABLE bets ADD COLUMN {col}")
        except Exception:                                              # noqa: BLE001
            pass
    return conn


def _bet(conn, player, market, line, category, side="OVER", stake=0.1):
    conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, hit_prob, "
                 "stake_units, status, category) VALUES "
                 "('2026-09-28T12:00:00Z','nfl','2026-W04',?,?,?,?,-150,0.66,?,'open',?)",
                 (player, market, side, line, stake, category))


def _board():
    return {"date": "2026-W04", "sport": "nfl",
            "games": [{"home": "CHI", "away": "PHI", "date": "2026-09-28", "kickoff": "20:15",
                       "live": {"state": "live", "home_score": 7, "away_score": 0, "period": "Q1"}}],
            "recommendations": [
                {"player": p, "team": t, "opponent": o, "market": m, "has_market": True}
                for p, t, o, m in (("Luther Burden III", "CHI", "PHI", "rec_yds"),
                                   ("DeVonta Smith", "PHI", "CHI", "rec_yds"),
                                   ("Jalen Hurts", "PHI", "CHI", "rush_yds"),
                                   ("Kyle Monangai", "CHI", "PHI", "rush_att"))]}


def test_the_board_book_is_tracked_and_counted_as_most_likely():
    assert BOARD_BOOK == "board"
    assert set(ledger.LIKELY_BOOKS) < set(LIVE_LIKELY_BOOKS)
    assert BOARD_BOOK in LIVE_LIKELY_BOOKS and BOARD_BOOK in TRACKER_CATEGORIES
    # The name the one board journals under is the name read here.
    src = (ROOT / "engine" / "likelyboard.py").read_text()
    assert 'category="board", grade_label=label' in src


def test_a_pick_only_the_board_posted_reaches_the_live_tab():
    conn = _journal()
    # On both the old shelves' book (staked) and the board's: one row.
    _bet(conn, "Luther Burden III", "rec_yds", 24.5, "likely_live", stake=0.25)
    _bet(conn, "Luther Burden III", "rec_yds", 24.5, "board")
    # Only the board posted these two — the ones that went missing.
    _bet(conn, "DeVonta Smith", "rec_yds", 74.5, "board", side="UNDER")
    _bet(conn, "Jalen Hurts", "rush_yds", 19.5, "board")
    # An edge bet stays in its own panel even on a board pick's player.
    _bet(conn, "Kyle Monangai", "rush_att", 9.5, "main", stake=0.34)
    result = _board()
    attach_tracker(result, "nfl", conn=conn, progress={})
    rows = result["live_picks"]
    likely = [(r["player"], r["category"]) for r in rows if r["category"] in LIVE_LIKELY_BOOKS]
    assert sorted(likely) == [("DeVonta Smith", "board"), ("Jalen Hurts", "board"),
                              ("Luther Burden III", "likely_live")], likely
    assert [r["player"] for r in rows if r["category"] == "main"] == ["Kyle Monangai"]
    # The masthead's edge count is untouched by the board's rows.
    assert result["open_elsewhere"] == 0


def test_one_row_per_wager_keeps_the_staked_row_and_the_first_rows_place():
    rows = [
        {"player": "A", "market": "rec_yds", "side": "OVER", "line": 24.5, "category": "board"},
        {"player": "E", "market": "rec_yds", "side": "OVER", "line": 60.5, "category": "main"},
        {"player": "a", "market": "rec_yds", "side": "over", "line": "24.5", "category": "likely"},
        {"player": "A", "market": "rec_yds", "side": "OVER", "line": 24.5, "category": "likely_live"},
        {"player": "B", "market": "receptions", "side": "UNDER", "line": 3.5, "category": "board"},
        # A different line is a different wager: both stay.
        {"player": "B", "market": "receptions", "side": "UNDER", "line": 4.5, "category": "likely"},
        # An edge bet on the same wager is another product: it stays.
        {"player": "A", "market": "rec_yds", "side": "OVER", "line": 24.5, "category": "main"},
    ]
    out = one_row_per_wager(rows)
    assert [(r["player"], r["category"], r["line"]) for r in out] == [
        ("A", "likely_live", 24.5), ("E", "main", 60.5), ("B", "board", 3.5),
        ("B", "likely", 4.5), ("A", "main", 24.5)], out
    # Paper beats the board's copy when nothing is staked.
    out = one_row_per_wager([rows[0], rows[2]])
    assert [r["category"] for r in out] == ["likely"]
    assert one_row_per_wager([]) == []


def test_every_reader_of_the_books_folds_the_same_way():
    build = (ROOT / "mlb_build.py").read_text()
    assert "one_row_per_wager as _one_row" in build and "rows = _one_row(rows)" in build
    sweat = (ROOT / "engine" / "sweat.py").read_text()
    assert "cats = TRACKER_CATEGORIES" in sweat and "rows = one_row_per_wager(rows)" in sweat
    lp = (ROOT / "engine" / "livepicks.py").read_text()
    assert "rows = one_row_per_wager(rows)\n            result[\"live_picks\"] = rows" in lp


def test_the_page_draws_board_rows_in_the_most_likely_panel_without_units():
    i = APP.index("function isLikelyBook(c) {")
    body = APP[i:APP.index("}", i)]
    assert 'c === "board"' in body, body
    assert '!["likely", "board"].includes(r.category) && r.stake_units > 0' in APP


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
