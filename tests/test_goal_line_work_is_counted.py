"""Goal-line work, counted: inside-5 carries and inside-10 targets.

Ethan's other model reads every scorer by his goal-line work — Gibbs "5
carries inside the 5", St. Brown and LaPorta "3 targets inside the 10"
(2026-09-27). The play-by-play fold already counted inside-5 carries; it
now counts inside-10 targets as their own market (`i10_tgt`), kept out of
the xFP buckets, and engine/tdfeatures measures all of it against the
shipped touchdown model.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdfeatures as F                                 # noqa: E402
from engine.sources import nflpbp as P                             # noqa: E402


def _pass(yl, who="A.St. Brown", td=0):
    return {"week": "2", "posteam": "DET", "defteam": "BUF", "play_type": "pass", "yardline_100": str(yl),
            "receiver_player_name": who, "air_yards": "5", "complete_pass": "1", "yards_gained": "5",
            "pass_touchdown": str(td)}


def test_inside_ten_targets_are_counted_and_never_priced_as_xfp():
    rows = ([_pass(8, td=1), _pass(3), _pass(15), _pass(40)] + [_pass(60, who=f"X{i}") for i in range(40)]
            + [_pass(15, who=f"Y{i}") for i in range(40)])
    agg = P.aggregate_pbp(rows)
    me = agg["players"][("A.St. Brown", "DET", 2)]
    assert me["_i10_tgt"] == 2 and me["tgt_rz"] == 3
    out = {r["market"]: r["value"] for r in P.xfp_player_rows(agg, 2026) if r["player"] == "A.St. Brown"}
    assert out["i10_tgt"] == 2.0 and out["rz_tgt"] == 3.0
    assert "xfp" in out, "the count is not an xFP bucket, so it cannot unprice his xFP"


def test_the_goal_line_candidates_are_measured():
    names = [n for n, _f in F.CANDIDATES]
    for n in ("inside-5 carries a game", "inside-10 targets a game",
              "goal-line touches a game", "share of team goal-line work"):
        assert n in names
    ctx = {"form": {(2026, ("a", "stbrown", "DET")): {"001": {"i5_car": 0.0, "i10_tgt": 2.0},
                                                        "002": {"i5_car": 1.0, "i10_tgt": 1.0}}},
           "team_week": {(2026, "001", "DET"): {"i5_car": 2.0, "i10_tgt": 4.0},
                         (2026, "002", "DET"): {"i5_car": 3.0, "i10_tgt": 3.0}},
           "goal_line_market": "i5_car", "has_i10": True}
    row = {"season": 2026, "short": ("a", "stbrown", "DET"), "team": "DET", "prior_weeks": ["001", "002"]}
    assert F.goal_line_carries(row, ctx) == 0.5 and F.goal_line_targets(row, ctx) == 1.5
    assert F.goal_line_touches(row, ctx) == 2.0 and abs(F.goal_line_share(row, ctx) - 2.0 / 6.0) < 1e-9
    assert F.goal_line_targets(row, dict(ctx, has_i10=False)) is None, "refused, not scored on zeros"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
