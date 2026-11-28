#!/usr/bin/env python3
"""EXP-006 — does EXP-005's shrink add to the two-stage model on NFL receptions?

    python3 research/exp6_shrink_b.py            (prints the fitted line, and the rows so far)

EXP-005 found the direct model's receptions centre spread about 15% too
wide: shrunk toward the middle by a straight line in its own centre, it
beat itself on 2024-26 games the search never saw (CRPS -0.0067). EXP-001
and EXP-004 found the two-stage model B beats the direct one on receptions
in both the NFL and college (-0.027 each), by its shape, not its centre.
The question left: is B's centre too wide in the same way, so that the two
gains add — or is B's gain the shrink already (B's centre is lower than A's
exactly where A runs high)?

THE CANDIDATE, written before any game it is scored on: B' is B's
distribution moved to the centre m' = max(0.05, m_B + c0 + c1 · m_B), the
line (c0, c1) fitted by least squares of (y − m_B) on m_B over 2017-2025
receptions rows, with B itself fitted on 2017-2025 — EXP-001b's training.
The line is printed by this script and does not change; fitted 2026-10-19
it is m' = m_B + 0.4919 − 0.18155 · m_B — B's centre spread too wide as
well, a little more than A's (EXP-005's slope was −0.154).

THE TEST. CRPS(B') − CRPS(B) on NFL receptions, on every 2026 regular-season
game played after 2026-10-17 (EXP-001's freeze), clustered by player-season;
B' ADVANCES if the upper bound is under zero at 95% (one test); right
direction with the bound over zero is INCONCLUSIVE; wrong direction
REJECTED. ONE READ: like EXP-001b, it is read once, when every one of
those games is final and in nflverse's weekly file; until then the script
prints how many rows have arrived and nothing else.

Reads data/cache only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import exp1_two_stage as E1                        # noqa: E402

FIT = range(2017, 2026)
MARKET = "receptions"
ALPHA = 0.05


def shrink_line(fit, rows: list[dict]) -> tuple[float, float]:
    """(c0, c1): least squares of (y − m_B) on m_B over ``rows``."""
    pairs = [(fit.mean_b(x), x["y"] - fit.mean_b(x)) for x in rows if x["m"] == MARKET]
    n = len(pairs)
    mx = sum(m for m, _r in pairs) / n
    mr = sum(r for _m, r in pairs) / n
    sxx = sum((m - mx) ** 2 for m, _r in pairs)
    c1 = sum((m - mx) * (r - mr) for m, r in pairs) / sxx
    return mr - c1 * mx, c1


def scored(fit, line: tuple, rows: list[dict]) -> list[dict]:
    """CRPS for B and for B moved to the shrunk centre, per row."""
    c0, c1 = line
    grid = E1.GRID[MARKET]
    out = []
    for x in rows:
        if x["m"] != MARKET:
            continue
        mb = fit.mean_b(x)
        target = max(0.05, mb + c0 + c1 * mb)
        fb = fit.cdf_b(x, grid)
        fs = fit.cdf_b(x, grid, scale=target / mb) if mb > 0 else fb
        out.append({"m": MARKET, "s": x["s"], "who": x["who"], "b": E1.crps(fb, grid, x["y"]),
                    "s_": E1.crps(fs, grid, x["y"])})
    return out


def decide(sc: list[dict]) -> tuple[str, tuple]:
    keep = E1.ALPHA
    E1.ALPHA = ALPHA
    try:
        mean, lo, hi = E1.boot_diff(sc, key_b="s_", key_a="b")
    finally:
        E1.ALPHA = keep
    verdict = "REJECTED" if mean >= 0 else ("ADVANCE" if hi < 0 else "INCONCLUSIVE")
    return verdict, (mean, lo, hi)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    train = [x for s in FIT for x in E1.rows_for(s)]
    fit = E1.Fit(train)
    line = shrink_line(fit, train)
    print(f"EXP-006 — B against B at its shrunk centre, NFL receptions. Fitted on {FIT.start}-{FIT.stop - 1}: "
          f"m' = m_B {line[0]:+.4f} {line[1]:+.5f} · m_B")
    done, total = E1.season_done()
    games = E1._after_freeze()
    if not total or done < total:
        n = sum(1 for x in E1.rows_for(2026, only=games) if x["m"] == MARKET) if games else 0
        print(f"  {done} of {total} regular-season games after {E1.FREEZE} final with stats; {n:,} rows so far. "
              f"Read once when all are in; nothing scored until then.")
        return 0
    sc = scored(fit, line, E1.rows_for(2026, only=games))
    verdict, (mean, lo, hi) = decide(sc)
    n = len(sc)
    print(f"  {n:,} rows: CRPS B {sum(p['b'] for p in sc) / n:.4f}  B' {sum(p['s_'] for p in sc) / n:.4f}  "
          f"B'-B {mean:+.4f} [{lo:+.4f}, {hi:+.4f}]  {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
