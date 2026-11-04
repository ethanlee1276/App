"""The NBA's minutes model runs on measured numbers, not the spec's
(engine/hoops.NBA, docs/NBA_LAB.md, 2026-11-04).

Ethan, 2026-11-04: "I want to make sure we're picking the right bets,
reading the right scripts, picking the right models ... everything's tuned
in." The rest and blowout haircuts were a written spec's and had never
been fitted. On two full seasons through the board's own minutes code
(every player-game with 15+ minutes a game), fitted on 2024-25 and judged
on 2025-26, minutes error fell from 6.404 to 6.209 (-3.0%). These hold:

  * a man who suits up on a back-to-back, or a third game in four nights,
    plays about his usual minutes: no rest haircut of more than 1%, where
    the spec's 4-8% read those nights light and leaned picks to the under;
  * a long break costs about 4%;
  * a favourite's starters lose 1-5% across the spreads, never the spec's
    9-14%; the underdog's share stays 0.6; rotation bench players gain
    nothing in a blowout (the spec gave them up to +20%);
  * the base reads the newest games more (0.60 / 0.25 / 0.15), and a bench
    player's recent minutes are trimmed 2%;
  * the WNBA inherits the measured haircuts (it has no sample of its own)
    and keeps its spec's own recency weights.

Run directly: `python3 tests/test_the_nba_minutes_are_measured.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import hoops                          # noqa: E402
from engine.nba import minutes as M               # noqa: E402

NBA = hoops.NBA


def test_a_compressed_schedule_does_not_cut_his_minutes():
    for key in ("b2b_home", "b2b_road", "b2b_road_30plus", "3in4", "4in6_road"):
        assert 0.99 <= NBA.rest_mult[key] <= 1.02, (key, NBA.rest_mult[key])
    # Every back-to-back is labelled b2b_home by the build (nba_build.rest_from
    # never says road); with one measured value for both, the label cannot
    # cost a road back-to-back anything.
    assert NBA.rest_mult["b2b_home"] == NBA.rest_mult["b2b_road"]
    assert NBA.rest_mult["2plus"] < 0.98, "a long break costs a few minutes"
    assert M.project_minutes(30.0, 0.0, True, False, rest="3in4") >= 30.0


def test_a_blowout_costs_starters_a_little_and_gives_the_bench_nothing():
    fav = [M.blowout_mult(-s, True, True) for s in (3, 6, 9, 12, 16)]
    assert fav == sorted(fav, reverse=True) and fav[0] == 1.0
    assert min(fav) >= 0.94, "a 16-point favourite's starters lose about 5%, not 14%"
    assert all(M.blowout_mult(-s, False, True) <= 1.0 for s in (6, 9, 12, 16)), \
        "rotation bench players gain nothing in a projected blowout"
    dog = M.blowout_mult(16, True, False)
    assert abs((1 - dog) / (1 - min(fav)) - NBA.dog_haircut_share) < 1e-9


def test_the_base_and_the_bench_correction():
    assert NBA.recency_weights == (0.60, 0.25, 0.15)
    assert NBA.role_minutes_mult == {"starter": 1.00, "bench": 0.98}
    bench = M.project_minutes(25.0, 0.0, False, False, rest="1day")
    starter = M.project_minutes(25.0, 0.0, True, False, rest="1day")
    assert starter == 25.0 and bench == 24.5


def test_the_wnba_inherits_the_measured_haircuts_and_keeps_its_own_weights():
    W = hoops.WNBA
    assert W.rest_mult == NBA.rest_mult and W.blowout_starter == NBA.blowout_starter
    assert W.blowout_bench == NBA.blowout_bench and W.role_minutes_mult == NBA.role_minutes_mult
    assert W.recency_weights == (0.40, 0.30, 0.20)


def test_the_spec_is_kept_for_the_record_not_used():
    # The class defaults are the spec's; the NBA's own values replace them.
    spec = hoops.LeagueTuning(key="x", name="x")
    assert spec.rest_mult["b2b_road"] == 0.93 and NBA.rest_mult["b2b_road"] == 0.99
    assert spec.blowout_bench[-1][1] == 1.20 and NBA.blowout_bench[-1][1] == 0.99


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
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
