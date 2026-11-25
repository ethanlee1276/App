"""A college game report counts each game once (step AFJ, 25 November 2026).

A game report quotes a player's form: his last games, his season's totals and how often he cleared a number ("6+
catches in 5 of 8", engine/gamereport.hit_lines), all read by engine/reportdata.player_form. Its rows were keyed by
day, and a college game can be stored on two days or under two codes for the opponent (step AFE: Miami of Ohio's game
against Buffalo as "BUFF" on 3 November and "BUF" on the 4th), so a report could count a game twice where the player
page's game log, the market cards and the college model count it once. The report's read now merges the same way
(engine/gamelog.once); the NFL's reads as before.

Offline. Run directly: `python3 tests/test_a_college_report_counts_each_game_once.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import db, reportdata  # noqa: E402


def _rows(sport, player, team, opp, home, period, gid, season=2026, **stats):
    return [{"sport": sport, "season": season, "period": period, "game_id": gid, "player": player, "team": team,
             "opponent": opp, "position": "WR", "home": home, "market": m, "value": float(v)} for m, v in stats.items()]


def _conn():
    path = os.path.join(tempfile.mkdtemp(), "history.db")
    rows = []
    rows += _rows("cfb", "Scoop Smith", "M-OH", "BUFF", 1, "2026-11-03", "401", receptions=3, rec_yds=42)
    rows += _rows("cfb", "Scoop Smith", "M-OH", "BUF", 1, "2026-11-04", "BUF@M-OH-box", receptions=3, rec_yds=42)
    rows += _rows("cfb", "Scoop Smith", "M-OH", "SAC", 0, "2026-10-30", "402", receptions=6, rec_yds=70)
    rows += _rows("cfb", "Scoop Smith", "M-OH", "SAC", 0, "2026-10-31", "402", receptions=6, rec_yds=70)
    rows += _rows("cfb", "Scoop Smith", "M-OH", "WMU", 0, "2026-11-24", "403", receptions=4, rec_yds=77)
    rows += _rows("cfb", "Scoop Smith", "M-OH", "KENT", 0, "2026-11-18", "404", receptions=1, rec_yds=18)
    # An NFL week stays a week.
    rows += _rows("nfl", "Test End", "CIN", "PIT", 1, "010", "CIN-010", receptions=5, rec_yds=50)
    rows += _rows("nfl", "Test End", "CIN", "BAL", 0, "011", "CIN-011", receptions=6, rec_yds=60)
    conn = db.connect(path)
    db.upsert_player_logs(conn, rows)
    conn.commit()
    return conn


def test_the_report_reads_each_college_game_once():
    conn = _conn()
    try:
        got = reportdata._player_form(conn, 2026, {"Scoop Smith": "M-OH"}, sport="cfb")["Scoop Smith"]
    finally:
        conn.close()
    assert got["season"]["games"] == 4, got["season"]
    assert got["season"]["s"]["receptions"] == 14.0 and got["season"]["s"]["rec_yds"] == 207.0
    days = [g["wk"] for g in got["log"]]
    assert days == ["2026-11-24", "2026-11-18", "2026-11-03", "2026-10-30"], days
    assert [g["opp"] for g in got["log"]] == ["WMU", "KENT", "BUFF", "SAC"]
    assert [g["day"] for g in got["games"]] == ["2026-11-24", "2026-11-18", "2026-11-03"]
    assert all(g["where"] in ("home", "away") for g in got["games"])


def test_the_nfl_reads_as_before():
    conn = _conn()
    try:
        got = reportdata._player_form(conn, 2026, {"Test End": "CIN"}, sport="nfl")["Test End"]
    finally:
        conn.close()
    assert got["season"]["games"] == 2 and [g["wk"] for g in got["log"]] == [11, 10]
    assert reportdata._one_game_once("nfl", [{"x": 1}, {"x": 2}]) == [{"x": 1}, {"x": 2}]


def test_the_kept_read_is_keyed_on_the_merge():
    assert any(str(p).endswith("gamelog.py") for p in reportdata._FORM_CODE)


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
