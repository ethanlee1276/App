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


def rankable(market: str) -> bool:
    """Has this market been SHOWN to rank, not merely modelled?"""
    return RANK_AUC.get(market, 0.0) >= MIN_RANK_AUC


def _sane(odds) -> bool:
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return False
    return SANE_ODDS[0] <= o <= SANE_ODDS[1]


def from_prop(row: dict, bettable) -> dict | None:
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
    fitted = display_prob(market, row.get("projection"), row.get("line"),
                          row.get("recent_values"))
    if fitted is not None:
        shown, source = float(fitted), "mixture"
    if shown < MIN_PROB:
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
          limit: int = LIMIT) -> list:
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
        seen.add(key)
        out.append(got)
    for row in props or []:
        got = from_prop(row, bettable)
        if got is None:
            continue
        key = (got["player"], got["team"], got["market"])
        if key in seen:
            continue
        seen.add(key)
        out.append(got)
    out.sort(key=lambda r: -float(r["model_prob"] or 0.0))
    return out[:limit]


def summary(board: list) -> dict:
    """What the page says about itself, counted rather than asserted."""
    by_market: dict = {}
    for r in board:
        by_market[r["market"]] = by_market.get(r["market"], 0) + 1
    return {
        "rows": len(board),
        "by_market": by_market,
        "bettable": sum(1 for r in board if r.get("bettable")),
        "rank_only": sum(1 for r in board if not r.get("bettable")),
    }
