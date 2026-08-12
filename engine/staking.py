"""One scale for every stake: 1 unit = 1% of bankroll, priced for trust.

The journal was quoting stakes off TWO different rulers. The parlay spec
pinned 1u = 1% of bankroll, but every prop path converted its Kelly
fraction to units with ``* 20`` — a 20-unit bankroll — so a solid -110
play that quarter-Kelly says deserves ~2.4% landed at 0.48u, and a thin
edge rounded to the same 0.1-0.2u as a home-run dime. Ethan read the
symptom straight off the board: "we put .1 on home runs AND .1 on
regular -100 props." The ROI line inherited the distortion, because
units staked is its denominator.

Everything now converts through here at BANKROLL_UNITS = 100, and the
per-grade caps (2u / 1u / 0.5u) become the working range instead of a
ceiling nothing reached: a real edge at an ordinary price stakes ~1u, a
hairline edge stakes under it, and Kelly still zeroes anything below
break-even at the offered price.

The second ruler is TRUST, and it caps by PRICE. Kelly assumes the
probability fed to it is right; ours is least right exactly where the
payout is long — the receipts say so (home-run overs: said 14%, hit 11%,
q=0.003, and the market self-closed on that evidence). So odds bands cap
what any model conviction may stake:

    +200 and longer     0.1u  — dime territory, whatever Kelly thinks
    +120 to +199        0.5u
    shorter than +120   the grade cap alone

A price cap is not a second opinion about the edge; it is honesty about
the error bars on our own probability at that price.

Settled history is NOT restated: those stakes were the bets as made, and
the Record page is receipts. The scale change dates a new model era and
reads honestly from here forward.
"""

from __future__ import annotations

from .odds import american_to_decimal

#: 1u = 1% of bankroll — the documented scale (§10 / parlays), now the
#: only one in the codebase.
BANKROLL_UNITS = 100.0
#: Any positive stake floors here so a real edge never displays as 0.00u.
MIN_STAKE_UNITS = 0.1

#: Price-band ceilings, in units.
LONGSHOT_ODDS = 200
LONGSHOT_CAP_U = 0.1
DOG_ODDS = 120
DOG_CAP_U = 0.5


def kelly_fraction(p: float, odds: int) -> float:
    """Full-Kelly bankroll fraction; 0 means the price beats the edge."""
    b = american_to_decimal(odds) - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (b * p - (1.0 - p)) / b)


def price_cap_units(odds: int) -> float:
    """The most units ANY conviction may stake at this price."""
    if odds >= LONGSHOT_ODDS:
        return LONGSHOT_CAP_U
    if odds >= DOG_ODDS:
        return DOG_CAP_U
    return float("inf")


def units_with_reason(fraction: float, odds: int,
                      cap_units: float = float("inf"),
                      mult: float = 1.0) -> tuple[float, str]:
    """``(units, why)`` — the stake and the rule that actually set it.

    Ethan, 2026-08-12, reading a board of 0.25 / 0.25 / 0.25 / 0.15 /
    0.05: "It doesn't make any sense and feels random." It was not
    random, but it was unreadable, because four different rules can set
    a stake and the board showed none of them. When a cap binds, the
    stake stops carrying information about the edge — five picks with
    five different edges all print 0.25u — and without the reason beside
    it there is no way to tell that from noise.
    """
    if fraction <= 0 or mult <= 0:
        return 0.0, "no bet"
    want = fraction * BANKROLL_UNITS * mult
    price = price_cap_units(odds)
    stake, why = want, "quarter-Kelly on the price offered"
    if price < stake:
        stake, why = price, f"capped at {price:g}u by the price band"
    if cap_units < stake:
        stake, why = cap_units, f"capped at {cap_units:g}u by the grade"
    if stake < MIN_STAKE_UNITS:
        stake, why = MIN_STAKE_UNITS, f"floored at the {MIN_STAKE_UNITS}u minimum"
    return round(stake, 2), why


def to_units(fraction: float, odds: int,
             cap_units: float = float("inf"), mult: float = 1.0) -> float:
    """Bankroll fraction → display units, price-capped, floored.

    ``fraction`` is the already-fractioned Kelly (or any bankroll share);
    ``cap_units`` is the caller's own ceiling (per-grade, per-play);
    ``mult`` is a caller-side downweight (e.g. the NBA minutes grade).
    """
    return units_with_reason(fraction, odds, cap_units, mult)[0]


def kelly_units(p: float, odds: int, fraction: float = 0.25,
                cap_units: float = float("inf")) -> float:
    """The whole path in one call: full Kelly, fractioned, scaled, capped."""
    full = kelly_fraction(p, odds)
    if full <= 0:
        return 0.0
    return to_units(full * fraction, odds, cap_units)
