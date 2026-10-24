"""The top of the touchdown board gets a measured correction, or none.

Ethan, 2026-10-04: the replay's top 1/3/5 per slate landed 5-6 points over
their claim while the top 20 sat on the number, and the live record said
the same. engine/tdtop tests one hinge above a knee fixed in advance, on
held-out seasons. Checks: below the knee the hinge adds nothing, so long
shots are untouched; a real lift at the top passes and closes the top-5
gap; a board with no lift does not pass; nothing reads the store yet.

Run directly: `python3 tests/test_the_top_of_the_td_board_is_measured_before_it_moves.py`
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import tdtop as F                                        # noqa: E402
from engine.tdfeatures import sigmoid                                # noqa: E402


def test_below_the_knee_the_hinge_is_zero():
    pts = F.points([{"season": 2023, "week": "05", "prob": p, "scored": 0} for p in (0.05, 0.2, 0.39, 0.41, 0.7)])
    assert [round(d[3], 6) for d in pts[:3]] == [0.0, 0.0, 0.0]
    assert pts[3][3] > 0 and pts[4][3] > pts[3][3]
    assert abs(F.knee() - math.log(0.4 / 0.6)) < 1e-12


def _rows(lift, seasons=(2021, 2022, 2023, 2024, 2025), slates=18, per=60, seed=9):
    rnd = random.Random(seed)
    out = []
    for s in seasons:
        for w in range(slates):
            for _ in range(per):
                p = min(0.8, max(0.02, rnd.betavariate(1.6, 6.0) * 1.3))
                z = math.log(p / (1 - p))
                true = 0.15 + z / 1.12 + lift * max(0.0, z - F.knee())
                out.append({"season": s, "week": f"{w:02d}", "prob": p,
                            "scored": 1 if rnd.random() < sigmoid(true) else 0})
    return out


def test_a_real_lift_at_the_top_passes_and_closes_the_gap():
    res = F.judge(F.points(_rows(1.2)))
    assert res["passed"], res
    (cb, lb), (ch, lh) = res["top"]["base"], res["top"]["hinge"]
    gap_base, gap_hinge = abs(lb - cb), abs(lh - ch)
    assert gap_base > 0.02, ("the planted lift leaves today's calibration short at the top", res["top"])
    assert gap_hinge < gap_base - 0.01, ("the hinge closes most of it", res["top"])
    assert res["c"] > 0


def test_no_lift_does_not_pass():
    for seed in (2, 3):
        assert not F.judge(F.points(_rows(0.0, seed=seed)))["passed"]


def test_nothing_reads_the_store_yet():
    for rel in ("engine/calibrate.py", "engine/longshots.py", "engine/touchdowns.py", "engine/pipeline.py"):
        assert "td_top" not in open(os.path.join(ROOT, rel), encoding="utf-8").read(), rel


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
