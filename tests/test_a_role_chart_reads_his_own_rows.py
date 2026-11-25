"""A role chart reads the player's own rows, not the league's (step AGN, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". The role chart asks for a player's seasons, then one season's games in order, over a list of
markets. With no statistics on the file to plan by, SQLite read both off the table's own key (sport, season,
period, ...), whose order those reads ask for: his seasons off every row the league has, and his season's games off
every row of the league's season. Nikita Kucherov's role chart took 22.6 s on the live site and Juan Soto's 32.8 s.
Both are now read by the player's own indexes (engine/role._pinned): on 2.6 million hockey rows here, the chart's
217 ms became 1 ms, the same chart. A file without those indexes reads as before.

Offline. Run directly: `python3 tests/test_a_role_chart_reads_his_own_rows.py`
"""
import json
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D, role as R  # noqa: E402


def _history(indexes=True):
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    conn = D.connect(path)
    rnd = random.Random(5)
    rows = []
    for season in (2025, 2026):
        for p in range(30):
            for g in range(12):
                for m in ("sog", "toi", "goals", "assists", "hits"):
                    rows.append(("nhl", season, f"{season}-11-{g + 1:02d}", f"g{season}{g}{p // 2}", f"Player {p}",
                                 f"T{p % 8}", f"T{(p + 1) % 8}", "F", g % 2, m, float(rnd.randint(0, 20))))
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    if not indexes:
        conn.execute("DROP INDEX idx_logs_player")
        conn.execute("DROP INDEX idx_logs_lookup")
    conn.commit()
    return conn


class _Seen:
    """A connection that keeps every statement it ran, with its arguments."""
    def __init__(self, conn):
        self.conn, self.ran = conn, []

    def execute(self, sql, args=()):
        self.ran.append((sql, tuple(args)))
        return self.conn.execute(sql, args)


def _plan(conn, sql, args):
    return " ".join(str(r[3]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args))


def test_his_seasons_and_his_games_are_read_off_his_own_rows():
    conn = _history()
    seen = _Seen(conn)
    out = R.chart(seen, "nhl", "Player 7")
    assert out["seasons"] == [2026, 2025] and len(out["games"]) == 12, out.get("seasons")
    seasons = next((s, a) for s, a in seen.ran if s.startswith("SELECT DISTINCT season"))
    logged = next((s, a) for s, a in seen.ran if s.startswith("SELECT period, game_id, team"))
    assert "COVERING INDEX idx_logs_lookup" in _plan(conn, *seasons), _plan(conn, *seasons)
    assert "INDEX idx_logs_player" in _plan(conn, *logged), _plan(conn, *logged)
    for sql, args in (seasons, logged):
        assert "autoindex" not in _plan(conn, sql, args), "never the table's own key: every row of the league"


def test_the_chart_is_the_one_the_planners_own_read_gave():
    conn = _history()
    pinned = R.chart(conn, "nhl", "Player 7")
    real = R._pinned
    R._pinned = lambda c, sql, index, args: c.execute(sql.format(hint=""), args).fetchall()
    try:
        planned = R.chart(conn, "nhl", "Player 7")
    finally:
        R._pinned = real
    assert json.dumps(pinned, sort_keys=True) == json.dumps(planned, sort_keys=True)


def test_a_file_without_the_indexes_reads_as_before_and_says_the_same():
    a = R.chart(_history(True), "nhl", "Player 7")
    b = R.chart(_history(False), "nhl", "Player 7")
    assert a and json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


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
