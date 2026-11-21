"""A college football game filed more than once counts once in the standings
(USEREYES1, 18 November 2026).

The live college football standings, counted from our own games because the
league's feed answered with no teams, read Utah 19-0 and Ohio State 16-7 in
the middle of November: 1,122 finished games counted where about 700 were
played. College's games table holds copies of one game from three writers
(engine/cfbdedupe names them and removes the copies with --apply, step TM's
command 00h), and the table, its unit rankings and the pressure ranks beside
it counted every copy. What these hold:

  * one pair of schools' rows a day or less apart are one game, the
    schedule's away@home row kept (cfbdedupe's choice), whatever the copies'
    ids, days or a provisional copy's partial score;
  * a real rematch weeks later (a conference title game) is a second game;
  * the table, the season simulation's games, the pressure ranks and a
    team's page all read the games once; every other league's rows are as
    they were.

    python3 tests/test_a_college_game_filed_twice_counts_once_in_the_standings.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, pressure, standings                                    # noqa: E402


def _conn(rows):
    c = db.connect(":memory:")
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score) "
                  "VALUES (?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return c


ROWS = [
    # One game, three copies: ESPN's number on the Eastern day, the schedule's
    # away@home a day later, and a provisional copy read mid-game.
    ("cfb", 2026, "2026-10-04", "401858249", "UTAH", "ASU", 31, 17),
    ("cfb", 2026, "2026-10-05", "ASU@UTAH", "UTAH", "ASU", 31, 17),
    ("cfb", 2026, "2026-10-04", "ASU@UTAH-box", "UTAH", "ASU", 14, 10),
    # Another game, filed twice, the copy with the sides the other way round.
    ("cfb", 2026, "2026-10-11", "BYU@UTAH", "UTAH", "BYU", 24, 21),
    ("cfb", 2026, "2026-10-11", "401858300", "BYU", "UTAH", 21, 24),
    # The same two schools again in December: a title game, a second game.
    ("cfb", 2026, "2026-12-05", "BYU@UTAH-ccg", "UTAH", "BYU", 20, 27),
    # The NFL's rows are as they were.
    ("nfl", 2026, "001", "2026_01_DAL_PHI", "PHI", "DAL", 24, 20),
]


def test_one_pair_a_day_apart_is_one_game_and_a_rematch_is_two():
    c = _conn(ROWS)
    got = standings._finished(c, "cfb", [2026])
    ids = [r["game_id"] for r in got]
    assert ids == ["ASU@UTAH", "BYU@UTAH", "BYU@UTAH-ccg"], ids
    assert [r["game_id"] for r in standings._finished(c, "nfl", [2026])] == ["2026_01_DAL_PHI"]
    assert standings.once("nba", [{"period": "2026-11-01", "home": "BOS", "away": "NYK"}] * 2) == \
        [{"period": "2026-11-01", "home": "BOS", "away": "NYK"}] * 2, "only the leagues that file copies"


def test_the_table_the_simulation_and_the_pressure_ranks_count_it_once():
    c = _conn(ROWS)
    table = standings.compute(c, "cfb", 2026, today="2026-12-10")
    rec = {t["team"]: (t["wins"], t["losses"]) for t in standings.team_rows(table)}
    assert rec["UTAH"] == (2, 1) and rec["BYU"] == (1, 1) and rec["ASU"] == (0, 1), rec
    assert table["games_counted"] == 3
    assert len(standings.season_games(c, "cfb", 2026)) == 3
    assert len(pressure._rows(c, "cfb", 2026)) == 3
    src = (ROOT / "engine" / "pressure.py").read_text(encoding="utf-8")
    assert "return once(sport, conn.execute(" in src


def test_the_team_page_lists_each_game_once():
    from engine import teamdex
    c = _conn(ROWS)
    assert len(teamdex._finals(c, "cfb")) == 3
    sched = teamdex.season_schedule(c, "cfb", "UTAH", 2026)
    assert [g.get("game_id") for g in sched["games"]] == ["ASU@UTAH", "BYU@UTAH", "BYU@UTAH-ccg"], sched["games"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
