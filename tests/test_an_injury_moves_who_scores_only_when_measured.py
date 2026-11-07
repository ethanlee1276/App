"""The touchdown scans' injury moves are measured on history before they move anything.

Ethan, 2026-10-04, with four touchdown-only scans: every one moves a scorer
on the injury report ("Cook and Dugger out — Washington", "Bosa out —
McCaffrey", "Evans out — Kittle"). engine/tdinjfit asks each on top of the
touchdown model. Checks: a depth position lands in the right group; only a
ruled-out STARTER counts; each claim reads the right side and positions;
an effect planted on top of the model is proven, and the same data with
no effect is not, and neither is an effect in one season only.

Run directly: `python3 tests/test_an_injury_moves_who_scores_only_when_measured.py`
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdinjfit as F                                     # noqa: E402
from engine.models import Injury                                     # noqa: E402
from engine.tdfeatures import logit, sigmoid                         # noqa: E402


def test_depth_positions_land_in_their_group():
    for pos, group in (("LCB", "secondary"), ("RCB", "secondary"), ("NB", "secondary"),
                       ("FS", "secondary"), ("SS", "secondary"), ("RDE", "front"),
                       ("DT", "front"), ("LDT", "front"), ("LWR", "catchers"),
                       ("SWR", "catchers"), ("TE", "catchers")):
        assert F.group_of(pos) == group, pos
    for pos in ("LB", "LT", "RB", "QB", "ROLB", "MLB", "K", ""):
        assert F.group_of(pos) == "", pos


def _inj(player, team, status, position=""):
    return Injury(player=player, team=team, position=position, role=position.lower(), status=status)


def test_only_a_ruled_out_starter_counts():
    depth = {("CIN", "bryan cook"): ("SS", 1), ("CIN", "kyle dugger"): ("FS", 1),
             ("CIN", "backup corner"): ("LCB", 2), ("CIN", "bj hill"): ("DT", 1),
             ("SF", "mike evans"): ("WR", 1)}
    injs = [_inj("Bryan Cook", "CIN", "OUT", "S"), _inj("Kyle Dugger", "CIN", "IR", "S"),
            _inj("Backup Corner", "CIN", "OUT", "CB"), _inj("BJ Hill", "CIN", "QUESTIONABLE", "DT"),
            _inj("Mike Evans", "SF", "DOUBTFUL", "WR"), _inj("Not Listed", "SF", "OUT", "WR")]
    got = F.starters_out(injs, depth)
    assert got["CIN"] == {"secondary": 2}, "a backup and a questionable starter count for nothing"
    assert got["SF"] == {"catchers": 1}, "a player missing from the chart cannot be called a starter"


def test_each_claim_reads_its_own_side_and_positions():
    rows = [{"season": 2023, "week": "05", "team": "JAX", "opponent": "CIN", "position": "WR",
             "prob": 0.3, "scored": 1},
            {"season": 2023, "week": "05", "team": "CIN", "opponent": "JAX", "position": "RB",
             "prob": 0.5, "scored": 0}]
    flags = {(2023, 5): {"CIN": {"secondary": 2, "catchers": 1}, "JAX": {"front": 4}}}
    got = F.samples(rows, flags)
    assert [d[3] for d in got["secondary"]] == [2.0], "the JAX receiver faces CIN's missing DBs"
    assert [d[3] for d in got["front"]] == [3.0], "capped at X_CAP"
    # CIN's back gets his own team's missing catcher; JAX's receiver gets JAX's (none).
    assert sorted(d[3] for d in got["catchers"]) == [0.0, 1.0]
    assert not F.samples(rows, {})["secondary"], "a week with no injury file is not read as no injuries"


def _data(effect, seasons=(2021, 2022, 2023, 2024), n=6000, seed=11):
    rnd = random.Random(seed)
    out = []
    for season in seasons:
        b = effect(season)
        for i in range(n):
            p = rnd.uniform(0.08, 0.6)
            x = float(rnd.choice((1, 2))) if rnd.random() < 0.15 else 0.0
            y = 1 if rnd.random() < sigmoid(logit(p) + b * x) else 0
            out.append((season, (season, i // 8), logit(p), x, y))
    return out


def test_a_real_effect_on_top_of_the_model_is_proven():
    res = F.judge(_data(lambda s: 0.35))
    assert res["passed"], res
    assert res["b"] > 0.2 and res["t"] >= F.MIN_T
    assert res["scored_vs_model_flagged"] > res["scored_vs_model_rest"]


def test_no_effect_is_not_proven():
    for seed in (1, 2, 3):
        res = F.judge(_data(lambda s: 0.0, seed=seed))
        assert not res["passed"], (seed, res)


def test_an_effect_in_one_season_only_is_not_proven():
    res = F.judge(_data(lambda s: 0.6 if s == 2022 else 0.0, seed=5))
    assert not res["passed"], res


def test_too_few_flagged_games_are_not_proven():
    data = [d if d[3] == 0 or i % 10 == 0 else d[:3] + (0.0, d[4])
            for i, d in enumerate(_data(lambda s: 0.35, n=1500))]
    res = F.judge(data)
    assert res["flagged"] < F.MIN_FLAGGED and not res["passed"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
