"""A name a chart's table does not hold costs a lookup, not the table (step AGR, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". A chart asked for a spelling its table does not keep folded every stored name on every ask,
and the empty answer was never kept, so every visit read it all again: on the live site a college basketball shot
chart took 20.3 s (it read every shot of the table for its shooter's id), a college role chart 6.9 s and an NBA one
1.2 s. Now:

  * each chart table's names are read once, off its name index, and kept folded (engine/db.folded_names); a
    basketball shot chart reads ids for the folded matches alone (since step AGW the list grows by the table's new
    rows and is kept on disk across restarts: tests/test_a_chart_name_list_grows_and_survives_a_restart.py);
  * the role chart finds its player by the player page's own rule (playerpage.stored_name, off the search's kept
    list of names), so a chart under a page means the player the page means.

Offline. Run directly: `python3 tests/test_a_name_a_chart_does_not_hold_costs_a_lookup.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import carries, db as D, kicks, passes, role, targets  # noqa: E402
from engine.nba import shots as S  # noqa: E402


class _Seen:
    """A connection that keeps every statement it ran."""
    def __init__(self, conn):
        self.conn, self.sql = conn, []

    def execute(self, sql, args=()):
        self.sql.append(sql)
        return self.conn.execute(sql, args)


def _history():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    return D.connect(path)


SHOT_COLS = ("game_id, action, season, date, person_id, player, team, opponent, home, period, clock, kind, made, shot, "
             "descriptor, distance, x, y, zone, area, assist, blocked, quals")


def _shot(conn, table, gid, act, pid, name):
    conn.execute(f"INSERT INTO {table} ({SHOT_COLS}) VALUES (?,?,2026,'2026-11-20',?,?,'DEN','LAL',1,1,'',"
                 "'2pt',1,'','',5.0,1.0,1.0,'paint','','',0,'')", (gid, act, pid, name))
    conn.commit()


def test_the_names_are_kept_per_file_until_the_table_gains_a_row():
    conn = _history()
    D._FOLDED_NAMES.clear()
    _shot(conn, "nba_shots", "g1", 1, 203999, "Nikola Jokić")
    seen = _Seen(conn)
    first = D.folded_names(seen, "nba_shots", "", (), str.lower)
    again = D.folded_names(seen, "nba_shots", "", (), str.lower)
    assert again is first and first == {"nikola jokić": ["Nikola Jokić"]}
    assert sum("SELECT DISTINCT player" in s for s in seen.sql) == 1, "read once"
    _shot(conn, "nba_shots", "g1", 2, 1629029, "Luka Dončić")
    third = D.folded_names(seen, "nba_shots", "", (), str.lower)
    assert "luka dončić" in third and sum("SELECT DISTINCT player" in s for s in seen.sql) == 2, "a row since: read"
    mem = D.connect(":memory:")
    D.folded_names(mem, "nba_shots", "", (), str.lower)
    assert all(k[0] for k in D._FOLDED_NAMES), "a database in memory is never kept"
    D._FOLDED_NAMES.clear()


def test_a_shot_chart_reads_ids_for_the_folded_matches_alone():
    for table, league in (("nba_shots", "nba"), ("cbb_shots", "cbb")):
        conn = _history()
        D._FOLDED_NAMES.clear()
        for i in range(30):
            _shot(conn, table, f"g{i}", i, 1000 + i % 3, f"Player {i % 3}")
        _shot(conn, table, "gx", 99, 203999, "Nikola Jokić")
        seen = _Seen(conn)
        assert S.resolve(seen, "Nikola Jokic", league) == (203999, "Nikola Jokić"), "a spelling without its accent"
        assert S.resolve(seen, "Cooper Flagg", league) == (None, ""), "a name the table does not hold"
        assert S.resolve(seen, "Cooper Flagg", league) == (None, "")
        every = [s for s in seen.sql if "DISTINCT person_id" in s]
        assert every and all("WHERE player=?" in s for s in every), "never every shot for its shooter's id"
        assert sum("SELECT DISTINCT player FROM" in s for s in seen.sql) == 1, "the names read once"
    D._FOLDED_NAMES.clear()


def _play(conn, table, player, sport="nfl"):
    if table == "kicks":
        conn.execute("INSERT INTO kicks (sport, season, period, game_id, play_id, player) VALUES (?,?,?,?,?,?)",
                     (sport, 2026, "011", "g1", f"p{player}", player))
    else:
        conn.execute(f"INSERT INTO {table} (sport, season, period, game_id, play_id, player) VALUES (?,?,?,?,?,?)",
                     (sport, 2026, "011", "g1", f"p{player}", player))
    conn.commit()


def test_the_play_charts_fold_a_spelling_off_their_kept_names():
    D._FOLDED_NAMES.clear()
    # carries.resolve takes (sport, player); targets' and passes' take (player, sport).
    for mod, table, ask in ((carries, "carries", lambda c, n: carries.resolve(c, "nfl", n)),
                            (targets, "targets", lambda c, n: targets.resolve(c, n, "nfl")),
                            (passes, "passes", lambda c, n: passes.resolve(c, n, "nfl"))):
        conn = _history()
        _play(conn, table, "Ja'Marr Chase")
        seen = _Seen(conn)
        assert ask(seen, "Ja'Marr Chase") == "Ja'Marr Chase", table
        assert ask(seen, "JA'MARR CHASE Jr.") == "Ja'Marr Chase", (table, "case and a suffix folded")
        assert ask(seen, "Nobody Here") == "" and ask(seen, "Nobody Here") == ""
        assert sum(f"SELECT DISTINCT player FROM {table}" in s for s in seen.sql) == 1, (table, "the names read once")
    conn = _history()
    _play(conn, "kicks", "Ka'imi Fairbairn")
    seen = _Seen(conn)
    assert kicks.resolve(seen, "Kaimi Fairbairn") == "Ka'imi Fairbairn"
    kicks.resolve(seen, "Nobody Here")
    kicks.resolve(seen, "Nobody Here")
    assert sum("SELECT DISTINCT player FROM kicks" in s for s in seen.sql) == 1
    D._FOLDED_NAMES.clear()


def test_the_role_chart_finds_its_player_by_the_pages_own_rule():
    conn = _history()
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
                     "home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     [("nfl", 2026, "011", "g1", "Nolan Smith", "PHI", "DAL", "LB", 1, "tackles", 5.0),
                      ("nfl", 2026, "011", "g1", "Ja'Marr Chase", "CIN", "PIT", "WR", 0, "receptions", 8.0)])
    conn.commit()
    seen = _Seen(conn)
    assert role.resolve(seen, "nfl", "Nolan Smith Jr.") == "Nolan Smith", "a suffix spelled or not, as the page has it"
    assert role.resolve(seen, "nfl", "Ja'Marr Chase") == "Ja'Marr Chase"
    assert role.resolve(seen, "nfl", "Cooper Flagg") == ""
    assert not any(s.strip().startswith("SELECT DISTINCT player FROM player_game_logs WHERE sport=?")
                   and "IN (" not in s for s in seen.sql), "never every name the league has logged, folded"
    src = (ROOT / "engine" / "role.py").read_text(encoding="utf-8")
    assert "from .playerpage import stored_name" in src


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
