"""The baseball report says each club's form (2026-11-15).

The basketball and hockey reports open on each side's form (its last ten
this season and by how much: engine/leaguereport.team_form). The MLB board
already carries each club's newest ten finals this season (`team_recent`,
engine/teamlogs.recent_games, for the game bets' charts), so the baseball
report's game facts say the same line from it, in runs
(leaguereport.form_from_recent), with no query of its own.

    python3 tests/test_the_baseball_report_says_each_teams_form.py
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


def _game(won, margin, home=True):
    return {"when": "2026-06-10", "opponent": "MIL", "home": home, "scored": 5.0, "allowed": 5.0 - margin,
            "margin": float(margin), "total": 10.0 - margin, "won": won}


def _report(recent):
    board = copy.deepcopy(E._mlb_board())
    board["team_recent"] = recent
    L.attach(board, "mlb")
    return R.to_text(board["game_reports"][0])


def test_the_facts_say_each_clubs_last_ten_in_runs():
    recent = {"PHI": [_game(True, 3)] * 7 + [_game(False, -2)] * 3,
              "CHC": [_game(False, -1)] * 2 + [_game(True, 1)] * 2}
    text = _report(recent)
    assert ("Form: the Phillies are 7-3 over their last ten, outscoring teams by 1.5 runs a game; the Cubs are 2-2 "
            "in their 4 games this season, even on runs.") in text, text
    # The ten are all the board holds: no record at home or on the road.
    assert "Where they play" not in text


def test_under_three_games_or_no_board_field_says_nothing():
    assert L.form_from_recent({"PHI": [_game(True, 1)] * 2}, ("PHI", "CHC")) == {}
    assert "Form:" not in _report({})
    got = L.form_from_recent({"PHI": [_game(False, -1)] * 12}, ("PHI",))
    assert got["PHI"] == {"n": 10, "w": 0, "l": 10, "margin": -1.0}, got
    assert "outscored by 1 run a game" in _report({"PHI": [_game(False, -1)] * 12})


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
