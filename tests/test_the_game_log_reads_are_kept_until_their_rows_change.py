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
