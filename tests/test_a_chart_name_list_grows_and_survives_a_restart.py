"""A chart's list of names grows by the table's new rows and is kept across a restart (step AGW, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". Step AGR kept each chart table's names ten minutes, so a name the table does not hold cost a
lookup, not the table. On the live site, just after the update that shipped it, a college basketball shot chart for
such a name still took 8.7 s (1.2 s of work, the rest waiting on the disk) and an NBA one 2.7 s: the first ask after
a restart read the table's whole name index, and so did the first ask of every ten minutes after it. Now:

  * the list grows by the rows the table gained since it was read, their names alone, off the rowid;
  * it is kept on disk beside the database, as stored, and folded as it is read back, so a restart reads none of it;
  * it is read whole again only after a day (behind the one in hand) or when the table's highest rowid falls;
  * and a typed name the spelling search has looked up is kept beside the league's name list, so a role chart for a
    name the league does not hold stops paying the search (0.23 to 0.31 s live) on every ask.

Offline. Run directly: `python3 tests/test_a_chart_name_list_grows_and_survives_a_restart.py`
"""
import gzip
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D  # noqa: E402


class _Seen:
    """A connection that keeps every statement it ran, with its arguments."""
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append((sql, tuple(args)))
        return self.conn.execute(sql, args)

    def whole(self, table):
        return [s for s, _ in self.sql if s.startswith(f"SELECT DISTINCT player FROM {table}") and "rowid >" not in s]

    def since(self, table):
        return [(s, a) for s, a in self.sql if s.startswith(f"SELECT DISTINCT player FROM {table}") and "rowid >" in s]


SHOT_COLS = ("game_id, action, season, date, person_id, player, team, opponent, home, period, clock, kind, made, shot, "
             "descriptor, distance, x, y, zone, area, assist, blocked, quals")


def _shot(conn, gid, act, pid, name, table="cbb_shots"):
    conn.execute(f"INSERT INTO {table} ({SHOT_COLS}) VALUES (?,?,2026,'2026-11-20',?,?,'DUKE','UNC',1,1,'',"
                 "'2pt',1,'','',5.0,1.0,1.0,'paint','','',0,'')", (gid, act, pid, name))
    conn.commit()


def _history(n=30):
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    for i in range(n):
        _shot(conn, f"g{i}", i, 1000 + i % 3, f"Player {i % 3}")
    return conn


def test_rows_since_are_read_alone_and_a_restart_reads_none():
    D._FOLDED_NAMES.clear()
    conn = _history()
    seen = _Seen(conn)
    first = D.folded_names(seen, "cbb_shots", "", (), str.lower)
    assert sorted(first) == ["player 0", "player 1", "player 2"] and len(seen.whole("cbb_shots")) == 1
    _shot(conn, "gx", 99, 4440, "Cooper Flagg")
    second = D.folded_names(seen, "cbb_shots", "", (), str.lower)
    assert second["cooper flagg"] == ["Cooper Flagg"], "a row since: its name joins the list"
    assert len(seen.whole("cbb_shots")) == 1 and len(seen.since("cbb_shots")) == 1, "the new rows alone are read"
    assert "cooper flagg" not in first, "a reader holding the list before keeps it as it was"
    plan = " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + seen.since("cbb_shots")[0][0],
                                               seen.since("cbb_shots")[0][1]))
    assert "rowid>?" in plan.replace(" ", ""), plan
    D._FOLDED_NAMES.clear()                               # a restart
    seen = _Seen(conn)
    assert D.folded_names(seen, "cbb_shots", "", (), str.lower) == second
    assert not seen.whole("cbb_shots") and not seen.since("cbb_shots"), "read off the disk: none of the table"
    D._FOLDED_NAMES.clear()
    upper = D.folded_names(seen, "cbb_shots", "", (), str.upper)
    assert upper["COOPER FLAGG"] == ["Cooper Flagg"], "kept as stored, folded as it is read back"
    D._FOLDED_NAMES.clear()


def test_the_rowid_is_read_not_the_leagues_index():
    """A filtered list (a league's carries) reads its new rows off the rowid: the (sport, player) index would read
    every row of the league to keep the new ones."""
    D._FOLDED_NAMES.clear()
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    for i, who in enumerate(("Jahmyr Gibbs", "David Montgomery", "Bijan Robinson")):
        conn.execute("INSERT INTO carries (sport, season, period, game_id, play_id, player) VALUES (?,?,?,?,?,?)",
                     ("nfl", 2026, "011", "g1", f"p{i}", who))
    conn.commit()
    seen = _Seen(conn)
    D.folded_names(seen, "carries", "sport=?", ("nfl",), str.lower)
    conn.execute("INSERT INTO carries (sport, season, period, game_id, play_id, player) VALUES (?,?,?,?,?,?)",
                 ("cfb", 2026, "012", "g2", "p9", "Jeremiah Smith"))
    conn.execute("INSERT INTO carries (sport, season, period, game_id, play_id, player) VALUES (?,?,?,?,?,?)",
                 ("nfl", 2026, "012", "g2", "p8", "Ashton Jeanty"))
    conn.commit()
    got = D.folded_names(seen, "carries", "sport=?", ("nfl",), str.lower)
    assert "ashton jeanty" in got and "jeremiah smith" not in got, "the filter holds for the new rows"
    sql, args = seen.since("carries")[0]
    plan = " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args))
    assert "INTEGER PRIMARY KEY" in plan and "carries_player" not in plan, plan
    D._FOLDED_NAMES.clear()


def test_a_table_whose_highest_row_went_is_read_whole():
    D._FOLDED_NAMES.clear()
    conn = _history()
    _shot(conn, "gx", 99, 4440, "Cooper Flagg")
    seen = _Seen(conn)
    assert "cooper flagg" in D.folded_names(seen, "cbb_shots", "", (), str.lower)
    conn.execute("DELETE FROM cbb_shots WHERE player='Cooper Flagg'")
    conn.commit()
    got = D.folded_names(seen, "cbb_shots", "", (), str.lower)
    assert "cooper flagg" not in got and len(seen.whole("cbb_shots")) == 2, "its highest rowid fell: read whole"
    D._FOLDED_NAMES.clear()


def test_a_list_a_day_old_answers_and_is_read_whole_behind():
    D._FOLDED_NAMES.clear()
    conn = _history()
    seen = _Seen(conn)
    D.folded_names(seen, "cbb_shots", "", (), str.lower)
    conn.execute("DELETE FROM cbb_shots WHERE player='Player 1'")    # rows from the middle: the highest stands
    conn.commit()
    k = next(iter(D._FOLDED_NAMES))
    at, top, out = D._FOLDED_NAMES[k]
    D._FOLDED_NAMES[k] = (at - D.FOLDED_NAMES_FULL_S - 5, top, out)
    t0 = time.time()
    old = D.folded_names(seen, "cbb_shots", "", (), str.lower)
    assert "player 1" in old and time.time() - t0 < 1.0, "the list in hand answers at once"
    end = time.time() + 5
    while time.time() < end and (k in D._FOLDED_BEHIND or "player 1" in D._FOLDED_NAMES[k][2]):
        time.sleep(0.02)
    assert "player 1" not in D._FOLDED_NAMES[k][2], "read whole behind it: the name gone with its rows"
    assert time.time() - D._FOLDED_NAMES[k][0] < 60
    D._FOLDED_NAMES.clear()
    kept = json.loads(gzip.open(D._folded_file(k), "rt", encoding="utf-8").read())
    assert "Player 1" not in kept["names"] and kept["top"] == top, "and kept on disk so"
    D._FOLDED_NAMES.clear()


def test_a_copy_on_disk_that_will_not_read_is_read_whole_again():
    D._FOLDED_NAMES.clear()
    conn = _history()
    seen = _Seen(conn)
    D.folded_names(seen, "cbb_shots", "", (), str.lower)
    k = next(iter(D._FOLDED_NAMES))
    D._folded_file(k).write_bytes(b"not a list")
    D._FOLDED_NAMES.clear()
    assert sorted(D.folded_names(seen, "cbb_shots", "", (), str.lower)) == ["player 0", "player 1", "player 2"]
    assert len(seen.whole("cbb_shots")) == 2, "read whole again"
    assert json.loads(gzip.open(D._folded_file(k), "rt", encoding="utf-8").read())["names"] == [
        "Player 0", "Player 1", "Player 2"], "and the copy written over"
    other = D._folded_file((k[0], "nba_shots", "", ()))
    assert other != D._folded_file(k), "each list its own file"
    D._FOLDED_NAMES.clear()


def test_a_typed_name_is_spelled_once_while_the_leagues_list_stands():
    from engine import statlogs as SL
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     [("cbb", 2026, "2026-11-20", "g1", "Cameron Boozer", "DUKE", "UNC", "F", 1, "points", 22.0),
                      ("cbb", 2026, "2026-11-20", "g1", "Darius Acuff Jr.", "ARK", "UK", "G", 1, "points", 18.0)])
    conn.commit()
    real, runs = SL._spelled, []
    SL._spelled = lambda c, sport, q: (runs.append(q), real(c, sport, q))[1]
    SL._SPELLED.clear()
    try:
        assert SL.resolve_player(conn, "cbb", "Cooper Flagg") == ""
        assert SL.resolve_player(conn, "cbb", "Cooper Flagg") == ""
        assert SL.resolve_player(conn, "cbb", "Camron Boozer") == "Cameron Boozer"
        assert SL.resolve_player(conn, "cbb", "Camron Boozer") == "Cameron Boozer"
        assert runs == ["Cooper Flagg", "Camron Boozer"], runs
        assert SL.resolve_player(conn, "cbb", "Cameron Boozer") == "Cameron Boozer" and len(runs) == 2, "exact: none"
        key = next(iter(SL._SPELLED))
        SL._SPELLED[key] = (object(), SL._SPELLED[key][1])          # the league's list built again (new logs)
        assert SL.resolve_player(conn, "cbb", "Cooper Flagg") == "" and len(runs) == 3, "a new list: spelled again"
        mem = D.connect(":memory:")
        SL.resolve_player(mem, "cbb", "Cooper Flagg")
        SL.resolve_player(mem, "cbb", "Cooper Flagg")
        assert len(runs) == 5, "a database in memory is never kept"
    finally:
        SL._spelled = real
        SL._SPELLED.clear()


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
