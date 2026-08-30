"""Long shots — NFL anytime touchdowns and MLB home runs.

These two markets behave differently from yardage props: the outcome is a rare
*event*, so the right model is a Poisson rate (expected scores per game) turned
into P(at least one), not a normal distribution around a mean.

The discipline both engines share, and the reason this module exists:

* **Opportunity over outcomes.** A player is rated on the chances he gets — red
  zone / goal line work, plate appearances and contact quality — never on a
  streak of recent scores. Chasing last week's touchdowns is the single most
  common way to lose money in these markets.
* **Priced against the book, in a sane odds window.** A pick only counts when
  the modelled probability beats the book's implied probability, and only
  inside the odds range where the payout justifies the risk (NFL -150..+200,
  MLB +250..+650 per the strategy specs).
* **Concentration limits.** At most a couple of picks per NFL game and one per
  MLB team, so a single game script or lineup can't sink the whole card.
* **No forced picks.** If nothing clears, the honest answer is an empty board.

What the model can and can't see is stated on each pick: where a factor comes
from a proxy rather than a true measurement (e.g. red-zone share inferred from
opportunity share and team implied total, because play-by-play isn't ingested),
the pick says so rather than implying precision we don't have.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .odds import american_to_prob, devig_two_way, expected_value, american_to_decimal
from .statmath import clamp
from .calibrate import calibrated, correction_for
from .betting import MARKET_SHRINK, MAX_CREDIBLE_EDGE

# Odds windows — outside these the payout doesn't justify the variance
# (or the price implies a probability we can't beat).
#
# NFL WIDENED 2026-08-25 (Ethan: "fix the odds range for long shot picks
# for nfl and CFB"). The original -150..+200 was the strategy spec's
# conservative window and it cut the board off at exactly the prices a
# LONG SHOTS page exists for: the committee back at +270, the red-zone
# TE at +320. The floor stays — below -150 the payout never justifies a
# scorer market's variance. The ceiling was +450 — "past which a price
# implies a sub-18% event our proxy-fed model cannot separate from
# noise". That was true when it was written and stopped being true
# twice over: the model is no longer proxy-fed (measured red-zone usage
# from play-by-play now reaches it, engine/nflusage), and on 2026-08-27
# `engine.tdbacktest` measured what it can actually do down there over
# 17,785 player-weeks.
#
# Inside the sub-18% region — 9,327 of those weeks — sorted by model
# probability into quintiles:
#
#     Q1 (longest)   claimed 5.0%   scored  6.2%
#     Q2             claimed 6.8%   scored  7.8%
#     Q3             claimed 9.0%   scored 11.6%
#     Q4             claimed 12.8%  scored 13.8%
#
# Monotone, and the top quintile out-scores the bottom by 7.4 points at
# z = 7.6. That is separation from noise, measured, in exactly the
# region the old ceiling said could not be separated. With the fitted
# correction on top (engine.tdbacktest.fit_calibration) the worst band
# sits 1.4 points off true.
#
# So the ceiling moves out — NOT because longshots are being chased, but
# because the reason for holding it in has been falsified. The line
# after this one still governs: the EV gate, the market shrink and the
# credibility guard do the filtering; the window only says which prices
# are worth filtering. Widening it hands the decision to those gates
# rather than pre-empting it.
NFL_TD_ODDS = (-150, 700)
MLB_HR_ODDS = (250, 650)
# CFB gets its own window, not NFL's: spreads run to -40, so books hang
# shorter juice on bell cows (-200 is an ordinary Saturday price for a
# stud back) and longer prices on everyone else. Same ceiling logic as
# the NFL note above, one notch out for the wilder distribution.
CFB_TD_ODDS = (-200, 900)

# League baselines used to convert a team's implied total into expected TDs.
NFL_AVG_TEAM_POINTS = 22.6
NFL_AVG_TEAM_OFF_TDS = 2.4


@dataclass
class LongShot:
    """One long-shot recommendation, with the reasoning that produced it."""
    player: str
    team: str
    opponent: str
    market: str                 # "anytime_td" | "home_runs"
    market_label: str
    book: str
    odds: int
    model_prob: float           # our probability of the event
    #: THE MARKET CONSENSUS, de-vigged off one book's complete board —
    #: an estimate of the true probability, which does NOT move with
    #: where you happen to bet.
    implied_prob: float
    edge: float
    ev_per_unit: float
    confidence: float           # 0..10
    stake_units: float
    grade: str
    expected_opportunities: float   # red-zone chances (NFL) / plate appearances (MLB)
    primary_reason: str
    reasons: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    #: The overround this pick was actually priced against, and where
    #: that number came from. Prose in a caveat is for the reader; a
    #: preflight needs to count how many of a live board's games got a
    #: MEASURED vig and how many fell back, and parsing a sentence to
    #: find out is how a check quietly stops checking.
    #: WHAT THIS BOOK IS CHARGING, raw, vig included. A different number
    #: from `implied_prob`, which is the market consensus off another
    #: book's board — and the gap between the two is the whole value of
    #: having shopped. Published because a card showing only the
    #: consensus beside a price can read as a de-vig that made the price
    #: SHORTER, which is impossible: they simply come from two books and
    #: nothing said so. Defaulted, so a caller that predates it (or a
    #: test fixture) still constructs.
    book_prob: float = 0.0
    #: The edge that PAYS: the model against the price on offer. `edge`
    #: above is the model against the market consensus — the honest
    #: disclosure, and a different question. This one decides the grade,
    #: the stake and the selection.
    net_edge: float = 0.0
    vig: float = 0.0
    vig_source: str = ""
    #: Players on the board the vig was measured off. Zero when it was
    #: not measured. A short board under-states the hold, so a vig
    #: without its board size cannot be judged.
    vig_listed: int = 0
    game_date: str = ""
    game_kickoff: str = ""
    live: bool = False
    #: The player's photo URL, carried from the prop the pick was built
    #: from. Ethan, 2026-08-13: "we are not showing headshots on the
    #: longshot page either." The page was never the problem — it has
    #: always called `playerAvatar(..., {headshot: r.headshot})`. This
    #: field did not exist, so `r.headshot` was undefined on every row and
    #: every card fell through to the drawn chip. The prop object beside
    #: the candidate had the URL the whole time; nothing copied it across.
    headshot: str = ""

    def to_dict(self) -> dict:
        return {
            "player": self.player, "team": self.team, "opponent": self.opponent,
            "market": self.market, "market_label": self.market_label,
            "book": self.book, "odds": self.odds,
            "model_prob": round(self.model_prob, 4),
            "implied_prob": round(self.implied_prob, 4),
            "book_prob": round(self.book_prob, 4),
            "edge": round(self.edge, 4),
            "net_edge": round(self.net_edge, 4),
            "ev_per_unit": round(self.ev_per_unit, 4),
            "confidence": self.confidence, "stake_units": self.stake_units,
            "grade": self.grade,
            "expected_opportunities": round(self.expected_opportunities, 2),
            "primary_reason": self.primary_reason,
            "reasons": self.reasons, "caveats": self.caveats,
            "matchup": f"{self.team} vs {self.opponent}",
            "vig": round(self.vig, 4), "vig_source": self.vig_source,
            "vig_listed": self.vig_listed,
            "game_date": self.game_date, "game_kickoff": self.game_kickoff,
            "live": self.live, "headshot": self.headshot,
            "headline": f"{self.player} — {self.market_label} ({self.odds:+d})",
        }


# --- shared helpers ---------------------------------------------------------
def prob_at_least_one(rate: float) -> float:
    """P(at least one event) for a Poisson rate — the right shape for a rare
    event, and much more honest than a normal approximation near zero.

    NO OVERDISPERSION SHRINK, AND THAT IS A MEASURED DECISION. Both
    handbooks prescribe one: "shrink lambda by 0.93 for any player above
    lambda = 0.80", with college going further at 0.90 above 1.20, on the
    reasoning that scoring "produces more three- and four-touchdown games
    than a Poisson process would, which necessarily means it also
    produces more zeroes than Poisson predicts, and the anytime market
    lives on the zeroes".

    Touchdown counts are UNDER-dispersed, not over. Over every player at
    a season rate of 0.50 or better — 3,688 NFL player-games and 9,221
    college ones — the realised distribution is tighter than Poisson at
    both ends, not fatter:

                     zeroes            three or more
        NFL      48.5% vs 51.1%       2.4% vs 3.6%
        college  47.1% vs 49.0%       3.9% vs 4.7%

    Both sports carry the missing mass on EXACTLY ONE (37.0% against
    33.6%, 35.9% against 33.6%), which is what a capped, drive-limited
    event looks like. So Poisson slightly UNDER-states P(at least one) —
    realised 1.02 to 1.05 times what this returns — and the prescribed
    shrink would push an already-low number lower, costing picks in the
    exact band it was meant to protect.

    The residual under-statement is not corrected here either. It is a
    few percent, multiplicative, and `calibrated` fits a curve on this
    market against outcomes — so a raw correction would be counted twice.
    """
    return 1.0 - math.exp(-max(rate, 0.0))


def in_odds_window(odds: int, window: tuple[int, int]) -> bool:
    lo, hi = window
    return lo <= odds <= hi


#: The net edge that earns full marks for edge in `_confidence`, and the
#: three bars `_grade` applies to it.
#:
#: UNCHANGED NUMBERS, MEASURED AGAINST A DIFFERENT QUANTITY. Grading
#: moved to net edge on 2026-08-30; these bars did not move with it, and
#: that is deliberate.
#:
#: The first attempt rescaled them to 0.020 / 0.010 / 0.005, borrowing
#: `betting.BASE_THRESHOLDS`, on the reasoning that net edge is smaller
#: than edge-against-the-consensus by the whole vig. True for a college
#: touchdown market at a 31% hold. False for MLB home runs, which are
#: quoted BOTH WAYS at a hold near 8% — and the retune promoted seven of
#: twenty-four MLB rows a full tier without a single settled result
#: behind it. Calibrating on one market's vig and applying it to
#: another's is the mistake this codebase keeps catching, and that was a
#: fresh instance of it.
#:
#: Held here instead. Net edge is smaller than the old quantity by the
#: vig, so the same numbers are slightly STRICTER everywhere — the safe
#: direction — while the case that was actually broken still gets fixed:
#: a bet whose PRICE beats the consensus now grades on that price rather
#: than being discarded for the model disagreeing with the market.
#:
#: They remain uncalibrated in the sense that matters. Nothing has
#: settled enough long-shot picks to say where they belong, and moving
#: them wants results, not reasoning.
CONFIDENCE_FULL_EDGE = 0.05
GRADE_BARS = (("Strong Play", 7.5, 0.05),
              ("Play", 6.0, 0.03),
              ("Lean", 4.5, 0.015))


def _confidence(edge: float, opportunities: float, opp_target: float,
                data_quality: float = 1.0) -> float:
    """0–10 confidence. Edge drives it; opportunity volume and data quality are
    discounts, so a thin-sample or low-usage player can't grade highly on a
    lucky projection alone.

    Scaled for *tempered* edges: these markets are efficiently priced, so a
    genuine 5% edge is a strong result and earns full marks here.

    ``edge`` here is the GRADED edge — the model's advantage over the
    cheaper of the consensus and the price on offer. See `build_pick`.
    """
    edge_pts = clamp(edge / CONFIDENCE_FULL_EDGE, 0.0, 1.0) * 6.5
    opp_pts = clamp(opportunities / opp_target, 0.0, 1.0) * 2.5
    return round(clamp((edge_pts + opp_pts) * clamp(data_quality, 0.7, 1.0), 0.0, 10.0), 1)


def _grade(confidence: float, edge: float, ev: float | None = None) -> str:
    """Grade the bet ON OFFER, not the disagreement behind it.

    `edge` is measured against the DE-VIGGED price, so it is a statement
    about the model versus the book's fair number — not about the ticket.
    The two come apart by exactly the vig, and these thresholds were set
    when that gap was the assumed 6%: EV turns negative at
    ``edge = implied x (hold - 1)``, which at a 6% hold is 0.014 on a 24%
    shot — just under the 0.015 Lean bar, so the two lines effectively
    coincided and nothing showed.

    Measuring the hold off the board broke that coincidence. At a real
    30% overround the same arithmetic puts EV negative all the way out to
    edge 0.06, and a +285 shot with a 4.5% edge graded "Play" at
    confidence 8.8 while losing 4.5 cents on the dollar. The stake was
    zero — Kelly prices the offered odds and refused it — but it was
    still graded, shown, and ranked above honest picks.

    So a price that does not pay cannot carry a grade, whatever the
    model thinks of the fair number. This is not a new doctrine: the
    game-lines grader (`betting._grade`) already grades on "net edge —
    what's left after the vig, not before it", having found the same
    thing there ("every Lean was -1.2 points at the price"). This board
    was the last one still grading the disagreement instead of the bet.

    `ev` omitted keeps the old behaviour for callers that have not
    measured it.
    """
    if ev is not None and ev <= 0:
        return "Pass"
    for name, conf_min, edge_min in GRADE_BARS:
        if confidence >= conf_min and edge >= edge_min:
            return name
    return "Pass"


#: The long-shot book's own ticket size. It used to be inherited from
#: `staking.LONGSHOT_CAP_U`, which the price ladder retired on 2026-08-12
#: — and the ladder would hand a +450 home-run ticket 0.35u, six times
#: what this book has ever staked.
#:
#: That is right for the main board and wrong here, because this is a
#: MEASUREMENT book. It prices every long shot on the slate so the record
#: can say whether the signal is real, under the house rule that a new
#: source earns its stakes at a flat nominal size first. Letting the
#: general sizing rule quietly re-scale a sampler would turn a
#: measurement into an exposure nobody chose. Its own constant, stated
#: here, so raising it is a decision someone makes on purpose.
LONGSHOT_TICKET_U = 0.1


def _stake(model_prob: float, odds: int, fraction: float = 0.2) -> float:
    """A flat nominal ticket, gated by Kelly. See LONGSHOT_TICKET_U."""
    from .staking import kelly_fraction
    kelly = kelly_fraction(model_prob, odds)
    if kelly <= 0:
        return 0.0
    return LONGSHOT_TICKET_U if clamp(kelly * fraction, 0.0, 0.03) > 0 else 0.0


#: Hold assumed when only one side of a market is published.
#:
#: Direction matters and is worth stating, because it is easy to get
#: backwards: implied = raw / this, so a SMALLER assumption leaves implied
#: HIGHER, which makes `model − implied` smaller and the pick harder to
#: qualify. Assuming the book is fairer than it is costs us picks; assuming
#: it is greedier than it is invents edge. 1.06 is the cautious end.
#:
#: MEASURED AT LAST, on 2026-08-30, and the old caveat here was
#: backwards. This used to say "real hold on a longshot prop is usually
#: wider than 6%, which means this understates the book's true margin".
#: That is true of ONE book's price and false of the screen. Over 3,700
#: harvested NFL anytime-TD closes at 6.0 books per player-date,
#: `engine.devigfit` puts the overround on the LONGEST price a shopper
#: could take at about 1.05 — and finds no band charging more than the
#: rest, including the +456-to-+900 band that reads as a 34% toll when
#: measured off an arbitrarily chosen book.
#:
#: So 1.06 is very slightly GREEDIER than the market, not more generous.
#: By the direction stated above that leaves implied a shade LOW and the
#: edge a shade high — a fraction of a point at a 15% prop, which is
#: small, and is the direction worth knowing about rather than the one we
#: had written down. It stays at 1.06: a single season's harvest is not
#: enough to move a constant that prices real money, and erring toward
#: fewer picks is the error to make.
#:
#: AND IT NOW CONFLICTS WITH THE OTHER MEASUREMENT, which is worth
#: recording rather than smoothing over. `engine.devig.board_hold` reads
#: the overround straight off the board being priced and reports 22-35%
#: on anytime-touchdown menus; `pipeline` prefers it over this constant
#: whenever a game's market is thick enough. The two numbers are four to
#: five times apart and they are not the same quantity: `board_hold`
#: divides summed implied probabilities by the MODEL's expected distinct
#: scorers, while devigfit divides them by what actually happened. Only
#: one of those denominators can be wrong, and it is not the outcomes.
#:
#: Nothing is changed on the strength of that here. Over-stating the hold
#: is the SAFE error in this path — a wider hold lowers implied, which
#: `calibrated_prob` shrinks the model toward, cutting EV and publishing
#: fewer picks. The cost is silence, not loss.
#:
#: It is still an assumption on any board whose hold has not been
#: measured. Every pick priced this way carries the caveat, and nothing
#: here is staked off a one-sided quote without it being said.
#: ONE DEFINITION, LIVING IN `engine.odds`. This module and that one each
#: declared a constant of this name and they held DIFFERENT values (1.06
#: here, 1.05 there) — and the split ran the wrong way round: four
#: modules import this one and reason about "6%" in prose, while the
#: function that actually computes a fair price used the other. Re-
#: exported rather than moved so every existing importer keeps working.
from .odds import ONE_SIDED_HOLD                           # noqa: E402,F401


def one_sided_hold(sport: str, market: str) -> tuple[float, int]:
    """``(hold, settled quotes behind it)`` — the measured hold once the
    season's quote journal has settled enough of the full board
    (engine/holdwatch), the conservative assumption with n=0 until then.
    Never raises: pricing must survive a broken state file."""
    try:
        from .holdwatch import load_hold
        h = load_hold(sport, market)
        if h:
            return float(h["hold"]), int(h.get("n") or 0)
    except Exception:  # noqa: BLE001
        pass
    return ONE_SIDED_HOLD, 0


def vig_of(hold_override, sport: str, market: str,
           under_odds: int | None = None) -> tuple[float, str, int]:
    """``(overround, where it came from, players on that board)``.

    One function so the card, the watchlist and the preflight cannot
    disagree about what a pick was priced against. The board size rides
    along because a measured vig is only as trustworthy as the board it
    was measured off, and the two belong together.
    """
    from .devig import as_devig
    if under_odds:
        return 0.0, "two-way", 0
    measured = as_devig(hold_override)
    if measured:
        where = getattr(measured, "book", "") or ""
        return (measured.overround,
                f"measured:{where}" if where else "measured",
                int(getattr(measured, "listed", 0) or 0))
    hold, n = one_sided_hold(sport, market)
    return hold - 1.0, (f"journal:{n}" if n else "assumed"), 0


def _price(model_prob: float, over_odds: int, under_odds: int | None,
           sport: str = "", market: str = "", hold_override=None):
    """De-vig the book's price. With only one side quoted (common for TD/HR
    markets) we strip the one-sided hold instead — measured off the
    settled quote journal when the season has produced one, assumed
    until then — and the caller says which on the card.

    The pair is sanity-checked first. A fabricated or stale under (the
    classic: -110 recorded against a +318 over, summing to 76% — a book
    that pays out more than it takes in) makes the "de-vigged" number
    HIGHER than the raw price's implied, which then drags the market-shrunk
    model probability and EV up with it. An impossible pair is treated as
    one-sided, exactly like the scanner's arb guard treats it."""
    from .odds import pair_is_sane
    if under_odds is not None and pair_is_sane(over_odds, under_odds):
        implied, _ = devig_two_way(over_odds, under_odds)
        exact = True
    else:
        raw = american_to_prob(over_odds)
        # A hold MEASURED off this game's own board beats the standing
        # assumption — see engine.devig.board_devig. The assumption stays
        # as the fallback for a market too thin to measure.
        #
        # `hold_override` is a Devig (or a bare multiplier, coerced), not
        # a number to divide by: how a board's overround is SHARED OUT
        # across its prices is a separate question from how big it is,
        # and the two cannot be carried in one float without some caller
        # eventually applying the wrong one.
        from .devig import as_devig
        dv = as_devig(hold_override)
        implied = dv.fair(raw) if dv else raw / one_sided_hold(sport, market)[0]
        exact = False
    return implied, exact


def calibrated_prob(sport: str, market: str, model_prob: float,
                    over_odds: int, under_odds: int | None = None,
                    hold_override=None) -> tuple[float, float]:
    """``(shrunk model prob, de-vigged implied)`` — the exact tempering and
    market shrink :func:`build_pick` applies, for callers that only display.

    The watchlist once used the RAW model probability here; on a hot board
    (projected lineups, barrel-heavy profiles) raw probs inflated EV past
    the broken-price guard and silently emptied the whole list while the
    shrunk picks survived. Every displayed probability goes through this
    one path now."""
    raw = clamp(calibrated(sport, market, model_prob), 1e-4, 0.999)
    implied, _ = _price(raw, over_odds, under_odds, sport, market,
                        hold_override=hold_override)
    return clamp(implied + MARKET_SHRINK * (raw - implied), 1e-4, 0.999), implied


def build_pick(player: str, team: str, opponent: str, market: str, label: str,
               book: str, odds: int, model_prob: float, under_odds: int | None,
               opportunities: float, opp_target: float, primary_reason: str,
               reasons: list[str], caveats: list[str], sport: str,
               data_quality: float = 1.0,
               headshot: str = "",
               hold_override=None) -> LongShot | None:
    """Price a modelled probability against the book and grade it."""
    # `calibrated`, not `apply_temperature`. A market whose bake-off chose
    # the ISOTONIC form stores a curve, and `calibrated` is the only
    # function that applies it — its own docstring calls itself "THE entry
    # point" and says "a stored isotonic curve wins over the temperature,
    # because the curve only exists when it beat the temperature on a
    # held-out slice". Two callers honoured that and four did not, so
    # every board but NFL yardage and MLB props priced through the form
    # that LOST its own bake-off.
    #
    # It went live on 2026-08-28: with 2021 and 2024 play-by-play
    # backfilled, `nfl:anytime_td` re-fitted on 22,581 pairs and isotonic
    # won at 0.14210 against the temperature's 0.14226. The curve was
    # written to disk and the touchdown board went on ignoring it.
    #
    # A market with no curve takes the identical path as before — the
    # disable switch and the boundary veto live inside `calibrated` too —
    # so this is a no-op everywhere the temperature really did win.
    raw_prob = clamp(calibrated(sport, market, model_prob), 1e-4, 0.999)
    implied, exact = _price(raw_prob, odds, under_odds, sport, market,
                            hold_override=hold_override)
    if not exact:
        # Say WHY there is one side. "Only one side quoted" on its own reads
        # as a feed we failed to pull; in fact books don't offer "no home
        # run" as a bet, so the other price does not exist to be pulled.
        # The vig starts the season ASSUMED (set so the error lands
        # against the pick, not for it) and becomes MEASURED once the
        # quote journal has settled enough of the full board — the card
        # says which of the two numbers it is wearing.
        from .devig import as_devig
        hold, hn = one_sided_hold(sport, market)
        measured = as_devig(hold_override)
        if measured:
            # Measured off THIS game's own board (engine.devig.board_hold),
            # which beats both the season-wide journal and the standing
            # assumption. The card must not keep announcing a 6% vig it
            # did not price against.
            where = (f" on {measured.book}" if getattr(measured, "book", "")
                     else "")
            spread = (". Longer prices carry more of that margin than short "
                      "ones, so it is shared out accordingly rather than "
                      "split evenly" if measured.kind == "power" else "")
            caveats = caveats + [
                f"Books don't offer the NO side of this market, so the vig "
                f"can't be read off a two-way pair. It is measured off this "
                f"game's own scorer board instead: {measured.overround:.1%} "
                f"across every player priced in the game{where}, against the "
                f"touchdowns its total and spread support{spread}"]
        elif hn:
            caveats = caveats + [
                f"Books don't offer the NO side of this market, so the vig "
                f"can't be read off a two-way pair. It is measured instead: "
                f"{hold - 1:.1%}, from {hn:,} settled quotes across the whole "
                f"board this season"]
        else:
            # TWO THINGS FAILED HERE, AND THE COPY USED TO NAME ONE.
            # There are three ways to know the margin: read it off a
            # two-way pair, measure it across the game's own scorer
            # board, or fall back to a standing number. This branch is
            # the fallback, so BOTH measurements were unavailable — and
            # saying only "books don't offer the NO side" left a reader
            # thinking a two-sided quote was all that stood between them
            # and a measured number.
            #
            # The board measurement usually fails for a reason worth
            # knowing: a menu whose listed prices do not even cover the
            # scorers its game line supports has no visible margin to
            # strip, which is what an early week looks like
            # (engine.devigcheck reports it as EARLY MENU). Not asserted
            # here, because this function cannot see which of the two it
            # was — named as the usual cause, and pointed at the check
            # that can tell.
            # THE LAST SENTENCE USED TO BE WRONG TWICE OVER. It read
            # "Real hold is usually wider than the assumption, so treat
            # this edge as the optimistic end of a range", and both
            # halves failed.
            #
            # The premise is contradicted by measurement. Over 3,700
            # harvested NFL anytime-TD closes at six books per
            # player-date, `engine.devigfit` puts the toll on the LONGEST
            # price on the screen — the one `odds.best_over_line`
            # publishes — at about 5%, so 6% is a shade WIDER than the
            # market, not narrower.
            #
            # And the inference points the wrong way for the number it
            # sits under. `edge` here is MARKET_SHRINK x (raw - implied)
            # and implied is raw_price / hold, so a WIDER hold makes the
            # displayed edge BIGGER, not smaller. At +220 with this
            # model: 1.06 shows +4.9%, 1.25 shows +7.2%, 1.35 shows
            # +8.1%. Under its own premise the old sentence should have
            # called +5.0% the pessimistic end.
            #
            # (EV moves the other way — +0.101, +0.029, -0.000 across the
            # same three — because EV is the shrunk probability against
            # the offered price rather than a difference of two
            # probabilities. Two headline numbers on one card that
            # respond to this assumption in opposite directions, which is
            # most of why the old copy was easy to get backwards.)
            caveats = caveats + [
                f"The vig here is assumed at {hold - 1:.0%}, not measured. "
                f"Books quote no NO side on this market, so it can't be read "
                f"off a two-way pair — and this game's own scorer board "
                f"couldn't be measured either, which usually means the menu "
                f"is still filling in and its prices don't yet cover the "
                f"touchdowns the game line supports. Measured across 3,700 "
                f"harvested closes the market takes about 5% at the best "
                f"price on the screen, so {hold - 1:.0%} is if anything a "
                f"shade wide — which makes this edge generous by a fraction "
                f"of a point, not by a range. Where a game's own board can "
                f"be measured it reads far wider than either number, and the "
                f"two have not been reconciled"]

    # Same discipline as the yardage-prop model: shrink toward the market while
    # the model is still uncalibrated, and treat an implausibly large
    # disagreement as a data or modelling error rather than found money.
    # Touchdown and home-run markets are heavily bet and efficiently priced —
    # a genuine 15% edge in them essentially does not exist.
    model_prob = clamp(implied + MARKET_SHRINK * (raw_prob - implied), 1e-4, 0.999)
    edge = model_prob - implied
    credible = abs(raw_prob - implied) <= MAX_CREDIBLE_EDGE
    if not credible:
        caveats = caveats + [
            f"Model disagrees with the market by {abs(raw_prob - implied):.0%} — "
            f"too large to trust, treated as a pricing/data error"]

    # THE EDGE THAT PAYS is against the price in front of you, not
    # against the market's consensus, and grading the second one made us
    # decline the first genuinely good bet the board ever produced.
    #
    # Jackson Arnold, 2026-08-29: DraftKings -170, Caesars -150, Hard
    # Rock +150. Consensus fair 0.505, our blended model 0.434, the +150
    # breakeven 0.400. BOTH estimates of the truth beat the breakeven, so
    # the bet is +8.5% EV whichever you believe — and it was filtered out
    # because `edge` (model minus consensus) was -0.071. You do not need
    # a better model than the market. You need a better price than the
    # truth, and that is a different comparison.
    #
    # `betting._grade` has graded game lines on "net edge — what's left
    # after the vig, not before it" since the same thing was found there.
    # The EV gate below adopted half of that doctrine on 2026-08-29; this
    # is the other half.
    #
    # `edge` stays published as the honest model-versus-market
    # disclosure. It is no longer what decides a bet.
    net_edge = model_prob - american_to_prob(odds)
    # GRADED AGAINST THE CHEAPER REFERENCE OF THE TWO, which is the only
    # formulation that fixes the broken case without moving anything
    # else. `edge` is the model over the consensus; `net_edge` is the
    # model over the price on offer.
    #
    #   Normal book, charging vig: the price sits ABOVE the consensus, so
    #   edge is the larger and grading is exactly what it always was.
    #   Nothing about MLB home runs or any two-way market moves.
    #
    #   Outlier book, price better than the consensus: net_edge is the
    #   larger, and the bet is graded on the price — which is the whole
    #   Jackson Arnold case.
    #
    # Rescaling the bars was the other candidate and it was wrong: net
    # edge is smaller than edge by the vig, so ONE constant cannot serve
    # an 8% two-way market and a 31% one-sided one. Bars tuned to
    # college's hold promoted seven of twenty-four MLB rows a full tier;
    # the old bars applied to net edge lost real NFL and college picks.
    # The quantity was the problem, not the threshold.
    #
    # `ev` below still gates: beating the consensus while losing to the
    # price is not a bet, and that is what stops this being merely the
    # more generous of two numbers.
    graded_edge = max(edge, net_edge)
    confidence = _confidence(graded_edge, opportunities, opp_target,
                             data_quality)
    vig, vig_source, vig_listed = vig_of(hold_override, sport, market,
                                         under_odds if exact else None)
    book_prob = american_to_prob(odds)
    # Imported here rather than borrowed from the one-sided branch above,
    # which only runs when `exact` is False.
    from .devig import as_devig as _as_devig
    backing = int(getattr(_as_devig(hold_override), "books", 0) or 0)
    if backing == 1:
        # ONE BOOK IS NOT A CONSENSUS. The 2026-08-29 college board
        # de-vigged a single book's card and published it as the market's
        # fair price; that book turned out to be the furthest from
        # consensus on 10 of 16 scorers where books disagreed at all.
        caveats = caveats + [
            "Only one book's board could be measured for this game, so "
            "the fair price is that book's opinion rather than the "
            "market's — a stale number has nothing to be checked against"]
    # A price LONGER than the consensus says it should be is a find, and
    # it is the reason to shop at all. Say it, with both numbers, rather
    # than leaving a reader to notice that two probabilities on the card
    # disagree and assume one of them is broken.
    if not exact and implied - book_prob >= 0.02 and backing > 1:
        reasons = reasons + [
            f"{book} is longer than the market: {book_prob:.0%} at this "
            f"price against a {implied:.0%} median across {backing} book(s) "
            f"— {implied - book_prob:.0%} of that edge is the price, not "
            f"the projection"]
    ev = expected_value(model_prob, odds)
    grade = _grade(confidence, graded_edge, ev) if credible else "Pass"
    return LongShot(
        player=player, team=team, opponent=opponent, market=market,
        market_label=label, book=book, odds=odds,
        model_prob=model_prob, implied_prob=implied,
        book_prob=round(book_prob, 4), edge=edge,
        net_edge=round(net_edge, 4),
        ev_per_unit=ev, vig=round(vig, 4), vig_source=vig_source,
        vig_listed=vig_listed,
        confidence=confidence, stake_units=_stake(model_prob, odds) if grade != "Pass" else 0.0,
        grade=grade, expected_opportunities=opportunities,
        primary_reason=primary_reason, reasons=reasons, caveats=caveats,
        headshot=headshot,
    )


def select(picks: list[LongShot], per_key_cap: int, key, limit: int,
           require_edge: bool = True) -> list[LongShot]:
    """Rank by graded edge and apply the spec's concentration limits.

    Sorting by edge (not by odds) is deliberate: the biggest payout is almost
    never the best bet, and ranking by price is how long-shot cards go broke.
    The same quantity the grade uses — the model's advantage over the
    cheaper of the consensus and the price — so the ranking and the grade
    cannot disagree about which pick is better.
    """
    ranked = sorted(picks, key=lambda p: (max(p.edge, p.net_edge),
                                          p.confidence), reverse=True)
    out: list[LongShot] = []
    seen: dict = {}
    for p in ranked:
        # ON THE PRICE, NOT ON THE DISAGREEMENT. Filtering `edge <= 0`
        # threw out every bet where the price beat the market consensus
        # but our model sat below it — which is the most ordinary shape a
        # real edge takes, and cost the board a +8.5% EV pick on
        # 2026-08-29. See `build_pick` for the case.
        if require_edge and (p.ev_per_unit <= 0 or p.grade == "Pass"):
            continue
        k = key(p)
        if seen.get(k, 0) >= per_key_cap:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(p)
        if len(out) >= limit:
            break
    return out
