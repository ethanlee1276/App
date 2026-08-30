"""The board that answers "who will actually hit", not "where is the edge".

Ethan, 2026-08-30: "we need to focus more on using the data to figure out
who will score each game, not who has the best edge... a page for EDGE
picks that give the best EDGE, then a separate page which will be the
main page for bets, that will show who we genuinely think will score or
hit the over."

THE MEASUREMENTS SAY HE IS RIGHT, AND THEY SAY IT LOUDLY. The model ranks
outcomes well and prices them badly, and those are separate abilities:

    what it is asked          how well it does it
    who scores a touchdown    AUC 0.721 (22,099 graded NFL player-weeks)
    who clears their line     AUC 0.76 rushing, 0.77 receptions,
                              0.73 receiving, 0.69 passing
    where the market is wrong AUC 0.468 — noise (the site's settle pass)

So the edge board is built on the model's weakest ability and the
likelihood board on its strongest, and until now only the weak one had a
page.

WHY A SHUT MARKET STILL BELONGS HERE, which looks wrong and is not.
`calibrate.is_reliable` closes rush_yds and rec_yds for BETTING because
their probability is wrong in ABSOLUTE terms — it cannot be compared to a
price. Ranking needs it right only in RELATIVE terms, and those are
different tests: rushing yards rank at 0.7605 while being unbettable.
Ordering barely moves when the calibration is stripped out entirely
(0.7605 against 0.7627 for the raw projection), because a monotone error
does not reorder a list.

A market therefore appears on this board when it can RANK, and carries an
honest flag saying whether it can also be BET. Nothing here is a
recommendation to stake; that is what the edge board is for.

WHAT THESE NUMBERS ARE NOT. The yardage figures are scored at synthetic
lines on a grid. A real book hangs its line at its own number, which
already contains most of the signal, so the achievable AUC against a live
board is lower — probably by a lot. Nothing on the page may quote these
as though they were the live figure until `engine.yardagefit --real` has
measured the same thing at real closes.

Standard library only.
"""

from __future__ import annotations

from .yardagefit import display_prob

#: Markets this board will rank, and whether the model has been shown to
#: rank them. Measured 2026-08-30 at synthetic lines over 2021-25 NFL
#: logs; `anytime_td` comes from `engine.tdbacktest` against outcomes.
#:
#: A market with no measurement does not appear. That is the whole
#: discipline: "we think he will hit" is a claim, and an unmeasured claim
#: on the main board is exactly what this product is trying to stop
#: being.
RANK_AUC = {
    "anytime_td": 0.721,
    "receptions": 0.770,
    "rush_yds": 0.761,
    "rec_yds": 0.733,
    "pass_yds": 0.691,
}

#: SHOULD THIS BOARD GET REAL MONEY? Ethan, 2026-08-30: "we need to
#: figure out if we are gonna put real money on these bets and record
#: them and if so we need them to be in the recommended bets."
#:
#: Measured rather than argued. Both orderings bet the TOP QUARTER of the
#: same qualifying pool — same rows available, same stakes, same prices,
#: same vig — so the only difference is which of them get the money:
#:
#:     market      picked by     bets   hit      ROI    95% interval
#:     receptions  likelihood      76  65.8%   +11.7%   [-8.7%, +32.1%]
#:     receptions  edge            76  53.9%    +2.4%   [-19.0%, +23.8%]
#:     rec_yds     likelihood      86  54.7%    +3.2%   [-16.9%, +23.3%]
#:     rec_yds     edge            86  54.7%    +3.9%   [-16.2%, +24.0%]
#:
#: The receptions result is the best evidence this thesis has, and it is
#: not proof: the hit-rate gap is +11.9 points at z = +1.5, and every ROI
#: above carries about ten points of standard error on 76-86 bets. One
#: market suggests likelihood-ranking is better, one shows no difference
#: at all, and both sit on fourteen weeks of a single season.
#:
#: SO THIS BOARD IS NOT JOURNALED, and the reason is specific rather than
#: cautious. Ranking says who hits; it does not say whether the price is
#: worth taking. A -260 near-lock can be correctly ranked first and still
#: lose money, because being right 70% of the time at a price that needs
#: 72% is a losing bet made confidently. This board deliberately ignores
#: EV when ordering, so wiring it to the journal as it stands would stake
#: negative-EV locks with conviction.
#:
#: What would settle it: the same table on two or three more seasons of
#: closes, and on more than one market. `engine.yardagefit --real` prints
#: it, and the harvest is the binding constraint, not the code.

#: Below this a market cannot sort its own board and has no business
#: claiming who will hit. 0.5 is a coin flip; this is the floor at which
#: an ordering is worth showing a reader.
MIN_RANK_AUC = 0.60

#: A price outside this is a stale quote or a market we have mis-keyed,
#: not a likelihood — the same guard the touchdown watch uses.
SANE_ODDS = (-100000, 2000)

#: How many rows the board carries per sport before it stops being a
#: ranking and starts being a dump.
LIMIT = 40

#: A model probability below this is not "likely" by any reading, whatever
#: it is ranked against.
MIN_PROB = 0.30

#: How far the displayed probability may sit from the book's own de-vigged
#: number before the row is refused — the same bar `engine.betting` uses,
#: for the same reason.
from .betting import MAX_CREDIBLE_EDGE                     # noqa: E402


def _credible(prob, fair) -> bool:
    """Is this probability defensible against the book's own number?"""
    if fair is None or prob is None:
        return True
    try:
        return abs(float(prob) - float(fair)) <= MAX_CREDIBLE_EDGE
    except (TypeError, ValueError):
        return True


def rankable(market: str) -> bool:
    """Has this market been SHOWN to rank, not merely modelled?"""
    return RANK_AUC.get(market, 0.0) >= MIN_RANK_AUC


def _sane(odds) -> bool:
    """In range for this board AND a price a book could have posted.

    SANE_ODDS bounds the outside; it says nothing about the dead zone in
    the middle, so -97 used to pass — and then win the shop, because it
    pays better than the -105 it was corrupting. See odds.is_quotable.
    """
    from .odds import is_quotable
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return False
    return SANE_ODDS[0] <= o <= SANE_ODDS[1] and is_quotable(o)


def from_prop(row: dict, bettable, fits=None) -> dict | None:
    """One likelihood row from a published prop row, or None.

    `row` is what `pipeline._rec_to_dict` already produces for EVERY
    prop, recommended or not — the likelihood board is a different cut of
    the same evaluation, not a second model. Building it any other way
    would let the two pages disagree about the same player.
    """
    market = row.get("market") or ""
    if not rankable(market):
        return None
    prob = row.get("hit_prob")
    if prob is None or float(prob) < MIN_PROB:
        return None
    if not row.get("has_market") or not _sane(row.get("odds")):
        return None
    # CALIBRATED FOR DISPLAY, and this is the fix for a real defect.
    # `calibrate.correction_for` DISCARDS a boundary fit rather than
    # applying it — right for betting, since a capped temperature is the
    # search failing — so rush_yds and rec_yds, the two markets whose fits
    # ran to the cap, reached this page with NO correction at all. The
    # likelihood board was quoting the raw number from the two markets
    # measured most overconfident.
    #
    # `yardagefit`'s mixture halves the miss between what is claimed and
    # what lands (rec_yds 0.1137 -> 0.0709, receptions 0.0610 -> 0.0285).
    # It was declined for BETTING because it makes no money the normal was
    # not already making; this page's objective is calibration, not ROI,
    # and there it is measurably the better number.
    shown = float(prob)
    source = "model"
    # `fits` is INJECTABLE for the same reason `nflready`'s shrink lookup
    # is: the suite points QB_MODELS_DIR at an empty sandbox, so a test
    # reading the ambient store asserts about whether THIS box has been
    # fitted rather than about the code.
    fitted = display_prob(market, row.get("projection"), row.get("line"),
                          row.get("recent_values"), fits=fits)
    if fitted is not None:
        shown, source = float(fitted), "mixture"
    if shown < MIN_PROB:
        return None
    # CREDIBILITY, AND THIS BOARD HAD NONE. Every other pick path refuses
    # a probability that disagrees with the market past
    # MAX_CREDIBLE_EDGE — `betting.evaluate_prop`, `longshots`,
    # `gamebets.temper` all carry it — because a 20-point disagreement in
    # a heavily bet market is our error far more often than a discovery.
    # This page does not grade or stake, so nothing ever forced the
    # question; it still makes the claim, and the claim is the product.
    #
    # CHECKED AFTER THE MIXTURE, not before. The mixture recomputes from
    # the projection and therefore discards the market shrink `hit_prob`
    # already carried, so the rows most able to run away from the book
    # are exactly the ones this page calibrated. Checking the input would
    # pass precisely what this exists to catch.
    #
    # REFUSED, NOT SHRUNK: a likelihood board that quietly moves its
    # number toward the market has stopped saying what it believes.
    if not _credible(shown, row.get("fair_prob")):
        return None
    return {
        "player": row.get("player", ""), "team": row.get("team", ""),
        "opponent": row.get("opponent", ""),
        "market": market, "market_label": row.get("market_label", market),
        "side": row.get("side", ""), "line": row.get("line"),
        "book": row.get("book", ""), "odds": row.get("odds"),
        "model_prob": round(shown, 4),
        # WHICH NUMBER THE READER IS LOOKING AT. A page that silently
        # swapped its probability source would be the opposite of the
        # point.
        "prob_source": source,
        "raw_prob": round(float(prob), 4),
        "implied_prob": row.get("fair_prob"),
        "projection": row.get("projection"),
        "ev_per_unit": row.get("ev_per_unit"),
        # THE FLAG THAT KEEPS THIS HONEST. A market can rank without
        # being bettable, and a reader deserves to know which they are
        # looking at rather than inferring it from the absence of a
        # stake.
        "bettable": bool(bettable(market)),
        "rank_auc": RANK_AUC.get(market),
        "reasons": row.get("reasons") or [],
        "recent_values": row.get("recent_values") or [],
        "game_date": row.get("date", ""), "kickoff": row.get("kickoff", ""),
        "headshot": row.get("headshot", ""),
        "position": row.get("position", ""),
    }


def from_watch(row: dict) -> dict:
    """A touchdown watch row, in the same shape.

    The most-likely-scorers list was already this board for one market;
    it keeps its own builder because it prices through the long-shot
    chain, and is merged here rather than rebuilt.
    """
    return {
        "player": row.get("player", ""), "team": row.get("team", ""),
        "opponent": row.get("opponent", ""),
        "market": "anytime_td", "market_label": "Anytime TD",
        "side": "yes", "line": None,
        "book": row.get("book", ""), "odds": row.get("odds"),
        "model_prob": row.get("model_prob"),
        "implied_prob": row.get("implied_prob"),
        "projection": None,
        "ev_per_unit": row.get("ev_per_unit"),
        "bettable": True,
        "rank_auc": RANK_AUC["anytime_td"],
        "reasons": row.get("reasons") or [],
        "recent_values": row.get("recent_values") or [],
        "game_date": row.get("game_date", ""),
        "kickoff": row.get("kickoff", ""),
        "headshot": row.get("headshot", ""),
        "position": row.get("position", ""),
    }


def build(props: list, td_picks=None, td_watch=None, sport: str = "nfl",
          limit: int = LIMIT, fits=None) -> list:
    """The likelihood board: every rankable market, ordered by probability.

    ORDERED BY PROBABILITY AND NOTHING ELSE. Sorting by EV, or breaking
    ties on it, would quietly rebuild the edge board under a different
    name — which is the exact failure this page exists to correct.
    """
    from .calibrate import is_reliable

    def bettable(market):
        return is_reliable(sport, market)

    out = []
    seen = set()
    for row in (td_picks or []) + (td_watch or []):
        got = from_watch(row)
        key = (got["player"], got["team"], "anytime_td")
        if got["model_prob"] is None or key in seen:
            continue
        # Watch rows arrive pre-shrunk toward the market, so this almost
        # never fires for them. Applied anyway: "almost never" is not a
        # guarantee, and one board means one bar.
        if not _credible(got["model_prob"], got.get("implied_prob")):
            continue
        seen.add(key)
        out.append(got)
    for row in props or []:
        got = from_prop(row, bettable, fits=fits)
        if got is None:
            continue
        key = (got["player"], got["team"], got["market"])
        if key in seen:
            continue
        seen.add(key)
        out.append(got)
    out.sort(key=lambda r: -float(r["model_prob"] or 0.0))
    return out[:limit]


def summary(board: list, refused: int = 0) -> dict:
    """What the page says about itself, counted rather than asserted.

    `refused` carries the rows the credibility bar dropped, so a board
    that came out short can say WHY rather than looking like a quiet
    slate — the same census discipline the pick funnel uses.
    """
    by_market: dict = {}
    for r in board:
        by_market[r["market"]] = by_market.get(r["market"], 0) + 1
    return {
        "rows": len(board),
        "by_market": by_market,
        "bettable": sum(1 for r in board if r.get("bettable")),
        "rank_only": sum(1 for r in board if not r.get("bettable")),
        "refused_incredible": refused,
    }
