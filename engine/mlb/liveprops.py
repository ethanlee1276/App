"""What a live player prop is actually worth right now.

Ethan, 2026-08-14: "Are we able to track the win probability of bets we
have made live too? Like player props and shit based of the current live
lines they would display durring the game."

THE BOOK IS THE WRONG SOURCE FOR THIS, ON TWO COUNTS.

Player props live only on the Odds API's EVENT endpoint, which bills per
game: one prop market across a fifteen-game slate is fifteen credits for
a single refresh, against a free plan of five hundred a month. And books
PULL their pre-game prop markets the moment a game goes live — that is
not a guess, it is the finding behind `livepicks`' three-tier lookup,
where every unmapped name on Ethan's Live Now screenshot was a pitcher
and every mapped one a hitter. We would be paying per game, repeatedly,
to be told the market no longer exists.

SO THIS COMPUTES IT INSTEAD, FROM THINGS THAT ARE FREE.

A prop is a race between what a player has already banked and what he has
left to bank it in. Both halves are already on disk every cycle:

    banked      `livestats.parse_live_stats` — the live boxscore
    remaining   the linescore's inning, half and outs

and the rates that turn opportunity into outcome are the same per-PA
table `gamesim.rates_from_means` builds from our own projection. Nothing
new is fetched and no credit is spent. It refreshes every sixty seconds
instead of every thirty minutes, and it still answers on a market no book
is quoting.

WHAT IS AN APPROXIMATION HERE, STATED PLAINLY, because a live number
reads as precise whether or not it deserves to:

  * Remaining plate appearances are an EXPECTATION, not a distribution.
    A team averages `PA_PER_OUT` batters per out remaining; where the
    order stands decides how many of those fall to one hitter. The
    variance of that count is not modelled, which makes the tails
    slightly too tight — a hitter with "1.2 PA left" sometimes gets two
    and sometimes none.
  * The rates are the ones built pre-game, against the STARTER. Facing a
    reliever in the eighth, they are the wrong table. `bullpen.py` has
    the material to adjust this and it is not wired in here yet.
  * A game can end early — a walk-off, or a home team that never bats in
    the ninth. Those are handled where they are knowable (below) and
    ignored where they are not.

None of the three is a reason to show nothing. All three are reasons the
number is labelled as ours, and as an estimate.

Standard library only. Pure functions; no I/O.
"""

from __future__ import annotations

import math

#: Plate appearances a team gets per out remaining. A team averages ~38 PA
#: over 27 outs in a nine-inning game, which is the ratio below. It is the
#: bridge from "outs left" to "cracks at it left", and it is a LEAGUE
#: constant on purpose: the alternative is estimating each lineup's own
#: turnover rate from a sample of one game in progress.
PA_PER_OUT = 38.0 / 27.0

#: Batters a starter is expected to face in total. Used only to cap a
#: still-in pitcher's remaining work: without it, a starter cruising in
#: the third is credited with every batter left in the game, which is a
#: promise no manager makes. Deliberately generous — the cap should bind
#: on the long outing, not shape the ordinary one.
STARTER_BF = 25.0

#: Markets this module can price, and how each one moves per plate
#: appearance. Anything not listed gets no live probability rather than a
#: guessed one.
HITTER_MARKETS = ("hits", "total_bases", "home_runs")
PITCHER_MARKETS = ("strikeouts",)


def outs_left(inning: int, half: str, outs: int, is_home: bool,
              home_score=None, away_score=None) -> float:
    """Outs one team still has to bat, from the live linescore.

    ``half`` is the feed's own word — "Top" or "Bottom".

    THE NINTH IS NOT SYMMETRIC and pretending it is overstates every home
    hitter's remaining chances in exactly the spot where the bet is
    closest to resolving. A home team leading after the top of the ninth
    never comes to the plate at all; its hitters' props are finished
    while the game is still officially live.

    Extra innings are counted one half at a time. Beyond the ninth
    nothing further is guaranteed — the game ends the moment the home
    team leads after a completed inning — so crediting a hitter with
    another turn through the order would be inventing baseball that may
    never be played.
    """
    inning = int(inning or 0)
    outs = max(0, min(3, int(outs or 0)))
    top = str(half or "").lower().startswith("t")
    if inning <= 0:
        return 0.0

    if inning > 9:
        # Only the half being played is safe to count. If this team is not
        # batting in it, they may never bat again.
        batting_now = top != is_home
        return float(3 - outs) if batting_now else 0.0

    full_innings_after = max(0, 9 - inning)
    if is_home:
        if inning >= 9 and top and home_score is not None and away_score is not None \
                and float(home_score) > float(away_score):
            return 0.0                     # no bottom of the ninth is coming
        this_half = (3 - outs) if not top else 3
    else:
        this_half = (3 - outs) if top else 0
    return float(this_half + 3 * full_innings_after)


def remaining_pa(spot: int, at_bat_spot: int, team_outs_left: float) -> float:
    """Expected plate appearances left for the hitter in ``spot``.

    The batting order is a queue: the hitter at ``spot`` comes up at team
    plate-appearance ``dist``, then ``dist + 9``, and so on, where
    ``dist`` counts how many hitters are ahead of him right now. The team
    has about ``PA_PER_OUT × outs_left`` plate appearances left, and this
    is how many of his turns fall inside that.

    WHY THE HALF, which is not a fudge and was put there by a failing
    test. Counting the turns exactly — ``floor((N-1-dist)/9) + 1`` — is
    right for a KNOWN number of team plate appearances and biased when
    the number is an average, which is all we have. Over a full game it
    handed the leadoff man 5.11 trips; real leadoff hitters average about
    4.65, and the gap is the whole top of the order being rounded up. A
    floor of a quantity that is itself uncertain averages half a step
    below its argument, so the continuous form is ``(N - dist)/9 + 0.5``.
    That reads 4.72 for the leadoff man and 3.83 for the nine-hole, which
    is what the league actually does.

    THE MAN AT THE PLATE IS BATTING, though, and the smooth form does not
    know that — in the ninth with one out it offered him 0.65 of a turn.
    ``dist == 0`` means he is standing in the box, so his floor is one.
    """
    n = float(team_outs_left) * PA_PER_OUT
    if n <= 0:
        return 0.0
    try:
        dist = (int(spot) - int(at_bat_spot)) % 9
    except (TypeError, ValueError):
        return 0.0
    if n <= dist:
        return 0.0
    est = max(0.0, (n - dist) / 9.0 + 0.5)
    return max(est, 1.0) if dist == 0 else est


def per_pa_outcomes(rates, market: str):
    """``[(added value, probability), …]`` for one plate appearance.

    Reads a `gamesim.BatterRates`. Walks add nothing to any of these
    markets, which is why they sit with outs in the zero bucket rather
    than being dropped — a walk still burns a plate appearance.
    """
    o, bb = float(rates.out), float(rates.bb)
    s, d, t, hr = (float(rates.single), float(rates.double),
                   float(rates.triple), float(rates.hr))
    if market == "hits":
        return [(0, o + bb), (1, s + d + t + hr)]
    if market == "home_runs":
        return [(0, o + bb + s + d + t), (1, hr)]
    if market == "total_bases":
        return [(0, o + bb), (1, s), (2, d), (3, t), (4, hr)]
    return []


def _p_at_least_n(outcomes, need: int, n: int) -> float:
    """P(sum of ``n`` independent draws ≥ ``need``) — exact.

    A convolution over a state space of at most ``need`` values, because
    everything at or above the target is one absorbing state. Exact beats
    Monte Carlo here: the counts are tiny, and a sampler would put noise
    on a number that refreshes every minute, so the display would flicker
    while nothing happened on the field.
    """
    if need <= 0:
        return 1.0
    if n <= 0:
        return 0.0
    # dist[k] = P(total so far == k), for k < need. `done` = P(≥ need).
    dist = [0.0] * need
    dist[0] = 1.0
    done = 0.0
    for _ in range(n):
        nxt = [0.0] * need
        for k, pk in enumerate(dist):
            if pk <= 0:
                continue
            for add, p in outcomes:
                if p <= 0:
                    continue
                tot = k + add
                if tot >= need:
                    done += pk * p
                else:
                    nxt[tot] += pk * p
        dist = nxt
    return min(1.0, max(0.0, done))


def p_at_least(outcomes, need: float, pa: float) -> float:
    """P(the player adds ``need`` more) over a FRACTIONAL ``pa``.

    ``pa`` is an expectation — 2.4 plate appearances means some nights
    two and some nights three. Blending the two integer answers by the
    fractional part is the honest reading of that; rounding would make
    the number jump a whole plate appearance at a time as the game moves,
    which on a chart looks like the market moved when only our rounding
    did.
    """
    need_i = int(math.ceil(need - 1e-9))
    if need_i <= 0:
        return 1.0
    if pa <= 0:
        return 0.0
    lo = int(math.floor(pa))
    frac = pa - lo
    p_lo = _p_at_least_n(outcomes, need_i, lo)
    if frac <= 1e-9:
        return p_lo
    p_hi = _p_at_least_n(outcomes, need_i, lo + 1)
    return p_lo * (1 - frac) + p_hi * frac


#: Floor and ceiling on the per-plate-appearance pen factor `pen_rebase`
#: produces. NOT a new number: `matchup._hitter_matchup` clamps its entire
#: matchup multiplier to [0.88, 1.15], so the engine has already said how
#: far a matchup may move a HITTER. Un-blending must not quietly exceed
#: the bound the blended version was held to.
#:
#: The hitter bound, specifically. `matchup` uses three different clamps —
#: 1.15 for hitters, 1.12 for strikeouts, 1.10 for outs — and this factor
#: only ever scales a hitter's table. Reaching for the wrong one was the
#: first version of this constant, caught by the test that reads the
#: clamp out of `_hitter_matchup` rather than trusting a comment.
PEN_PER_PA_CAP = (0.88, 1.15)


def pen_rebase(applied: float, facing_pen: bool, share: float = None) -> float:
    """Re-aim a pre-game pen adjustment at the plate appearances LEFT.

    `matchup._hitter_matchup` multiplies a hitter's WHOLE-GAME mean by the
    opposing pen's factor — a tired or badly-ranked pen is worth something
    extra late. Right shape for a number that has to cover a whole game
    before it starts; wrong shape once the game is running, because by
    then we know what the pre-game model could not: which pitcher the
    remaining plate appearances are against.

    Read the applied factor ``A`` as the blend it is::

        A = s·1 + (1 − s)·p

    ``s`` is the share of plate appearances against the STARTER, where the
    pen bonus does not apply at all, and ``p`` is the per-plate-appearance
    factor against the pen. Inverting gives ``p = 1 + (A − 1)/(1 − s)``.
    The rates carry ``A``, so they are re-based by ``1/A`` while the
    starter is in and by ``p/A`` once he is gone.

    THE STARTER-IN CASE IS THE COMMON ONE AND THE UNAMBIGUOUS ONE.
    Whatever the pre-game factor was meant to describe, it cannot describe
    a plate appearance against the starter, so dividing it out is right
    under every reading. The facing-pen case depends on reading ``A`` as a
    blend rather than a flat bump — a defensible reading, and the reason
    its result is capped to the bound `matchup` already holds itself to
    rather than being trusted to arbitrary size.

    ``facing_pen`` IS THREE-STATE, and the third state is why. ``None``
    means we could not tell who is pitching — no probable starter on the
    game, a feed that missed him — and it returns 1.0, leaving the
    pre-game blend exactly as it was. Collapsing "unknown" into "facing
    the starter" would divide the pen bonus out of every game whose
    pitcher feed came up empty, which is a real adjustment made on the
    strength of a missing field.
    """
    from .bullpen import RELIEF_SHARE
    share = RELIEF_SHARE if share is None else share
    applied = float(applied or 1.0)
    if applied == 1.0 or applied <= 0 or facing_pen is None:
        return 1.0
    if not facing_pen:
        return 1.0 / applied
    if not 0 < share < 1:
        return 1.0
    lo, hi = PEN_PER_PA_CAP
    per_pa = max(lo, min(hi, 1.0 + (applied - 1.0) / share))
    return per_pa / applied


def scale_rates(rates, factor: float):
    """A rate table with every REACHING outcome scaled by ``factor``.

    ``out`` absorbs the difference so the table still sums to one, which is
    why this cannot simply multiply every field — the same discipline
    `gamesim._scale_reaching` already encodes, and this defers to it for a
    real `BatterRates`. Walks scale with the rest: a tired pen issues more
    of those too, and holding them fixed would silently change what share
    of a hitter's plate appearances are walks every time the factor moved.
    """
    if factor == 1.0 or rates is None:
        return rates
    if isinstance(rates, _Binomial):
        return _Binomial(min(0.999, max(0.0, rates.rate * float(factor))),
                         rates.market)
    from .gamesim import _scale_reaching
    return _scale_reaching(rates, float(factor))


def rates_for(market: str, means: dict, spot: int = 0):
    """A per-PA outcome table for one live prop, or None.

    ``means`` is ``{market: projected per-game mean}`` for this player,
    taken from tonight's own board — the same projections that priced the
    bet, so the live number and the pre-game number come from one model
    rather than two that can disagree.

    NO LEAGUE SHAPE CONSTANT IS USED, and that is a deliberate refusal.

      * ``hits`` and ``home_runs`` are one-per-plate-appearance events, so
        a single mean determines the whole table exactly. Nothing is
        assumed.
      * ``total_bases`` is not: a mean of 1.6 could be four singles or a
        home run, and those are very different bets late in a game. The
        split needs the hits and home-run means alongside it, which the
        board carries whenever it priced those markets too.

    When total bases is on its own, this returns None and the caller
    shows no live probability. Splitting it on a guessed extra-base share
    would be inventing the one number the market is actually about.
    """
    from .gamesim import rates_from_means, expected_pa

    pa = expected_pa(int(spot or 0))
    if market in ("hits", "home_runs"):
        mean = means.get(market)
        if mean is None:
            return None
        r = max(0.0, min(1.0, float(mean) / pa))
        # A one-shot event per plate appearance: the table only has to be
        # right about this market, so everything else sits in `out`.
        return _Binomial(r, market)
    if market == "total_bases":
        h, tb, hr = (means.get("hits"), means.get("total_bases"),
                     means.get("home_runs"))
        if h is None or tb is None or hr is None:
            return None
        return rates_from_means(float(h), float(tb), float(hr), pa)
    return None


class _Binomial:
    """A `BatterRates`-shaped table for a single yes/no market.

    Duck-typed rather than a real `BatterRates` because the other five
    fields would have to be invented to fill it, and every one of them
    would be a number nobody measured sitting in a dataclass that
    everything else in the engine treats as real.
    """

    def __init__(self, rate: float, market: str):
        self.rate, self.market = float(rate), market
        self.out = 1.0 - self.rate
        self.bb = 0.0
        self.single = self.rate if market == "hits" else 0.0
        self.double = self.triple = 0.0
        self.hr = self.rate if market == "home_runs" else 0.0


def hitter_probability(rates, market: str, line: float, side: str,
                       banked: float, pa_left: float) -> float | None:
    """Live probability that a hitter prop CASHES, from where it stands.

    ``side`` is OVER or UNDER and the answer is always the probability
    the BET wins, not the probability the over hits — a live number that
    silently reports the over while the ticket says under is worse than
    no number at all.
    """
    outcomes = per_pa_outcomes(rates, market)
    if not outcomes:
        return None
    banked = float(banked or 0.0)
    line = float(line)
    over = str(side or "OVER").upper() != "UNDER"
    # Lines are half-numbers, so "over 1.5" needs 2 and there is no push.
    need = math.floor(line) + 1 - banked
    p_over = p_at_least(outcomes, need, max(0.0, float(pa_left)))
    return p_over if over else 1.0 - p_over


def pitcher_probability(rates_k_per_bf: float, line: float, side: str,
                        banked: float, bf_left: float) -> float | None:
    """Live probability for a strikeout prop.

    Strikeouts per batter faced is a rate, and the count over ``bf_left``
    batters is Poisson-ish; the binomial is the better fit and is what
    this uses, since a batter is struck out at most once.

    ``bf_left`` of zero is the important case and it is not an edge case:
    once the starter is out of the game the prop cannot move, so the
    answer is a certainty, not an estimate.
    """
    try:
        r = float(rates_k_per_bf)
    except (TypeError, ValueError):
        return None
    if not 0.0 < r < 1.0:
        return None
    outcomes = [(0, 1.0 - r), (1, r)]
    over = str(side or "OVER").upper() != "UNDER"
    need = math.floor(float(line)) + 1 - float(banked or 0.0)
    p_over = p_at_least(outcomes, need, max(0.0, float(bf_left)))
    return p_over if over else 1.0 - p_over


def bf_left(outs_left_for_opponent: float, banked_bf: float,
            leash: float = STARTER_BF, own_pen_score: float = None) -> float:
    """Batters a pitcher still in the game is expected to face.

    Two limits, whichever binds first: the game does not have infinite
    batters left, and neither does the manager's patience. Without the
    second, a starter cruising in the third gets credit for every hitter
    remaining in the game — an outing nobody actually makes.

    ``own_pen_score`` is his OWN bullpen's measured two-day workload, and
    it stretches the patience limit through `bullpen.leash_factor` — the
    same function, with the same `market_is_outs=True` reading, that the
    pre-game outs model already uses for exactly this. A manager with no
    available relievers rides his starter longer; that is the most
    reliably observable managerial behaviour in baseball and it lands
    straight on how many more hitters this man will face.

    It moves only the LEASH, never the game limit. A short pen cannot
    conjure batters that do not exist in the innings remaining.
    """
    leash = float(leash)
    if own_pen_score is not None:
        from .bullpen import leash_factor
        leash *= leash_factor(own_pen_score, market_is_outs=True)
    from_game = max(0.0, float(outs_left_for_opponent)) * PA_PER_OUT
    from_leash = max(0.0, leash - float(banked_bf or 0.0))
    return max(0.0, min(from_game, from_leash))
