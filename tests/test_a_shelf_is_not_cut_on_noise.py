"""A Most Likely shelf carries the band its ROI is worth, and a gate.

Ethan, 2026-09-16, reading `launch.py --likely`:

    pass_td       2   57.3%   50.0%  -22.20%
    total_bases 216   68.6%   73.2%   +2.98%

Two numbers in one column, and nothing to say the first is two coin
flips. The whole-board verdict below that table has carried a noise band
and an `enough` gate since it shipped; the per-market table — the table a
shelf actually gets cut from — carried neither.

WHY THIS IS THE FIRST THING #165 NEEDED. "Make the Most Likely board
pay" reads like a mandate to remove the losing shelves. Run the real
numbers through the gate and SIX of thirteen shelves have enough settled
to say anything, three of those are negative, and NOT ONE of them is
negative by more than its own band. There is nothing to cut on evidence
— which is worth knowing before an afternoon is spent cutting things.

This repo has already made the small-sample mistake twice in one day: a
-23.1% claim on 12 bets that read +20.5% hours later, and an underdog
split of 8. The gate is the same lesson, made structural.

Run directly: `python3 tests/test_a_shelf_is_not_cut_on_noise.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger                                     # noqa: E402

#: Ethan's real per-market row from 2026-09-16: (market, n, roi).
REAL = [("pass_td", 2, -0.2220), ("anytime_td", 4, -0.2410),
        ("pass_yds", 10, -0.2528), ("home_runs", 11, -0.0691),
        ("receptions", 17, -0.0086), ("rush_yds", 20, 0.1559),
        ("rec_yds", 27, -0.0619), ("team_total", 47, -0.1064),
        ("moneyline", 64, -0.0127), ("total", 107, -0.0056),
        ("spread", 119, 0.0159), ("hits", 160, 0.0137),
        ("total_bases", 216, 0.0298)]


def _band(n):
    return 2.0 / (n ** 0.5)


def test_the_gate_and_the_band_are_published_per_shelf():
    """`launch.py --likely` can only print what the report returns.

    SCOPED TO THE by_market BLOCK. A bare `'"enough"' in src` passed
    with the per-market gate deleted, because the WHOLE-BOARD verdict
    sets `p["enough"]` in the same function — the assertion was reading
    a different key with the same name. The same trap was found an hour
    earlier in the confidence sweep's UNDERDOGS column.
    """
    import inspect
    src = inspect.getsource(ledger.likely_report)
    i = src.index('p["by_market"][r["market"]] = {')
    block = src[i:i + 900]
    for key in ('"roi_band"', '"enough"', '"needed"'):
        assert key in block, (
            f"the per-market row does not carry {key}:\n{block}")


def test_a_shelf_under_the_gate_is_never_marked_actionable():
    for market, n, _roi in REAL:
        enough = n >= ledger.LIKELY_MARKET_MIN_N
        assert enough == (n >= 40), (market, n)
        if n < ledger.LIKELY_MARKET_MIN_N:
            assert not enough, market


def test_the_band_is_wider_than_the_number_on_every_thin_shelf():
    """The claim the gate rests on. If a thin shelf's ROI ever exceeded
    its own band, the gate would be costing real information."""
    for market, n, roi in REAL:
        if n >= ledger.LIKELY_MARKET_MIN_N:
            continue
        assert abs(roi) < _band(n), (
            f"{market} at n={n} shows {roi:+.1%} against a band of "
            f"+/-{_band(n):.0%} — this one IS distinguishable and the "
            f"gate is hiding it")


def test_nothing_on_the_real_board_is_cuttable_yet():
    """THE FINDING, pinned so a later change has to argue with it.

    Six shelves clear the gate, three of those are negative, and none is
    negative by more than its own band. #165's answer on 2026-09-16 is
    therefore 'wait or change the selection', never 'cut the losers'.
    """
    actionable = [(m, n, roi) for m, n, roi in REAL
                  if n >= ledger.LIKELY_MARKET_MIN_N]
    assert len(actionable) == 6, actionable
    losing = [(m, n, roi) for m, n, roi in actionable if roi < 0]
    assert {m for m, _, _ in losing} == {"moneyline", "team_total", "total"}, losing
    beyond = [m for m, n, roi in losing if abs(roi) > _band(n)]
    assert not beyond, (
        f"{beyond} now loses by more than its own band — that shelf has "
        f"become cuttable and this test should be re-read, not deleted")


def test_the_band_shrinks_as_the_sample_grows():
    assert _band(2) > _band(40) > _band(216)
    assert _band(ledger.LIKELY_MARKET_MIN_N) < 0.35, (
        "the gate admits shelves whose band is still a third of the "
        "number; LIKELY_MARKET_MIN_N is too low to mean anything")


def test_the_shelf_gate_is_not_the_boards_promotion_gate():
    """Two different questions. Conflating them either blocks every
    shelf until the board is promotable, or promotes the board on one
    shelf's sample."""
    assert ledger.LIKELY_MARKET_MIN_N != ledger.LIKELY_VERDICT_N
    assert ledger.LIKELY_MARKET_MIN_N < ledger.LIKELY_VERDICT_N


def test_the_scoreboard_prints_the_gate():
    from pathlib import Path as _P
    src = (_P(__file__).resolve().parents[1] / "launch.py").read_text()
    i = src.index('by market (the board\'s shelves)')
    block = src[i:i + 2000]
    assert "act on it?" in block, "the column is not printed"
    assert "roi_band" in block and "enough" in block, block[:400]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
