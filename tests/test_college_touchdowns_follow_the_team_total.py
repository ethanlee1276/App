"""College touchdowns follow the team total as hard as college's own history
says — the NFL's engine/tdscale, measured and applied for college.

Ethan, 2026-10-10: "make sure everything of college football is done and
complete. we want the same methods and tools and models as we use for
nfl." The NFL's touchdown board has carried a per-position team-total
exponent since 2026-10-04; college's parity table said "not refitted per
position yet".

These check, one rule each: the exponent is measured from college's
average team (26.7 points), not the NFL's; college has its own store and
the NFL's file keeps its name; a college exponent never moves an NFL
chance; the NFL's bar adopts a planted college effect and refuses none;
the fitter reads college's replay with the correction switched off; the
college replay applies it when on, so the college temperature is fitted on
top of it; the live college board applies it after its rate and says so;
it is refitted weekly before the college temperature.

Run directly: `python3 tests/test_college_touchdowns_follow_the_team_total.py`
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


def _clear():
    for sport in T.SPORTS:
        p = T._store(sport)
        if p.exists():
            p.unlink()
    T._CACHE.clear()


def _data(true_g: float, per=500, seed=7):
    rng = random.Random(seed)
    out = []
    for s in (2022, 2023, 2024, 2025, 2026):
        for _ in range(per):
            p = rng.uniform(0.08, 0.6)
            imp = rng.uniform(14.0, 44.0)
            truth = T.adjust(p, imp, true_g, "cfb") if true_g else p
            out.append((s, p, imp, int(rng.random() < min(0.97, truth))))
    return out


def test_college_measures_from_its_own_average_team():
    from engine.cfb.tds import CFB_AVG_TEAM_POINTS
    assert T.average_points("cfb") == CFB_AVG_TEAM_POINTS
    assert abs(T.adjust(0.4, CFB_AVG_TEAM_POINTS, 0.8, "cfb") - 0.4) < 1e-9, \
        "an average college team is not touched"
    assert T.adjust(0.4, CFB_AVG_TEAM_POINTS, 0.8) > 0.42, "the NFL's average would call it a high total"
    assert T.adjust(0.4, 40.0, 0.8, "cfb") > 0.4 > T.adjust(0.4, 17.0, 0.8, "cfb")


def test_college_has_its_own_store_and_never_moves_the_nfl():
    _clear()
    assert T._store("nfl").name == "td_implied.json", "the box's NFL file is read as it is"
    assert T._store("cfb").name == "cfb_td_implied.json"
    T.save({"RB": {"g": 0.8, "n": 5000, "gain": 0.002, "passed": True}}, sport="cfb")
    assert T.gamma_for("RB", "cfb") == 0.8
    assert T.gamma_for("RB") == 0.0 and T.gamma_for("RB", "nfl") == 0.0
    with T.raw():
        assert T.gamma_for("RB", "cfb") == 0.0
    _clear()


def test_the_nfls_bar_adopts_a_planted_college_effect_and_refuses_none():
    for seed in (0, 1, 3):
        real = T.judge(_data(1.2, seed=seed), "cfb")
        assert real["passed"] and real["g"] >= 0.6, (seed, real)
    # The bar is the NFL's, unchanged, and at 2,500 rows it is not
    # perfect: with no effect at all it adopted a small g on 2 of 12
    # seeds (the NFL's own range: 1 of 30), measured 2026-10-10. The box
    # has far more college rows than this. What it must never do is
    # adopt noise most of the time.
    adopted = [s for s in range(6) if T.judge(_data(0.0, seed=s), "cfb")["passed"]]
    assert len(adopted) <= 1, adopted


def test_the_fitter_reads_colleges_replay_switched_off():
    import engine.cfbtdfit as F
    seen = []

    def fake_run(conn, collect=None, **_kw):
        seen.append(T._STATE["enabled"])
        collect({"season": 2025, "prob": 0.3, "scored": 1, "position": "RB", "implied": 31.0})
        collect({"season": 2025, "prob": 0.2, "scored": 0, "position": "WR", "implied": None})
        collect({"season": 2025, "prob": 0.2, "scored": 0, "position": "K", "implied": 30.0})

    real = F.run
    F.run = fake_run
    try:
        by = T.replay_rows(None, "cfb")
    finally:
        F.run = real
    assert seen == [False], "the college replay must run with the correction off"
    assert dict(by) == {"RB": [(2025, 0.3, 31.0, 1)]}, "no implied total, no row; only the four positions"


def _sample():
    from engine.cfbtdfit import Sample
    return Sample(season=2025, position="RB", share=0.30, td_mean=0.6, games=5, scored=1,
                  period="2025-10-04", team="UGA", opponent="VAN", is_home=True, spread=-24.5, total=58.5,
                  player="Dawg Back")


def test_the_college_replay_applies_it_so_the_temperature_fits_on_top():
    import engine.cfbtdfit as F
    s = _sample()
    assert abs(s.implied - 41.5) < 1e-9, "the row keeps the team's implied points"
    real_samples, real_def = F.samples, F.defense_to_date
    F.samples = lambda conn, seasons=None, **_kw: [_sample()]
    F.defense_to_date = lambda conn, seasons=None: {}
    try:
        _clear()
        rows_off = []
        F.run(None, collect=rows_off.append)
        T.save({"RB": {"g": 0.8, "n": 5000, "gain": 0.002, "passed": True}}, sport="cfb")
        rows_on = []
        F.run(None, collect=rows_on.append)
        with T.raw():
            rows_raw = []
            F.run(None, collect=rows_raw.append)
    finally:
        F.samples, F.defense_to_date = real_samples, real_def
        _clear()
    assert rows_on[0]["prob"] > rows_off[0]["prob"], "a 41.5-point college offence's back is likelier"
    assert rows_raw[0]["prob"] == rows_off[0]["prob"], "switched off, the replay is the base model"
    assert rows_on[0]["implied"] == 41.5


def test_the_live_college_board_applies_it_and_says_so():
    src = open(os.path.join(ROOT, "engine", "cfb", "tds.py"), encoding="utf-8").read()
    i = src.index('td_gamma = _td_gamma(pos, "cfb")')
    assert src.index("prob = prob_at_least_one(rate)") < i < src.index('calibrated_prob("cfb", "anytime_td"')
    assert 'prob = _td_adjust(prob, implied, td_gamma, "cfb")' in src[i:i + 200]
    assert "Team total: college" in src


def test_it_is_refitted_weekly_before_the_college_temperature():
    src = open(os.path.join(ROOT, "engine", "deepfit.py"), encoding="utf-8").read()
    body = src[src.index("def refit_td_scale("):src.index("def refit_touchdowns(")]
    assert 'for sport in ("nfl", "cfb")' in body
    allfit = src[src.index("def refit_all("):]
    assert allfit.index("refit_td_scale(db)") < allfit.index("refit_cfb_touchdowns(db)")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
