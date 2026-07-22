"""Tests for the depth-chart adapter (offline, fixture-driven)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import depthcharts as dc
from engine.injuries import evaluate_injuries
from engine.models import Injury, Prop, GameLog, SportsbookLine, REC_YDS


def _row(name, team, dp, rank, week=5):
    return {"season": "2024", "week": str(week), "club_code": team,
            "full_name": name, "depth_position": dp, "depth_team": str(rank),
            "position": dp}


ROWS = [
    _row("Big Tackle", "KC", "LT", 1),
    _row("Nickel Guy", "BUF", "NB", 1),
    _row("Boundary One", "BUF", "LCB", 1),
    _row("Backup Corner", "KC", "RCB", 2),
    _row("Last Week LT", "KC", "LT", 1, week=4),
]


def test_index_keeps_best_rank():
    rows = ROWS + [_row("Big Tackle", "KC", "LT", 3)]  # extra formation listing
    idx = dc.index_for_week(rows, 5)
    assert idx[("KC", "big tackle")] == ("LT", 1)
    # wrong-week rows are excluded
    assert ("KC", "last week lt") not in idx


def test_refine_starter_roles():
    injuries = [
        Injury("Big Tackle", "KC", "T", "OT", "OUT"),        # generic OT -> LT
        Injury("Nickel Guy", "BUF", "CB", "cb1", "OUT"),      # boundary -> slot
        Injury("Boundary One", "BUF", "CB", "cb1", "OUT"),    # stays cb1
    ]
    res = dc.refine_injury_roles(injuries, ROWS, 5)
    assert injuries[0].role == "LT"
    assert injuries[1].role == "slot_cb"
    assert injuries[2].role == "cb1"
    assert res.refined == 2 and res.demoted == 0


def test_backup_demoted_and_knockon_cancelled():
    injuries = [Injury("Backup Corner", "KC", "CB", "cb1", "OUT")]
    res = dc.refine_injury_roles(injuries, ROWS, 5)
    assert res.demoted == 1
    assert injuries[0].role == "depth_cb1"

    # A demoted backup CB no longer boosts the opposing receiver.
    prop = Prop("WR X", "BUF", "KC", "WR", REC_YDS,
                [GameLog(w, "X", 60) for w in range(1, 5)], 58, None,
                [SportsbookLine("proxy", 55.0)], "wr1")
    effect = evaluate_injuries(prop, injuries)
    assert effect.multiplier == 1.0


def test_starter_slot_cb_triggers_slot_knockon():
    injuries = [Injury("Nickel Guy", "BUF", "CB", "cb1", "OUT")]
    dc.refine_injury_roles(injuries, ROWS, 5)
    prop = Prop("Slot WR", "KC", "BUF", "WR", REC_YDS,
                [GameLog(w, "X", 55) for w in range(1, 5)], 52, None,
                [SportsbookLine("proxy", 50.0)], "slot")
    effect = evaluate_injuries(prop, injuries)
    assert effect.multiplier > 1.0
    assert any("slot" in r.lower() for r in effect.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
