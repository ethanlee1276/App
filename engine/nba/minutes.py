"""The minutes engine — build this first, every time.

~70% of prop outcome variance traces back to minutes played, so minutes
are modeled explicitly before any stat projection:

    ProjMIN = BaseMIN × M_blowout × M_rest (+ vacancy), capped

* BaseMIN weights the current role only: last 5 games ×0.50, games 6-10
  ×0.30, games 11-20 ×0.20.
* M_blowout is ASYMMETRIC: the favorite's starters lose more minutes than
  the dog's, because trailing teams keep starters in chasing the game —
  the underdog takes ~60% of the haircut.
* Vacancy minutes are capped: nobody projects more than +8 over their
  recent high. Coaches are more conservative than models.
* Every prop gets a Minutes Confidence Grade (A-D) that gates the stake:
  A full, B 0.75×, C 0.5×, D = no bet.

Blowout probability comes from the spread with margin ~ Normal(spread,
11.5) — a 12-point favorite blows the doors off ~30% of the time, and any
prop in a game with P(blowout) > 25% drops one full grade.
"""

from __future__ import annotations

import math

BLOWOUT_STARTER = ((4.5, 1.00), (7.5, 0.98), (10.5, 0.95),
                   (13.5, 0.91), (float("inf"), 0.86))
BLOWOUT_BENCH = ((4.5, 1.00), (7.5, 1.02), (10.5, 1.06),
                 (13.5, 1.12), (float("inf"), 1.20))
DOG_HAIRCUT_SHARE = 0.6            # the dog takes ~60% of the starter haircut

REST_MULT = {"2plus": 1.01, "1day": 1.00, "b2b_home": 0.96,
             "b2b_road": 0.93, "b2b_road_30plus": 0.88,
             "3in4": 0.94, "4in6_road": 0.92}

VACANCY_CAP_OVER_HIGH = 8.0
MARGIN_SD = 11.5
BLOWOUT_MARGIN = 18.0
BLOWOUT_GRADE_DROP = 0.25          # P(blowout) above this drops one grade

GRADE_STAKE = {"A": 1.0, "B": 0.75, "C": 0.5, "D": 0.0}


def base_minutes(recent_minutes: list[float]) -> float | None:
    """Weighted current-role minutes, most recent first. The caller feeds
    only current-role games with early-exit/blowout games excluded."""
    if len(recent_minutes) < 3:
        return None
    m = recent_minutes[:20]
    chunks = ((m[:5], 0.50), (m[5:10], 0.30), (m[10:20], 0.20))
    num = den = 0.0
    for vals, w in chunks:
        if vals:
            num += w * (sum(vals) / len(vals))
            den += w
    return round(num / den, 2) if den else None


def blowout_mult(spread: float, is_starter: bool, is_favorite: bool) -> float:
    """Spread-driven minutes multiplier, asymmetric by side."""
    size = abs(spread)
    table = BLOWOUT_STARTER if is_starter else BLOWOUT_BENCH
    for cap, mult in table:
        if size <= cap:
            full = mult
            break
    if is_favorite:
        return full
    return round(1.0 + (full - 1.0) * DOG_HAIRCUT_SHARE, 4)


def blowout_prob(spread: float, sd: float = MARGIN_SD) -> float:
    """P(final margin ≥ 18) with margin ~ Normal(|spread|, sd)."""
    z = (BLOWOUT_MARGIN - abs(spread)) / sd
    return round(1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2))), 4)


def project_minutes(base: float, spread: float, is_starter: bool,
                    is_favorite: bool, rest: str = "1day",
                    vacancy_minutes: float = 0.0,
                    recent_high: float | None = None) -> float:
    proj = base * blowout_mult(spread, is_starter, is_favorite) \
        * REST_MULT.get(rest, 1.0) + vacancy_minutes
    if recent_high is not None:
        proj = min(proj, recent_high + VACANCY_CAP_OVER_HIGH)
    return round(proj, 1)


def minutes_grade(is_starter: bool, spread: float, sample_games: int,
                  restriction: bool = False,
                  role_uncertain: bool = False) -> str:
    """A-D confidence grade. D means no bet, full stop."""
    if restriction:
        return "D"
    if not is_starter and sample_games < 10:
        return "D"
    grade = "A" if (is_starter and sample_games >= 3) else "B"
    if role_uncertain:
        grade = "C" if grade == "B" else "B"
    if blowout_prob(spread) > BLOWOUT_GRADE_DROP:
        grade = {"A": "B", "B": "C", "C": "D"}.get(grade, "D")
    return grade
