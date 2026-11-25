"""The sign-up screen's newest graded pick is read alone (step AGZ, 25 November 2026).

Ethan: "Ok keep going and work more on these issues as they are not fixed". The sign-up screen (engine/firstlook)
shows the newest graded pick, and read it as the Record's whole first page (engine/ledger.settled_page): a count of
every settled bet and fifty rows, each graded for its process, to keep the first. On the live site that part ("last")
was 564 ms of the server's time, again whenever the record changed (step AGP keeps it between changes).
ledger.newest_settled reads that one row with the page's own WHERE (ledger._settled_where, which the page now builds
from too), so the two can never disagree about which pick is newest.

Offline. Run directly: `python3 tests/test_the_newest_graded_pick_is_read_alone.py`
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import firstlook, ledger as L  # noqa: E402


class _Seen:
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return self.conn.execute(sql, args)


def _ledger():
    conn = L.connect(":memory:")
    base = dt.date.fromisoformat(L.RECORD_EPOCH)
    rows = []
    for i, (sport, status, cat, market) in enumerate((
            ("nfl", "won", "main", "receptions"), ("nba", "lost", "main", "points"),
            ("nhl", "won", "likely", "sog"), ("nfl", "open", "main", "rec_yds"),        # open: not settled
            ("nba", "push", "main", "spread"), ("nfl", "won", "main", "rush_yds"))):
        day = (base + dt.timedelta(days=10 + i)).isoformat()
        rows.append((sport, day, day, f"P{i}", market, "OVER", 5.5, -110, "DraftKings", 0.6, 1.0, 10.0, status, cat,
                     0.9 if status == "won" else (-1.0 if status == "lost" else 0.0)))
    conn.executemany("INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,book,hit_prob,stake_units,"
                     "stake_dollars,status,category,pnl_units) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_the_newest_is_the_pages_first_row_under_every_filter():
    conn = _ledger()
    for sport in (None, "nfl", "nba", "nhl", "mlb"):
        page = L.settled_page(conn, sport=sport)["rows"]
        one = L.newest_settled(conn, sport=sport)
        if not page:
            assert one is None, sport
            continue
        assert one is not None, sport
        for k in firstlook.LAST_FIELDS:
            assert one[k] == page[0][k], (sport, k, one[k], page[0][k])
    assert L.newest_settled(conn)["player"] == "P5", "the newest settled, past an open bet journalled after it"


def test_the_first_look_counts_nothing_and_reads_one_row():
    conn = _ledger()
    seen = _Seen(conn)
    got = firstlook.last_graded(seen)
    assert got == {k: L.newest_settled(conn)[k] for k in firstlook.LAST_FIELDS}
    assert not any("COUNT(" in s for s in seen.sql), "no count of every settled bet"
    assert any("LIMIT 1" in s for s in seen.sql), "one row"
    assert firstlook.last_graded(_Seen(L.connect(":memory:"))) is None, "an empty record has no newest pick"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
