"""Every chart reads its player's own rows (step AGO, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". The history file carries no statistics for SQLite to plan by, and a read of one player's
season sorted by its games (ORDER BY period ...) was planned off the table's own key, (sport, season, period,
game_id, play_id), which is in that order: every play of the league's season, read to keep his. The role chart's
two reads were the worst of it (step AGN: Nikita Kucherov's 22.6 s, Juan Soto's 32.8 s). The same shape stood in the
carry chart's read of his carries, and in the carry, route, passing and kicking charts' read of his position and
number. Each is now pinned to the index that leads with the player (engine/db.pinned), and a file without that
index reads as before.

Offline. Run directly: `python3 tests/test_every_chart_reads_its_players_own_rows.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D  # noqa: E402

READS = [  # (module, table, the read as the module runs it, its arguments)
    ("engine/carries.py", "carries",
     "SELECT * FROM carries{hint} WHERE sport=? AND player=? AND season=? ORDER BY period, game_id",
     ("nfl", "Jahmyr Gibbs", 2026)),
    ("engine/carries.py", "carries",
     "SELECT position, jersey FROM carries{hint} WHERE sport=? AND player=? AND season=? "
     "AND position != '' ORDER BY period DESC LIMIT 1", ("nfl", "Jahmyr Gibbs", 2026)),
    ("engine/targets.py", "targets",
     "SELECT position, jersey FROM targets{hint} WHERE sport=? AND player=? AND season=? "
     "AND position != '' ORDER BY period DESC LIMIT 1", ("nfl", "Amon-Ra St. Brown", 2026)),
    ("engine/passes.py", "passes",
     "SELECT position, jersey FROM passes{hint} WHERE sport=? AND player=? AND season=? "
     "AND position != '' ORDER BY period DESC LIMIT 1", ("nfl", "Jared Goff", 2026)),
    ("engine/kicks.py", "kicks",
     "SELECT position, jersey FROM kicks{hint} WHERE sport='nfl' AND player=? AND season=? "
     "AND position != '' ORDER BY period DESC LIMIT 1", ("Jake Bates", 2026)),
]


def _plan(conn, sql, args, index=None):
    if index:
        rows = D.pinned(conn, "EXPLAIN QUERY PLAN " + sql, index, args).fetchall()
    else:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql.format(hint=""), args).fetchall()
    return " ".join(str(r[3]) for r in rows)


def test_each_read_goes_by_the_index_that_leads_with_the_player():
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    for module, table, sql, args in READS:
        src = (ROOT / module).read_text(encoding="utf-8")
        assert f'"{table}_player"' in src and sql.split("{hint}")[0] in src, (module, sql[:60])
        unpinned = _plan(conn, sql, args)
        assert "autoindex" in unpinned, ("the shape this step is about: planned off the table's key", unpinned)
        pinned = _plan(conn, sql, args, f"{table}_player")
        assert f"INDEX {table}_player" in pinned and "autoindex" not in pinned, pinned


def test_a_file_without_the_index_reads_as_before():
    conn = D.connect(os.path.join(tempfile.mkdtemp(), "history.db"))
    conn.execute("DROP INDEX carries_player")
    sql, args = READS[0][2], READS[0][3]
    assert D.pinned(conn, sql, "carries_player", args).fetchall() == []
    assert "INDEX carries_player" not in _plan(conn, sql, args)


def test_the_role_chart_reads_through_the_same_pin():
    src = (ROOT / "engine" / "role.py").read_text(encoding="utf-8")
    assert "from .db import pinned" in src and "return pinned(conn, sql, index, args).fetchall()" in src


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
