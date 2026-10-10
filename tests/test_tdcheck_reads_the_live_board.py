"""tdcheck.py: the command Ethan runs on the box to see today's touchdown
work on every game of the live NFL board. Fixtures only — never the box."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tdcheck  # noqa: E402

STEPS = [{"key": "line"}, {"key": "out"}, {"key": "matchup"},
         {"key": "who", "rows": [{"player": "Jahmyr Gibbs", "model_prob": 0.72, "odds": -320,
                                  "why": ["Likely — but -320 is past the board's -250 cap"]}]}]


def _board(**over):
    b = {"game_plans": [{"game": "NYJ@DET", "steps": STEPS}],
         "td_field": [{"player": "Jahmyr Gibbs", "position": "RB"}, {"player": "Josh Allen", "position": "QB"}],
         "longshot_watch": [
             {"player": "Jahmyr Gibbs", "model_prob": 0.72, "odds": -320, "goal_line": {"i5_car": 5},
              "reasons": ["Goal-line work: 11 red-zone carries", "Running back: read on the measured back curve"]},
             {"player": "Josh Allen", "model_prob": 0.50, "odds": -135,
              "reasons": ["Quarterback: scoring rate ×1.40 — measured"]}]}
    b.update(over)
    return b


def test_a_full_board_passes():
    assert tdcheck.check(_board(), out=lambda *_: None) == []


def test_each_missing_piece_is_named():
    no_who = _board(game_plans=[{"game": "NYJ@DET", "steps": STEPS[:3]}])
    assert tdcheck.check(no_who, out=lambda *_: None) == ["NYJ@DET: no 'Who scores' step after the matchup"]
    bare = _board()
    bare["longshot_watch"][0]["reasons"] = []
    bare["longshot_watch"][1]["reasons"] = []
    assert tdcheck.check(bare, out=lambda *_: None) == [
        "Jahmyr Gibbs: running-back curve missing",
        "Jahmyr Gibbs: goal-line counts measured but not said",
        "Josh Allen: quarterback scale missing"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
