"""Two reads of the game logs are kept until their rows change (engine/logcache).

The heartbeat at 00:56 on 9 November had the NHL build reading every
player's games of two seasons in 17 of its 25 board seconds, on every
build, and the fantasy file's season means reading the same seasons again
for every sport, while those rows change about once a day. Each result is
now stored with the count and highest rowid of exactly the rows it read, and
the source file that computed it, and served while all three still match.

Checks, through the real write path (engine.db.upsert_player_logs):
a second read is served; a new row, a corrected row, a deleted row and a
changed source file each read the table again; another sport's or season's
rows do not; only the production history file is cached unless forced; a
broken cache file is a read, never an error; and the NHL player games and
the season means come out the same through the cache as off the table.

THE SAME ROWS WRITTEN AGAIN (2026-11-09, the box at 02:15): the NHL build
read its player games again (19.7 s) and its season means (25.3 s) though
nothing in them had changed, because the results pulls re-read days they
already hold and every rewrite filed the same row under a new rowid. Checks:
a row stored exactly as given keeps its place, whatever Python type it
arrives in, and a changed one still goes above every other; the same rows
written again leave a kept read standing; each read notes what it did and
why, for the heartbeat; and a delete or an update in place, after which a
freed rowid can come back, drops the sport's kept reads.

Run directly: `python3 tests/test_the_game_log_reads_are_kept_until_their_rows_change.py`
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, logcache                                  # noqa: E402
from engine import fantasy_daily as FD                           # noqa: E402
from engine.nhl import model as M                                # noqa: E402


class _Sandbox:
    """A history file and a feedstate directory of the test's own."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.keep = os.environ.get("QB_FEEDSTATE_DIR")
        os.environ["QB_FEEDSTATE_DIR"] = os.path.join(self.dir, "feedstate")
        self.conn = db.connect(os.path.join(self.dir, "history.db"))
        return self

    def __exit__(self, *exc):
        self.conn.close()
        if self.keep is None:
            os.environ.pop("QB_FEEDSTATE_DIR", None)
        else:
            os.environ["QB_FEEDSTATE_DIR"] = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)


def _row(sport, season, period, player, market, value, team="EDM", game=None):
    return {"sport": sport, "season": season, "period": period, "game_id": game or f"{sport}-{period}",
            "player": player, "team": team, "opponent": "CGY", "position": "C", "home": 1,
            "market": market, "value": value}


def _seed(conn):
    rows = []
    for season, day in ((2024, "2024-11-0"), (2025, "2025-11-0")):
        for d in range(1, 6):
            for player, team in (("Connor McDavid", "EDM"), ("Nazem Kadri", "CGY")):
                for market, value in (("sog", 3 + d % 3), ("points", d % 2), ("toi", 20.5)):
                    rows.append(_row("nhl", season, f"{day}{d}", player, market, value, team=team,
                                     game=f"g{season}{d}"))
    rows.append(_row("nba", 2025, "2025-11-01", "Nikola Jokic", "points", 31, team="DEN"))
    db.upsert_player_logs(conn, rows)
    conn.commit()


def _counted(box):
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}
    return calls, compute


def test_a_result_is_served_until_its_own_rows_change():
    with _Sandbox() as s:
        _seed(s.conn)
        calls, compute = _counted(s)
        memo = lambda: logcache.memo(s.conn, "probe", "nhl", (2025, 2024), compute, force=True)
        assert memo() == {"n": 1} and memo() == {"n": 1} and len(calls) == 1, "the second read is served"
        db.upsert_player_logs(s.conn, [_row("nba", 2025, "2025-11-02", "Nikola Jokic", "points", 28,
                                            team="DEN")])
        db.upsert_player_logs(s.conn, [_row("nhl", 2023, "2023-11-01", "Connor McDavid", "sog", 4)])
        s.conn.commit()
        assert memo() == {"n": 1}, "another sport's row or another season's leaves it standing"
        db.upsert_player_logs(s.conn, [_row("nhl", 2025, "2025-11-09", "Connor McDavid", "sog", 6)])
        s.conn.commit()
        assert memo() == {"n": 2}, "a new row reads the table again"
        assert memo() == {"n": 2}
        db.upsert_player_logs(s.conn, [_row("nhl", 2025, "2025-11-09", "Connor McDavid", "sog", 7)])
        s.conn.commit()
        assert memo() == {"n": 3}, "a corrected row (same key, new value) reads it again"
        s.conn.execute("DELETE FROM player_game_logs WHERE sport='nhl' AND player='Nazem Kadri' "
                       "AND period='2024-11-01'")
        s.conn.commit()
        assert memo() == {"n": 4}, "a deleted row reads it again"
        assert memo() == {"n": 4}


def test_a_changed_source_file_reads_the_table_again():
    with _Sandbox() as s:
        _seed(s.conn)
        src = Path(s.dir) / "computer.py"
        src.write_text("VERSION = 1\n")
        calls, compute = _counted(s)
        memo = lambda: logcache.memo(s.conn, "probe", "nhl", (2025, 2024), compute, code=str(src),
                                     force=True)
        assert memo() == {"n": 1} and memo() == {"n": 1}
        src.write_text("VERSION = 2\n")
        assert memo() == {"n": 2}, "a deploy that changes the computing file is never served the old shape"


def test_only_the_production_history_file_is_cached_unless_forced():
    with _Sandbox() as s:
        _seed(s.conn)
        assert not logcache.enabled_for(s.conn), "a test's own file reads fresh"
        calls, compute = _counted(s)
        logcache.memo(s.conn, "probe", "nhl", (2025,), compute)
        logcache.memo(s.conn, "probe", "nhl", (2025,), compute)
        assert len(calls) == 2
        assert not os.path.exists(os.path.join(os.environ["QB_FEEDSTATE_DIR"], logcache.DIRNAME)), \
            "and leaves nothing behind"
        mem = db.connect(":memory:")
        assert logcache.db_file(mem) == "" and not logcache.enabled_for(mem)
        assert logcache.db_file(s.conn) == os.path.realpath(os.path.join(s.dir, "history.db"))


def test_a_broken_cache_file_is_a_read_never_an_error():
    with _Sandbox() as s:
        _seed(s.conn)
        calls, compute = _counted(s)
        logcache.memo(s.conn, "probe", "nhl", (2025,), compute, force=True)
        folder = Path(os.environ["QB_FEEDSTATE_DIR"]) / logcache.DIRNAME
        files = list(folder.glob("probe-nhl-*.pkl"))
        assert len(files) == 1, files
        files[0].write_bytes(b"not a pickle")
        assert logcache.memo(s.conn, "probe", "nhl", (2025,), compute, force=True) == {"n": 2}
        assert logcache.memo(s.conn, "probe", "nhl", (2025,), compute, force=True) == {"n": 2}, \
            "and the read is stored again"


def _forced(fn):
    """Run ``fn`` with the cache switched on for any file."""
    keep = logcache.enabled_for
    logcache.enabled_for = lambda conn: True
    try:
        return fn()
    finally:
        logcache.enabled_for = keep


def test_the_nhl_player_games_come_out_the_same_through_the_cache():
    with _Sandbox() as s:
        _seed(s.conn)
        fresh = M._player_games(s.conn, [2025, 2024])
        first = _forced(lambda: M.player_games(s.conn, seasons=[2025, 2024]))
        again = _forced(lambda: M.player_games(s.conn, seasons=[2025, 2024]))
        assert first == fresh and again == fresh, "stored and served, the same players and games"
        assert list(fresh) and fresh["Connor McDavid"]["games"][0]["date"] == "2025-11-05"
        edm = _forced(lambda: M.player_games(s.conn, teams={"EDM"}, seasons=[2025, 2024]))
        assert set(edm) == {"Connor McDavid"}, "the team filter still applies, after the cache"
        again["Connor McDavid"]["games"].clear()
        assert _forced(lambda: M.player_games(s.conn, seasons=[2025, 2024])) == fresh, \
            "a caller changing what it was given never changes what the next one gets"


def test_the_season_means_come_out_the_same_through_the_cache():
    with _Sandbox() as s:
        _seed(s.conn)
        fresh = FD._season_means(s.conn, "nhl", 2025)
        assert _forced(lambda: FD.season_means(s.conn, "nhl")) == fresh
        assert _forced(lambda: FD.season_means(s.conn, "nhl")) == fresh
        assert FD.season_means(s.conn, "nhl") == fresh, "and the same off the table"
        assert fresh["Connor McDavid"]["sog"] > 0 and FD.season_means(None, "nhl") == {}


def _rowids(conn):
    return {(r[1], r[2], r[3], r[4]): r[0] for r in conn.execute(
        "SELECT rowid, sport, period, player, market FROM player_game_logs")}


def test_a_row_stored_exactly_as_given_keeps_its_place_and_a_changed_one_moves_up():
    with _Sandbox() as s:
        _seed(s.conn)
        rows = [_row("nhl", 2025, "2025-11-05", "Connor McDavid", "sog", 5, game="g20255"),
                _row("nhl", 2025, "2025-11-05", "Connor McDavid", "toi", 20.5, game="g20255")]
        before = _rowids(s.conn)
        assert db.upsert_player_logs(s.conn, rows) == 2, "the count given, as before"
        s.conn.commit()
        assert _rowids(s.conn) == before, "written again unchanged: every row where it was"
        as_other_types = [dict(rows[0], value=5.0, season="2025", home=True)]
        db.upsert_player_logs(s.conn, as_other_types)
        s.conn.commit()
        assert _rowids(s.conn) == before, "5 and 5.0, '2025' and 2025, True and 1 are the same row"
        top = max(before.values())
        cur = dict(rows[0])
        for change in ({"value": 6}, {"team": "CGY"}, {"position": None}, {"position": "C"}):
            cur.update(change)
            db.upsert_player_logs(s.conn, [cur])
            s.conn.commit()
            now = _rowids(s.conn)
            moved = now[("nhl", "2025-11-05", "Connor McDavid", "sog")]
            assert moved > top, (change, moved, top)
            top = moved
            assert len(now) == len(before), "replaced, never doubled"
        got = s.conn.execute("SELECT value, team, position FROM player_game_logs WHERE period='2025-11-05' "
                             "AND player='Connor McDavid' AND market='sog'").fetchone()
        assert tuple(got) == (6.0, "CGY", "C"), tuple(got)


def test_the_same_rows_written_again_leave_a_kept_read_standing():
    """The daily catch-up re-reads the last final day; the settle pass
    re-reads every day with an open pick, every pass."""
    with _Sandbox() as s:
        _seed(s.conn)
        calls, compute = _counted(s)
        memo = lambda: logcache.memo(s.conn, "probe", "nhl", (2025, 2024), compute, force=True)
        assert memo() == {"n": 1}
        night = [_row("nhl", 2025, "2025-11-03", p, m, v, team=t, game="g20253")
                 for p, t in (("Connor McDavid", "EDM"), ("Nazem Kadri", "CGY"))
                 for m, v in (("sog", 3), ("points", 1), ("toi", 20.5))]
        for _ in range(3):
            db.upsert_player_logs(s.conn, night)
            s.conn.commit()
            assert memo() == {"n": 1}, "a night already on file, read again, changes nothing"
        db.upsert_player_logs(s.conn, [dict(night[0], value=4)])
        s.conn.commit()
        assert memo() == {"n": 2}, "a stat the league corrected is a change"


def _note_of(name="probe", sport="nhl"):
    return logcache.status().get(f"{name}.{sport}") or {}


def test_each_read_notes_what_it_did_and_why():
    with _Sandbox() as s:
        _seed(s.conn)
        src = Path(s.dir) / "computer.py"
        src.write_text("VERSION = 1\n")
        calls, compute = _counted(s)
        memo = lambda: logcache.memo(s.conn, "probe", "nhl", (2025, 2024), compute, code=str(src),
                                     force=True)
        assert logcache.status() == {}, "nothing noted before the first read"
        memo()
        n = _note_of()
        assert n["kept"] is False and n["why"] == "no copy", n
        assert n["seasons"] == [2024, 2025] and n["rows"] == 60, n
        assert {"key_s", "read_s", "store_s", "mb", "at"} <= set(n), n
        memo()
        n = _note_of()
        assert n["kept"] is True and "why" not in n and {"key_s", "load_s", "mb"} <= set(n), n
        db.upsert_player_logs(s.conn, [_row("nhl", 2025, "2025-11-09", "Connor McDavid", "sog", 6)])
        s.conn.commit()
        memo()
        assert _note_of()["why"] == "rows changed", _note_of()
        src.write_text("VERSION = 2\n")
        memo()
        assert _note_of()["why"] == "code changed", _note_of()
        folder = Path(logcache.folder())
        next(folder.glob("probe-nhl-*.pkl")).write_bytes(b"not a pickle")
        memo()
        assert _note_of()["why"] == "unreadable", _note_of()
        logcache.memo(s.conn, "probe", "nba", (2025,), compute, force=True)
        assert set(logcache.status()) == {"probe.nhl", "probe.nba"}, "one entry per read and sport"
        assert len(calls) == 5


def test_a_note_that_cannot_be_written_says_so_once_and_costs_nothing():
    import contextlib
    import io
    with _Sandbox() as s:
        _seed(s.conn)
        calls, compute = _counted(s)
        seasons = [2024, 2025]
        pkl = logcache._path("probe", "nhl", seasons, logcache.db_file(s.conn))
        os.makedirs(pkl[:-len(".pkl")] + ".json")          # a folder where the note goes
        keep = logcache._NOTE_FAILED[0]
        logcache._NOTE_FAILED[0] = False
        said = io.StringIO()
        try:
            with contextlib.redirect_stdout(said):
                first = logcache.memo(s.conn, "probe", "nhl", seasons, compute, force=True)
                again = logcache.memo(s.conn, "probe", "nhl", seasons, compute, force=True)
        finally:
            logcache._NOTE_FAILED[0] = keep
        assert first == again == {"n": 1} and len(calls) == 1, "stored and served all the same"
        lines = [ln for ln in said.getvalue().splitlines() if "not noted" in ln]
        assert len(lines) == 1 and "kept game-log read not noted" in lines[0], said.getvalue()
        assert logcache.status() == {}, "nothing noted, and nothing made up"
    keep_folder = logcache.folder
    with tempfile.NamedTemporaryFile() as fh:
        logcache.folder = lambda: fh.name                    # a file where the folder goes
        try:
            assert logcache.status() == {"error": "NotADirectoryError"}, \
                "notes that cannot be listed say so, not 'nothing yet'"
        finally:
            logcache.folder = keep_folder


def test_the_heartbeat_carries_each_kept_reads_note():
    src = (ROOT / "launch.py").read_text()
    beat = src[src.index("def _write_heartbeat("):]
    beat = beat[:beat.index("os.replace(tmp, p)")]
    assert '"logcache": _logcache_public()' in beat
    import launch
    with _Sandbox() as s:
        _seed(s.conn)
        logcache.memo(s.conn, "probe", "nhl", (2025,), lambda: {}, force=True)
        got = launch._logcache_public()
        assert list(got) == ["probe.nhl"] and got["probe.nhl"]["why"] == "no copy", got
        json_safe = __import__("json").dumps(got)
        assert s.dir not in json_safe, "no path of the box goes on the public heartbeat"
    keep = logcache.status
    logcache.status = lambda: 1 / 0
    try:
        assert launch._logcache_public() == {}, "a side read never fails the heartbeat"
    finally:
        logcache.status = keep


def test_a_delete_lets_a_rowid_come_back_so_it_forgets():
    with _Sandbox() as s:
        _seed(s.conn)
        calls, compute = _counted(s)
        memo = lambda: logcache.memo(s.conn, "probe", "nhl", (2025, 2024), compute, force=True)
        memo()
        key = logcache.scope_key(s.conn, "nhl", (2025, 2024))
        top = s.conn.execute("SELECT MAX(rowid) FROM player_game_logs").fetchone()[0]
        s.conn.execute("DELETE FROM player_game_logs WHERE rowid IN (?, ?)", (top, top - 1))
        s.conn.commit()
        db.upsert_player_logs(s.conn, [_row("nhl", 2025, "2025-11-09", "Connor McDavid", "sog", 6),
                                       _row("nba", 2025, "2025-11-02", "Nikola Jokic", "points", 28,
                                            team="DEN")])
        s.conn.commit()
        assert logcache.scope_key(s.conn, "nhl", (2025, 2024)) == key, "a freed rowid came back"
        assert memo() == {"n": 1}, "the trap: the same key over different rows"
        assert logcache.forget("nhl") == 1 and logcache.forget("nhl") == 0
        logcache.memo(s.conn, "probe", "nba", (2025,), compute, force=True)
        assert memo() == {"n": len(calls)} and len(calls) == 3, "forgotten, so read again"
        assert logcache.forget("nba") == 1, "one sport at a time"


def test_every_delete_or_update_in_place_forgets():
    """The three paths that take game-log rows away or relabel them."""
    from engine import seasons
    for path, body_of in (("engine/boxsettle.py", "def ingest_for_open("),
                          ("engine/ledger.py", "def repair_premature("),
                          ("engine/seasons.py", "def relabel(")):
        src = (ROOT / path).read_text()
        body = src[src.index(body_of):]
        body = body[:body.index("\ndef ", 1)]
        assert "logcache.forget(" in body, path
    with _Sandbox() as s:
        db.upsert_player_logs(s.conn, [_row("nba", 2027, "2026-03-01", "Nikola Jokic", "points", 31,
                                            team="DEN")])
        s.conn.commit()
        calls, compute = _counted(s)
        logcache.memo(s.conn, "probe", "nba", (2026, 2027), compute, force=True)
        assert seasons.relabel(s.conn, "nba", apply=True)["player_game_logs"]["wrong"] == 1
        assert logcache.memo(s.conn, "probe", "nba", (2026, 2027), compute, force=True) == {"n": 2}, \
            "a relabel keeps the rows and their rowids, and the read is forgotten"


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
