"""A scorer's chance follows his team's expected points as hard as history
says (engine/tdscale).

Ethan, 2026-10-04: "can we do that same work for the most likely td
models." The record: teams expected to score 18-22 went 1-for-12 on our
touchdown picks at a claimed 43%; teams at 26+ went 13-for-21 at 49%.
Checks, one rule each: an exponent that orders scorers better on held-out
seasons is adopted and one that does not stays 0; it is judged after a
recalibration, so it cannot win by redoing the temperature's job; the
production model applies it per position and says so; the fitter reads
the model with it switched off; it is refitted weekly BEFORE the
touchdown temperature.

Run directly: `python3 tests/test_touchdowns_follow_the_team_total.py`
"""
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine import tdscale as T                                     # noqa: E402


def _data(true_g: float, per=500, seed=11, scale=1.0):
    rng = random.Random(seed)
    out = []
    for s in (2021, 2022, 2023, 2024, 2025):
        for _ in range(per):
            p = rng.uniform(0.08, 0.6)
            imp = rng.uniform(15.0, 32.0)
            truth = T.adjust(p, imp, true_g) if true_g else p
            truth = min(0.97, truth * scale)
            out.append((s, p, imp, int(rng.random() < truth)))
    return out


def test_the_exponent_moves_chances_with_the_team_total():
    assert T.adjust(0.4, 21.5, 0.0) == 0.4
    assert T.adjust(0.4, 30.0, 0.8) > 0.4 > T.adjust(0.4, 17.0, 0.8)
    assert abs(T.adjust(0.4, 21.5, 0.8) - 0.4) < 0.02, "an average team is barely touched"


def test_a_real_effect_passes_on_held_out_seasons_and_a_miscalibration_does_not():
    real = T.judge(_data(1.2))
    assert real["passed"] and real["g"] >= 0.6, real
    none = T.judge(_data(0.0))
    assert not none["passed"], none
    # Every chance 25% too high, with no team-total pattern: the
    # recalibration absorbs it, so no exponent is adopted for it.
    shy = T.judge(_data(0.0, scale=0.75))
    assert not shy["passed"], shy


def test_the_model_applies_it_per_position_and_the_fitter_reads_it_switched_off():
    path = Path(os.environ["QB_MODELS_DIR"]) / "td_implied.json"
    T.save({"RB": {"g": 0.8, "n": 5000, "gain": 0.002, "passed": True},
            "WR": {"g": 0.4, "n": 5000, "gain": -0.001, "passed": False}}, path)
    assert T.gamma_for("RB") == 0.8 and T.gamma_for("WR") == 0.0
    with T.raw():
        assert T.gamma_for("RB") == 0.0, "the fitter never learns from its own correction"
    assert T.gamma_for("RB") == 0.8
    src = open(os.path.join(ROOT, "engine", "touchdowns.py"), encoding="utf-8").read()
    i = src.index("td_gamma = _td_gamma(pos)")
    assert "prob = _td_adjust(prob, implied, td_gamma)" in src[i:i + 200]
    assert "Team total:" in src
    fitter = open(os.path.join(ROOT, "engine", "tdscale.py"), encoding="utf-8").read()
    j = fitter.index("def replay_rows(")
    assert "with raw():" in fitter[j:j + 600]


def test_it_is_refitted_weekly_before_the_touchdown_temperature():
    src = open(os.path.join(ROOT, "engine", "deepfit.py"), encoding="utf-8").read()
    body = src[src.index("def refit_all("):]
    assert body.index("refit_td_scale(db)") < body.index("refit_touchdowns(db)")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
