"""The books' chance at ANY line, from the main lines they hang.

WHY. The NFL one board shows the books' price where our chance runs above
it (likelyboard.trust_price), but only where three books or more price
both sides of the pick's own line. On the box's first full board after it
shipped, 133 of 230 player picks had no such field (Ethan's paste,
2026-10-17) — mostly alternate rungs (over 2.5 catches when the main line
is 4.5), which books hang one-sided, and one-sided prices carry a vig
nobody can see. So those picks keep our chance, unjudged.

WHAT THIS DOES. Each book's MAIN line is two-sided, so it says where that
book puts the middle: de-vigged, "over 4.5 at 52%" pins one point of the
book's curve. Given a SHAPE for the market's distribution, one point fixes
the curve, and the curve gives the chance at any other line. Every book
quoting both sides gives its own centre; the field's centre is their
median (three books or more, the floor the site's consensus uses), and
the chance at the pick's line is read off the field's curve.

THE SHAPE, MEASURED (fieldcurvefit.py, 2022-2025 regular-season games of
regulars — six games or more in a season at a regular's level). Within a
player's season, a game's variance is a fixed multiple PHI of his mean, in
every market, at every level of mean:

    receptions      1.19   (1.19, 1.20, 1.19 by low, middle and high mean)
    rec_yds        21.5    (20.5, 20.5, 22.4)
    rush_yds       20.3    (20.1, 20.1, 20.5)
    pass_yds       19.7    (21.6, 19.0, 19.3)
    rush_rec_yds   21.2    (20.8, 22.1, 20.9)
    pass_rush_yds  19.2    (21.4, 19.2, 18.2)
    pass_att        1.77   (1.72, 1.83, 1.75)
    pass_cmp        1.39   (1.25, 1.44, 1.43)
    tackles_ast     1.27   (1.35, 1.29, 1.22)
    kick_pts        1.82   (1.85, 1.93, 1.70)
    rush_att        2.31   (3.02, 2.52, 1.94 — the one that drifts)
    pass_td, pass_int, fg_made: at or under 1 — read as Poisson (a little
                                 wide for passing touchdowns, 0.80)

That is a compound process — a game is many plays, each adding a few
yards (about 20 yards² per yard of mean, the same in every yardage
market). So: a count is a negative binomial with mean m and variance
PHI·m (Poisson where PHI is 1 or under); yards are a gamma with mean m and
variance PHI·m (shape m/PHI, scale PHI).

WHAT IT IS NOT. Within-season spread includes the game-to-game moves in
his true mean that the books partly see coming, so these curves are, if
anything, a little wide. Whether the field's curve is close enough to be
worth showing is not argued here: research/thinmarket_box.py (EXP-R06)
tests it week by week on settled board picks, with pricetrust's bar, and
nothing on the board reads it unless that passes and Ethan says yes.

Standard library only.
"""

from __future__ import annotations

import math

#: Variance over mean, per market (module docstring; fieldcurvefit.py).
PHI = {
    "receptions": 1.194, "rec_yds": 21.496, "rush_yds": 20.314, "pass_yds": 19.694,
    "rush_rec_yds": 21.249, "pass_rush_yds": 19.218, "pass_att": 1.772, "pass_cmp": 1.392,
    "tackles_ast": 1.270, "kick_pts": 1.822, "rush_att": 2.311,
    "pass_td": 0.795, "pass_int": 1.006, "fg_made": 0.880,
}
#: Markets read as continuous (a gamma); every other one in PHI is a count.
YARDS = frozenset({"rec_yds", "rush_yds", "pass_yds", "rush_rec_yds", "pass_rush_yds", "kick_pts"})
#: Books needed for a field, as engine.odds.consensus_fair asks.
MIN_BOOKS = 3
#: A book whose fair over sits outside this is too lopsided to pin a centre.
FAIR_BOUNDS = (0.02, 0.98)


# ---- the distributions -------------------------------------------------------------------

def _gamma_p(a: float, x: float) -> float:
    """The regularized lower incomplete gamma P(a, x)."""
    if x <= 0.0:
        return 0.0
    lead = math.exp(-x + a * math.log(x) - math.lgamma(a))
    if x < a + 1.0:
        term = total = 1.0 / a
        n = 1
        while n < 1000:
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-13:
                break
            n += 1
        return min(1.0, total * lead)
    tiny = 1e-300
    b = x + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        step = d * c
        h *= step
        if abs(step - 1.0) < 1e-13:
            break
    return max(0.0, 1.0 - lead * h)


def _count_pmf(m: float, phi: float, top: int) -> list[float]:
    """P(Y = 0..top) for a count with mean m and variance phi·m."""
    m = max(m, 1e-9)
    if phi <= 1.0:
        out = [math.exp(-m)]
        for k in range(1, top + 1):
            out.append(out[-1] * m / k)
        return out
    r = m / (phi - 1.0)
    p = r / (r + m)
    out = [math.exp(r * math.log(p))]
    for k in range(1, top + 1):
        out.append(out[-1] * (k - 1 + r) / k * (1.0 - p))
    return out


def over_chance(market: str, m: float, line: float) -> float | None:
    """P(over ``line`` | the market's mean m), a push left out (a count on a
    whole-number line can land on it). None for a market with no shape."""
    phi = PHI.get(market)
    if phi is None or m is None or m <= 0:
        return None
    if market in YARDS:
        return 1.0 - _gamma_p(m / phi, max(0.0, line) / phi)
    if line < 0:
        return 1.0
    whole = abs(line - round(line)) < 1e-9
    top = int(math.floor(line))
    pmf = _count_pmf(m, phi, top)
    below = sum(pmf[:top + (0 if whole else 1)])
    push = pmf[top] if whole else 0.0
    over = 1.0 - below - push
    return over / (1.0 - push) if push < 1.0 else None


def centre(market: str, line: float, fair_over: float) -> float | None:
    """The mean m at which ``over_chance(market, m, line)`` is ``fair_over``
    — one book's middle, from its de-vigged main line."""
    if market not in PHI or not (FAIR_BOUNDS[0] <= fair_over <= FAIR_BOUNDS[1]):
        return None
    lo, hi = 1e-3, max(4.0 * abs(line), 1.0) + (300.0 if market in YARDS else 30.0)
    if (over_chance(market, hi, line) or 0.0) < fair_over:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if (over_chance(market, mid, line) or 0.0) < fair_over:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def field_chance(market: str, quotes, line: float, side: str, min_books: int = MIN_BOOKS):
    """``(the field's chance for this side at ``line``, books, field mean)``
    or None. ``quotes``: each book's main line as (book, line, over odds,
    under odds), the latest per book; a book quoting one side only, a
    proxy, or an impossible pair is left out; each remaining book gives a
    centre and the median is the field's."""
    from .odds import devig_two_way, pair_is_sane
    if market not in PHI:
        return None
    try:
        line = float(line)
    except (TypeError, ValueError):
        return None
    seen, centres = set(), []
    for book, b_line, over, under in quotes or ():
        book = str(book or "").lower()
        if not book or book == "proxy" or book in seen or not pair_is_sane(over, under):
            continue
        try:
            fair_over = devig_two_way(int(over), int(under))[0]
            c = centre(market, float(b_line), fair_over)
        except (TypeError, ValueError):
            continue
        if c is None:
            continue
        seen.add(book)
        centres.append(c)
    if len(centres) < min_books:
        return None
    centres.sort()
    n = len(centres)
    m = centres[n // 2] if n % 2 else 0.5 * (centres[n // 2 - 1] + centres[n // 2])
    over = over_chance(market, m, line)
    if over is None:
        return None
    under = str(side or "").upper() in ("UNDER", "NO")
    return (1.0 - over if under else over), n, m
