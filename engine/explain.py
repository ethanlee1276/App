"""Explanation generator.

Produces the "why we like this bet" summary. The engine never asks the user to
trust a black box: every recommendation carries a one-line headline and a
ranked list of the concrete factors that moved the projection.
"""

from __future__ import annotations

from .models import MARKET_LABELS
from .betting import Recommendation


def headline(rec: Recommendation) -> str:
    label = MARKET_LABELS.get(rec.market, rec.market)
    return f"{rec.player} OVER {rec.line:g} {label}"


def summary(rec: Recommendation) -> str:
    """One sentence tying the numbers together."""
    return (
        f"Model projects {rec.projection:g} "
        f"(range {rec.proj_low:g}–{rec.proj_high:g}) vs a line of {rec.line:g}, "
        f"a {rec.hit_prob:.0%} hit probability against the book's {rec.fair_prob:.0%} "
        f"— a {rec.edge:+.1%} edge. Confidence {rec.confidence}/10 → {rec.grade}."
    )


def bullet_reasons(rec: Recommendation, limit: int = 8) -> list[str]:
    """Deduplicated, capped list of contributing factors for the UI."""
    seen: set[str] = set()
    out: list[str] = []
    for r in rec.reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
        if len(out) >= limit:
            break
    return out
