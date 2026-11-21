"""The referee check: a referee's past, scored on seasons it never saw.

refcheck.py answered "do NFL referees predict the total against the closing
line?" — no, on 7,340 games (2026-10-17). Pinned here: the check finds an
effect that is really there, finds none in noise, uses only earlier seasons
for each season it scores, and skips a game without a referee or a close.

Offline: synthetic games from a fixed seed.

Run directly: `python3 tests/test_refcheck.py`
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import refcheck  # noqa: E402

REFS = [f"Ref {i}" for i in range(17)]


def _games(effect: bool, seed: int) -> list:
    rng = random.Random(seed)
    lean = {r: rng.gauss(0, 4.0) for r in REFS}
    out = []
    for season in range(2012, 2024):
        for _ in range(260):
            ref = rng.choice(REFS)
            total = (lean[ref] if effect else 0.0) + rng.gauss(0, 13)
            out.append({"season": season, "ref": ref, "total": total, "margin": rng.gauss(0, 13)})
    return out


def test_a_real_lean_is_found_and_noise_is_not():
    assert refcheck.verdict(refcheck.heldout(_games(True, 3), "total", 50))["holds"]
    assert not refcheck.verdict(refcheck.heldout(_games(False, 4), "total", 50))["holds"]


def test_each_season_reads_only_the_seasons_before_it():
    games = [{"season": 2015, "ref": "A", "total": 10.0, "margin": 0.0},
             {"season": 2016, "ref": "A", "total": -10.0, "margin": 0.0},
             {"season": 2017, "ref": "A", "total": 0.0, "margin": 0.0}]
    folds = {f["season"]: f for f in refcheck.heldout(games, "total", 0)}
    assert 2015 not in folds, "the first season has nothing before it"
    # 2016 is predicted from 2015's +10 alone, never from its own -10.
    assert folds[2016]["gain_pct"] < 0


def test_a_game_without_a_referee_or_a_close_is_left_out():
    raw = [{"season": "2020", "home_score": "24", "away_score": "20", "total_line": "44", "spread_line": "3",
            "referee": "Brad Allen"},
           {"season": "2020", "home_score": "24", "away_score": "20", "total_line": "44", "spread_line": "3",
            "referee": ""},
           {"season": "2026", "home_score": "", "away_score": "", "total_line": "44", "spread_line": "3",
            "referee": "Brad Allen"}]
    got = refcheck.rows_from(raw)
    assert len(got) == 1 and got[0]["total"] == 0.0 and got[0]["margin"] == 1.0


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
