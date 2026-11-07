"""The team-volume check: how much of a team's dropbacks and carries the line knows.

volumecheck.py (2026-10-17) found the line knows a little, consistently, on
4,316 NFL team-games. Pinned here: the least squares is right, the line's
part is found when it is really there and adds nothing when it is not, each
season is scored on a fit of the seasons before it only, and a team's own
trailing mean never includes the game being predicted.

Offline: synthetic seasons from a fixed seed.

Run directly: `python3 tests/test_volumecheck.py`
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import volumecheck as V  # noqa: E402


def test_least_squares_recovers_a_plane():
    rng = random.Random(1)
    X = [[1.0, rng.random(), rng.random()] for _ in range(200)]
    y = [2 + 3 * a - 1.5 * b for _, a, b in X]
    w = V.ols(X, y)
    assert all(abs(p - q) < 1e-6 for p, q in zip(w, (2, 3, -1.5))), w


def _league(line_matters: bool, seed: int) -> list:
    rng = random.Random(seed)
    teams = [f"T{i}" for i in range(16)]
    out = []
    for season in range(2016, 2024):
        base = {t: rng.gauss(36, 3) for t in teams}
        for week in range(1, 18):
            order = teams[:]
            rng.shuffle(order)
            for a, b in zip(order[::2], order[1::2]):
                imp_a, imp_b = rng.gauss(22, 4), rng.gauss(22, 4)
                for t, o, imp, tsp in ((a, b, imp_a, imp_a - imp_b), (b, a, imp_b, imp_b - imp_a)):
                    db = base[t] + (0.4 * (imp - 22) - 0.2 * tsp if line_matters else 0.0) + rng.gauss(0, 6)
                    car = 26 - (0.2 * (imp - 22) - 0.25 * tsp if line_matters else 0.0) + rng.gauss(0, 5)
                    out.append({"season": season, "week": week, "team": t, "opp": o, "imp": imp, "tsp": tsp,
                                "db": db, "car": car, "plays": db + car})
    return out


def test_the_line_is_found_when_it_matters_and_adds_nothing_when_it_does_not():
    real = V.with_trailing(_league(True, 3))
    folds = V.heldout(real, "db")
    better = sum(1 for f in folds if f["market"] < f["base"])
    assert folds and better >= len(folds) - 1, folds
    assert sum(f["base"] - f["market"] for f in folds) > 0.1, "pooled, the line helps"
    assert 0.25 < folds[-1]["market_w"][3] < 0.55, "the implied-points slope comes back"
    noise = V.with_trailing(_league(False, 4))
    gain = sum(f["base"] - f["market"] for f in V.heldout(noise, "db"))
    assert gain < 0.05, "no line effect, no real gain"


def test_trailing_means_use_only_earlier_weeks():
    rows = [{"season": 2020, "week": w, "team": "A", "opp": "B", "imp": 22, "tsp": 0,
             "db": float(w), "car": 1.0, "plays": float(w) + 1} for w in range(1, 6)]
    rows += [{"season": 2020, "week": w, "team": "B", "opp": "A", "imp": 22, "tsp": 0,
              "db": 10.0, "car": 1.0, "plays": 11.0} for w in range(1, 6)]
    got = {(r["team"], r["week"]): r for r in V.with_trailing(rows)}
    assert ("A", 3) not in got, "fewer than three games behind it"
    assert got[("A", 4)]["own_db"] == 2.0, "weeks 1-3, never week 4 itself"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
