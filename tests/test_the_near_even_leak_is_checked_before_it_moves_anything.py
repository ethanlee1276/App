"""The near-even leak is checked every way that could break it.

Ethan's loss audit, 2026-10-04: the one board's −149 to −111 picks went
147-177 at a claimed 62% against a price asking 56%. bandcheck.py splits
those picks by how far the claim sits over the price, by sport and by time,
and says "holds" only when all four written-down checks agree. Checks: the
band is +120 to −149 and nothing else; a leak spread across sports and
weeks holds; a leak that lives in one sport or one week does not; a band
where small gaps lose as badly does not (the gap is not the cause).

Run directly: `python3 tests/test_the_near_even_leak_is_checked_before_it_moves_anything.py`
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bandcheck as B                                                # noqa: E402


def _rows(spec):
    """spec: [(sport, day, odds, claim, won, count)]"""
    out = []
    for sport, day, odds, claim, won, k in spec:
        need = B.implied(odds)
        out += [{"sport": sport, "day": day, "need": need, "claim": claim, "gap": claim - need,
                 "won": won, "pnl": -1.0 if not won else 0.8}] * k
    return out


def test_the_band_is_plus_120_to_minus_149():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE bets (sport, date, game_day, odds, hit_prob, status, pnl_units, category)")
    for odds in (-200, -149, -111, 120, 150):
        c.execute("INSERT INTO bets VALUES ('nfl','2026-10-04',NULL,?,0.6,'won',1,'board')", (odds,))
    assert sorted(r["need"] for r in B.load(c, ("board",))) == sorted(B.implied(o) for o in (-149, -111, 120))


def _leak(sports=("NFL", "MLB", "CFB"), days=("2026-09-20", "2026-09-27")):
    spec = []
    for s in sports:
        for d in days:
            spec += [(s, d, -130, 0.63, True, 9), (s, d, -130, 0.63, False, 12),   # big gap: 43%
                     (s, d, -130, 0.58, True, 7), (s, d, -130, 0.58, False, 5)]    # small gap: 58%
    return spec


def test_a_leak_across_sports_and_weeks_holds():
    j = B.judge(_rows(_leak()))
    assert j["holds"], j["checks"]


def test_a_leak_in_one_week_only_does_not_hold():
    spec = []
    for s in ("NFL", "MLB", "CFB"):
        spec += [(s, "2026-09-20", -130, 0.63, True, 4), (s, "2026-09-20", -130, 0.63, False, 30),
                 (s, "2026-09-27", -130, 0.63, True, 20), (s, "2026-09-27", -130, 0.63, False, 12),
                 (s, "2026-09-27", -130, 0.58, True, 7), (s, "2026-09-27", -130, 0.58, False, 5)]
    j = B.judge(_rows(spec))
    assert not j["checks"][2] and not j["holds"]


def test_a_leak_in_one_sport_only_does_not_hold():
    spec = _leak(sports=("NFL",))
    for s in ("MLB", "CFB"):
        for d in ("2026-09-20", "2026-09-27"):
            spec += [(s, d, -130, 0.63, True, 15), (s, d, -130, 0.63, False, 6)]
    j = B.judge(_rows(spec))
    assert not j["holds"]


def test_small_gaps_losing_as_badly_means_the_gap_is_not_the_cause():
    spec = []
    for s in ("NFL", "MLB", "CFB"):
        for d in ("2026-09-20", "2026-09-27"):
            spec += [(s, d, -130, 0.63, True, 9), (s, d, -130, 0.63, False, 12),
                     (s, d, -130, 0.58, True, 4), (s, d, -130, 0.58, False, 8)]
    j = B.judge(_rows(spec))
    assert not j["checks"][3] and not j["holds"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
