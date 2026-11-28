"""A college game's stat lines are filed once (2026-11-14).

Ethan's catch-up run (step PU): Cooper Barkate's Miami games each sat two
and three times — the official row ("401858249"), the same-night box
score's copy under the schedule's key ("MIA@CLEM-box") and under ESPN's
("401858249-box") — and the Notre Dame game on two days, 92 yards in the
box score and 144 in the play file. 53,072 of 2026's 107,233 college keys
sat under two or more game ids, and grading voids a bet whose two rows of
one game fall either side of its line.

    python3 tests/test_a_college_game_is_filed_once.py
"""
import contextlib
import io
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boxsettle as BS                     # noqa: E402
from engine import cfbdedupe as D                      # noqa: E402
from engine import db                                  # noqa: E402


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    return conn


def _log(conn, season, period, gid, value, market="rec_yds", player="Cooper Barkate", team="MIA", opp="ND"):
    conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                 "position, home, market, value) VALUES ('cfb',?,?,?,?,?,?,'WR',0,?,?)",
                 (season, period, gid, player, team, opp, market, value))


def _barkate(conn):
    for gid in ("401858249", "401858249-box", "MIA@CLEM-box"):
        _log(conn, 2026, "2026-10-03", gid, 98.0, opp="CLEM")
    _log(conn, 2026, "2026-11-07", "401858291-box", 75.0)
    _log(conn, 2026, "2026-11-07", "MIA@ND-box", 92.0)
    _log(conn, 2026, "2026-11-08", "401858291", 144.0)
    _log(conn, 2026, "2026-11-08", "MIA@ND-box", 92.0)
    _log(conn, 2026, "2026-10-31", "401858282", 71.0, opp="UNC")          # filed once: untouched
    _log(conn, 2025, "2025-12-06", "401777328", 91.0, opp="DUKE")
    _log(conn, 2025, "2025-12-07", "401777328", 91.0, opp="DUKE")        # the title game, two days
    _log(conn, 2025, "2025-09-06", "401752825", 88.0, opp="DUKE")       # a different game, weeks apart


def test_each_game_keeps_its_official_row_and_loses_the_copies():
    conn = _conn()
    _barkate(conn)
    p26 = D.plan_logs(conn, 2026)
    assert p26["groups"] == 2 and len(p26["delete"]) == 5, p26
    assert p26["disagree"] == 1 and "kept 144, box [75.0, 92.0]" in p26["examples"][0], p26["examples"]
    p25 = D.plan_logs(conn, 2025)
    assert p25["groups"] == 1 and len(p25["delete"]) == 1, "the title game on two days is one game"
    D.apply(conn, p26, {"delete": [], "fill": []})
    D.apply(conn, p25, {"delete": [], "fill": []})
    left = conn.execute("SELECT season, period, game_id, value FROM player_game_logs ORDER BY season, period").fetchall()
    assert [tuple(r) for r in left] == [
        (2025, "2025-09-06", "401752825", 88.0), (2025, "2025-12-06", "401777328", 91.0),
        (2026, "2026-10-03", "401858249", 98.0), (2026, "2026-10-31", "401858282", 71.0),
        (2026, "2026-11-08", "401858291", 144.0)], [tuple(r) for r in left]


def test_a_game_in_the_games_table_three_times_is_kept_once_with_its_line():
    conn = _conn()
    for period, gid, spread in (("2026-11-07", "MIA@ND", None), ("2026-11-07", "401858291", -2.5),
                                ("2026-11-08", "MIA@ND", None)):
        conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                     "spread, extra) VALUES ('cfb', 2026, ?, ?, 'ND', 'MIA', 31, 24, ?, ?)",
                     (period, gid, spread, '{"espn_game_id": "401858291"}' if period == "2026-11-08" else None))
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                 "VALUES ('cfb', 2026, '2026-12-05', 'MIA@ND', 'ND', 'MIA', 17, 20)")        # a rematch
    plan = D.plan_games(conn, 2026)
    assert plan["pairs"] == 1 and len(plan["delete"]) == 2, plan
    D.apply(conn, {"delete": []}, plan)
    rows = conn.execute("SELECT period, game_id, spread, extra FROM games ORDER BY period").fetchall()
    assert [(r["period"], r["game_id"]) for r in rows] == [("2026-11-07", "MIA@ND"), ("2026-12-05", "MIA@ND")]
    assert rows[0]["spread"] == -2.5 and "401858291" in rows[0]["extra"], "the kept row takes what only the others had"


def test_the_command_writes_nothing_without_apply():
    import tempfile
    from engine import db as _db
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "h.db"
        conn = _db.connect(path)
        _barkate(conn)
        conn.commit()
        conn.close()
        was = _db.DEFAULT_DB
        orig = _db.connect
        _db.connect = lambda p=path: orig(path)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                D.main([])
            n_dry = orig(path).execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]
            with contextlib.redirect_stdout(io.StringIO()):
                D.main(["--apply"])
            n_after = orig(path).execute("SELECT COUNT(*) FROM player_game_logs").fetchone()[0]
        finally:
            _db.connect = orig
            _db.DEFAULT_DB = was
    assert "nothing written" in out.getvalue() and "5 row(s) to remove" in out.getvalue(), out.getvalue()
    assert n_dry == 11 and n_after == 5, (n_dry, n_after)


def test_the_box_settle_purges_a_college_game_by_its_teams():
    conn = _conn()
    _barkate(conn)
    g = {"season": 2026, "period": "2026-11-07", "game_id": "MIA@ND", "home": "ND", "away": "MIA"}
    assert BS.has_official_rows(conn, "cfb", g), "the official row is keyed by ESPN's number, a day later"
    assert BS.purge_provisional(conn, "cfb", g) == 3
    assert conn.execute("SELECT COUNT(*) FROM player_game_logs WHERE game_id LIKE '%-box' "
                        "AND period >= '2026-11-01'").fetchone()[0] == 0
    nfl = {"season": 2026, "period": "010", "game_id": "x", "home": "KC", "away": "BUF"}
    assert BS._official_ids("nfl", nfl) == ["KC-010", "BUF-010"], "the NFL's rule is untouched"


def test_one_college_game_is_one_provisional_copy():
    src = (ROOT / "engine" / "boxsettle.py").read_text(encoding="utf-8")
    assert "ONE COLLEGE GAME ONCE" in src
    ing = (ROOT / "engine" / "ingest.py").read_text(encoding="utf-8")
    i = ing.index("def cfb_games_for(")
    body = ing[i:ing.index("\ndef ", i + 10)]
    assert "ORDER BY period, game_id" in body
    # The ESPN number joins the pair's earliest standing row a day or less older (step AHV), else its own.
    assert "out.setdefault(espn_id, stood if stood is not entry and _within_a_day(stood, entry) else entry)" in body


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
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
