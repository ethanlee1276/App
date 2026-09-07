"""The price tape keeps the sharp book's number, not only the shopped best.

Ethan, 2026-09-07: "A price database. Timestamped quotes from every book,
Pinnacle included, from open to close, for game lines and props in both
leagues. Every edge we can measure is a comparison of prices."

Both halves of every measured edge here are prices: the sharp anchor
(+13.5% on the MLB replay) and the stale-line flag (64.8% CLV on 30,448
quotes) each compare one book against another. The build parsed the sharp
book's own two-sided pair on every pull — `apply_odds_to_slate` and
`apply_board_lines_to_slate` hang it on the game, `cfb_build._sharp_for`
puts it on the entry — priced against it, and then wrote only the shopped
best to `odds_history`. So the stored tape was one number per game per
minute with nothing to compare it against. Now the same rows are written
for the sharp book under its own name, on all three sports.

Run directly: `python3 tests/test_sharp_price_tape.py`
"""

import datetime as dt
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, lineledger as L                       # noqa: E402
from engine.sources import oddsapi                           # noqa: E402

NOW = dt.datetime(2026, 9, 12, 18, 30, 12, tzinfo=dt.timezone.utc)
STAMP = "2026-09-12T18:30:00Z"


class _Game:
    """An NFL/MLB slate game: the sharp fields default the way the real
    dataclass defaults them, so an unquoted book reads as 0, not as None."""

    def __init__(self, **kw):
        self.home, self.away, self.date = "DET", "NO", "2026-09-12"
        self.total = self.spread = None
        self.total_over_odds = self.total_under_odds = 0
        self.spread_home_odds = self.spread_away_odds = 0
        self.home_ml = self.away_ml = 0
        self.sharp_total = self.sharp_spread = 0.0
        self.sharp_total_over_odds = self.sharp_total_under_odds = 0
        self.sharp_spread_home_odds = self.sharp_spread_away_odds = 0
        self.sharp_home_ml = self.sharp_away_ml = 0
        for k, v in kw.items():
            setattr(self, k, v)


def _by_book(rows, book):
    return [{k: r[k] for k in ("player", "market", "line", "over_odds", "under_odds")}
            for r in rows if r["book"] == book]


def test_the_spelling_matches_what_the_harvest_writes():
    """A build row and a harvested row for the same book must carry one
    spelling or the two halves of the tape never join."""
    assert L.SHARP_BOOK == oddsapi.BOOK_TITLES["pinnacle"]
    assert oddsapi.SHARP_BOOKS == {"pinnacle"}, "one sharp book; this is its title"
    assert L.BEST_BOOK == "best", "the shopped aggregate the harvest also writes"
    assert L.SHARP_BOOK != L.BEST_BOOK


def test_both_books_are_written_for_every_game_market():
    g = _Game(total=47.5, total_over_odds=-110, total_under_odds=-110,
              spread=-3.5, spread_home_odds=-108, spread_away_odds=-112,
              home_ml=-175, away_ml=155,
              sharp_total=47.0, sharp_total_over_odds=-104,
              sharp_total_under_odds=-108,
              sharp_spread=-3.0, sharp_spread_home_odds=-105,
              sharp_spread_away_odds=-115,
              sharp_home_ml=-168, sharp_away_ml=148)
    rows = L.rows_for_games("nfl", [g], now=NOW)
    # The shopped rows are exactly what they always were.
    assert _by_book(rows, "best") == [
        {"player": "TOTAL", "market": "total", "line": 47.5,
         "over_odds": -110, "under_odds": -110},
        {"player": "DET", "market": "spread", "line": -3.5,
         "over_odds": -108, "under_odds": -112},
        {"player": "DET", "market": "moneyline", "line": 0.0,
         "over_odds": -175, "under_odds": None},
        {"player": "NO", "market": "moneyline", "line": 0.0,
         "over_odds": 155, "under_odds": None},
    ]
    # …and the sharp book's own pair rides beside them, same shape.
    assert _by_book(rows, L.SHARP_BOOK) == [
        {"player": "TOTAL", "market": "total", "line": 47.0,
         "over_odds": -104, "under_odds": -108},
        {"player": "DET", "market": "spread", "line": -3.0,
         "over_odds": -105, "under_odds": -115},
        {"player": "DET", "market": "moneyline", "line": 0.0,
         "over_odds": -168, "under_odds": None},
        {"player": "NO", "market": "moneyline", "line": 0.0,
         "over_odds": 148, "under_odds": None},
    ]
    # One event, one minute, both books — which is what makes the two
    # series comparable at all.
    assert {r["event_id"] for r in rows} == {"2026-09-12-NO@DET"}
    assert {r["taken_at"] for r in rows} == {STAMP}


def test_a_game_the_sharp_book_never_quoted_writes_only_the_best():
    rows = L.rows_for_games("nfl", [_Game(total=47.5, total_over_odds=-110,
                                          total_under_odds=-110)], now=NOW)
    assert [r["book"] for r in rows] == ["best"]


def test_a_one_sided_sharp_quote_is_not_a_number_this_table_carries():
    """The price is the evidence the book posted it — the `total_is_posted`
    rule. The sharp LINE cannot say: it defaults to 0.0 and a real pick'em
    spread is also 0.0."""
    half = _Game(sharp_total=47.0, sharp_total_over_odds=-104,
                 sharp_spread=-3.0, sharp_spread_home_odds=-105,
                 sharp_home_ml=-168)
    assert L.rows_for_games("nfl", [half], now=NOW) == []
    # A sharp pick'em IS stored — 0.0 is a line, and the pair proves it.
    pk = _Game(sharp_spread=0.0, sharp_spread_home_odds=-110,
               sharp_spread_away_odds=-110)
    assert _by_book(L.rows_for_games("nfl", [pk], now=NOW), L.SHARP_BOOK) == [
        {"player": "DET", "market": "spread", "line": 0.0,
         "over_odds": -110, "under_odds": -110}]


def test_the_two_books_survive_the_round_trip_as_separate_rows():
    """`odds_history` is keyed by book, so the sharp row cannot overwrite
    the shopped one — the reason the tape can be read back as two series."""
    g = _Game(total=47.5, total_over_odds=-110, total_under_odds=-110,
              sharp_total=47.0, sharp_total_over_odds=-104,
              sharp_total_under_odds=-108)
    conn = db.connect(":memory:")
    assert L.record(conn, "nfl", [g], now=NOW) == 2
    got = sorted(tuple(r) for r in conn.execute(
        "SELECT book, line, over_odds FROM odds_history "
        "WHERE sport='nfl' AND market='total'"))
    assert got == [("Pinnacle", 47.0, -104), ("best", 47.5, -110)], got


def test_college_hands_over_the_pair_its_own_pull_parsed():
    """CFB's board is dicts, not dataclasses — one accessor reads both."""
    row = {"home": "TOL", "away": "BGSU", "date": "2026-09-12",
           "total": 50.5, "total_over_odds": -110, "total_under_odds": -110,
           "sharp_total": 51.0, "sharp_total_over_odds": -108,
           "sharp_total_under_odds": -112,
           "sharp_home_ml": -140, "sharp_away_ml": 120}
    rows = L.rows_for_games("cfb", [row], now=NOW)
    assert _by_book(rows, L.SHARP_BOOK) == [
        {"player": "TOTAL", "market": "total", "line": 51.0,
         "over_odds": -108, "under_odds": -112},
        {"player": "TOL", "market": "moneyline", "line": 0.0,
         "over_odds": -140, "under_odds": None},
        {"player": "BGSU", "market": "moneyline", "line": 0.0,
         "over_odds": 120, "under_odds": None},
    ]
    # And the build fills those keys from the entry `_sharp_for` already
    # writes, rather than parsing the payload a second time.
    import cfb_build
    src = inspect.getsource(cfb_build.main)
    i = src.index('_rows = []')
    block = src[i:i + 1600]
    assert 'sh = e.get("sharp") or {}' in block, block[:400]
    for key in ("sharp_spread", "sharp_total", "sharp_home_ml"):
        assert f'row["{key}"]' in block, key
    assert 'lineledger.record(_lc, "cfb", _rows)' in src


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
