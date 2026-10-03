"""How wide a player's outcomes really are, by position (engine/posspread).

The 2026-10-04 NFL record: tight ends over-claimed on BOTH sides (overs 47%
where we said 64%, unders 41% where we said 65%) — too sure, not leaning
the wrong way. Checks, one rule each: a width that predicts held-out
seasons better is adopted and one that does not is left at 1.0; the
projection widens the spread by it for that position only, in the NFL
only, and says so; the weekly deep-fit job runs it.

Run directly: `python3 tests/test_a_position_gets_its_own_spread.py`
"""
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()

from engine import posspread as P                                   # noqa: E402


def _data(true_mult: float, seasons=(2021, 2022, 2023, 2024, 2025), per=900, seed=3):
    """Rows priced at sd=10 whose outcomes really spread true_mult × 10."""
    rng = random.Random(seed)
    out = []
    for s in seasons:
        for _ in range(per):
            mu = rng.uniform(30, 60)
            actual = rng.gauss(mu, 10 * true_mult)
            for line in (25.5, 40.5, 60.5):
                if P.NEAR_LO * mu <= line <= P.NEAR_HI * mu:
                    out.append((s, 10.0, mu, line, actual > line))
    return out


def test_a_width_that_predicts_held_out_seasons_is_adopted_and_noise_is_not():
    too_sure = P.judge(_data(1.35))
    assert too_sure["passed"] and 1.25 <= too_sure["m"] <= 1.45, too_sure
    assert too_sure["better"] >= P.MIN_SEASONS_BETTER
    honest = P.judge(_data(1.0))
    assert not honest["passed"], "an honest width stays at 1.0"
    small = P.judge(_data(1.35, per=40))
    assert not small["passed"], "too few rows prove nothing"


def test_the_projection_widens_that_position_only_and_says_so():
    path = Path(os.environ["QB_MODELS_DIR"]) / "position_spread.json"
    P.save({"TE|receptions": {"m": 1.3, "n": 9000, "gain": 0.01, "passed": True},
            "WR|receptions": {"m": 0.9, "n": 9000, "gain": -0.01, "passed": False}}, path)
    assert P.width_mult("TE", "receptions") == 1.3
    assert P.width_mult("WR", "receptions") == 1.0, "a width that did not pass is not used"
    assert P.width_mult("te", "rec_yds") == 1.0
    # The first (far-tail) version's store carries no version: never read.
    path.write_text('{"widths": {"TE|receptions": {"m": 1.35}}}', encoding="utf-8")
    import time
    time.sleep(0.01)
    os.utime(path, None)
    assert P.width_mult("TE", "receptions") == 1.0, "a store from the far-tail version is ignored"
    src = open(os.path.join(ROOT, "engine", "projection.py"), encoding="utf-8").read()
    i = src.index("from .posspread import width_mult")
    assert 'if sport == "nfl":' in src[i - 200:i], "measured on NFL games, used on NFL props"
    assert "adj_std *= _w" in src[i:i + 300] and "Spread:" in src[i:i + 500]


def test_only_lines_near_his_projection_are_scored():
    rows = [{"season": 2025, "mu": 40.0, "form_sd": 12.0, "actual": 50.0}]
    lines = sorted(line for _s, _sd, _mu, line, _h in P.samples(rows, "rec_yds"))
    assert lines == [40.5], "15.5, 25.5 and 60.5 are far tails a book would not hang for a 40-yard man"


def test_it_reads_the_history_database_by_position():
    from engine import db
    hist = db.connect(Path(tempfile.mkdtemp()) / "history.db")
    logs = [{"sport": "nfl", "season": 2025, "period": f"{w:03d}", "game_id": f"LV-{w:03d}", "player": "Tight End",
             "team": "LV", "opponent": "KC", "position": "TE", "home": 0, "market": "receptions",
             "value": float(2 + w % 4)} for w in range(1, 12)]
    db.upsert_player_logs(hist, logs)
    hist.commit()
    res = P.measure(hist)
    assert set(res) == {"TE|receptions"} and res["TE|receptions"]["passed"] is False, res


def test_the_weekly_job_runs_it():
    src = open(os.path.join(ROOT, "engine", "maintenance.py"), encoding="utf-8").read()
    body = src[src.index("def _run_deep_refit("):src.index("def _run_lab(")]
    assert '_spawn_module("engine.posspread", log)' in body


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
