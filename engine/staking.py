"""One scale for every stake: 1 unit = 1% of bankroll, and the PRICE
sets the size.

The journal was quoting stakes off TWO different rulers. The parlay spec
pinned 1u = 1% of bankroll, but every prop path converted its Kelly
fraction to units with ``* 20`` — a 20-unit bankroll — so a solid -110
play that quarter-Kelly says deserves ~2.4% landed at 0.48u, and a thin
edge rounded to the same 0.1-0.2u as a home-run dime. Ethan read the
symptom straight off the board: "we put .1 on home runs AND .1 on
regular -100 props." The ROI line inherited the distortion, because
units staked is its denominator.

Everything converts through here at BANKROLL_UNITS = 100. What changed on
2026-08-12 is what decides the number of units, and it is no longer
Kelly-times-grade — see the ladder note below for the three measurements
that retired that, and `docs/SELECTION_CORRECTION.md` for the related
correction to the claims those stakes were computed from.

Settled history is NOT restated: those stakes were the bets as made, and
the Record page is receipts. A scale change dates a new model era and
reads honestly from here forward.
"""

from __future__ import annotations

from .odds import american_to_decimal

#: 1u = 1% of bankroll — the documented scale (§10 / parlays), now the
#: only one in the codebase.
BANKROLL_UNITS = 100.0
#: Any positive stake floors here so a real edge never displays as 0.00u.
MIN_STAKE_UNITS = 0.1

# --- the price ladder ------------------------------------------------------
#
# Ethan, 2026-08-12: "with these unit sizes that means we are putting 30
# cents or 50 cents or a couple dollars on our bets ... we should have our
# base line unit at 1 or something", and "i dont think we should be judging
# how many units we put on a pick based on the grade we give it but we
# should base it on the line of the prop."
#
# Both halves are supported by our own record, which is why this replaced
# Kelly-times-grade rather than sitting beside it. `stakecheck.py` on 113
# settled bets in the current era:
#
#   flat 1u on every bet          -12.96%   <- best of the three
#   as actually staked            -20.96%
#   what the sizing rules asked   -25.49%   <- following our own sizing
#                                              MORE closely lost MORE
#
#   largest stake quartile   0.972u avg, 34.5% hit, -33.9%   <- the worst
#   grade A+  -18.3%   ·   grade A  -7.9%                    <- inverted
#
# Three independent readings of the same thing: our conviction signal is
# anti-correlated with what happens next. Sizing on conviction therefore
# puts the most money on the worst bets, and the fix is not a better
# conviction weight — it is to stop weighting by conviction at all.
#
# WHAT SETS THE SIZE INSTEAD. The price, on one stated principle: equal
# variance per bet. A stake s at decimal odds d has return variance
# proportional to s²d², so holding s·d constant across prices holds each
# bet's contribution to bankroll swing constant. Normalised so a standard
# -110 prop is exactly the base unit:
#
#     -200   1.25u (ceiling)     +150   0.76u
#     -110   1.00u               +200   0.64u
#     +100   0.95u               +400   0.38u
#
# It is smooth, so two picks a few cents apart in price cannot end up a
# factor of five apart in stake — the artefact Ethan read off the board as
# ".05 units on a +100 pick then .25 on a +100".
#
# THE FLOOR, AND THE ROUND TRIP IT TOOK. Ethan first asked for "nothing
# under 10 dollars", which at 1u = 1% of bankroll puts the floor ON the
# base unit and flattens the entire plus side to a flat unit. Shipped,
# then reverted the same day on his read: "that might completely contradict
# what you just did ... i just want it to where we make the most money and
# the roi is at the lowest loss."
#
# He is right, and the reason is worth keeping. A flat unit from -110 out
# to +900 abandons the principle that set the ladder in the first place —
# a +400 at one unit carries about five times the payout swing of a -110
# at one unit, so a night heavy on long prices moves the bankroll much
# further than the unit count says. Buying a round dollar figure with
# that much extra variance is not the trade he was asking for.
#
# The thing he actually wanted is already satisfied here without the
# contradiction: "the .005 and .1 unit bets are unacceptable, no one wants
# to bet 50 cents." Those came from the RETIRED Kelly-times-grade rule,
# not from this ladder. At 1u = $10 the ladder's smallest possible ticket
# is $3.50 and a standard prop is $10 — nothing on the board can be a
# 50-cent bet any more, and the slope survives.
#
# The dollar figures are CONDITIONAL on 1u = $10, i.e. bankroll x unit% =
# 10. At a $500 bankroll on 1% every number above halves. The engine works
# in units and cannot see dollars; the site converts and prints the dollar
# amount beside every stake.
#
# WHAT KELLY STILL DOES. It vetoes. A negative Kelly means the price beats
# the edge and there is no bet at any size; that judgement is sound and is
# kept. What is dropped is Kelly's opinion about how MUCH, because the
# quartile table above says that opinion is worse than useless.

# AND THE SAME QUESTION ASKED AGAIN FOR GAME BETS, 2026-09-02. Ethan,
# reading a lint flag that called a +190 card at 0.66u an over-stake:
# "i want it where we just make the most money and roi looks the best, i
# dont care about what grade it allowed how much money." The 0.66u was
# this ladder's own answer, and the flag was auditing `quality
# .STAKE_CAP_U`, which this file retired — but "the cap is retired" is
# not the same claim as "the cap does no good", so it was replayed.
#
# 1,050 settled NFL game bets (moneyline, spread, total, team total),
# the production pricers over stored closes, the SAME bets re-sized:
#
#   ladder (ships now)   -2.76%   ± 6.11 (95%)
#   flat 1u              -2.14%   ± 6.57
#   grade cap on top     -2.53%   ± 6.37     1,007u staked -> 522u
#   quarter Kelly size   -3.44%   ± 6.90
#   half Kelly size      -3.45%   ± 6.90
#
# Every gap is inside the noise band, so nothing here is a reason to
# change the rule — and the ladder is kept for that reason rather than
# because it won. What the table DOES settle is the cap: it halves the
# money staked and leaves ROI where it was, which is the one thing a
# risk limit is supposed to buy and does not. Kelly sizing is worst
# again, on a different board from the one that retired it.
#
# AND WHERE THIS QUESTION CANNOT BE ASKED, recorded so the dead end is
# walked once. The same bake-off over the PROP board's walk-forward
# backtest (`backtest.backtest_from_stats`, 1,094 recommended bets
# across 2023-25) returned an IDENTICAL 10.11% for the ladder, flat and
# the grade cap — not a tie, an artefact: without harvested closes that
# walk prices every prop at `nflverse.build_slate`'s synthetic -110, so
# a rule whose whole input is the price has nothing to vary over. Any
# staking comparison needs real prices, which means the settled journal
# — `stakecheck.py` on the box that holds it — and not this replay.

#: The standard bet, at the reference price. 1u = 1% of bankroll, so at a
#: $1,000 bankroll this is $10 — the floor Ethan asked for.
BASE_UNITS = 1.0
#: The price the base unit is defined at: standard two-way prop juice.
REF_ODDS = -110
#: The ladder's ends. The ceiling stops heavy chalk from turning a "safe"
#: price into a big bet — short prices are exactly where the model's
#: over-claim was measured worst.
MAX_PRICED_U = 1.25
#: The floor keeps a long price a real wager rather than a token: 0.35u
#: is $3.50 at 1u = $10, where the retired rule was quoting 50 cents.
#: Briefly raised to the base unit and reverted — see the round trip in
#: the ladder note, and do not raise it again without deciding what to do
#: about the variance a flat plus-side carries.
MIN_PRICED_U = 0.35


def kelly_fraction(p: float, odds: int) -> float:
    """Full-Kelly bankroll fraction; 0 means the price beats the edge."""
    b = american_to_decimal(odds) - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (b * p - (1.0 - p)) / b)


def units_for_price(odds: int) -> float:
    """The stake this price gets, before any caller-side downweight.

    Equal variance per bet: ``s ∝ 1/d``, normalised so the reference
    price stakes :data:`BASE_UNITS`. See the ladder note above for why
    the price and not the grade decides this.
    """
    d = american_to_decimal(odds)
    if d <= 1.0:
        return 0.0
    raw = BASE_UNITS * (american_to_decimal(REF_ODDS) / d)
    return round(min(MAX_PRICED_U, max(MIN_PRICED_U, raw)), 2)


def price_cap_units(odds: int) -> float:
    """Back-compat shim: the ladder IS the price rule now.

    Kept because `launch.py --stakes` and the restatement paths ask "what
    would this price allow?", which used to be a ceiling over Kelly and is
    now simply the stake. Returning the ladder's answer keeps those
    readouts honest instead of quoting a rule that no longer runs.
    """
    return units_for_price(odds)


def units_with_reason(fraction: float, odds: int,
                      mult: float = 1.0) -> tuple[float, str]:
    """``(units, why)`` — the stake and the rule that actually set it.

    ``fraction`` is Kelly's answer and is used ONLY as a veto: at or
    below zero the price beats the edge and there is no bet. Its size is
    ignored, deliberately — see the ladder note at the top of this file
    for the three measurements that retired it.

    Ethan, 2026-08-12, reading a board of 0.25 / 0.25 / 0.25 / 0.15 /
    0.05: "It doesn't make any sense and feels random." It was not
    random, but it was unreadable, because four different rules could set
    a stake and the board showed none of them. Now one rule sets it and
    the string says which rung.

    The ``cap_units`` argument is GONE rather than ignored. It carried
    the per-grade ceiling, and a parameter that silently stops working is
    how a retired rule keeps looking alive at every call site.
    """
    if fraction <= 0 or mult <= 0:
        return 0.0, "no bet — the price beats the edge"
    stake = units_for_price(odds)
    if stake >= MAX_PRICED_U:
        why = f"{stake:g}u — the ladder's ceiling for a price this short"
    elif odds == REF_ODDS:
        # Kept ahead of the floor test from the reverted round trip. It is
        # a no-op while the floor sits below the base unit, and it is the
        # difference between "-110 is the price this ladder is normalised
        # to" and "-110 is the smallest ticket we allow" if anyone raises
        # the floor again.
        why = f"{stake:g}u — the base unit, at standard juice"
    elif stake <= MIN_PRICED_U:
        why = f"{stake:g}u — the ladder's floor for a payout this long"
    else:
        why = f"{stake:g}u — the ladder's size for {odds:+d}"
    if mult != 1.0:
        # NOT rounded here. Rounding before the floor check turns a
        # severe downweight (×0.001) into 0.0, which reads as "no bet"
        # — a decision the caller never made. The floor exists precisely
        # to catch stakes this small, so it has to see them first.
        stake = stake * mult
        why += f", ×{mult:.2f} for the caller's own downweight"
    if 0 < stake < MIN_STAKE_UNITS:
        stake, why = MIN_STAKE_UNITS, f"floored at the {MIN_STAKE_UNITS}u minimum"
    return round(stake, 2), why


def to_units(fraction: float, odds: int, mult: float = 1.0) -> float:
    """Kelly veto + the price ladder → display units.

    ``fraction`` decides only whether there is a bet; ``odds`` decides how
    big; ``mult`` is a caller-side downweight for something that is not
    conviction (the NBA minutes uncertainty, say).
    """
    return units_with_reason(fraction, odds, mult=mult)[0]


def kelly_units(p: float, odds: int, fraction: float = 0.25) -> float:
    """The whole path in one call: Kelly decides IF, the price decides how
    much. ``fraction`` is retained because a caller may want a stricter
    veto than full Kelly, and it cannot change the size."""
    full = kelly_fraction(p, odds)
    if full <= 0:
        return 0.0
    return to_units(full * fraction, odds)
