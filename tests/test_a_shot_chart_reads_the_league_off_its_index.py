"""A shot chart reads the league's zones off their index (step AGL, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". A basketball shot chart sets each zone beside the league's percentage there, and read it by
every shot's kind: each row of the season, a college season's hundreds of thousands, for every chart built (a
college basketball shot chart took 4.0 s on the live site). Only a field goal has a zone (a free throw's is "", as
is a game's empty marker's), so the shots with a zone are the field goals and the (season, zone, made) index
answers alone: the same numbers. The league's zones are kept half an hour per database file; the matchup's zones
by defense read their own index the same way.

Offline. Run directly: `python3 tests/test_a_shot_chart_reads_the_league_off_its_index.py`
"""
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as D, matchview as MV  # noqa: E402
from engine.nba import shots as S  # noqa: E402

COLS = ("game_id, action, season, date, person_id, player, team, opponent, home, period, clock, kind, made, shot, "
        "descriptor, distance, x, y, zone, area, assist, blocked, quals")
ZONES = ("rim", "paint", "mid", "corner3", "above3")


def _shots(table="cbb_shots", n_games=40):
    d = tempfile.mkdtemp()
    path = Path(d) / "history.db"
    conn = D.connect(path)
    rnd = random.Random(7)
    rows = []
    for g in range(n_games):
        rows.append((f"g{g}", -1, 2026, "2026-11-20", None, "", "", "", 0, 0, "", "none", 0, "", "", None, None,
                     None, "", "", "", 0, ""))                                   # a game's empty marker
        for a in range(60):
            k = rnd.random()
            kind = "ft" if k < 0.25 else ("3pt" if k < 0.6 else "2pt")
            zone = "" if kind == "ft" or rnd.random() < 0.03 else rnd.choice(ZONES)  # a field goal off the map: ""
            rows.append((f"g{g}", a, 2026, "2026-11-20", rnd.randint(1, 30), "P", "DUKE" if a % 2 else "UNC",
                         "UNC" if a % 2 else "DUKE", a % 2, 1, "", kind, rnd.randint(0, 1), "", "", 10.0, 1.0, 1.0,
                         zone, "", "", 0, ""))
    conn.executemany(f"INSERT INTO {table} ({COLS}) VALUES ({','.join('?' * 23)})", rows)
    conn.commit()
    return d, path, conn


def _by_kind(conn, table):
    """The league's zones the way they were read before: by every shot's kind."""
    out = {}
    for z, n, m in conn.execute(f"SELECT zone, COUNT(*), SUM(made) FROM {table} WHERE season=? "
                                "AND kind IN ('2pt', '3pt') GROUP BY zone", (2026,)):
        if z and n:
            out[z] = round((m or 0) / n, 3)
    return out


def test_the_league_zones_are_the_same_numbers_off_the_index_alone():
    for league, table in (("cbb", "cbb_shots"), ("nba", "nba_shots")):
        d, path, conn = _shots(table)
        try:
            S._LEAGUE.clear()
            got = S._league(conn, 2026, league)
            assert got == _by_kind(conn, table) and set(got) == set(ZONES), (league, got)
            sql = (f"SELECT zone, COUNT(*), SUM(made) FROM {table} WHERE season=? AND zone != '' GROUP BY zone")
            plan = " ".join(str(r[3]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, (2026,)))
            assert "COVERING INDEX" in plan, plan
            src = Path(S.__file__).read_text(encoding="utf-8")
            assert ('f"SELECT zone, COUNT(*), SUM(made) FROM {table} WHERE season=? AND zone != \'\' "' in src)
        finally:
            conn.close()
            shutil.rmtree(d, ignore_errors=True)


def test_they_are_kept_half_an_hour_per_database_file():
    d, path, conn = _shots()
    keep = S.LEAGUE_TTL
    try:
        S._LEAGUE.clear()
        first = S._league(conn, 2026, "cbb")
        conn.execute(f"INSERT INTO cbb_shots ({COLS}) VALUES ('x', 1, 2026, '2026-11-21', 1, 'P', 'DUKE', 'UNC', 1, 1, "
                     "'', '3pt', 1, '', '', 25.0, 1.0, 1.0, 'mid', '', '', 0, '')")
        conn.commit()
        assert S._league(conn, 2026, "cbb") == first, "kept"
        S._league(conn, 2026, "cbb")["mid"] = -1
        assert S._league(conn, 2026, "cbb") == first, "a caller's change never reaches the kept copy"
        S.LEAGUE_TTL = -1
        assert S._league(conn, 2026, "cbb") != first, "past its time, read again"
        assert S.LEAGUE_TTL == -1 and keep == 30 * 60
        mem = D.connect(":memory:")
        S._LEAGUE.clear()
        S.LEAGUE_TTL = keep
        S._league(mem, 2026, "cbb")
        assert not S._LEAGUE, "a database in memory is never kept"
        mem.close()
    finally:
        S.LEAGUE_TTL = keep
        S._LEAGUE.clear()
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


def test_the_matchups_zones_by_defense_read_their_index_alone_too():
    d, path, conn = _shots()
    try:
        MV._MEMO.clear()
        got = MV._nba(conn, 2026, "cbb")
        want: dict = {}
        for opp, zone, n, made in conn.execute("SELECT opponent, zone, COUNT(*), SUM(made) FROM cbb_shots WHERE "
                                               "season=? AND kind IN ('2pt', '3pt') GROUP BY opponent, zone", (2026,)):
            MV._add(want, opp, zone, n, float(made or 0))
        assert got == want and set(got) == {"DUKE", "UNC"}, got
        plan = " ".join(str(r[3]) for r in conn.execute(
            "EXPLAIN QUERY PLAN SELECT opponent, zone, COUNT(*), SUM(made) FROM cbb_shots WHERE season=? "
            "AND zone != '' GROUP BY opponent, zone", (2026,)))
        assert "COVERING INDEX" in plan, plan
    finally:
        MV._MEMO.clear()
        conn.close()
        shutil.rmtree(d, ignore_errors=True)


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
