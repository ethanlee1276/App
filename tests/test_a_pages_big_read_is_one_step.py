"""A page's big read is one step of the database (step AHG, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". On the live site Connor McDavid's page waited 3.4 s on the read of his rows, 128 ms of it its own
work: the rest waiting on the server's other threads. Python's sqlite3 lets go of the interpreter for each row it
steps through and takes it back after, and beside a busy thread each taking back waits out that thread's turn: 800
rows that read in 1.7 ms alone took 3.2 to 6.1 s beside one. `db.rows_at_once` reads them as one JSON text, one step
(18 to 29 ms beside the same thread), every REAL digit kept through quote(); the server's turns are 0.5 ms, not 5.

Offline. Run directly: `python3 tests/test_a_pages_big_read_is_one_step.py`
"""
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D  # noqa: E402

SQL = "SELECT season, period, game_id, team, opponent, position, home, market, value FROM player_game_logs " \
      "WHERE sport=? AND player=?"


def _history(n=300, odd=False):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    vals = [0.1 + 0.2, 1 / 3, 21.483333333333334, 7.0, None, 123456789.12345679, 2.0 ** 53, -4.5]
    rows = [("nhl", 2015 + i % 11, f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}", f"g{i}", "Connor McDavid", "EDM",
             "CGY" if i % 2 else "Bärenstadt", "C", i % 2 if i % 7 else None, f"m{i % 9}", vals[i % len(vals)])
            for i in range(n)]
    rows.append(("nhl", 2026, "2026-11-20", "g-other", "Leon Draisaitl", "EDM", "VAN", "C", 1, "goals", 1.0))
    if odd:
        rows.append(("nhl", 2026, "2026-11-21", "g-odd", "Connor McDavid", "EDM", "VAN", "C", 1, "toi", "n/a"))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def _plain(conn, args=("nhl", "Connor McDavid")):
    return [tuple(r) for r in conn.execute(SQL, args).fetchall()]


def _key(rows):
    return sorted(rows, key=lambda r: tuple("" if v is None else str(v) for v in r))


def test_the_same_rows_every_digit_kept():
    conn = _history()
    got = D.rows_at_once(conn, SQL, ("nhl", "Connor McDavid"), n=9, real=(8,))
    plain = _plain(conn)
    assert len(got) == 300 and _key(got) == _key(plain), "the same rows"
    for a, b in zip(_key(got), _key(plain)):
        assert a == b and [type(x) for x in a] == [type(x) for x in b], (a, b)
    vals = {r[8] for r in got}
    assert {0.1 + 0.2, 1 / 3, 21.483333333333334, 123456789.12345679, None} <= vals, "every digit, and NULL as None"
    assert {r[4] for r in got} == {"CGY", "Bärenstadt"}, "text as it was written"
    assert D.rows_at_once(conn, SQL, ("nhl", "Nobody"), n=9, real=(8,)) == [], "nothing is nothing"


def test_a_value_that_will_not_read_back_and_a_bad_read_go_the_plain_way():
    conn = _history(n=20, odd=True)
    got = D.rows_at_once(conn, SQL, ("nhl", "Connor McDavid"), n=9, real=(8,))
    assert _key(got) == _key(_plain(conn)) and "n/a" in {r[8] for r in got}, "a text in a REAL column: the plain read"
    try:
        D.rows_at_once(conn, "SELECT nope FROM player_game_logs", (), n=1)
        raise AssertionError("the read's own error must raise")
    except sqlite3.OperationalError as exc:
        assert "nope" in str(exc)


def test_a_sqlite_without_json_reads_the_plain_way_from_then_on():
    conn = _history(n=10)

    class NoJson:
        def __init__(self, c):
            self.c, self.asked = c, []

        def execute(self, sql, args=()):
            self.asked.append(sql)
            if "json_group_array" in sql:
                raise sqlite3.OperationalError("no such function: json_group_array")
            return self.c.execute(sql, args)
    was = D._AT_ONCE[0]
    try:
        wrapped = NoJson(conn)
        assert _key(D.rows_at_once(wrapped, SQL, ("nhl", "Connor McDavid"), n=9, real=(8,))) == _key(_plain(conn))
        assert D._AT_ONCE[0] is False and len(wrapped.asked) == 2
        D.rows_at_once(wrapped, SQL, ("nhl", "Connor McDavid"), n=9, real=(8,))
        assert len(wrapped.asked) == 3 and "json_group_array" not in wrapped.asked[-1], "not asked again"
    finally:
        D._AT_ONCE[0] = was


def test_beside_a_busy_thread_the_one_step_read_does_not_wait_row_by_row():
    conn = _history(n=400)
    conn2 = sqlite3.connect(conn.execute("PRAGMA database_list").fetchone()[2], check_same_thread=False)
    stop = threading.Event()

    def burn():
        x = 0
        while not stop.is_set():
            for i in range(5000):
                x += i * i
    was = sys.getswitchinterval()
    sys.setswitchinterval(0.005)                          # Python's own turn, as before the server set its own
    t = threading.Thread(target=burn, daemon=True)
    try:
        t.start()
        time.sleep(0.05)
        t0 = time.perf_counter()
        plain = conn2.execute(SQL, ("nhl", "Connor McDavid")).fetchall()
        slow = time.perf_counter() - t0
        t0 = time.perf_counter()
        one = D.rows_at_once(conn2, SQL, ("nhl", "Connor McDavid"), n=9, real=(8,))
        fast = time.perf_counter() - t0
    finally:
        stop.set()
        t.join(5)
        sys.setswitchinterval(was)
    assert len(plain) == len(one) == 400
    # Whether a busy thread stretches the row-by-row read depends on the machine and what else it runs (on the
    # gate's, eight files at once, it once read in 1 ms beside it). Where it does, the one step must not be.
    if slow < 0.05:
        print(f"  (the busy thread did not stretch the row-by-row read here: {slow * 1000:.0f} ms)")
        return
    assert fast * 4 < slow, f"one step {fast * 1000:.0f} ms against row by row {slow * 1000:.0f} ms"


def test_the_one_step_read_is_one_statement_with_one_row():
    conn = _history(n=50)
    said = []
    conn.set_trace_callback(said.append)
    try:
        got = D.rows_at_once(conn, SQL, ("nhl", "Connor McDavid"), n=9, real=(8,))
    finally:
        conn.set_trace_callback(None)
    assert len(got) == 50 and len(said) == 1, said
    assert said[0].startswith("WITH q(c0, c1, c2, c3, c4, c5, c6, c7, c8) AS (SELECT season") \
        and "SELECT json_group_array(json_array(c0, c1, c2, c3, c4, c5, c6, c7, quote(c8))) FROM q" in said[0], said


def test_the_player_page_reads_its_rows_so_and_the_server_takes_short_turns():
    page = (ROOT / "engine" / "playerpage.py").read_text(encoding="utf-8")
    assert "rows = _db.rows_at_once(\n                    conn, \"SELECT season, period, game_id, team, opponent, " \
           "position, home, market, value \"" in page
    assert '"FROM player_game_logs WHERE sport=? AND player=?", (sport, player), n=9, real=(8,))' in page
    import server
    assert server.SWITCH_INTERVAL_S == 0.0005
    main = (ROOT / "server.py").read_text(encoding="utf-8")
    body = main[main.index("def main() -> None:"):]
    assert body.index("sys.setswitchinterval(SWITCH_INTERVAL_S)") < body.index("server.serve_forever()")


def test_the_page_is_the_page_it_was():
    from engine import playerpage
    conn = _history(n=120)
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    conn.close()
    data = tempfile.mkdtemp()
    one = playerpage.page("nhl", "Connor McDavid", db_path=path, data_dir=data)
    was = D._AT_ONCE[0]
    try:
        D._AT_ONCE[0] = False
        plain = playerpage.page("nhl", "Connor McDavid", db_path=path, data_dir=data)
    finally:
        D._AT_ONCE[0] = was
    assert one and one == plain, "the same page either way"


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
