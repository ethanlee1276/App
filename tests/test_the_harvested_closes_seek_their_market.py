"""The harvested closes seek their market instead of walking every row the
league stored (engine/gamebacktest.harvest_rows, behind game_line_closes and
moneyline_closes: the game-line calibration, the game ranks and the Pick of
the Day's replay read them).

Found 13 November 2026, on the first learning pass with the calibration's
timers (runbook OJ, OS): 244.7 of its 250.3 seconds were these two reads.
They ask for one market of one book in time order, and SQLite, on the box's
never-ANALYZEd file, answered by walking the table's key (sport, taken_at,
...): every prop at every book at every snapshot, to keep the game lines.
What these hold:

  * the read names the (sport, market, player, taken_at) index;
  * every close is the same, in the same order, as the old walk's, with the
    awkward rows in it: two listings of one game at one time, a key with a
    missing event id written twice, missing prices, other books' prices,
    a later day's snapshot;
  * it reads a small part of what the walk read (counted in SQLite's own
    steps, not seconds);
  * a file without the index is read the old way.

Run directly: `python3 tests/test_the_harvested_closes_seek_their_market.py`
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db as D                                         # noqa: E402
from engine import gamebacktest as GB                              # noqa: E402

#: The old reads, held to the plan the box's file gave them: the table's key
#: walked on the league alone, in its own order.
OLD_LINES = ("SELECT taken_at, home, away, line, over_odds, under_odds FROM odds_history "
             "INDEXED BY sqlite_autoindex_odds_history_1 "
             "WHERE sport=? AND market=? AND book=? ORDER BY taken_at")
OLD_ML = ("SELECT taken_at, home, away, player, over_odds FROM odds_history "
          "INDEXED BY sqlite_autoindex_odds_history_1 "
          "WHERE sport=? AND market='moneyline' AND book=? ORDER BY taken_at")
BOOKS = ("fanduel", "draftkings", "pinnacle")


def _old_lines(conn, sport, market, book="best"):
    out = {}
    for r in conn.execute(OLD_LINES, (sport, market, book)):
        if r["line"] is None or r["over_odds"] is None or r["under_odds"] is None:
            continue
        out[(str(r["taken_at"])[:10], r["home"], r["away"])] = (
            float(r["line"]), int(r["over_odds"]), int(r["under_odds"]))
    return out


def _old_ml(conn, sport, book="best"):
    out = {}
    for r in conn.execute(OLD_ML, (sport, book)):
        out.setdefault((str(r["taken_at"])[:10], r["home"], r["away"]), {})[r["player"]] = r["over_odds"]
    return out


def _rows():
    rows = []
    teams = [("H%d" % i, "A%d" % i) for i in range(4)]
    for day in (1, 2, 3):
        for snap in range(4):
            at = "2026-10-%02dT%02d:00:00Z" % (day, 12 + snap)
            for gi, (h, a) in enumerate(teams):
                ev = "e%d_%d" % (day, gi)
                for p in range(10):                      # the props that swamp the walk
                    for m in ("pass_yds", "rec_yds", "receptions"):
                        for b in BOOKS:
                            rows.append(("nfl", at, ev, h, a, "P%d%s" % (p, h), m, b, 40.5 + p, -110, -110))
                line = 44.5 + snap - gi
                rows.append(("nfl", at, ev, h, a, "TOTAL", "total", "best",
                             None if (day, snap, gi) == (2, 3, 1) else line, -110, -105))
                rows.append(("nfl", at, ev, h, a, h, "spread", "best", -3.5 + snap, -108, -112))
                rows.append(("nfl", at, ev, h, a, h, "moneyline", "best", 0.0, -150 + snap, None))
                rows.append(("nfl", at, ev, h, a, a, "moneyline", "best", 0.0, 130 - snap, None))
                for b in BOOKS:
                    rows.append(("nfl", at, ev, h, a, h, "moneyline", b, 0.0, -155 + snap, None))
                    rows.append(("nfl", at, ev, h, a, a, "moneyline", b, 0.0, 135 - snap, None))
            # The first game listed twice at one time: the walk's key order
            # (event, then player) decides which listing is the close.
            h, a = teams[0]
            rows.append(("nfl", at, "e%d_0x" % day, h, a, "TOTAL", "total", "best", 51.5, -120, 100))
            rows.append(("nfl", at, "e%d_0x" % day, h, a, a, "moneyline", "best", 0.0, 140, None))
            # A game whose key has no event id, written twice a snapshot (a
            # missing part never collides, so both rows stay): the row's id
            # breaks the tie.
            rows.append(("nfl", at, None, "K", "L", "TOTAL", "total", "best", 39.5, -115, -105))
            rows.append(("nfl", at, None, "K", "L", "TOTAL", "total", "best", 38.5, -125, 105))
            rows.append(("nfl", at, None, "K", "L", "K", "moneyline", "best", 0.0, -170, None))
            rows.append(("nfl", at, None, "K", "L", "K", "moneyline", "best", 0.0, -175, None))
    # Another league's rows, which neither read may touch.
    rows.append(("cfb", "2026-10-01T12:00:00Z", "c1", "X", "Y", "TOTAL", "total", "best", 60.5, -110, -110))
    return rows


def _fill(conn):
    conn.executemany("INSERT OR REPLACE INTO odds_history (sport, taken_at, event_id, home, away, player, "
                     "market, book, line, over_odds, under_odds) VALUES (?,?,?,?,?,?,?,?,?,?,?)", _rows())
    conn.commit()


def _history():
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    _fill(conn)
    return conn


def _ml_items(d):
    return [(k, list(v.items())) for k, v in d.items()]


def test_the_read_names_the_market_index():
    conn = _history()
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN " + GB.HARVEST_SEEK.format(cols="taken_at, home, away, line"),
        ("nfl", "total", "best")))
    assert "idx_odds_hist_lookup" in plan and "market=?" in plan, plan
    assert "sqlite_autoindex_odds_history_1" not in plan, plan


def test_every_close_is_the_same_and_in_the_same_order():
    conn = _history()
    for market in ("total", "spread"):
        old, new = _old_lines(conn, "nfl", market), GB.game_line_closes(conn, "nfl", market)
        assert old and list(new.items()) == list(old.items()), market
    for book in ("best",) + BOOKS:
        old, new = _old_ml(conn, "nfl", book), GB.moneyline_closes(conn, "nfl", book)
        assert old and _ml_items(new) == _ml_items(old), book
    # The awkward rows did decide something: the day's last snapshot, the
    # second listing of the first game, the later of two keyless rows.
    totals = GB.game_line_closes(conn, "nfl", "total")
    assert totals[("2026-10-03", "H0", "A0")] == (51.5, -120, 100)
    assert totals[("2026-10-03", "K", "L")] == (38.5, -125, 105)
    assert totals[("2026-10-02", "H1", "A1")] == (45.5, -110, -105), "a missing line is passed over"
    assert GB.moneyline_closes(conn, "nfl")[("2026-10-01", "K", "L")] == {"K": -175}
    assert GB.game_line_closes(conn, "cfb", "total") == {("2026-10-01", "X", "Y"): (60.5, -110, -110)}
    assert GB.game_line_closes(conn, "nhl", "total") == {} and GB.moneyline_closes(conn, "nfl", "nope") == {}


def test_it_reads_a_small_part_of_what_the_walk_read():
    conn = _history()
    steps = [0]

    def tick():
        steps[0] += 1
        return 0
    conn.set_progress_handler(tick, 100)
    _old_lines(conn, "nfl", "total")
    walk, steps[0] = steps[0], 0
    GB.game_line_closes(conn, "nfl", "total")
    seek = steps[0]
    conn.set_progress_handler(None, 0)
    assert seek * 5 < walk, (seek, walk)


def test_a_file_without_the_index_is_read_the_old_way():
    conn = _history()
    want_t = list(GB.game_line_closes(conn, "nfl", "total").items())
    want_m = _ml_items(GB.moneyline_closes(conn, "nfl"))
    conn.execute("DROP INDEX idx_odds_hist_lookup")
    assert list(GB.game_line_closes(conn, "nfl", "total").items()) == want_t
    assert _ml_items(GB.moneyline_closes(conn, "nfl")) == want_m
    # A bare table (a test's, or an old copy's) with no key and no index.
    bare = sqlite3.connect(":memory:")
    bare.row_factory = sqlite3.Row
    bare.execute("CREATE TABLE odds_history (sport TEXT, market TEXT, book TEXT, taken_at TEXT, "
                 "home TEXT, away TEXT, player TEXT, line REAL, over_odds INT, under_odds INT)")
    bare.execute("INSERT INTO odds_history VALUES ('nfl','total','best','2026-10-01T12:00:00Z',"
                 "'H','A','TOTAL',44.5,-110,-110)")
    assert GB.game_line_closes(bare, "nfl", "total") == {("2026-10-01", "H", "A"): (44.5, -110, -110)}
    try:
        GB.harvest_rows(bare, "nope_column", "nfl", "total", "best")
    except sqlite3.OperationalError as exc:
        assert "no such column" in str(exc)
    else:
        raise AssertionError("an error that is not a missing index is not swallowed")


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
