"""Sportsbook odds math: American odds, implied probability, de-vigging and
converting an edge into an expected-value figure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import SportsbookLine


def american_to_prob(odds: int) -> float:
    """Convert American odds to the book's implied probability (with vig)."""
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def american_to_decimal(odds: int) -> float:
    if odds < 0:
        return 1.0 + 100.0 / (-odds)
    return 1.0 + odds / 100.0


# Assumed hold when a market is quoted on one side only (books shade the
# quoted side by roughly this much).
ONE_SIDED_HOLD = 1.05


def devig_two_way(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Remove the vig from a two-way market, returning fair (over, under)
    probabilities that sum to 1.0.

    A missing side (odds of 0/None — e.g. home-run markets are quoted
    Over-only) de-vigs the quoted side with an assumed hold instead of
    pretending a fabricated opposite price is information."""
    if not under_odds and over_odds:
        fair_over = min(0.99, american_to_prob(over_odds) / ONE_SIDED_HOLD)
        return fair_over, 1.0 - fair_over
    if not over_odds and under_odds:
        fair_under = min(0.99, american_to_prob(under_odds) / ONE_SIDED_HOLD)
        return 1.0 - fair_under, fair_under
    if not over_odds and not under_odds:
        return 0.5, 0.5
    p_over = american_to_prob(over_odds)
    p_under = american_to_prob(under_odds)
    total = p_over + p_under
    if total <= 0:
        return 0.5, 0.5
    return p_over / total, p_under / total


def expected_value(model_prob: float, odds: int, stake: float = 1.0) -> float:
    """EV of a 1-unit bet given the model's true win probability."""
    dec = american_to_decimal(odds)
    win = (dec - 1.0) * stake
    return model_prob * win - (1.0 - model_prob) * stake


@dataclass
class BestLine:
    book: str
    line: float
    odds: int
    fair_prob: float      # de-vigged implied probability at this book


def best_over_line(lines: list[SportsbookLine]) -> BestLine:
    """Pick the most bettor-friendly OVER line across books.

    We prefer the lowest line, breaking ties by the best (highest) odds. This
    is the "shop for the best number" step every sharp bettor does.
    """
    best: BestLine | None = None
    for ln in lines:
        fair_over, _ = devig_two_way(ln.over_odds, ln.under_odds)
        cand = BestLine(ln.book, ln.line, ln.over_odds, fair_over)
        if best is None:
            best = cand
            continue
        if ln.line < best.line or (ln.line == best.line and ln.over_odds > best.odds):
            best = cand
    assert best is not None
    return best


def best_under_line(lines: list[SportsbookLine]) -> BestLine:
    """Pick the most bettor-friendly UNDER line across books.

    Mirror image of ``best_over_line``: for an under you want the *highest*
    line (more cushion), breaking ties by the best (highest) under odds.
    """
    best: BestLine | None = None
    for ln in lines:
        _, fair_under = devig_two_way(ln.over_odds, ln.under_odds)
        cand = BestLine(ln.book, ln.line, ln.under_odds, fair_under)
        if best is None:
            best = cand
            continue
        if ln.line > best.line or (ln.line == best.line and ln.under_odds > best.odds):
            best = cand
    assert best is not None
    return best


# A book's two sides must sum to MORE than 100% — that sum minus one is
# its margin, which is how it makes money. A pair summing meaningfully
# below 100% is not a gift, it is corrupt data: most often an over-only
# prop (home runs) whose absent under got filled with a placeholder.
# Measured on harvested rows: Caesars showing "over +850 / under -110"
# on a home run, which implies 10.5% + 52.4% = 63% and reads as a 37%
# arbitrage against itself.
#
# Genuine cross-book arbitrage exists but is small — a 5% cushion admits
# every real one while rejecting fabrications.
PAIR_SANITY_FLOOR = 0.95


def pair_is_sane(over_odds, under_odds) -> bool:
    """False when a single book's over/under pair is arithmetically
    impossible, i.e. the two sides imply less than PAIR_SANITY_FLOOR."""
    try:
        o, u = int(over_odds), int(under_odds)
    except (TypeError, ValueError):
        return False
    if not o or not u:          # 0 = side not offered
        return False
    return (american_to_prob(o) + american_to_prob(u)) >= PAIR_SANITY_FLOOR
