"""The NFL teammate fit gives one answer on every Python (3.9 to 3.13).

Found 2026-11-04: `engine/matefit`'s shipped rule matched `teammates.EFFECT`
on Python 3.11 and not on 3.12 or 3.13, which the box runs. Python 3.12
changed the built-in sum() of floats to a compensated algorithm, so the form
blend (`statmath.weighted_mean`) came out an ulp apart; a blend landing
exactly on a market's floor (Latavius Murray's 8, 22 and 15 rushing yards
average exactly 15 in every window) was 15.0 on one and 14.999999999999998
on the other, so one Python kept the game and the other dropped it, and the
running backs' rushing multiplier behind a back just ruled out came out
1.102 or 1.103. These hold, with no cached data needed:

  * the shared averages are the correctly rounded sum on every Python
    (math.fsum), so the same inputs give the same bits;
  * a blend ON the floor is a sample whatever its last bit
    (`matefit.below_floor`), one under it is not, and the sample builders
    all use that one rule;
  * the measurement does not depend on the order of its games.

With the box scores cached (data/cache), tests/test_every_input_reaches_the_
most_likely_number.py holds the full rule to EFFECT and EFFECT_SNAPS.

Run directly: `python3 tests/test_the_teammate_fit_gives_one_answer_on_every_python.py`
"""
import random
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import matefit as F                                       # noqa: E402
from engine import qbfit as Q                                         # noqa: E402
from engine import statmath as S                                      # noqa: E402
from engine.form import compute_form, _avg                            # noqa: E402
from engine.models import GameLog                                     # noqa: E402


def _blend(vals):
    logs = [GameLog(week=len(vals) - j, opponent="", value=v) for j, v in enumerate(reversed(vals))]
    return compute_form(logs, sum(vals) / len(vals), None).mean


def test_the_averages_are_the_correctly_rounded_sum_on_every_python():
    # Ten tenths: 0.9999999999999999 added up the old way (3.9-3.11), 1.0 exactly.
    assert S.weighted_mean([(0.1, 1.0)] * 10) == 0.1
    assert _avg([0.1] * 10) == 0.1
    rng = random.Random(7)
    for _ in range(200):
        pairs = [(rng.uniform(-50, 120), rng.choice((0.07, 0.09, 0.14, 0.16, 0.22, 0.25))) for _ in range(7)]
        num = sum((Fraction(v * w) for v, w in pairs), Fraction(0))
        den = sum((Fraction(w) for _v, w in pairs), Fraction(0))
        assert S.weighted_mean(pairs) == float(num) / float(den), pairs
    vals = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    mean = float(sum((Fraction(v) for v in vals), Fraction(0))) / len(vals)
    assert S.sample_std(vals) > 0 and abs(mean - sum(vals) / len(vals)) < 1e-15


def test_a_blend_on_the_floor_is_a_sample_and_one_under_it_is_not():
    on = _blend([8.0, 22.0, 15.0])                    # Murray, BUF 2023, before week 4
    assert abs(on - 15.0) < 1e-12, on
    assert not F.below_floor(on, 15.0), "exactly on the floor: kept, whatever the last bit"
    assert not F.below_floor(15.0 - 1e-12, 15.0) and not F.below_floor(15.0 + 1e-12, 15.0)
    assert F.below_floor(14.99, 15.0) and F.below_floor(0.0, 0.0) and F.below_floor(-1.0, 0.0)
    assert not F.below_floor(0.4, 0.0), "a touchdown market's floor is zero: any blend above it counts"
    src = (ROOT / "engine" / "matefit.py").read_text(encoding="utf-8")
    assert src.count("if below_floor(e, floor):") == 4 and "if e < floor or e <= 0:" not in src, \
        "every sample builder reads the same floor"


def test_the_sample_builder_keeps_the_game_on_the_floor():
    rows = []
    games = {"Starter": [18, 18, 18, 18, 18], "Back": [8, 22, 15, 30, 30], "Third": [3, 3, 3, 3, 3]}
    for name, yds in games.items():
        for wk, y in enumerate(yds, start=1):
            rows.append({"season_type": "REG", "week": str(wk), "team": "BUF", "position": "RB",
                         "player_display_name": name, "carries": "12", "rushing_yards": str(y),
                         "targets": "0", "receptions": "0", "receiving_yards": "0",
                         "receiving_tds": "0", "rushing_tds": "0"})
    pts = [p for p in F.samples({2023: rows}) if p["m"] == "rush_yds"]
    back = [p for p in pts if abs(p["e"] - 15.0) < 1e-9]
    assert back, "the back whose blend lands exactly on 15 rushing yards is measured in week 4"


def test_the_measurement_does_not_depend_on_the_order_of_its_games():
    rng = random.Random(11)
    pts = []
    for i in range(600):
        tier = None if i % 3 else rng.choice(("above_new", "below_new"))
        pts.append({"season": 2022 + i % 4, "m": "rush_yds", "g": "RB", "tier": tier,
                    "y": float(rng.randint(0, 140)), "e": rng.uniform(15.0, 95.0)})
    a = Q.measure(pts)
    for _ in range(5):
        shuffled = list(pts)
        rng.shuffle(shuffled)
        assert Q.measure(shuffled) == a
    assert a and all(set(v) == {"mult", "se", "n", "per"} for v in a.values())


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"  FAIL {name}: {exc}")
            traceback.print_exc()
    if fails:
        print(f"\n{fails} of {len(tests)} tests failed.")
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
