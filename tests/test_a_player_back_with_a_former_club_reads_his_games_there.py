"""A receiver or back with a club he played for is read against his own games there (step ACK, 22 November 2026).

Ethan: "when they realize a QB or another player is back with the team they used to be on." The quarterback is
engine/qblean.reunion (tests/test_a_starter_back_with_a_former_club_reads_his_games_there.py); every other man is
engine/reunion, off the game logs. What these hold:

  * his games are read club by club, season by season, in one pass, kept until the logs change;
  * a man on a club now that he played for before playing elsewhere (four games there or more) has those games
    added up; one who never left, or never played there, has none; a quarterback's are qblean's;
  * the game's report says it, one line a man, the most games there first, three at most; words only.

    python3 tests/test_a_player_back_with_a_former_club_reads_his_games_there.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, reunion as R                              # noqa: E402


def _history():
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    rows = []

    def games(player, team, season, n, pos, **vals):
        for i in range(n):
            for m, v in vals.items():
                rows.append(("nfl", season, f"{season}-W{i + 1:02d}", f"{season}{team}{i}", player, team, "OPP", pos,
                             1, m, v))
    for yr in (2019, 2020, 2021):
        games("Old Hand", "MIN", yr, 16, "WR", receptions=5.0, rec_yds=60.0)
    games("Old Hand", "LV", 2022, 15, "WR", receptions=3.0, rec_yds=40.0)
    games("Old Hand", "MIN", 2026, 9, "WR", receptions=4.0, rec_yds=50.0)
    for yr in (2023, 2024):
        games("Back Field", "DET", yr, 10, "RB", rush_att=12.0, rush_yds=55.0, receptions=1.0, rec_yds=8.0)
    games("Back Field", "CHI", 2025, 12, "RB", rush_att=8.0, rush_yds=30.0)
    games("Back Field", "DET", 2026, 5, "RB", rush_att=10.0, rush_yds=40.0)
    games("Stayed Put", "MIN", 2024, 16, "WR", receptions=6.0, rec_yds=80.0)
    games("Stayed Put", "MIN", 2026, 9, "WR", receptions=6.0, rec_yds=80.0)
    games("Short Stay", "SF", 2023, 3, "TE", receptions=2.0, rec_yds=20.0)
    games("Short Stay", "NYJ", 2024, 10, "TE", receptions=2.0, rec_yds=20.0)
    games("Short Stay", "SF", 2026, 9, "TE", receptions=2.0, rec_yds=20.0)
    games("Kirk Cousins", "MIN", 2023, 8, "QB", pass_yds=290.0)
    games("Kirk Cousins", "LV", 2025, 8, "QB", pass_yds=250.0)
    games("Kirk Cousins", "MIN", 2026, 2, "QB", pass_yds=240.0)
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position,"
                     " home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_a_man_back_with_a_club_he_played_for_has_those_games_added_up():
    conn = _history()
    st = R.stints(conn)
    assert st["Old Hand"][2019]["MIN"] == (16, "WR") and st["Old Hand"][2022]["LV"] == (15, "WR")
    back = R.returning(st, "Old Hand", "MIN", 2026)
    assert back == {"team": "MIN", "seasons": [2019, 2020, 2021], "games": 48, "position": "WR"}, back
    assert R.line(conn, "Old Hand", back) == {"receptions": 5.0, "rec_yds": 60.0}
    assert R.returning(st, "Stayed Put", "MIN", 2026) is None, "never left"
    assert R.returning(st, "Short Stay", "SF", 2026) is None, "three games there are too few"
    assert R.returning(st, "Old Hand", "LV", 2026) is None, "not his club now"
    assert R.returning(st, "Nobody", "MIN", 2026) is None
    assert R.stints(conn) is st, "kept until the logs change"
    conn.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position,"
                 " home, market, value) VALUES ('nfl', 2026, '2026-W12', 'x', 'New Man', 'MIN', 'GB', 'WR', 1,"
                 " 'receptions', 3)")
    conn.commit()
    assert R.stints(conn) is not st and "New Man" in R.stints(conn)


def test_the_report_says_it_one_line_a_man():
    conn = _history()
    club = {"MIN": "the Vikings", "DET": "the Lions", "SF": "the 49ers"}.get
    lines = R.lines_for(conn, [("Back Field", "DET"), ("Old Hand", "MIN"), ("Stayed Put", "MIN"),
                               ("Kirk Cousins", "MIN"), ("Short Stay", "SF")], 2026, club)
    assert lines == [
        "Old Hand is back with the Vikings: in his 48 games for them (2019–2021) he caught 5.0 passes for 60 yards a "
        "game",
        "Back Field is back with the Lions: in his 20 games for them (2023–2024) he caught 1.0 passes for 8 yards "
        "and ran 12.0 times for 55 yards a game"], lines
    assert R.lines_for(conn, [("Old Hand", "MIN")] * 5, 2026, club, most=1) == lines[:1]
    assert R.lines_for(None, [("Old Hand", "MIN")], 2026, club) == []

    class Broken:
        def execute(self, *a):
            raise RuntimeError("no history")
    R._STINTS.clear()
    assert R.lines_for(Broken(), [("Old Hand", "MIN")], 2026, club) == []
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "    for line in _reunion_lines(c):\n        blocks.append(_p(line))" in gr
    assert "return reunion.lines_for(c.conn, players, int(c.season), club_words)" in gr


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
