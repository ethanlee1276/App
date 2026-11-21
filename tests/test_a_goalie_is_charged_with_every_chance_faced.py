"""A goalie is charged with every chance faced, misses included (USEREYES1,
18 November 2026).

Walking a hockey game page: "Darcy Kuemper · .892 save rate · −47.8 saved
above expected". Every one of the night's 22 starters read below zero, from
−0.8 to −60.3 (Vasilevskiy −28.6, Sorokin −23.9), the size following how much
each had played. The expected-goals model is fitted on unblocked attempts —
a cell's rate is goals over goals, shots on goal and misses — so its chances
add up to the goals only over all three; a goalie's were summed over the
shots on goal alone, about three-quarters of what the goalie faced. The same
ratio, goals allowed over expected, is `goalie_skill`, and the goal markets
(goals, the anytime goal, points, assists) multiply a skater's chance by it
against a confirmed starter, capped at ±20%: near 1.3 for an average goalie,
the cap was the multiplier, a fifth more goals against every confirmed
starter. What these hold:

  * a goalie's expected goals against are every unblocked attempt faced, no
    empty net — the same chances the team allowed — while the shots stay the
    shots on goal;
  * a goalie who allowed what the chances were worth reads 0 saved above
    expected and a skill of 1: the goal markets are left as they were;
  * the save map's line counts the misses' chances and still draws only what
    reached the net (tests/test_a_shot_map_and_save_map_for_hockey.py);
  * the kept board summaries are rebuilt (BOARD_VERSION 3).

    python3 tests/test_a_goalie_is_charged_with_every_chance_faced.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.nhl import model as M, xg as X                                  # noqa: E402


def _row(kind, xg, goal=0, goalie="Kuemper", en=0, ev=0):
    return {"game_id": 1, "event_id": ev, "team": "BOS", "opponent": "LAK", "shooter": "Pastrnak",
            "goalie": goalie, "kind": kind, "xg": xg, "is_goal": goal, "empty_net": en, "strength": "EV",
            "assist1": "", "assist2": ""}


ROWS = [_row("goal", 0.30, goal=1, ev=1), _row("sog", 0.10, ev=2), _row("sog", 0.05, ev=3),
        _row("miss", 0.20, ev=4), _row("miss", 0.35, ev=5), _row("block", 0.0, ev=6),
        _row("goal", 0.60, goal=1, goalie="", en=1, ev=7)]


def test_a_goalies_chances_are_every_unblocked_attempt_faced():
    s = X.summaries(ROWS)
    g, team = s["goalies"]["Kuemper"], s["teams"]["LAK"]
    assert g["xga"] == round(0.30 + 0.10 + 0.05 + 0.20 + 0.35, 3), g
    assert g["xga"] == round(team["xga"] - 0.60, 3), "the goalie's chances are the team's, the empty net aside"
    assert g["shots"] == 3 and g["ga"] == 1, "the shots stay the shots on goal"
    assert g["gsax"] == round(1.0 - 1, 2) == 0.0, "allowed what the chances were worth"


def test_an_average_goalie_leaves_the_goal_markets_as_they_were():
    g = X.summaries(ROWS)["goalies"]["Kuemper"]
    assert M.goalie_skill(g) == 1.0, M.goalie_skill(g)
    # Over the shots on goal alone the same night read 0.45 expected against
    # 1 allowed: a skill of (1 + 30) / (0.45 + 30) — and over forty games, the
    # cap's 1.2 on every confirmed starter.
    assert (1 + M.GSAX_PRIOR_XGA) / (0.45 + M.GSAX_PRIOR_XGA) > 1.0
    assert X.BOARD_VERSION == 3, "the kept summaries are rebuilt"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
