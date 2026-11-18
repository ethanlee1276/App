"""A college chart's games take the box score's side (2026-11-18, walk 15, step YE).

Arch Manning's passing chart read "Nov 15 vs TEX", "Oct 24 @ TEX" and "Oct 17
@ TEX" under a Previous game card at LSU: the college play file names a play's
school, matched to the stored game by name (sources.cfbstats._side_of), and in
four of Texas's games the match landed on the other side. Each chart (passes,
carries, targets, role) now takes a game's side from the player's own box
score row when the box has the same two schools the other way round; a game
the box does not hold, or holds against someone else, is left alone, and the
NFL's charts are untouched.

    python3 tests/test_a_college_chart_game_takes_the_box_scores_side.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import carries                                                       # noqa: E402


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, period TEXT, game_id TEXT, player TEXT, "
                  "team TEXT, opponent TEXT, home INT, market TEXT, value REAL)")
    conn.execute("CREATE TABLE games (sport TEXT, season INT, period TEXT, home TEXT, away TEXT, "
                  "home_score REAL, away_score REAL)")
    for day, opp, home in (("2026-11-15", "LSU", 0), ("2026-11-07", "MIZ", 0), ("2026-10-17", "FLA", 1)):
        for market, value in (("pass_yds", 174.0), ("pass_att", 35.0)):
            conn.execute("INSERT INTO player_game_logs VALUES ('cfb', 2026, ?, ?, 'Arch Manning', 'TEX', ?, ?, ?, ?)",
                         (day, f"g{day}", opp, home, market, value))
    conn.execute("INSERT INTO games VALUES ('cfb', 2026, '2026-11-15', 'LSU', 'TEX', 21, 22)")
    conn.commit()
    return conn


def test_a_flipped_game_takes_the_box_scores_side():
    games = [{"date": "2026-11-15", "period": "2026-11-15", "team": "LSU", "opp": "TEX", "home": True},
             {"date": "2026-11-07", "period": "2026-11-07", "team": "TEX", "opp": "MIZ", "home": False},
             {"date": "2026-10-17", "period": "2026-10-17", "team": "FLA", "opp": "TEX", "home": False},
             {"date": "2026-10-10", "period": "2026-10-10", "team": "OU", "opp": "TEX", "home": False},   # not in the box
             {"date": "2026-11-07", "period": "2026-11-07", "team": "TEX", "opp": "OSU", "home": True}]   # other schools
    carries.scoreboard(_conn(), "cfb", 2026, games, player="Arch Manning")
    sides = [(g["team"], g["opp"], g["home"]) for g in games]
    assert sides == [("TEX", "LSU", False), ("TEX", "MIZ", False), ("TEX", "FLA", True),
                     ("OU", "TEX", False), ("TEX", "OSU", True)], sides
    assert games[0]["score"] == [22.0, 21.0], "the final reads from the player's side once the side is right"


def test_the_nfl_and_a_chart_without_a_player_are_untouched():
    nfl = [{"date": "2026-11-15", "period": "11", "team": "LSU", "opp": "TEX", "home": True}]
    carries.own_side(_conn(), "nfl", 2026, "Arch Manning", nfl)
    assert nfl[0]["team"] == "LSU"
    cfb = [{"date": "2026-11-15", "period": "2026-11-15", "team": "LSU", "opp": "TEX", "home": True}]
    carries.own_side(_conn(), "cfb", 2026, "", cfb)
    assert cfb[0]["team"] == "LSU"


def test_every_chart_hands_the_scoreboard_its_player():
    for f in ("engine/carries.py", "engine/passes.py", "engine/targets.py", "engine/role.py"):
        body = (ROOT / f).read_text(encoding="utf-8")
        assert "scoreboard(conn, sport, pick, " in body and ", player=name)" in body, f


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
