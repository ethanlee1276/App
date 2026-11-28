"""The input check flags a person only for what needs one.

Ethan's box run, 2026-09-24: LOOK AT THESE listed twenty-three steps that
"moved none" of their rows. Most were the code doing what it says — a
factor built without a coefficient for that market, or per-player memory
the record has not earned for it — and they sat beside the ones that do
need a person (pitcher strikeouts' contact quality: the loader reads the
batter files only, so the strikeout branch has never had data).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import inputcheck as I                          # noqa: E402


def _market(steps, n=24):
    return {"n": n, "moved": {}, "seen": {k: n for k in steps}, "priced": n,
            "roles": {}, "cards": 0}


def _flags(sport, cen, adopted=False):
    real = I._memory_on
    I._memory_on = lambda s, m: adopted
    try:
        return I.findings(sport, cen)
    finally:
        I._memory_on = real


def test_flat_by_construction_is_known_not_flagged():
    cen = {"outs": _market(["park", "weather", "statcast"]),
           "hits": _market(["weather"]),
           "home_runs": _market(["ump"])}
    assert _flags("mlb", cen) == []
    assert _flags("nfl", {"rush_yds": _market(["weather"], 103)}) == []


def test_memory_the_record_has_not_earned_is_not_a_loose_wire():
    cen = {"receptions": _market(["player"], 230)}
    assert _flags("nfl", cen, adopted=False) == []
    got = _flags("nfl", cen, adopted=True)
    assert got and "'Player memory' moved none of 230 rows" in got[0], \
        "adopted and still moving nothing IS a loose wire"


def test_the_real_gap_still_reaches_a_person():
    got = _flags("mlb", {"strikeouts": _market(["statcast"])})
    assert got == ["mlb strikeouts: 'Contact quality' moved none of 24 rows — wired in and reading nothing?"]


def test_an_unreadable_store_still_asks():
    real = I._memory_on
    try:
        import engine.playerfit as P
        load = P._load
        P._load = lambda path=None: (_ for _ in ()).throw(OSError("gone"))
        try:
            assert I._memory_on("nfl", "receptions") is True
        finally:
            P._load = load
    finally:
        I._memory_on = real


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
