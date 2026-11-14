"""Step-ups across positions: measured, and too small to move a number.

Ethan, 2026-09-27: the other model "finds where other players are out and
other players could step up" — asked whether the site should measure the
broader effect (a WR1 out lifting the TE and the back), "Yes, measure then
apply". engine/matefit.cross_samples measures it on 2022-2025 with the
same yardstick and the same shipping rule as the same-position step-up.
It came out small and not significant (a WR's targets +11% ± 9% with the
TE leader out, a TE's +7% ± 7% with the WR leader out, against +19% to
+75% for the same-position cases), so nothing ships — and a cell resting
on two games cannot (MIN_CROSS_N).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import matefit as F                                    # noqa: E402
from engine import teammates as T                                  # noqa: E402


def _row(team, pos, name, wk, targets, **kw):
    return {"season_type": "REG", "week": str(wk), "team": team, "position": pos,
            "player_display_name": name, "targets": str(targets), **{k: str(v) for k, v in kw.items()}}


def _season(wr1_out_week=None):
    rows = []
    for wk in range(1, 8):
        if wk != wr1_out_week:
            rows.append(_row("DET", "WR", "Alpha", wk, 11, receptions=7, receiving_yards=90))
        rows.append(_row("DET", "WR", "Bravo", wk, 3, receptions=2, receiving_yards=25))
        rows.append(_row("DET", "TE", "Tango", wk, 5 if wk != wr1_out_week else 8,
                         receptions=4 if wk != wr1_out_week else 6,
                         receiving_yards=40 if wk != wr1_out_week else 70))
        rows.append(_row("DET", "RB", "Romeo", wk, 3, carries=15, rushing_yards=70, receptions=2,
                         receiving_yards=15))
    return rows


def test_a_target_leader_at_another_position_is_the_case():
    games, _tw = F._games_from_stats(_season())
    leaders = F.target_leaders(games, "DET", 6)
    assert [(n, p) for n, p, _t, _l in leaders] == [("Alpha", "WR"), ("Tango", "TE")], \
        "the top two by targets, each 18%+ of the team's (Bravo's 3 of 22 is under)"
    assert F.cross_case(leaders, "Tango", "TE", {"Tango", "Bravo", "Romeo"}, 5) == "xWR_new"
    assert F.cross_case(leaders, "Bravo", "WR", {"Tango", "Bravo", "Romeo"}, 5) is None, \
        "a receiver out ahead of a receiver is the same-position question"
    assert F.cross_case(leaders, "Tango", "TE", {"Alpha", "Tango"}, 5) is None


def test_the_samples_skip_a_game_with_his_own_position_short():
    pts = F.cross_samples({2024: _season(wr1_out_week=6)})
    te = [p for p in pts if p["g"] == "TE" and p["tier"] == "xWR_new"]
    assert te and all(p["y"] in (6.0, 70.0) for p in te)
    assert not [p for p in pts if p["g"] == "WR" and p["tier"]], "Bravo's game is a same-position absence"


def test_nothing_ships_and_a_two_game_cell_cannot():
    assert not hasattr(T, "EFFECT_CROSS"), "measured small and not significant — nothing applied"
    assert F.MIN_CROSS_N >= 20
    src = open(os.path.join(ROOT, "matefit.py"), encoding="utf-8").read()
    assert "--cross" in src and 'res[k]["n"] >= F.MIN_CROSS_N' in src
    note = open(os.path.join(ROOT, "engine", "matefit.py"), encoding="utf-8").read()
    assert "WRs +11% ± 9% (n 30, up all four" in note


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
