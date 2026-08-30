"""Betting model.

Turns a projection into a bettable recommendation: it shops for the best line,
computes the model's hit probability, measures the edge against the book's
de-vigged price, sizes a stake with a fractional-Kelly rule, and rolls
everything into a 0–10 confidence score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Prop, RECEPTIONS
from .projection import Projection
from .odds import (best_over_line, best_under_line, consensus_fair,
                   devig_two_way, expected_value, is_quotable)
from .statmath import prob_over, prob_over_discrete, clamp
from .calibrate import apply_temperature, calibrated, correction_for

# --- calibration guards -----------------------------------------------------
# The prop model is not yet calibrated to real outcomes, and live feeds
# sometimes attach a mismatched/one-sided line. Two guards keep the output
# honest:
#   1. shrink the model's probability toward the market price, so a raw edge is
#      damped to a realistic size while the model is still uncalibrated, and
#   2. treat a raw edge beyond MAX_CREDIBLE_EDGE (or a placeholder "proxy" line)
#      as a data error, not alpha — in an efficient prop market a 20%+ edge is
#      always bad data. Those are graded Pass instead of shown as strong plays.
MARKET_SHRINK = 0.5
MAX_CREDIBLE_EDGE = 0.10


def temper_edge(hit_raw: float, fair: float, book: str,
                allow_synthetic_line: bool = False,
                shrink: float | None = None) -> tuple[float, float, bool]:
    """Shrink the model probability toward the market and judge credibility.

    Returns ``(hit, edge, credible)`` where ``hit`` is the tempered win
    probability, ``edge = hit - fair``, and ``credible`` is False when the line
    is a placeholder or the raw disagreement is implausibly large.

    ``shrink`` is the §3 haircut — how much of a raw disagreement with the
    market we trust. It scales by market tier (see engine.quality): Tier 1
    keeps half, Tier 3 keeps under a third, because most of a big raw edge in
    a noisy market is model error. Defaults to the flat MARKET_SHRINK for
    callers that don't tier (the backtest harness, older tests).

    ``allow_synthetic_line`` is for the backtest harness, which deliberately
    prices against a naive baseline line rather than a real book — there a
    "proxy" line is the point of the exercise, not a data error.
    """
    if shrink is None:
        shrink = MARKET_SHRINK
    hit = clamp(fair + shrink * (hit_raw - fair), 1e-6, 1.0 - 1e-6)
    real_line = allow_synthetic_line or (book or "").lower() != "proxy"
    credible = real_line and abs(hit_raw - fair) <= MAX_CREDIBLE_EDGE
    return hit, hit - fair, credible


@dataclass
class Recommendation:
    player: str
    team: str
    opponent: str
    market: str
    side: str                 # "OVER" or "UNDER" — whichever side has the edge
    book: str
    line: float
    odds: int
    projection: float
    proj_low: float
    proj_high: float
    hit_prob: float
    fair_prob: float          # book's de-vigged implied probability
    edge: float               # hit_prob - fair_prob
    ev_per_unit: float
    confidence: float         # quality / 10 — one score, two displays
    stake_units: float
    grade: str                # "A+" / "A" / "B+" / "Pass" — no Leans (§10)
    reasons: list[str] = field(default_factory=list)
    trend: str = "flat"
    #: Model probability minus the break-even implied by the PRICE WE CAN
    #: ACTUALLY GET — the number Kelly sizes on, and the one that decides
    #: whether a bet makes money. `edge` above is measured against the
    #: de-vigged fair, so it is systematically larger: the gap between
    #: them is the juice. A board showing only `edge` advertises +4.3%
    #: on a bet whose real margin over the offered price is 0.6 points,
    #: which is exactly why the stakes beside it looked arbitrary
    #: (Ethan, 2026-08-12: "It doesn't make any sense and feels random").
    net_edge: float = 0.0
    #: WHICH RULE SET THE STAKE — "quarter-Kelly on the price offered",
    #: a price-band cap, a grade cap, the floor, or the slate's exposure
    #: scaling appended downstream. When a cap binds, the stake stops
    #: carrying information about the edge, and the board has to say so.
    stake_basis: str = ""
    quality: int = 0          # the unified 0–100 grade (engine.quality)
    tier: int = 2             # §8 market tier
    volatility: str = "HIGH"  # LOW / MEDIUM / HIGH / EXTREME
    # False when no real book line was available and the "line" is the engine's
    # own proxy. There is nothing to have an edge *against* in that case, so the
    # edge is reported as zero rather than as a number that looks like alpha.
    has_market: bool = True
    #: The model's UNTEMPERED probability for ``side``, before temper_edge
    #: shrinks it toward the market. ``hit_prob`` above is what we BET on
    #: and is the right number everywhere a price is involved; this is the
    #: number the calibration fitter has to learn on, because the fitted
    #: correction is applied to the raw probability inside the evaluator.
    #: Fitting the tempered one and correcting the raw one is fitting a
    #: different quantity than you correct — see engine/backtest.py.
    raw_prob: float = 0.0
    #: The FIELD's de-vigged fair for the over, and how many books it is,
    #: at pick time. Evidence only — nothing prices from it.
    #:
    #: `fair_prob` above is de-vigged from the book being bet, so the
    #: benchmark moves with the outlier: shopping selects the price
    #: furthest from the field, and that same price defines what "fair"
    #: means. Whether that costs anything is a question for the record,
    #: and the record can only answer it if the field is captured at the
    #: moment the pick was made — reconstructing it afterwards from
    #: snapshots is a different, looser number. See bookcheck.py.
    fair_consensus: float | None = None
    consensus_books: int = 0


#: THE TWO REASONS THAT REFUSE THE BET, named rather than inlined.
#:
#: They used to be string literals at their insert sites, which made them
#: invisible to anything that wanted to ask "is this reason a refusal or a
#: point in the pick's favour". The front end has to answer exactly that —
#: `NEG_REASON` in web/js/app.js decides whether a bullet renders as a
#: green tick or a struck-through negative — and it answered by matching
#: a hand-kept list of keywords that neither of these strings contained.
#:
#: So a card told a reader FOUR TIMES that nothing here was bettable, with
#: two of those four wearing the same green tick as "Dome game — no
#: weather impact". Reported 2026-08-30 from a live Puka Nacua card.
#:
#: Named constants make them referenceable, and `tests/test_refusals.py`
#: asserts every one of them is classified as a refusal — so the next
#: string added here fails the suite instead of shipping as an
#: endorsement.
UNRELIABLE_CALIBRATION_REASON = (
    "This market's calibration fit hit the edge of its search range — the "
    "model can't price it reliably, so nothing here is bettable until it's "
    "fixed")
NO_CREDIBLE_EDGE_REASON = (
    "No credible market edge — line unavailable or price looks off")

#: Every reason string that means "we are not betting this". Anything
#: added above belongs here, and the suite checks that it is.
REFUSAL_REASONS = (UNRELIABLE_CALIBRATION_REASON, NO_CREDIBLE_EDGE_REASON)


def _confidence_score(edge: float, hit_prob: float, proj: Projection,
                      trend_align: float = 0.0) -> float:
    """How much do we trust THIS EDGE ESTIMATE, on a 0–10 scale?

    Note what is deliberately absent: the absolute win probability. An
    earlier version paid up to 2.5 points simply for a high hit
    probability, which no plus-money bet can ever earn — a ~2.5-point
    handicap applied to every underdog before a shred of evidence was
    weighed. That is a category error (confidence in an estimate is not
    the same thing as the estimate being large), and it pointed exactly
    the wrong way: this journal measured favourites at 45.7% against a
    66.9% break-even while underdogs came in ahead of theirs.

    So the score is now built only from things that actually bear on
    whether the edge is real: its size, the sample and variance behind
    the projection, and whether it runs with or against recent form.
    ``hit_prob`` is kept in the signature for callers and future use.

    PROVISIONAL weighting — the August backtest should re-fit it."""
    # Edges are tempered toward the market (see temper_edge), so the credible
    # range is a few percent — a 4.5% tempered edge earns full weight here.
    edge_component = clamp(edge / 0.045, 0.0, 1.0) * 6.5          # up to 6.5

    # Data-quality discount: thin samples and high relative variance cost points.
    games = proj.form.sample_games
    sample_q = clamp(games / 8.0, 0.3, 1.0)
    rel_var = proj.std / proj.mean if proj.mean > 0 else 1.0
    var_q = clamp(1.0 - (rel_var - 0.30), 0.4, 1.0)
    quality = 2.5 * sample_q * var_q                              # up to 2.5

    total = edge_component + quality + trend_align
    return round(clamp(total, 0.0, 10.0), 1)


def _trend_alignment(side: str, trend: str) -> float:
    """Confidence nudge for betting with — or against — the player's trend.

    Backing an OVER on a cooling player (or an UNDER on a heating one) fights
    the direction of recent form and takes a real haircut; riding the trend
    earns a small bonus. This is the piece that makes the model stop
    recommending a name that has stopped producing."""
    if trend == "flat":
        return 0.0
    with_trend = (side == "OVER" and trend == "up") or (side == "UNDER" and trend == "down")
    against_trend = (side == "OVER" and trend == "down") or (side == "UNDER" and trend == "up")
    if with_trend:
        return 0.5
    if against_trend:
        return -1.2
    return 0.0


def pick_side(lines, p_over_at, hold: float | None = None):
    """Shop both sides and return the one with the larger edge.

    ``p_over_at(line) -> P(stat > line)`` is supplied by the caller so each
    sport prices with its own distribution (normal, discrete, Poisson…).
    Returns ``(side, best_line, win_prob, fair_prob, edge)`` where ``win_prob``
    is the probability the chosen bet cashes.

    ``hold`` is the MEASURED one-sided hold for this market, passed down
    to the de-vig. It matters only on a market quoted one side — every
    scorer prop — where the fair price is an assumption until something
    measures it. Without this the long-shot board priced those props off
    `holdwatch`'s measurement and this board could not see it, so the
    same prop carried two different fair prices depending on the page."""
    over = best_over_line(lines, hold)
    p_over_at_over = clamp(p_over_at(over.line), 1e-6, 1.0 - 1e-6)
    over_edge = p_over_at_over - over.fair_prob

    # A market quoted Over-only (home runs, most scorer props) has no under
    # to bet: never price the side that doesn't exist.
    two_sided = [ln for ln in lines if ln.under_odds]
    if not two_sided:
        return "OVER", over, p_over_at_over, over.fair_prob, over_edge
    under = best_under_line(two_sided, hold)

    p_over_at_under = clamp(p_over_at(under.line), 1e-6, 1.0 - 1e-6)
    under_win = 1.0 - p_over_at_under
    under_edge = under_win - under.fair_prob

    if over_edge >= under_edge:
        return "OVER", over, p_over_at_over, over.fair_prob, over_edge
    return "UNDER", under, under_win, under.fair_prob, under_edge


def apply_selection(hit: float, edge: float, sport: str) -> tuple[float, float]:
    """Apply the measured selection haircut to a claim and its edge.

    See engine/selectionfit.py for what is being corrected and why the
    per-market calibrators could not see it. Two properties matter here:

    * It runs AFTER ``pick_side``. The haircut can shrink a bet out of
      existence but never turn an OVER into an UNDER — changing sides on
      a bias correction would be a different model, not a corrected one.
    * ``edge`` moves by exactly the same amount as ``hit``, because edge
      is ``hit − fair`` and the haircut does not touch the market's fair.
      Re-deriving it any other way is how a board ends up advertising a
      headline edge its own stake no longer agrees with.

    No store on disk (fresh clone, CI, a journal under the floor) → the
    shift is 0.0 and both numbers come back untouched.
    """
    from .selectionfit import apply_haircut
    cut = apply_haircut(sport, hit)
    return cut, edge + (cut - hit)


def net_edge(hit: float, odds: int) -> float:
    """Model probability minus the break-even implied by the REAL price.

    This is the number that decides whether a bet makes money. Beating
    the de-vigged "fair" probability is not the same thing: at standard
    −110/−110 prop juice, break-even sits ~2.4 points ABOVE fair, so a
    +1.2-point edge over fair is a 1.2-point LOSS against the price."""
    from .odds import american_to_prob
    return hit - american_to_prob(odds)


# --- the favourite-overconfidence surcharge --------------------------------
# Measured, not assumed: the journal's first 46 favourite bets hit 45.7%
# against a 66.9% break-even (z = −3.07, one-tailed p = 0.001), while
# underdogs came in slightly ahead. The model's probabilities inflate as
# the price shortens — a known failure mode, since selecting the biggest
# edges out of noisy estimates preferentially selects the overestimates,
# and that bias bites hardest where the true probability is already high.
#
# So: demand progressively more proven edge the shorter the price. Below
# a 55% break-even nothing changes; from there the requirement climbs,
# which makes heavy chalk effectively unreachable (at −235 even a maximum
# credible edge falls short) without banning any price outright.
# PROVISIONAL — the August backtest recalibrates the tail on thousands of
# samples instead of 46, and this surcharge should be re-fit then.
FAV_GUARD_FROM = 0.55
FAV_GUARD_SLOPE = 0.18

# No "Lean" tier — §10: a lean is a bet that failed the filter published
# anyway. Below these floors the answer is Pass, not a softer yes.
BASE_THRESHOLDS = (("Strong Play", 8.0, 0.020),
                   ("Play", 6.5, 0.010))


def favourite_surcharge(odds: int) -> float:
    """Extra net edge required at this price, in probability points."""
    from .odds import american_to_prob
    return FAV_GUARD_SLOPE * max(0.0, american_to_prob(odds) - FAV_GUARD_FROM)


def _grade(confidence: float, net: float, odds: int | None = None) -> str:
    """Grade on net edge — what's left after the vig, not before it.

    The old thresholds compared edge-vs-fair (1.2 / 2.5 / 4.0 points) and
    so graded bets the juice had already eaten: every "Lean" was −1.2
    points at the price, and a threshold "Play" was +0.1 — which is why
    Kelly sized them at 0.00 units. Grading on what actually clears the
    price means every graded bet is one Kelly will size for real.

    ``odds`` adds the favourite surcharge above; omit it only where the
    price isn't known (nothing in the live path does)."""
    extra = favourite_surcharge(odds) if odds is not None else 0.0
    for name, conf_min, net_min in BASE_THRESHOLDS:
        if confidence >= conf_min and net >= net_min + extra:
            return name
    return "Pass"


# The smallest stake worth showing. Below this, Kelly is telling us the
# edge is indistinguishable from noise — and a "bet 0.00 units"
# recommendation is not a recommendation, it's a rounding artifact.
MIN_STAKE_UNITS = 0.1


def _zone_for(sport, game, prop):
    """§6's coverage tell for the veto — the opposing defence's zone rate.

    A helper rather than eight lines at the call site, because
    `tests/test_fatigue.py` asserts that `_fatigue_state` sits within 500
    characters of the `lp_veto(` call: the two have to be read together,
    and a block wedged between them is exactly the drift that guard
    exists to catch. The same guard already made this repo extract
    `_velo_for` and `_tto_for` on the MLB side.

    NOT A PRICE. The veto only ever ENFORCES a slice the journal already
    convicted, which is a different act from letting a new signal move a
    number — see docs/THE_INFORMATION_TEST.md.
    """
    if sport != "nfl" or game is None:
        return None
    try:
        from .pipeline import _opp_zone_rate
        return _opp_zone_rate(game, {"opponent": getattr(prop, "opponent", "")})
    except Exception:                                         # noqa: BLE001
        return None


def _kelly_stake(model_prob: float, odds: int, fraction: float = 0.25,
                 cap_units: float = 1.0) -> float:
    """Fractional-Kelly stake in units (0 = no bet).

    §10: quarter Kelly is the default; half Kelly only for A+ plays in
    Tier 1 markets. The input is the POST-haircut probability — feeding raw
    model edge into Kelly would compound the same optimism twice.
    ``cap_units`` is the per-grade cap (2u max on any single play).

    The arithmetic lives in engine/staking.py — one scale (1u = 1% of
    bankroll) and one set of price-band ceilings for every sport, because
    this function's old private twenty-unit ruler is how a solid -110 play
    and a home-run dime both displayed as pocket change.

    Zero has one meaning here: Kelly says this price is not beatable at
    our estimated probability."""
    from .staking import kelly_units
    return kelly_units(model_prob, odds, fraction)


def under_reason(mean: float, line: float, places: int = 1) -> str:
    """Why the model took the under, in words that survive a right skew.

    THE CARD THAT CONTRADICTED ITSELF. Ethan found a pick siding UNDER
    58.5 on a player the same card projected for 71.6, and the reason
    string read "projects 71.6038 under the 58.5 line" — a sentence whose
    two halves disagree, printed at full float precision beside a
    projection field rounded to a tenth.

    Both halves were honest separately. `pick_side` chooses from the
    empirical distribution, not from the mean, and §8 is explicit that
    averages lie on right-skewed stats: a receiver with three quiet games
    and one 180-yard afternoon has a mean above his median, so the under
    can be the better side while the mean sits above the line. The text
    was the only thing claiming otherwise.

    ONE COPY, because there were two and they drifted. `engine/mlb`
    corrected its version on 2026-08-22 and this one kept the single
    branch for six days, over a stretch where the NFL calibrations were
    also fitting one-sided — which is what put a whole board's worth of
    unders on screen with an impossible sentence under each one.

    `places` follows the caller's stored `projection` field: MLB rounds
    to 2, NFL to 1. Two numbers on the same card describing the same
    quantity have to agree, which `:g` could not promise.
    """
    if mean <= line:
        return (f"Model sides UNDER — projects {mean:.{places}f} under "
                f"the {line:g} line")
    return (f"Model sides UNDER — the mean is {mean:.{places}f} but a few "
            f"big games inflate it; the game log clears {line:g} less "
            f"often than the price implies")


def evaluate_prop(prop: Prop, proj: Projection,
                  allow_synthetic_line: bool = False,
                  game=None, sport: str = "nfl") -> Recommendation:
    """§3's procedure end to end: shop the line, devig, price the
    distribution, haircut by tier, gate on the tier minimum, grade 0–100,
    size with fractional Kelly. ``game`` supplies the spread for the
    game-script component of the grade (None → neutral).

    ``sport`` keys every self-tuning store. It was once hardcoded "nfl"
    here — harmless while only NFL priced through this path and nothing
    else had a fitted correction, and a silent cross-sport leak the day
    either stopped being true."""
    from .quality import (tier_shrink, tier_min_edge, market_tier,
                          volatility as market_volatility, quality_score,
                          letter as quality_letter, STAKE_CAP_U)
    from .calibrate import is_reliable
    from .losspatterns import veto as lp_veto
    temp, bias = correction_for(sport, prop.market)

    def p_over_at(line: float) -> float:
        if prop.market == RECEPTIONS:
            raw = prob_over_discrete(line, proj.mean, proj.std)
        else:
            raw = prob_over(line, proj.mean, proj.std)
        # Calibrate before the side is chosen — see engine/mlb/betting.py.
        return calibrated(sport, prop.market, raw)

    # THE MEASURED HOLD, NOT THE ASSUMPTION, when one exists for this
    # market. `one_sided_hold` answers the fitted value from
    # engine/holdwatch or falls back to the shared constant, so this is
    # the same number the long-shot board prices against rather than a
    # second opinion about the same market.
    from .longshots import one_sided_hold
    _hold, _hold_n = one_sided_hold(sport, prop.market)
    side, best, hit_raw, fair, edge_raw = pick_side(prop.lines, p_over_at,
                                                    hold=_hold)
    hit, edge, credible = temper_edge(hit_raw, fair, best.book,
                                      allow_synthetic_line,
                                      shrink=tier_shrink(prop.market))
    hit, edge = apply_selection(hit, edge, sport)      # see apply_selection
    # A price no book could have posted is not a market, the same way a
    # proxy is not. `is_quotable` also answers False for 0, which is the
    # unquoted-side sentinel: if the side we chose is the side nobody
    # quotes, there is nothing here to bet.
    has_market = ((allow_synthetic_line or (best.book or "").lower() != "proxy")
                  and is_quotable(best.odds))
    ev = expected_value(hit, best.odds)
    net = net_edge(hit, best.odds)
    if not has_market:
        # No real price to beat — don't report a number that reads as an
        # edge. THAT USED TO MEAN `edge` ALONE, and the other two are
        # computed from `best.odds`, which on a proxy row is the engine's
        # own invented price. So a card whose Edge cell correctly read
        # "—" printed "EV / unit +13%" one cell to its right, off a price
        # no book had posted. Bigger than the +9% that got this looked at.
        #
        # Zeroed rather than blanked, matching what `edge` has always
        # done: `ev_per_unit` is sorted and ranked on in three places and
        # a None there is a NaN in the sort. The card blanks it on
        # `has_market`, the same way it already blanks the edge.
        edge = 0.0
        ev = 0.0
        # `net_edge` is the exception, and deliberately: its one render
        # site is already guarded on null, and "+0.0% over the price you
        # get" is a claim about a price that does not exist. None makes
        # the sentence disappear, which is the right amount to say.
        net = None

    # Game-script inputs: who's favored, by how much (None when no spread).
    favored, spread_abs = None, 0.0
    spread = getattr(game, "spread", None) if game is not None else None
    if spread:
        home_fav = spread < 0
        is_home = prop.team == getattr(game, "home", None)
        favored = home_fav == is_home
        spread_abs = abs(spread)

    # The unified §10 grade — one score, the spec's exact weights.
    form_cv = (proj.form.std / proj.form.mean) if proj.form.mean > 0 else 1.0
    from .projection import CV_FLOOR
    quality, quality_notes = quality_score(
        edge=edge, market=prop.market, side=side,
        favored=favored, spread_abs=spread_abs,
        matchup_mult=proj.matchup.multiplier,
        weather_mult=proj.weather.multipliers.get(prop.market, 1.0),
        cv=form_cv, cv_typical=CV_FLOOR.get(prop.market, 0.35),
        sample_games=proj.form.sample_games)
    confidence = round(quality / 10.0, 1)

    # The gates, in order of what they mean:
    #  credible  — a >10% raw disagreement is bad data, not alpha (§2.5)
    #  tier edge — the §3 minimum post-haircut edge for this market's tier
    #  net       — the REAL price must still clear break-even (plus the
    #              measured favourite surcharge). NOT a second edge bar:
    #              requiring a full extra point here (the old +0.010) sat
    #              ABOVE the tier minimums at standard juice and silently
    #              overrode the §3 bars — the same double-charging disease
    #              as the old quality scaling, one layer down.
    #  quality   — below 70 is no bet, not a lean (§10)
    # Two more gates, in parity with the MLB engine:
    #  calibration — a fit at its search boundary closed this market
    #  pattern     — the loss-pattern miner closed this SLICE (a side, a
    #                price band) under false-discovery control
    calibration_ok = is_reliable(sport, prop.market)
    from .losspatterns import minutes_until
    # Football's environment, handed to the veto live: a closed "howling
    # wind" slice must refuse the NEXT windy-night pass-yards over, not
    # just explain the last one. Indoor = no wind dimension, honestly.
    _env = {}
    _w = getattr(game, "weather", None)
    if sport in ("nfl", "cfb") and _w is not None:
        # Unmeasured weather is NO wind dimension rather than a mild
        # one: nflverse fills a schedule row's wind from the played
        # game, so a forward board's 6 mph is the prior, not a forecast.
        _env = {"roofed": bool(_w.dome),
                "wind_out": None if _w.dome or not getattr(_w, "measured", False)
                else round(float(_w.wind_mph or 0), 1)}
    _rest_days = _body_clock = None
    if sport in ("nfl", "cfb") and game is not None:
        from .fatigue import state_for as _fatigue_state
        _st = _fatigue_state(game, getattr(prop, "team", ""))
        _rest_days, _body_clock = _st.get("rest_days"), _st.get("body_clock")
    _zone = _zone_for(sport, game, prop)
    pattern_block = lp_veto(sport, prop.market, side=side, odds=best.odds,
                            prob=hit, book=best.book, horizon_days=0,
                            lead_min=minutes_until(
                                getattr(game, "kickoff", None)),
                            # Schedule fatigue: the same bands the board
                            # shows, so a convicted "short week" pocket
                            # refuses the next matching pick.
                            rest_days=_rest_days, body_clock=_body_clock,
                            opp_zone_rate=_zone,
                            **_env)
    tier = market_tier(prop.market)
    min_edge = tier_min_edge(prop.market)
    gate_ok = (credible and has_market
               and calibration_ok and pattern_block is None
               and edge >= min_edge
               and net > favourite_surcharge(best.odds))
    grade = quality_letter(quality) if gate_ok else "Pass"
    fraction = 0.5 if (grade == "A+" and tier == 1) else 0.25
    if grade == "Pass":
        stake, stake_basis = 0.0, "no bet — did not clear the gate"
    else:
        # The grade decides WHETHER (above); the price decides HOW MUCH.
        # STAKE_CAP_U no longer participates — see engine/staking.py.
        from .staking import kelly_fraction, units_with_reason
        stake, stake_basis = units_with_reason(
            kelly_fraction(hit, best.odds) * fraction, best.odds)

    reasons = list(proj.reasons)
    # WHAT THE GRADE ABOUT TO GO ON THIS CARD HAS ACTUALLY DONE. The
    # ladder's order is hard-coded; whether it holds up is measured
    # (`engine.ladder`), and until now the measurement reached a terminal
    # report and stopped there while the board went on presenting A above
    # B+. Same shape as the market haircut's note, for the same reason.
    from .ladder import note_for as _ladder_note
    _ladder = _ladder_note(sport) if grade in ("A+", "A") else None
    if _ladder:
        reasons.insert(0, _ladder)
    if pattern_block:
        reasons.insert(0, pattern_block)
    if not calibration_ok:
        reasons.insert(0, UNRELIABLE_CALIBRATION_REASON)
    if not credible:
        reasons.insert(0, NO_CREDIBLE_EDGE_REASON)
    elif side == "UNDER":
        reasons.insert(0, under_reason(proj.mean, best.line, 1))
    # `calibration_ok` here too: without it a pick blocked by an
    # unreliable calibration ALSO gets told its edge missed the tier bar,
    # which names the wrong cause and quotes an edge the same card has
    # just said cannot be priced. engine/mlb had the guard; this did not.
    if credible and calibration_ok and has_market and 0 < edge < min_edge:
        reasons.append(f"Edge {edge:+.1%} is under the Tier {tier} bar "
                       f"({min_edge:.1%} post-haircut) — pass, not a lean")
    reasons.extend(quality_notes)

    # The field's opinion at pick time, captured beside the book we
    # shopped to. Restricted to books quoting the SAME number, since
    # a fair at 1.5 and a fair at 2.5 are opinions about different
    # events. Evidence only — see Recommendation.fair_consensus.
    _field = consensus_fair(prop.lines, best.line)

    return Recommendation(
        player=prop.player,
        team=prop.team,
        opponent=prop.opponent,
        market=prop.market,
        side=side,
        book=best.book,
        line=best.line,
        odds=best.odds,
        projection=round(proj.mean, 1),
        proj_low=round(proj.mean - proj.std, 1),
        proj_high=round(proj.mean + proj.std, 1),
        hit_prob=round(hit, 4), raw_prob=round(hit_raw, 6),
        fair_prob=round(fair, 4),
        fair_consensus=(round(_field[0], 4) if _field else None),
        consensus_books=(_field[1] if _field else 0),
        edge=round(edge, 4),
        ev_per_unit=round(ev, 4),
        net_edge=(None if net is None else round(net, 4)),
        stake_basis=stake_basis,
        confidence=confidence,
        stake_units=round(stake, 2),
        grade=grade,
        reasons=reasons,
        trend=proj.form.trend,
        has_market=has_market,
        quality=quality,
        tier=tier,
        volatility=market_volatility(prop.market),
    )
