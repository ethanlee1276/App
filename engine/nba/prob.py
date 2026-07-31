"""The probability layer — the math that makes it a model.

A point projection is worthless without a distribution. Every prop gets
P(cross the line), computed from the right shape for the stat:

* points / PRA — normal, CV from the spec's table (a 25-ppg scorer has an
  SD near 7.5; combos are tighter, which is why they're safer);
* rebounds / assists — NEGATIVE BINOMIAL, exact CDF. NBA counting stats
  are overdispersed (variance > mean); Poisson systematically understates
  the tails, and on a .5 line the difference IS the edge;
* threes — wide (CV ~0.5) and computed exactly for low counts.

Then the two pieces of discipline that keep the model honest:

* the HUMILITY CLAMP — never bet a raw model number. p_final shrinks
  toward the de-vigged market (default w = 0.28), and any 12+ point
  disagreement with a liquid market kills the bet outright: that means an
  input is wrong, not that we found a goldmine;
* the APPROVAL GATE — p_final must beat break-even by 3 points (5 on
  high-hold markets), EV ≥ 3.5%, price no worse than −250, hold ≤ 10%,
  and a minutes grade better than D. Nothing clears? "No qualifying
  plays" is a correct output, not a failure.

De-vig offers both methods: multiplicative for balanced two-ways, POWER
for skewed markets (alt lines, longshots) — multiplicative mis-prices
longshots by the 2-3 points that flip a bet.
"""

from __future__ import annotations

import math

from ..hoops import NBA, LeagueTuning

SD_CV = {"pts": 0.30, "reb": 0.40, "ast": 0.43, "pra": 0.24,
         "fg3m": 0.50, "stl": 0.90, "blk": 0.90}
DISCRETE = {"reb", "ast", "fg3m", "stl", "blk"}

# RE-TUNED 2026-07-29 (same audit as the NFL/MLB tier re-tune): the old
# pairing (w=0.28, gate 3.0pts over break-even) was mathematically closed —
# the largest clamped edge the model could EVER produce was
# 0.28 × 0.12 = 3.36pts vs fair, which is ~0.9pts over a −110 break-even
# against a 3.0pt requirement. No combination of line and price could
# yield a pick at standard juice; verified by grid search. w=0.45 keeps
# the market dominant (most of any disagreement is still assumed to be
# our error) and 2.0pts over break-even still demands the model beat the
# price by nearly a full vig — but the door now physically opens.
CLAMP_W_DEFAULT = 0.45
CLAMP_KILL_DIFF = 0.12
GATE_EDGE_PTS = 0.02
GATE_EDGE_PTS_HIGH_HOLD = 0.04
GATE_MIN_EV = 0.035
GATE_WORST_PRICE = -250
GATE_MAX_HOLD = 0.10
HIGH_HOLD = 0.08


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def _dec(odds: int) -> float:
    return 1.0 + (100.0 / abs(odds) if odds < 0 else odds / 100.0)


def break_even(odds: int) -> float:
    return round(1.0 / _dec(odds), 4)


def sd_for(stat: str, mean: float, tune: LeagueTuning = NBA) -> float:
    return max(0.1, tune.sd_cv.get(stat, 0.35) * mean)


def p_over_normal(proj: float, line: float, sd: float) -> float:
    return 1.0 - _phi((line - proj) / sd)


def _negbin_pmf(k: int, r: float, p: float) -> float:
    # P(X = k) for NB(r successes, prob p), mean r(1-p)/p.
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log(1.0 - p))


def p_over_negbin(mean: float, line: float, cv: float) -> float:
    """Exact P(X > line) under negative binomial with SD = cv × mean.
    Falls back to Poisson-like shape when the target variance ≤ mean."""
    var = (cv * mean) ** 2
    if var <= mean + 1e-9:
        var = mean * 1.0001
    r = mean * mean / (var - mean)
    p = r / (r + mean)
    k_line = int(math.floor(line))          # P(X ≥ k_line+1) for .5 lines
    cdf = 0.0
    for k in range(0, k_line + 1):
        cdf += _negbin_pmf(k, r, p)
    return max(0.0, min(1.0, 1.0 - cdf))


def p_over(stat: str, proj: float, line: float,
           tune: LeagueTuning = NBA) -> float:
    """P(stat crosses the line), exact for low-count discrete stats —
    normal approximation there is off by the 2-4 points that ARE the edge."""
    cv = tune.sd_cv.get(stat, 0.35)
    if stat in DISCRETE and line < 25:
        return round(p_over_negbin(proj, line, cv), 4)
    return round(p_over_normal(proj, line, sd_for(stat, proj, tune)), 4)


# --- market math ------------------------------------------------------------
def devig_multiplicative(odds_a: int, odds_b: int) -> tuple[float, float]:
    qa, qb = 1.0 / _dec(odds_a), 1.0 / _dec(odds_b)
    return qa / (qa + qb), qb / (qa + qb)


def devig_power(odds_a: int, odds_b: int) -> tuple[float, float]:
    """Power-method de-vig: solve q_a^k + q_b^k = 1. The right method for
    skewed markets — multiplicative shortchanges the longshot side."""
    qa, qb = 1.0 / _dec(odds_a), 1.0 / _dec(odds_b)
    lo, hi = 0.5, 10.0
    for _ in range(80):
        k = (lo + hi) / 2.0
        s = qa ** k + qb ** k
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2.0
    return qa ** k, qb ** k


def market_hold(odds_a: int, odds_b: int) -> float:
    return round(1.0 / _dec(odds_a) + 1.0 / _dec(odds_b) - 1.0, 4)


def devig(odds_a: int, odds_b: int) -> tuple[float, float]:
    """Method chosen by shape: balanced → multiplicative, skewed → power."""
    if abs(abs(odds_a) - abs(odds_b)) >= 60 or odds_a > 130 or odds_b > 130:
        return devig_power(odds_a, odds_b)
    return devig_multiplicative(odds_a, odds_b)


# --- the discipline ---------------------------------------------------------
def humility_clamp(p_model: float, p_market: float,
                   w: float = CLAMP_W_DEFAULT) -> tuple[float | None, str]:
    """(p_final, note) — or (None, why) when the disagreement kills it."""
    diff = abs(p_model - p_market)
    if diff > CLAMP_KILL_DIFF:
        return None, (f"model and market disagree by {diff:.0%} — that means "
                      f"an input is wrong, not a goldmine. No bet; re-audit.")
    return (round(w * p_model + (1.0 - w) * p_market, 4),
            f"clamped toward market (w={w:g})")


def required_edge(stat: str, hold: float, tune: LeagueTuning = NBA,
                  high_hold_market: bool = False) -> float:
    """The post-clamp edge this market has to clear.

    A league that declares market tiers uses them; one that doesn't keeps
    the original points-based bar. That split is deliberate — the WNBA spec
    raised its own minimums, and applying its numbers to the calibrated NBA
    board would be re-tuning a working model on another league's say-so.
    """
    tier = (tune.market_tier or {}).get(stat)
    if tier is not None and tune.tier_min_edge:
        return tune.tier_min_edge.get(tier, max(tune.tier_min_edge.values()))
    return (GATE_EDGE_PTS_HIGH_HOLD if (high_hold_market or hold > HIGH_HOLD)
            else GATE_EDGE_PTS)


def approval_gate(p_final: float, odds: int, hold: float,
                  minutes_grade: str, high_hold_market: bool = False,
                  stat: str = "", tune: LeagueTuning = NBA) -> list[str]:
    """Every reason this bet fails the gate; empty list = approved."""
    fails: list[str] = []
    be = break_even(odds)
    need = required_edge(stat, hold, tune, high_hold_market)
    if p_final - be < need:
        # .1%, not .0% — the tier bars are 3.0/4.5/6.5, and rounding to
        # whole percent printed the 6.5% bar as "6%".
        fails.append(f"edge {p_final - be:+.1%} < required {need:.1%} over "
                     f"break-even {be:.1%}")
    ev = p_final * (_dec(odds) - 1.0) - (1.0 - p_final)
    if ev < GATE_MIN_EV:
        fails.append(f"EV {ev:+.1%} < +3.5%")
    if odds < GATE_WORST_PRICE:
        fails.append(f"price {odds} worse than −250")
    if hold > GATE_MAX_HOLD:
        fails.append(f"hold {hold:.1%} > 10%")
    if minutes_grade == "D":
        fails.append("minutes grade D — no bet, full stop")
    return fails


def ev_per_unit(p: float, odds: int) -> float:
    return round(p * (_dec(odds) - 1.0) - (1.0 - p), 4)
