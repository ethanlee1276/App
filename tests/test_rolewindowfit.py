"""The usage bridge weights a player's games by age — measured, and only where it measured better.

rolewindowfit.py chose a half-life per opportunity on 2017-2021 and judged
it on 2022-2025, the board's whole base rebuilt (form, bridge, last-season
pull, defence step). Targets (H=8) and carries (H=2) improved every test
season; attempts did not (2024 worse), so attempts keep the flat four.

What these hold: the age weighting is exactly 0.5 ** (age / H) with the
newest game at age zero; no half-life is the flat last VOL_WEEKS; a role
under the efficiency floor is absent, not junk; the chooser picks the
half-life with the least squared error; the shipped setting is the one
the measurement passed.

Run directly: `python3 tests/test_rolewindowfit.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rolewindowfit as RW                                       # noqa: E402
from engine import nflusage as NU                                # noqa: E402


def test_the_age_weighting_is_exact_and_flat_without_a_half_life():
    assert NU.ewma_opps([2.0, 4.0, 6.0, 8.0, 10.0], None) == 7.0, "the last four, flat"
    got = NU.ewma_opps([0.0, 10.0], 1.0)
    assert round(got, 6) == round(10.0 / 1.5, 6), "last game weight 1, the one before 0.5"
    assert NU.ewma_opps([], 4.0) == 0.0
    long = NU.ewma_opps([20.0] * 6 + [5.0] * 2, 8.0)
    short = NU.ewma_opps([20.0] * 6 + [5.0] * 2, 2.0)
    assert short < long < 20.0, "a short half-life believes the two-game drop sooner"


def test_a_role_under_the_floor_is_absent():
    assert RW.role([3.0, 3.0], [20.0, 25.0], "targets", 8.0) is None, "six targets is no role"
    assert RW.role([7.0], [50.0], "targets", 8.0) is None, "one game is no role"
    got = RW.role([6.0, 8.0], [40.0, 80.0], "targets", None)
    assert got == 7.0 * (120.0 / 14.0)


def test_the_chooser_takes_the_least_squared_error():
    pts = [{"m": "rush_yds", "y": 50.0, "base": 40.0, "by": {h: 40.0 + h for h in RW.HALF_LIVES}}]
    assert RW.choose(pts, "carries") == 8.0
    cut = RW.cuts({2024: pts}, "rush_yds", 8.0)
    assert cut[0][:2] == (2024, 1) and cut[0][2] > 0


def test_the_shipped_setting_is_the_one_that_passed():
    assert NU.ROLE_HALF_LIFE == {"targets": 8.0, "carries": 2.0}
    assert "pass_att" not in NU.ROLE_HALF_LIFE, "attempts were worse in 2024; they stay flat"
    src = (ROOT / "engine" / "nflusage.py").read_text(encoding="utf-8")
    assert "if ratio == 1.0 and ROLE_HALF_LIFE.get(opp):" in src, "the detector, once it holds, stays in charge"


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
