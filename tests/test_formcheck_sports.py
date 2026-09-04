"""The form harness answered "no game logs" for two of the three sports.

`engine.formcheck` is the walk-forward that decided `WINDOW_WEIGHTS` and,
since 2026-09-03, scores the recency shade. It could only ever be pointed
at the NFL, and it did not say so — it said the table was empty.

TWO LAYERS, EITHER OF WHICH ALONE IS SILENT.

    _rows  had `WHERE sport='nfl'` hardcoded in the SQL, so college and
           baseball could not be asked for at all.
    _rows  keyed the week with `int(period)` and `continue`d on failure.
           NFL files a week number ('001'); college and baseball file a
           DATE ('2022-09-03'). Every one of their rows was dropped.

So `run` returned `{"skipped": "no game logs for this market"}` for a
table holding 26,072 college rushing rows, and that sentence is what an
EMPTY table returns. A harness that cannot read a sport must say which
of those two things happened; they want opposite fixes.

Both are fixed, and the second is now COUNTED where it is dropped, so
"present and unreadable" is a distinct answer from "absent".

WHAT IT UNLOCKED, measured the moment it could run — college rush_yds,
2024-25, 5,408 player-weeks scored and 4,883 comparable:

    market            form    gentle   season
    nfl  rush_yds    0.6451   0.6635   0.6602
    cfb  rush_yds    0.4551   0.4551   0.4428

College ranks its own rushing markedly worse than the NFL ranks its
own. That is a finding this harness previously could not have produced,
and it is recorded here rather than acted on.

Run directly: `python3 tests/test_formcheck_sports.py`
"""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import formcheck as F                            # noqa: E402


def _db(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE player_game_logs (
        sport TEXT, season INT, period TEXT, player TEXT, team TEXT,
        opponent TEXT, market TEXT, value REAL)""")
    conn.executemany(
        "INSERT INTO player_game_logs (sport, season, period, player, team,"
        " opponent, market, value) VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def _slate(sport, periods):
    """Eight players a period, so a week clears the ranking floor."""
    out = []
    for p in periods:
        for i in range(8):
            out.append((sport, 2025, p, f"P{i}", "AAA", "BBB",
                        "rush_yds", 40.0 + i * 7))
            out.append((sport, 2025, p, f"P{i}", "AAA", "BBB",
                        "carries", 10.0 + i))
    return out


# --- the key -----------------------------------------------------------------
def test_both_shapes_a_period_takes_are_keyed():
    assert F._period_key("001") == 1, "the NFL week number stopped parsing"
    assert F._period_key("2022-09-03") == "2022-09-03", \
        "a date period is still being thrown away"
    assert F._period_key(7) == 7


def test_an_unusable_period_is_still_dropped():
    for bad in (None, "", "   "):
        assert F._period_key(bad) is None, f"{bad!r} was accepted as a key"


def test_iso_dates_sort_in_date_order_as_strings():
    """The key only has to ORDER correctly within a season. A zero-padded
    week and an ISO date both sort lexicographically the way they sort
    chronologically, which is why the raw string is a correct key and a
    parsed one is not needed."""
    dates = ["2025-10-11", "2025-09-06", "2025-11-29", "2025-09-27"]
    assert sorted(dates) == ["2025-09-06", "2025-09-27",
                             "2025-10-11", "2025-11-29"]
    assert sorted(["001", "002", "010", "018"]) == ["001", "002", "010", "018"]


# --- the sport ---------------------------------------------------------------
def test_a_date_keyed_sport_is_read_rather_than_skipped():
    """THE BUG. Rows exist, every one was discarded, and the report said
    the table was empty."""
    conn = _db(_slate("cfb", ["2025-09-06", "2025-09-13", "2025-09-20",
                              "2025-09-27", "2025-10-04"]))
    rows, unreadable = F._rows(conn, "rush_yds", sport="cfb")
    assert rows, "college rows are still being dropped"
    assert unreadable == 0, unreadable
    assert all(isinstance(r[1], str) for r in rows), \
        "a date period was coerced to something else"


def test_asking_for_a_sport_does_not_return_another_ones_rows():
    conn = _db(_slate("cfb", ["2025-09-06", "2025-09-13"])
               + _slate("nfl", ["001", "002"]))
    cfb, _ = F._rows(conn, "rush_yds", sport="cfb")
    nfl, _ = F._rows(conn, "rush_yds", sport="nfl")
    assert cfb and nfl
    assert {r[1] for r in cfb} == {"2025-09-06", "2025-09-13"}
    assert {r[1] for r in nfl} == {1, 2}


def test_the_nfl_read_is_unchanged():
    """This harness's published results are NFL results. Widening it must
    not move the rows it already scored or the keys they carry."""
    conn = _db(_slate("nfl", ["001", "002", "003", "004", "005"]))
    rows, unreadable = F._rows(conn, "rush_yds")
    assert unreadable == 0
    assert [r[1] for r in rows[:8]] == [1] * 8, \
        "the NFL week key is no longer an int"


def test_the_curve_follows_the_sport():
    """`weights_for("nfl", ...)` was hardcoded, so a college run would
    have been scored under the football curve."""
    import inspect
    src = inspect.getsource(F.run)
    assert "weights_for(sport, market)" in src
    assert 'weights_for("nfl"' not in src


# --- the honest skip ----------------------------------------------------------
def test_an_empty_table_and_an_unreadable_one_read_differently():
    """The whole point. Both used to return the same sentence, and they
    want opposite fixes — one is a data gap, the other is this file."""
    empty = F.run(_db([]), "rush_yds", sport="cfb")
    assert empty["n"] == 0
    assert empty["skipped"] == "no game logs for this market"
    assert "unreadable" not in empty

    junk = _db([("cfb", 2025, None, "P0", "AAA", "BBB", "rush_yds", 40.0)
                for _ in range(5)])
    bad = F.run(junk, "rush_yds", sport="cfb")
    assert bad["n"] == 0
    assert bad.get("unreadable") == 5, bad
    assert "harness fault" in bad["skipped"], bad["skipped"]
    assert bad["skipped"] != empty["skipped"]


def test_a_readable_sport_scores_and_names_its_candidates():
    conn = _db(_slate("cfb", [f"2025-09-{d:02d}" for d in (6, 13, 20, 27)]
                      + ["2025-10-04", "2025-10-11"]))
    got = F.run(conn, "rush_yds", sport="cfb")
    assert not got.get("skipped"), got
    assert got["n"] > 0
    for name in ("form", "form_trend", "gentle", "season"):
        assert name in got["candidates"], f"{name} was not scored"


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
