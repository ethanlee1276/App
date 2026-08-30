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

THE SAME PAIR SERVES COLLEGE FOOTBALL, and that was measured rather than
assumed. The CFB handbook gives its own form -- scorers = TDs x D + 0.20
with D = 0.88, rising to 0.92 when the spread is 21 or more, on the
argument that "the ratio rises in blowouts because scoring spreads across
a deeper set of players once the benches empty". Over 2,710 CFB games
with both teams logged, fitted on 2022-24 and scored on 2025:

    form                          held-out MAE   paired t vs handbook
    x0.666 + 0.920  (this one)        0.650            -5.62
    CFB's own fit  x0.679 + 0.773     0.657            -5.14
    handbook D = 0.88/0.92 + 0.20     0.838

The handbook's form is decisively worse -- at 10-13 offensive TDs it says
9.57 distinct scorers against a realised 7.67. A CFB-specific fit is NOT
better than the shared pair (t = -1.46, indistinguishable), so college
football does not get its own constant: one fewer number to maintain, and
the reason is a measurement rather than a convenience.

Its blowout rule buys nothing either. Splitting the fit by spread moved
held-out error by 0.0008 scorers, and the raw ratio is flat across spread
buckets (0.806 / 0.809 / 0.805 under 21, then 0.814 / 0.799 / 0.784) --
with the widest spreads the LOWEST, which is the opposite of the claim.

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

IT WAS RUN, AND IT DID NOT SETTLE THE WAY THE ARGUMENT SAID. Scored on
3,890 harvested NFL closes (2,635 fitted, 1,255 held out), both methods
beat the raw price decisively -- log loss 0.41583 raw against 0.41133
proportional and 0.41118 power -- so the de-vig itself is doing real
work. Between the two there is nothing: power by 0.00016, inside this
module's own "not a result" band.

The band table is the part that matters, and it undercuts the reason
POWER is the default. What the market actually charged, raw price
against realised rate:

    raw band     n     charged    prop z   power z
    0.00-0.10   968     13.8%      +0.00     -1.28
    0.10-0.18   898     34.8%      +3.07     +1.90
    0.18-0.28   838     14.6%      +0.15     -0.37
    0.28-0.45   840      8.8%      -1.06     -0.68
    0.45-1.01   346     15.0%      +0.22     +1.60

Four bands cluster near 14% and one sits at 35%. That is FLAT PLUS A
SPIKE, not the smooth monotone curve a power exponent draws -- so the
favourite-longshot story used to justify power is not what this data
shows. Proportional matches four bands almost exactly and misses the
fifth by 3.1 sigma; power is mediocre in all five. Neither is rejected
(chi-square 10.60 and 8.45 against a 5% critical 11.07).

POWER STAYS THE DEFAULT, on a narrower reason than before. Flipping on a
0.00016 margin would be exactly the kind of move this codebase keeps
having to undo. The tie-breaker is direction: the two disagree most at
the ends, and power gives a LOWER fair price out where the board actually
bets (+300 and longer), so being wrong with it costs picks rather than
inventing edge. That is a safety argument, not a fit argument, and it
should be replaced by a measurement as more closes land.

THE SPIKE WAS NOT A FINDING AT ALL, and that took three passes to
establish. In the 0.10-0.18 raw band -- roughly +456 to +900, which is
where the touchdown board lives -- the market appeared to charge 35%
while every other band charged 14%. It survived an error bar (z = +2.9,
`devigfit.BAND_Z`) and it survived dropping every bet that was VOID
because the player never took a snap (35.0% to 33.9%; that filter
belonged to the +900-and-longer band, which fell from 13.7% to 0.8%).

It did not survive being priced at the number a bettor takes. The quote
behind every one of those rows was whichever book SQLite happened to
hand back last, and `db.closing_odds_by_date` keeps exactly one per
player-date while a single harvest writes six. Re-measured on the
LONGEST price on the screen -- which is what `odds.best_over_line`
publishes -- the band charges 8.6% +/-8.6%, z = +0.4, and no band on the
board charges more than the rest:

    raw band     arbitrary book    shopped
    0.00-0.10          0.8%         -9.4%
    0.10-0.18         33.9%          8.6%
    0.18-0.28         16.0%          7.9%
    0.28-0.45          9.2%          3.0%
    0.45-1.01         14.6%          9.0%

So the favourite-longshot spike is a property of reading one book, not
of the market. What survives is the shape argument for POWER above and
the fact that both methods beat the raw price.

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
#:
#: THOSE 1,216 GAMES ARE EXACTLY THE ONES WHERE BOTH TEAMS SCORED, out of
#: 1,424 with both teams logged, and that is worth knowing because it
#: looks like a filtered fit and is not one. Refitting on all 1,424 gives
#: 0.7114/0.6330 and removes a +0.0725 bias -- but it is WORSE once
#: `expected_distinct_scorers` caps its answer at the touchdowns
#: themselves (RMSE 0.6909 against 0.6860), because the bound is what
#: those 208 extra games were really teaching. Fit on the region where
#: the cap does not bind and the answer returns 0.6646/0.9131. These
#: constants are right; the function was missing an identity.
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

    CAPPED AT THE TOUCHDOWNS THEMSELVES, which is not a tuning choice but
    an identity: a game with two offensive touchdowns cannot have three
    men score one. The affine form has no such knowledge and broke the
    bound in 193 of 1,424 replayed NFL games — 13.6% — every one of them
    a low-scoring game where the intercept outruns the slope. Below 2.75
    total offensive touchdowns the line predicts more scorers than there
    are scores.

    Adding the cap takes the bias from +0.0725 scorers per game to
    +0.0201 and the RMSE from 0.7075 to 0.6860, and moves no constant.

    THE CONSTANTS WERE NOT THE PROBLEM, and that took two wrong turns to
    establish. Refitting the line on all 1,424 games gives 0.7114/0.6330
    and looks like a correction to a fit made on a filtered sample --
    the 1,216 games this was fitted over are exactly the ones where BOTH
    teams scored, which reproduces 0.666/0.920 to three decimals. But
    that refit is WORSE once the cap is in place (RMSE 0.6909 against
    0.6860), because the bound is what the extra games were really
    teaching. Fit on the region where the cap does not bind and the
    answer comes back 0.6646/0.9131 -- the shipped numbers.

    So this changes nothing about live NFL pricing either: the cap binds
    below 2.75 total offensive touchdowns, which is a game total under
    26 points, and no NFL game is priced there. It is a correctness fix
    for anyone grading this function against outcomes, which is how the
    violation was found.
    """
    total = max(0.0, float(team_a_tds)) + max(0.0, float(team_b_tds))
    return min(SCORERS_SLOPE * total + SCORERS_BASE, total)


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


class FairQuote:
    """A player's fair probability, already measured. Prices like a Devig.

    THE SUM HAS TO COME FROM ONE BOOK. Both boards pick each player's
    BEST price across books, and summing those is summing a line no book
    offers: best = highest payout = lowest implied probability, so the
    sum comes in low, the multiplier comes in low, and the hold is
    under-stated -- which makes the book look fairer than it is and
    inflates every edge. That is the exact error this module exists to
    remove, so measuring it that way would have been self-defeating.

    So the margin is measured off ONE book's complete board, that book's
    own price for the player is what gets de-vigged, and the result is
    compared against the best price anyone offers. That is also what
    makes an outlier price detectable: fair comes from the consensus,
    edge comes from one book being out of line with it.
    """

    __slots__ = ("prob", "overround", "kind", "book", "listed", "books")

    def __init__(self, prob: float, overround: float, kind: str,
                 book: str = "", listed: int = 0, books: int = 1):
        self.prob = float(prob)
        self.overround = float(overround)
        self.kind = kind
        self.book = book
        #: How many players the reference book listed. THE DIRECT
        #: EVIDENCE for the failure this whole path is exposed to: if the
        #: feed returns a fraction of a game's scorers, the sum comes in
        #: low and so does the measured hold, silently, in the direction
        #: that inflates edge. Inferring truncation from a suspiciously
        #: small vig is a guess; the board size is the fact.
        self.listed = int(listed)
        #: How many books' de-vigged prices the median was taken over.
        #: One is not a consensus and the card should be able to say so.
        self.books = int(books)

    def fair(self, raw_implied: float) -> float:
        """The measured fair price. ``raw_implied`` is deliberately
        ignored — it is the best-of-books number, and de-vigging that
        again would double-count the shopping."""
        return self.prob

    def __repr__(self) -> str:                                # pragma: no cover
        return (f"FairQuote({self.prob:.4f}, {self.overround:+.1%}, "
                f"{self.kind}, {self.book!r}, listed={self.listed}, "
                f"books={self.books})")


def reference_book(by_book: dict) -> str:
    """The book whose board sets the game's MARGIN.

    Most players listed, because a truncated board under-states the sum
    and therefore the hold. Ties break to the largest sum — the greediest
    of the equally complete — since assuming a book is fairer than it is
    invents edge.

    This chooses whose OVERROUND to trust, not whose PRICE to trust. The
    two were the same thing until 2026-08-30 and that was the bug; see
    `board_fair`.
    """
    if not by_book:
        return ""
    return max(by_book,
               key=lambda b: (len(by_book[b]), sum(by_book[b].values())))


def board_fair(by_book: dict, expected_scorers: float,
               method: str = None) -> dict:
    """``{player: FairQuote}`` — the MEDIAN de-vigged price across books.

    ONE BOOK IS NOT A CONSENSUS, and the first cut of this treated it as
    one: it de-vigged the reference book's board and published that as
    the market's fair price. The reference is chosen by board size, and
    on 2026-08-29 that was Hard Rock — which turned out to be the
    furthest-from-consensus book on 10 of 16 college scorers where books
    disagreed by 8 points or more, systematically pricing LONGER than
    everyone else:

        player              consensus   Hard Rock
        jackson arnold        0.600       0.400
        manny covey           0.294       0.091
        quintrevion wisner    0.627       0.455

    Jackson Arnold was DraftKings -170, Caesars -150, Hard Rock +150.
    Three majors agreed he was about 60%; the reference said 40%; so the
    model was asked to beat 0.36 and the +150 sitting in front of it —
    an enormous overlay against the other three — became invisible. The
    design exists to price a consensus and attack the book out of line
    with it, and taking the fair FROM that book erases exactly the thing
    it was built to find.

    So every book that quotes a player gets de-vigged and the MEDIAN is
    published. A median rather than a mean because the failure mode is
    one stale book, and that is precisely what a median ignores and a
    mean absorbs.

    A book with its own measurable board is de-vigged by its own
    overround. One too thin to measure still contributes its price,
    de-vigged by the median exponent of the books that could be measured
    — a shape borrowed from its neighbours beats dropping a real quote.
    """
    method = method or DEFAULT_METHOD
    ref = reference_book(by_book)
    if not ref:
        return {}
    per_book: dict = {}
    for book, prices in by_book.items():
        dv = game_devig(list(prices.values()), expected_scorers, method)
        if dv:
            per_book[book] = dv
    if not per_book:
        return {}
    # The shape a book without its own measurable board borrows.
    shared = sorted(per_book.values(), key=lambda d: d.param)[len(per_book) // 2]
    listed = len(by_book.get(ref) or {})

    fairs: dict = {}
    for book, prices in by_book.items():
        dv = per_book.get(book) or shared
        for player, raw in prices.items():
            if raw and 0.0 < raw < 1.0:
                fairs.setdefault(player, []).append(dv.fair(raw))
    out: dict = {}
    for player, got in fairs.items():
        got.sort()
        mid = (got[len(got) // 2] if len(got) % 2
               else (got[len(got) // 2 - 1] + got[len(got) // 2]) / 2.0)
        out[player] = FairQuote(mid, shared.overround, shared.kind, ref,
                                listed=listed, books=len(got))
    return out


def as_devig(value) -> "Devig | None":
    """Coerce a bare multiplier to a proportional de-vig; pass one through.

    Callers that only ever knew about a single hold number keep working,
    and nothing has to guess what a loose float meant.
    """
    if value is None or isinstance(value, (Devig, FairQuote)):
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


def game_devig(implied: list, expected_scorers: float,
               method: str = DEFAULT_METHOD) -> "Devig | None":
    """One game's de-vig from its own board, or None if unmeasurable.

    Both sports come through here. `engine/cfb/tds` prices a game at a
    time and NFL's pipeline prices a slate, but the arithmetic is the
    same and a second copy of it would be a second place to get the
    allocation wrong.
    """
    mult = hold_multiplier(implied, expected_scorers)
    if not mult:
        return None                      # thin, or no measurable margin
    if method != POWER:
        return Devig.proportional(mult)
    k = power_exponent(implied, expected_scorers)
    # No exponent means the solver could not place this board, and the
    # overround it would have shared out is still real — fall back to
    # spreading it evenly rather than to not de-vigging at all, which is
    # the one option known to be wrong.
    return Devig.power(k, mult - 1.0) if k else Devig.proportional(mult)


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
        dv = game_devig(probs, scorers, method)
        if dv:
            out[key] = dv
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
           "hold_multiplier", "fair_probability", "american", "game_prices",
           "game_devig", "FairQuote", "board_fair", "reference_book"]
