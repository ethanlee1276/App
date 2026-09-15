"""Statcast layer — batted-ball quality & expected-stats regression.

The single most valuable Statcast signal for props is the gap between
*expected* and *actual* results:

  * a hitter whose **xSLG exceeds his SLG** has been hitting the ball hard
    without the results to show for it — a positive-regression (buy) candidate;
  * one whose SLG runs ahead of his xSLG has been lucky — a fade candidate.

On top of that, barrel rate and hard-hit rate forecast power (total bases /
home runs), and for pitchers CSW% / whiff% forecast strikeouts. This module
turns a :class:`StatcastProfile` into a bounded multiplier plus reasons; the
magnitudes are deliberately small because books price obvious hot streaks in —
the edge is in the *expected-stats* correction they underweight.

This is the batted-ball-quality forecasting piece of the vision. The full
pitch-by-pitch simulation and ML on 5+ years of Statcast remain the historical-
database phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..statmath import clamp
from .models import (
    StatcastProfile, TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS, HITTER_MARKETS,
)

LEAGUE_BARREL = 0.08
LEAGUE_HARD_HIT = 0.38
LEAGUE_CSW = 0.28


@dataclass
class StatcastEffect:
    multiplier: float
    reasons: list[str] = field(default_factory=list)


def _slg(v: float) -> str:
    return f".{round(v * 1000):03d}"


def evaluate_statcast(p: StatcastProfile, market: str) -> StatcastEffect:
    mult = 1.0
    reasons: list[str] = []

    if market in HITTER_MARKETS:
        # Expected-stats regression: xSLG vs SLG.
        if p.xslg is not None and p.slg is not None:
            gap = p.xslg - p.slg
            mult *= 1.0 + clamp(gap * 0.6, -0.06, 0.06)
            if gap >= 0.03:
                reasons.append(f"xSLG {_slg(p.xslg)} vs SLG {_slg(p.slg)} — "
                               f"positive regression (quality contact ahead of results)")
            elif gap <= -0.03:
                reasons.append(f"SLG {_slg(p.slg)} ahead of xSLG {_slg(p.xslg)} — "
                               f"results running hot, regression risk")
        # xwOBA vs wOBA reinforces the same signal on overall production.
        elif p.xwoba is not None and p.woba is not None:
            gap = p.xwoba - p.woba
            mult *= 1.0 + clamp(gap * 0.5, -0.04, 0.04)
            if abs(gap) >= 0.02:
                verb = "under" if gap > 0 else "over"
                reasons.append(f"xwOBA {_slg(p.xwoba)} vs wOBA {_slg(p.woba)} — "
                               f"{verb}performing expected output")

        # Quality of contact forecasts power.
        if p.barrel_pct is not None and market in (TOTAL_BASES, HOME_RUNS):
            if p.barrel_pct >= 0.12:
                mult *= 1.05 if market == HOME_RUNS else 1.03
                reasons.append(f"Elite barrel rate {p.barrel_pct:.0%} — power backing")
            elif p.barrel_pct <= 0.04:
                mult *= 0.95 if market == HOME_RUNS else 0.98
                reasons.append(f"Low barrel rate {p.barrel_pct:.0%} — soft contact")
        if p.hard_hit_pct is not None and p.hard_hit_pct >= 0.48 \
                and market in (TOTAL_BASES, HITS):
            mult *= 1.02
            reasons.append(f"Hard-hit rate {p.hard_hit_pct:.0%}")

    elif market == STRIKEOUTS:
        if p.csw_pct is not None:
            factor = clamp(p.csw_pct / LEAGUE_CSW, 0.85, 1.20)
            mult *= 1.0 + (factor - 1.0) * 0.5
            if p.csw_pct >= 0.31:
                reasons.append(f"Elite CSW% {p.csw_pct:.0%} — swing-and-miss stuff")
            elif p.csw_pct <= 0.25:
                reasons.append(f"Below-average CSW% {p.csw_pct:.0%} — K upside capped")
        elif p.whiff_pct is not None and p.whiff_pct >= 0.30:
            mult *= 1.04
            reasons.append(f"High whiff rate {p.whiff_pct:.0%}")

    return StatcastEffect(clamp(mult, 0.90, 1.12), reasons)
