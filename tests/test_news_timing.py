"""Injury designations get a first-seen stamp, written once.

Ethan, 2026-09-07, on the data a winning model needs: "News timing.
Injuries, inactives, quarterback changes, weather, each timestamped. The
value is not knowing, it is knowing before the soft books move."

Knowing is worth nothing on its own — the closing line knows too, and
every information test here says no input on disk beats it. The INTERVAL
is worth something, and the interval could not be computed: the injuries
page has read ESPN's feed since 2026-08-10 and `current_rows` keeps only
the newest filing per player, so a designation four minutes old and one
standing since Tuesday are the same row.

This is the capture, and it claims nothing beyond capture. It is
deliberately paired with `engine.lineledger`, which since 2026-09-07
stores the sharp book's price beside the shopped best on the same minute
grid — the two tables are meant to be read against each other later.

Run directly: `python3 tests/test_news_timing.py`
"""

import datetime as dt
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, lineledger, newstape as N             # noqa: E402

T1 = dt.datetime(2026, 9, 12, 14, 5, 40, tzinfo=dt.timezone.utc)
T2 = dt.datetime(2026, 9, 12, 18, 30, 0, tzinfo=dt.timezone.utc)


def _row(**kw):
    r = {"team": "Detroit Lions", "player": "Jameson Williams", "pos": "WR",
         "status": "Questionable", "date": "2026-09-11T20:00Z",
         "injury": "Hamstring", "side": "Left", "return_date": None,
         "comment": None, "face": None}
    r.update(kw)
    return r


def test_only_designations_a_book_reprices_on_are_kept():
    assert N.is_watched("Out") and N.is_watched("questionable")
    assert N.is_watched("Injured Reserve") and N.is_watched("Day-To-Day")
    # ESPN emits plenty of these and they are not news.
    assert not N.is_watched("Active") and not N.is_watched("")
    assert not N.is_watched(None) and not N.is_watched("Probable")
    assert N.rows_for("nfl", [_row(status="Active")], now=T1) == []
    assert N.rows_for("nfl", [_row(player="")], now=T1) == []
    assert N.rows_for("nfl", [None, "nonsense"], now=T1) == []
    assert N.rows_for("nfl", None, now=T1) == []


def test_the_two_clocks_are_kept_apart():
    """The feed's stamp is the feed's; first_seen is ours. Their gap is
    the feed's lag, and it cannot be measured from one column."""
    got = N.rows_for("nfl", [_row()], now=T1)
    assert got == [{"sport": "nfl", "player": "Jameson Williams",
                    "team": "Detroit Lions", "status": "Questionable",
                    "posted_at": "2026-09-11T20:00Z",
                    "first_seen": "2026-09-12T14:05:00Z",
                    "injury": "Hamstring", "pos": "WR"}]
    # Minute resolution, and the SAME format the price tape stamps with,
    # because the two tables exist to be read against each other.
    assert N._stamp(T1) == lineledger._stamp(T1)


def test_a_feed_with_no_stamp_of_its_own_still_writes_one_row_per_pull():
    """Empty rather than None: `posted_at` is half the primary key, and
    NULL never compares equal to NULL in SQLite — so a None would make
    every pull look like a new filing."""
    conn = db.connect(":memory:")
    rows = N.rows_for("nfl", [_row(date=None)], now=T1)
    assert rows[0]["posted_at"] == ""
    assert db.insert_injury_events(conn, rows) == 1
    assert db.insert_injury_events(conn, N.rows_for("nfl", [_row(date=None)],
                                                    now=T2)) == 0
    assert conn.execute("SELECT COUNT(*) FROM injury_events").fetchone()[0] == 1


def test_the_stamp_is_written_once_and_a_new_designation_is_a_new_row():
    conn = db.connect(":memory:")
    assert N.record(conn, "nfl", [_row()], now=T1) == 1
    # The same filing, seen again four hours later: nothing is rewritten.
    assert N.record(conn, "nfl", [_row()], now=T2) == 0
    # He is ruled out: that MOVE is the news, so it is its own row.
    assert N.record(conn, "nfl", [_row(status="Out",
                                       date="2026-09-12T18:00Z")], now=T2) == 1
    got = sorted(tuple(r) for r in conn.execute(
        "SELECT status, posted_at, first_seen FROM injury_events"))
    assert got == [("Out", "2026-09-12T18:00Z", "2026-09-12T18:30:00Z"),
                   ("Questionable", "2026-09-11T20:00Z", "2026-09-12T14:05:00Z")], got


def test_a_status_change_under_one_stamp_is_still_two_events():
    """THE CASE THAT NEEDS `status` IN THE KEY. A feed that re-files a
    player under the SAME posted_at — or files everything without a
    stamp at all — would otherwise overwrite Questionable with Out and
    lose the move, which is the only thing here worth timing."""
    conn = db.connect(":memory:")
    assert N.record(conn, "nfl", [_row(date="")], now=T1) == 1
    assert N.record(conn, "nfl", [_row(date="", status="Out")], now=T2) == 1
    got = sorted(tuple(r) for r in conn.execute(
        "SELECT status, first_seen FROM injury_events"))
    assert got == [("Out", "2026-09-12T18:30:00Z"),
                   ("Questionable", "2026-09-12T14:05:00Z")], got


def test_two_leagues_do_not_collide_on_one_name():
    conn = db.connect(":memory:")
    assert N.record(conn, "nfl", [_row()], now=T1) == 1
    assert N.record(conn, "cfb", [_row()], now=T1) == 1
    assert conn.execute("SELECT COUNT(*) FROM injury_events").fetchone()[0] == 2


def test_telemetry_never_breaks_the_board():
    class _Broken:
        def execute(self, *a, **k):
            raise RuntimeError("database is locked")
        executemany = execute
    assert N.record(_Broken(), "nfl", [_row()], now=T1) == 0


def test_the_build_records_what_it_already_parsed():
    import injuries_build
    src = inspect.getsource(injuries_build.main)
    assert "newstape.record(hconn, league, rows)" in src, src[:200]
    # The FULL parse, not the page's current-board cut: an event row for
    # a filing the page has since dropped is exactly what timing needs.
    i = src.index("newstape.record(")
    assert "current_rows" not in src[i:i + 80]
    assert "hconn is not None" in src, "an unreadable DB costs stamps, not the page"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
