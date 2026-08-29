"""The price you actually have to beat in a one-way market.

`engine/tdbook` said the anytime-touchdown market "cannot be de-vigged
without the other side, which does not exist here", and printed the raw
implied probability as context rather than as a number to bet against.
That was wrong, and the fix does not need a second side.

THE MARKET-SUM METHOD. Every listed player's raw implied probability in
one game, summed, estimates how many DISTINCT scorers the book is
pricing. Compare that to how many the game line implies and the ratio is
the hold:

    hold multiplier = sum of raw implied / expected distinct scorers
    fair probability = raw implied / hold multiplier

A player at +200 is 33.3% raw. In a game whose prices sum to 1.30x the
scorers the line supports, his fair price is 25.6% — +290, not +200.
That is the number a projection has to beat, and it is far longer than
the board shows. Anytime-touchdown markets run 22-35% overround against
4.5% on a side, so the gap is not a rounding detail; it is most of the
question.

BOTH CONSTANTS ARE MEASURED HERE, and one of them had to be. The
handbook this follows gives distinct scorers as offensive touchdowns x
0.90 + 0.12, which assumes a flat one-in-ten repeat rate. Repeats grow
with scoring. Fitted over 1,216 games with both teams logged:

    off TDs   actual   x0.666+0.920   x0.900+0.120
    5-6         4.36       4.25           4.62
    7-9         5.74       5.81           6.73
    9-15        7.03       7.25           8.67

At the top the handbook's constants over-count distinct scorers by 23%,
which under-states the hold, which makes the book look fairer than it is
and quietly shrinks every edge. The measured pair is used instead.

HOW THE HOLD IS SHARED OUT IS A SECOND QUESTION, and a bigger one than
it looks. Knowing a game's board carries 19% overround does not say what
each player's share of it is. Dividing every price by the same multiplier
assumes the book spreads its margin evenly, which books do not do: the
favourite-longshot bias means the darts carry more vig than the short
prices. Proportional therefore over-corrects the bell-cow and
under-corrects the dart -- the worst pairing available to us, since it
deletes the reliable picks and flatters the lottery tickets.

The POWER method fixes the allocation: fair = raw ** k, with k solved so
the fair prices sum to the expected scorers. It shrinks small
probabilities relatively more, which is the bias's actual shape. On a
22-player board carrying 18.8% overround (k = 1.138):

    price     raw   proportional        power
    -125    0.556   0.467 (+114)   0.512 (-105)
    +250    0.286   0.240 (+316)   0.240 (+316)
    +900    0.100   0.084 (+1088)  0.073 (+1274)

They cross near +250 and disagree by a tenth of the price at both ends.
The difference is not academic: under proportional, MAX_CREDIBLE_EDGE and
the EV floor together make NO price shorter than +364 gradeable at a 30%
hold, which silently deletes the short half of the touchdown board.

WHICH ONE IS RIGHT IS AN EMPIRICAL QUESTION AND IT IS ANSWERABLE -- the
droplet has 33,926 harvested anytime-TD closing prices, and scoring both
methods against realised outcomes decides it. Until that is run, POWER is
the default: it is what the handbook prescribes above an 8% hold, it is
the standard treatment of a bias that is well established, and the
uniform-vig assumption behind proportional is known to be false rather
than merely unverified.

(The handbook's own worked example of this is wrong in both directions --
it reports multiplicative at 55.9% for a -140/+110 pair, which is really
55.06%, and says multiplicative "overstates the favorite" when power
gives that favourite MORE, 55.52%. Its recommendation stands; its
arithmetic does not, and taking the arithmetic at face value would have
inflated exactly the longshots this board is made of.)

Standard library only.
"""

from __future__ import annotations

import math

#: Distinct scorers from a game's total offensive touchdowns, fitted over
#: 1,216 games. See the module note for why this is not the handbook's
#: 0.90 / 0.12.
SCORERS_SLOPE = 0.666
SCORERS_BASE = 0.920

#: Expected offensive touchdowns from a team's implied total. Fitted over
#: 2,848 team-games as (total - 5.36) / 7.18, which confirms the
#: handbook's 7.2 divisor and corrects its 4.5 offset.
#:
#: NOT USED BY DEFAULT. `touchdowns.expected_team_tds` scales
#: proportionally instead, and measured against the same 2,848 games it
#: fits the tails BETTER — 3.61 against a realised 3.39 where this gives
#: 4.10. Kept because the devig needs a team-total-to-touchdowns step and
#: a caller may want the affine form, but the proportional one is the
#: default for a reason that was checked.
TD_OFFSET, TD_DIVISOR = 5.36, 7.18

#: Below this the sum is not a market. A game with three prices listed
#: says nothing about the book's hold.
MIN_PRICED = 6


def expected_tds_affine(team_total: float) -> float:
    """The handbook's shape, with the offset this data supports."""
    return max(0.0, (float(team_total) - TD_OFFSET) / TD_DIVISOR)


def expected_distinct_scorers(team_a_tds: float, team_b_tds: float) -> float:
    """How many different players are expected to score in this game.

    The 0.92 base absorbs defensive and special-teams touchdowns, which
    take scoring equity out of the offensive market a book is pricing.
    """
    total = max(0.0, float(team_a_tds)) + max(0.0, float(team_b_tds))
    return SCORERS_SLOPE * total + SCORERS_BASE


def hold_multiplier(implied: list, expected_scorers: float,
                    min_priced: int = MIN_PRICED) -> float | None:
    """``sum(implied) / expected_scorers``, or None when unmeasurable.

    Returns None rather than 1.0 for a thin board, because "no hold" and
    "no idea" are different claims and only one of them is safe to price
    against.
    """
    got = [p for p in implied if p and p > 0]
    if len(got) < min_priced or expected_scorers <= 0:
        return None
    mult = sum(got) / expected_scorers
    # A multiplier below 1 means the listed prices sum to fewer scorers
    # than the line supports, which is a book with no hold — not
    # something that happens. Treat it as unmeasurable rather than
    # inflating everybody's fair price.
    return mult if mult > 1.0 else None


def fair_probability(raw_implied: float, mult: float | None) -> float:
    """The devigged price. Unchanged when the hold could not be measured."""
    if not mult or mult <= 0:
        return float(raw_implied)
    return float(raw_implied) / mult


#: Bounds on the power exponent. k = 1 is no correction at all; past
#: PROPORTIONAL an exponent this large means the board and the game line
#: disagree so badly that something upstream is wrong, and a solver that
#: silently returns the boundary would price the whole game off it.
K_MIN, K_MAX = 1.0, 8.0


def power_exponent(implied: list, expected_scorers: float,
                   min_priced: int = MIN_PRICED) -> float | None:
    """``k`` such that ``sum(p ** k) == expected_scorers``, or None.

    Monotone in k because every p is below 1, so a bisection is exact
    enough and cannot get stuck. Returns None on the same terms as
    `hold_multiplier` -- a thin board, or prices that already sum to
    fewer scorers than the line supports -- and also at the boundary,
    where the answer is "the inputs disagree", not a number.
    """
    got = [p for p in implied if p and 0.0 < p < 1.0]
    if len(got) < min_priced or expected_scorers <= 0:
        return None
    if sum(got) <= expected_scorers:
        return None
    lo, hi = K_MIN, K_MAX
    if sum(p ** hi for p in got) > expected_scorers:
        return None                      # off the top of the grid
    for _ in range(80):
        k = (lo + hi) / 2.0
        if sum(p ** k for p in got) > expected_scorers:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2.0
    return k if K_MIN < k < K_MAX else None


PROPORTIONAL, POWER = "proportional", "power"


class Devig:
    """One game's de-vig, as something that can price a number.

    A bare multiplier cannot express the power method, and passing two
    optional floats around invites exactly one caller to apply the wrong
    one. This carries the method with the parameter so a price and its
    correction cannot be separated.
    """

    __slots__ = ("kind", "param", "overround")

    def __init__(self, kind: str, param: float, overround: float):
        self.kind = kind
        self.param = float(param)
        self.overround = float(overround)

    @classmethod
    def proportional(cls, mult: float) -> "Devig":
        return cls(PROPORTIONAL, mult, mult - 1.0)

    @classmethod
    def power(cls, k: float, overround: float) -> "Devig":
        return cls(POWER, k, overround)

    def fair(self, raw_implied: float) -> float:
        """The price this player really has to beat."""
        raw = float(raw_implied)
        if not 0.0 < raw < 1.0:
            return raw
        if self.kind == POWER:
            return raw ** self.param
        return raw / self.param if self.param > 0 else raw

    def __repr__(self) -> str:                                # pragma: no cover
        return f"Devig({self.kind}, {self.param:.4f}, {self.overround:+.1%})"


def as_devig(value) -> "Devig | None":
    """Coerce a bare multiplier to a proportional de-vig; pass one through.

    Callers that only ever knew about a single hold number keep working,
    and nothing has to guess what a loose float meant.
    """
    if value is None or isinstance(value, Devig):
        return value
    try:
        mult = float(value)
    except (TypeError, ValueError):
        return None
    return Devig.proportional(mult) if mult > 0 else None


def american(prob: float) -> int | None:
    """Fair American odds for a probability — what the price should be."""
    if not 0.0 < prob < 1.0:
        return None
    dec = 1.0 / prob
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 \
        else int(round(-100.0 / (dec - 1.0)))


def game_prices(implied: list, expected_scorers: float) -> dict:
    """Everything about one game's market, for a report or a card."""
    mult = hold_multiplier(implied, expected_scorers)
    got = [p for p in implied if p and p > 0]
    return {
        "listed": len(got),
        "sum_implied": sum(got) if got else 0.0,
        "expected_scorers": expected_scorers,
        "hold_multiplier": mult,
        "overround": (mult - 1.0) if mult else None,
    }


#: How a measured overround is shared out across a game's prices. See the
#: module note: proportional assumes the book spreads its margin evenly,
#: which it does not, and the consequence is not small.
DEFAULT_METHOD = POWER


def board_devig(candidates, game_of, implied_of, scorers_of,
                method: str = DEFAULT_METHOD) -> dict:
    """``{game key: Devig}`` from the board being priced.

    NOTHING HISTORICAL IS NEEDED. Every input exists at build time: the
    board already holds every quoted scorer in a game, and the schedule
    already holds that game's total and spread. So the hold can be
    measured off the very prices being priced, rather than assumed at a
    constant and caveated.

    ``game_of(c)`` keys a candidate to its game, ``implied_of(c)`` gives
    its raw implied probability, and ``scorers_of(key)`` the expected
    distinct scorers for that game. A game whose market is too thin to
    measure is absent from the result, and the caller falls back to the
    standing assumption rather than being handed an invented number.
    """
    by_game: dict = {}
    for c in candidates:
        key = game_of(c)
        if key is None:
            continue
        prob = implied_of(c)
        if prob and prob > 0:
            by_game.setdefault(key, []).append(prob)
    out: dict = {}
    for key, probs in by_game.items():
        scorers = scorers_of(key)
        if not scorers:
            continue
        mult = hold_multiplier(probs, scorers)
        if not mult:
            continue                     # thin, or no measurable margin
        if method == POWER:
            k = power_exponent(probs, scorers)
            # No exponent means the solver could not place this board, and
            # the overround it would have shared out is still real — fall
            # back to spreading it evenly rather than to not de-vigging at
            # all, which is the one option known to be wrong.
            out[key] = Devig.power(k, mult - 1.0) if k \
                else Devig.proportional(mult)
        else:
            out[key] = Devig.proportional(mult)
    return out


def board_hold(candidates, game_of, implied_of, scorers_of) -> dict:
    """``{game key: hold multiplier}`` from the board being priced.

    NOTHING HISTORICAL IS NEEDED. Every input exists at build time: the
    board already holds every quoted scorer in a game, and the schedule
    already holds that game's total and spread. So the hold can be
    measured off the very prices being priced, rather than assumed at a
    constant and caveated.

    ``game_of(c)`` keys a candidate to its game, ``implied_of(c)`` gives
    its raw implied probability, and ``scorers_of(key)`` the expected
    distinct scorers for that game. A game whose market is too thin to
    measure is absent from the result, and the caller falls back.
    """
    by_game: dict = {}
    for c in candidates:
        key = game_of(c)
        if key is None:
            continue
        prob = implied_of(c)
        if prob and prob > 0:
            by_game.setdefault(key, []).append(prob)
    out: dict = {}
    for key, probs in by_game.items():
        scorers = scorers_of(key)
        if not scorers:
            continue
        mult = hold_multiplier(probs, scorers)
        if mult:
            out[key] = mult
    return out


__all__ = ["SCORERS_SLOPE", "SCORERS_BASE", "TD_OFFSET", "TD_DIVISOR",
           "board_hold", "board_devig", "Devig", "as_devig", "power_exponent",
           "PROPORTIONAL", "POWER", "DEFAULT_METHOD", "K_MIN", "K_MAX",
           "MIN_PRICED", "expected_tds_affine", "expected_distinct_scorers",
           "hold_multiplier", "fair_probability", "american", "game_prices"]
