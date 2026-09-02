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

#: The heaviest price the board will show. Ethan, 2026-09-01, reading
#: the likely book's first settled night (52/73 won, ROI -11.2%, rows
#: at -800/-1200/-1800): "i dont wanna be betting on -1200 or -1800
#: bets. the point of the most likley page is to push bets based of
#: game data, game script, weather, offense, defense... not just
#: grabbing random -1200 props. and thats for every sport." The model
#: WAS using all of that — the probabilities were calibrated (claimed
#: 75%, landed 71%) — but the gate never asked whether a row was a bet
#: a human would want, and baseball's most-likely outcomes are mostly
#: heavy-juice failures to do things. At -250 a bet needs 71.4% to
#: break even; past it, "most likely" stops being a pick and becomes
#: chalk.
HEAVIEST_PRICE = -250

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


#: The college touchdown ranking, measured by engine.cfbtdfit over
#: 29,047 player-weeks. Shipped like the NFL constants because it was
#: measured the same way — by a person, against this repo's own replay —
#: and previously the CFB board wore the NFL's 0.721 by accident:
#: `from_watch` read RANK_AUC["anytime_td"] with no idea whose chain
#: built the row.
CFB_TD_AUC = 0.675


def rank_auc(sport: str, market: str):
    """The measured ranking AUC for this market, or None.

    THREE SOURCES, IN TRUST ORDER. The fitted store first — written by
    engine.rankfit on the box whose logs it walked, which is the only
    number that can exist for MLB at all (its logs never leave the
    droplet). Then the shipped constants: NFL's hand-measured five and
    the college touchdown figure. A market in none of them has no
    measurement, and no measurement means no shelf — the founding rule
    of this board, now enforced per sport instead of assuming every
    caller was the NFL.
    """
    from .rankfit import rank_auc as _fitted
    got = _fitted(sport, market)
    if got is not None:
        return got
    if sport == "nfl":
        return RANK_AUC.get(market)
    if sport == "cfb" and market == "anytime_td":
        return CFB_TD_AUC
    return None


def rankable(market: str, sport: str = "nfl") -> bool:
    """Has this market been SHOWN to rank, not merely modelled?"""
    return (rank_auc(sport, market) or 0.0) >= MIN_RANK_AUC


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


def admissible(row: dict) -> str:
    """"" if this row belongs on the board, else why it does not.

    ONE BAR, APPLIED TO EVERY ROW, WHATEVER BUILT IT. `build` takes rows
    from two makers — `from_prop` for the priced prop board and
    `from_watch` for the touchdown chain — and only the first one
    enforced anything. `build`'s own comment claimed "one board means one
    bar" while applying that bar on one of its two paths, which is this
    codebase's most-repeated bug: a rule announced in prose and enforced
    in one place.

    IT MATTERED MOST WHERE IT WAS CHECKED LEAST. College football's
    entire likelihood board is watch rows — `cfb_build` calls
    `build([], rows, watch)` with no props at all — so every refusal
    added to this module protected the NFL prop board and left the whole
    college board ungated. Measured 2026-08-30, all of these published:
    an 8% row on a board whose floor is 30%, a -97 price no book can
    post, and a `proxy` quote the model invented.

    THE FLOOR IS ABOUT THE WORD, NOT THE SPORT. MIN_PROB says a
    probability below it "is not likely by any reading" — that is a claim
    about what the page is called, so a college board that empties under
    it is a board honestly reporting it has nothing likely tonight,
    rather than one relabelling 8% as likely.
    """
    prob = row.get("model_prob")
    if prob is None:
        return "no probability"
    if float(prob) < MIN_PROB:
        return "under the likelihood floor"
    if (row.get("book") or "").lower() == "proxy":
        # A fabricated price. `from_prop` catches this as `has_market`;
        # watch rows carry no such key and the book name is the tell.
        return "no real market price"
    if not _sane(row.get("odds")):
        return "price a book could not have posted"
    # The two product refusals (Ethan, 2026-09-01 — see HEAVIEST_PRICE):
    # the board shows who's most likely to DO something, priced like a
    # bet. An UNDER is a wager on failure — the most likely outcome of
    # most baseball nights, and not what anyone opens a picks page for.
    if (row.get("side") or "").lower() == "under":
        return "a bet on something not happening"
    if int(row["odds"]) < HEAVIEST_PRICE:
        return f"heavier than {HEAVIEST_PRICE} — chalk, not a pick"
    if not _credible(prob, row.get("implied_prob")):
        return "disagrees with the market by more than we credit"
    # THE INJURY HOLD, WHICH THIS BOARD NEVER HAD. `rules.apply_rules`
    # holds a Questionable / Doubtful / Out player "until inactives
    # confirm status" — and only the edge board read that decision. This
    # page took the same evaluated row, ignored `recommended`, and had
    # no field carrying the designation at all, so a player ruled out
    # on Friday could top "who is most likely to hit" on Sunday. Ethan,
    # 2026-09-02: "some of them seem weird ... especially the most likely
    # bets." A hold that applies to one board and not the other is not a
    # hold; it is the announced-in-prose, enforced-in-one-place bug this
    # module's own docstring names.
    status = str(row.get("injury_status") or "").strip()
    if status:
        return f"listed {status} — held until inactives confirm"
    return ""


def from_prop(row: dict, bettable, fits=None,
              sport: str = "nfl") -> dict | None:
    """One likelihood row from a published prop row, or None.

    `row` is what `pipeline._rec_to_dict` already produces for EVERY
    prop, recommended or not — the likelihood board is a different cut of
    the same evaluation, not a second model. Building it any other way
    would let the two pages disagree about the same player.
    """
    market = row.get("market") or ""
    if not rankable(market, sport):
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
        "rank_auc": rank_auc(sport, market),
        "reasons": row.get("reasons") or [],
        "game_script": row.get("game_script"),
        "recent_values": row.get("recent_values") or [],
        "game_date": row.get("date", ""), "kickoff": row.get("kickoff", ""),
        "headshot": row.get("headshot", ""),
        "position": row.get("position", ""),
        "usage_role": row.get("usage_role", ""),
        # Carried so `admissible` can refuse on it and a lint can see it.
        "injury_status": row.get("injury_status", "") or "",
        "warnings": list(row.get("warnings") or []),
    }


def from_watch(row: dict, sport: str = "nfl") -> dict:
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
        "rank_auc": rank_auc(sport, "anytime_td"),
        "reasons": row.get("reasons") or [],
        "game_script": row.get("game_script"),
        "recent_values": row.get("recent_values") or [],
        "game_date": row.get("game_date", ""),
        "kickoff": row.get("kickoff", ""),
        "headshot": row.get("headshot", ""),
        "position": row.get("position", ""),
        "injury_status": row.get("injury_status", "") or "",
        "warnings": list(row.get("caveats") or []),
    }


def build(props: list, td_picks=None, td_watch=None, sport: str = "nfl",
          limit: int = LIMIT, fits=None, census: dict | None = None) -> list:
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
    refused: dict = {}

    def keep(got) -> bool:
        """The one gate. Every row passes through here or does not ship."""
        why = admissible(got)
        if why:
            refused[why] = refused.get(why, 0) + 1
            return False
        return True

    for row in (td_picks or []) + (td_watch or []):
        got = from_watch(row, sport=sport)
        key = (got["player"], got["team"], "anytime_td")
        if key in seen or not keep(got):
            continue
        seen.add(key)
        out.append(got)
    for row in props or []:
        got = from_prop(row, bettable, fits=fits, sport=sport)
        # `from_prop` already refuses on the same grounds and returns
        # None; it stays as a cheap pre-filter because the mixture work
        # below it is not cheap. `keep` is what actually decides.
        if got is None:
            continue
        key = (got["player"], got["team"], got["market"])
        if key in seen or not keep(got):
            continue
        seen.add(key)
        out.append(got)
    out.sort(key=lambda r: -float(r["model_prob"] or 0.0))
    # WHY THE BOARD IS THE SIZE IT IS, handed back to a caller that asked
    # for it. An empty college Saturday has several causes and a census
    # that only reaches stdout is one nobody has the morning they need
    # it. Filled in place rather than returned, so no existing caller
    # has to change and no row carries metadata that would follow it
    # into the journal.
    if census is not None:
        census.update(refused)
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
