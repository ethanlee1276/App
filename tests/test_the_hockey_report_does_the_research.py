"""The hockey report does the research (2026-11-15).

Ethan: "I want our game reports for each game to be scanning for all that type
of data and matchup shit ... for every sport." The NHL report had the tape,
the goalies and the reads; what the research's game cards also carried was
who plays with whom with a regular out, and the last meeting. Now
(engine/leaguereport):

  * The lines: each team's top two forward lines and top defence pair, off
    the shift charts of its newest games with tonight's ruled-out men left
    out (the board's own `lines`, nhl_build.team_lines), how settled each
    is, and who they are built without;
  * The last meeting (hockey_meeting, filled by nhl_build on each game): the
    score and who scored for each side;
  * Each side's form (team_form, filled beside it): its last ten this season
    in goals, and its record where it plays tonight, at the top of the
    matchup.

    python3 tests/test_the_hockey_report_does_the_research.py
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as R                                   # noqa: E402
from engine import leaguereport as L                                 # noqa: E402


class _Fixtures:
    """The every-league report test's boards, imported when a test needs them."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_every_league_gets_a_game_report"), attr)


E = _Fixtures()

LINES = {"TOR": {"forwards": [{"players": ["Matthew Knies", "Auston Matthews", "Mitch Marner"], "together": 0.72},
                              {"players": ["William Nylander", "John Tavares", "Max Domi"], "together": 0.51}],
                 "defence": [{"players": ["Morgan Rielly", "Jake McCabe"], "together": 0.8}], "games": 5},
         "BOS": {"forwards": [{"players": ["David Pastrnak", "Elias Lindholm", "Pavel Zacha"], "together": 0.66}],
                 "defence": [{"players": ["Hampus Lindholm", "Brandon Carlo"], "together": 0.58}], "games": 5}}


def _conn():
    from engine import db as D
    conn = D.connect(Path(tempfile.mkdtemp()) / "history.db")
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                 "VALUES ('nhl', 2026, '2026-10-12', 'TOR@BOS', 'BOS', 'TOR', 2, 4, '2026-10-12')")
    conn.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, market, "
                     "value) VALUES ('nhl', 2026, '2026-10-12', 'TOR@BOS', ?, ?, ?, 'goals', ?)",
                     [("Auston Matthews", "TOR", "BOS", 2), ("Mitch Marner", "TOR", "BOS", 1),
                      ("William Nylander", "TOR", "BOS", 1), ("David Pastrnak", "BOS", "TOR", 2),
                      ("Brad Marchand", "BOS", "TOR", 0)])
    conn.commit()
    return conn


def _report():
    board = copy.deepcopy(E._nhl_board())
    board["lines"] = copy.deepcopy(LINES)
    board["games"][0]["last_meeting"] = L.hockey_meeting(_conn(), "TOR", "BOS", "2026-10-21")
    L.attach(board, "nhl")
    return board["game_reports"][0]


def test_the_lines_say_who_plays_with_whom_and_who_they_are_built_without():
    rep = _report()
    text = R.to_text(rep)
    assert "THE LINES" in text, text
    assert "Top line: Matthew Knies, Auston Matthews and Mitch Marner (together for 72% of their ice lately)." in text
    assert "Top pair: Morgan Rielly and Jake McCabe (together for 80% of their ice lately)." in text
    # BOS lists Charlie McAvoy out (the fixture's injury report).
    assert ("Built without Charlie McAvoy (out): whoever takes their shifts gets more ice time.") in text, text
    assert "From the shift charts of each team's last 5 games." in text


def test_the_last_meeting_says_the_score_and_who_scored():
    m = L.hockey_meeting(_conn(), "TOR", "BOS", "2026-10-21")
    assert (m["day"], m["home"], m["away"], m["home_score"], m["away_score"]) == ("2026-10-12", "BOS", "TOR", 2, 4)
    assert m["scorers"]["TOR"][0] == {"player": "Auston Matthews", "goals": 2}
    assert [x["player"] for x in m["scorers"]["BOS"]] == ["David Pastrnak"], "a scoreless night is not a goal"
    text = R.to_text(_report())
    assert "Oct. 12: the Maple Leafs beat the Bruins 4-2 on the road." in text, text
    assert "The Maple Leafs' goals: Auston Matthews (2), Mitch Marner and William Nylander." in text, text
    assert not L.hockey_meeting(_conn(), "TOR", "MTL", "2026-10-21"), "never met: no section"


def test_the_form_says_each_teams_last_games_in_goals_and_where_it_plays():
    conn = _conn()
    conn.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, date) "
                     "VALUES ('nhl', 2026, ?, ?, ?, ?, ?, ?, ?)",
                     [(d, f"{a}@{h}", h, a, hs, as_, d) for d, h, a, hs, as_ in (
                         ("2026-10-14", "TOR", "MTL", 3, 1), ("2026-10-16", "TOR", "OTT", 2, 3),
                         ("2026-10-15", "BOS", "NYR", 4, 2), ("2026-10-18", "DET", "BOS", 1, 2))])
    conn.commit()
    # The fixture's game is the Bruins at the Maple Leafs.
    form = L.team_form(conn, "nhl", "TOR", "BOS", "2026-10-21")
    assert form["TOR"] == {"n": 3, "w": 2, "l": 1, "margin": 1.0, "where": "home", "venue_w": 1, "venue_l": 1}, form
    assert form["BOS"] == {"n": 3, "w": 2, "l": 1, "margin": 0.3, "where": "road", "venue_w": 1, "venue_l": 0}, form
    board = copy.deepcopy(E._nhl_board())
    board["lines"] = copy.deepcopy(LINES)
    board["games"][0]["form"] = form
    L.attach(board, "nhl")
    text = R.to_text(board["game_reports"][0])
    # Said in goals, a goal when it is one.
    assert ("Form: the Bruins are 2-1 in their 3 games this season, outscoring teams by 0.3 goals a game; the "
            "Maple Leafs are 2-1 in their 3 games this season, outscoring teams by 1 goal a game.") in text, text
    assert "Where they play: the Maple Leafs are 1-1 at home and the Bruins are 1-0 on the road this season." in text
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert '_tf(conn, SPORT, _gd["home"], _gd["away"], date)' in src and '_gd["form"] = _fm' in src


def test_the_sections_sit_in_the_researchs_order_and_the_build_fills_the_meeting():
    keys = [s["key"] for s in _report()["sections"]]
    for a, b in (("goalies", "lines"), ("lines", "watch"), ("watch", "meetings")):
        assert keys.index(a) < keys.index(b), keys
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert "_hm(conn, _gd[\"home\"], _gd[\"away\"], date)" in src and '_gd["last_meeting"] = _m' in src
    # No lines on the board, no section.
    board = copy.deepcopy(E._nhl_board())
    L.attach(board, "nhl")
    assert "lines" not in [s["key"] for s in board["game_reports"][0]["sections"]]


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
