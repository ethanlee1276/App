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

GAME LINES, MEASURED THE SAME WAY. Ethan, 2026-09-02: "all I see us is
doing overs, but we have no unders, and we also have no money lines or
spreads or totals ... there is more bets that we can salvage." Measured
by `engine.gamerank` — the ratings-only replay `engine.gamebacktest`
runs over the stored closes, keeping for EVERY quoted game the
probability the pricer put on its side and whether that side won:

    who wins the game (moneyline)   AUC 0.677 NFL (1,356 games)
                                    AUC 0.752 CFB (2,729 games)
    …and the market's own number    AUC 0.722 NFL · 0.791 CFB — better
                                    in both, so game rows rank on it
                                    (GAME_RANK_MARKET, 2026-09-07), and
                                    the model's disagreement with it
                                    does not bar a row (engine_credible,
                                    measured 2026-09-08)
    who covers the spread           0.491 NFL · 0.496 CFB — a coin flip
    over or under the total         0.497 NFL · 0.503 CFB — a coin flip
    a team over its own number      0.513 NFL · 0.492 CFB — a coin flip

(The college walk rebuilds the production opponent-adjusted ratings
before every date — `gamerank.measure_cfb`; the plain-ratings floor
had said 0.708 for the moneyline and the same coin flips elsewhere.)

The model can say who WINS and cannot say who COVERS. That is not a
surprise — the close already holds the ratings, and the market's own
de-vigged moneyline ranks the winner at 0.714 — and it is what decides
the board: moneylines are ranked here, spreads and totals are not, and
they stay off until a measurement says otherwise. The MLB figures can
only be measured where the MLB history is (`gamerank --save` on the
droplet writes them into the store `rank_auc` reads first).

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

#: The game markets a card can carry (`gamebets._game_bet` bet_type).
GAME_MARKETS = ("moneyline", "spread", "total", "team_total")

#: Game markets shown to rank, per sport — measured 2026-09-02 by
#: `engine.gamerank` (see the header). ONLY the markets that cleared
#: MIN_RANK_AUC are listed, because an entry here is what puts a market
#: on the board; the ones that tested as a coin flip are written out in
#: the header so nobody re-measures them by accident and nobody quietly
#: adds them. A sport with no entry ranks no game market until the
#: store on its own box says so.
GAME_RANK_AUC = {
    "nfl": {"moneyline": 0.677},
    "cfb": {"moneyline": 0.752},
}

#: EVERY game-market figure that was measured, floor or not — the same
#: run, the whole table. Ethan, 2026-09-02, after the first cut shipped
#: moneylines alone: "I only see money lines in the best bets. I don't
#: see team totals over or unders ... I don't see spread bets, I don't
#: see anything like that I just asked you to do." His call: the
#: spreads, totals and team totals go on the board. The measurement's
#: job is then to be PRINTED on each of them — a row from a market that
#: sorts games at 0.49 says so on its face, carries `ranked` False, and
#: is shown as the model's lean at that number rather than as a claim to
#: rank. A market with NO figure at all (MLB, until `gamerank --save`
#: runs on the droplet) still has nothing to say and stays off.
GAME_RANK_MEASURED = {
    "nfl": {"moneyline": 0.677, "spread": 0.504, "total": 0.496, "team_total": 0.500},
    "cfb": {"moneyline": 0.752, "spread": 0.496, "total": 0.503, "team_total": 0.492},
}

#: THE MARKET'S OWN RANKING, and why the board ranks on it where it can.
#: Ethan, 2026-09-07: "you worked on the NFL and CFB Most Likely model
#: and made it better." The one thing measured to rank winners better
#: than the model is the closing market itself. Measured 2026-09-07 on
#: this box's stored closes — the schedule's de-vigged moneyline against
#: the result, every scored game with a price, ties out:
#:
#:     nfl  market 0.722 on 1,420 games (2021-26)   model 0.677
#:     cfb  market 0.791 on 3,011 games (2022-26)   model 0.752
#:
#: So a game row on the NFL or college board ranks on the book's
#: de-vigged number for its side — `fair_prob` on the card — rather
#: than on the model's, whenever the market's measured figure beats the
#: model's (`ranking_number`). The model's number stays on the row and
#: on the card; only the ORDER changes, and the row says which number
#: ordered it (`prob_source`). A sharp-anchored card ranks on its own
#: `win_prob`, which IS a market number — the sharp book's fair. Spreads,
#: totals and team totals have no market figure here and rank (or are
#: shown as leans) exactly as before. A market with no entry ranks on
#: the model, so nothing changes for a sport that has not been measured.
GAME_RANK_MARKET = {
    "nfl": {"moneyline": 0.722},
    "cfb": {"moneyline": 0.7905},
}


def ranking_number(sport: str, market: str, row: dict, model_auc):
    """``(probability, source, auc)`` a game row ranks on.

    ``source`` is "sharp" (the card's own probability is the sharp
    book's fair), "market" (the book's de-vigged number, because it
    measures better than the model here), or "model".
    """
    prob = row.get("win_prob")
    fair = row.get("fair_prob")
    market_auc = GAME_RANK_MARKET.get(sport, {}).get(market)
    if row.get("sharp_anchored") and prob is not None and market_auc is not None:
        return float(prob), "sharp", float(market_auc)
    if (market_auc is not None and fair is not None
            and (model_auc is None or float(market_auc) > float(model_auc))):
        return float(fair), "market", float(market_auc)
    return (None if prob is None else float(prob)), "model", model_auc


#: EVERY MARKET KEEPS ITS BEST ROWS. Ethan, 2026-09-07: "for some reason
#: its only displaying tight ends for reciving props and thats it. that
#: seems strang and wrong." The board kept the forty highest
#: probabilities across every player market in one list, and the
#: highest probabilities belong to the lowest lines — a tight end or a
#: back over 2.5 receptions at 68% — so the forty filled with those and
#: a receiver's 58% over on 64.5 yards, ranked just as honestly, never
#: reached the receiving shelf. A shelf that shows one position is a
#: shelf that shows one kind of line.
#:
#: So the cut is in two passes: first up to PER_MARKET rows from each
#: player market in probability order, then the remaining seats filled
#: from whatever is left, by probability. The floor, the price cap and
#: the credibility bar are untouched — a market whose every row sits
#: under 55% still shows nothing, and the census says so.
PER_MARKET = 8


def _cut_players(rows: list, limit: int, per_market: int = PER_MARKET) -> list:
    """The player rows the board keeps: each market's best `per_market`
    first, then the best of the rest, `limit` in all, probability order."""
    rows = sorted(rows, key=lambda r: -float(r.get("model_prob") or 0.0))
    kept, taken = [], {}
    for r in rows:
        m = r.get("market") or ""
        if taken.get(m, 0) < per_market:
            taken[m] = taken.get(m, 0) + 1
            kept.append(r)
    if len(kept) > limit:
        kept = kept[:limit]
    if len(kept) < limit:
        chosen = {id(r) for r in kept}
        kept += [r for r in rows if id(r) not in chosen][:limit - len(kept)]
    return sorted(kept, key=lambda r: -float(r.get("model_prob") or 0.0))


#: Game rows the board carries per sport, beside LIMIT player rows.
#: Five cards a game across a sixteen-game Sunday is eighty rows of
#: 50-60% leans, which would push every player row off a board capped
#: at forty; the two kinds are capped apart so neither crowds the other.
GAME_LIMIT = 20

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

#: How far a game's MONEYLINE and its own SPREAD may disagree about who
#: wins before the pair is not a price any book has posted.
#:
#: Ethan, 2026-09-08, with two screenshots side by side — his book and
#: our page: "Also the money lines we are showing on the most likley
#: page is completely wrong." His book had DAL -3 and DAL -162 at the
#: Giants; our board had NYG ML -218 as a 66% favourite. The two numbers
#: on OUR OWN card disagreed about which team was going to win, and
#: nothing looked at them together. It is the third report of this class
#: (2026-09-03, twice: "The lines on the most likely best bet page ...
#: are completely wrong so we are giving bad bets" and "A lot of the
#: money lines and shit are wrong"), and the first two were answered
#: with freshness stamps — which say a price is OLD and cannot say a
#: price is WRONG.
#:
#: MEASURED, on this box's 1,424 stored NFL closes with both a closing
#: moneyline and a spread (2026-09-08). For each, the book's de-vigged
#: P(home) against the same book's spread read through the sport's own
#: win curve (`gamebets.spread_win_prob`):
#:
#:     median gap  0.036      99th  0.102      99.9th  0.113
#:     the largest disagreement in five seasons          0.118
#:     games where the two named a different favourite   0 of 1,424
#:
#: A real book keeps its two markets within about a tenth of each other
#: and never crosses over. So 0.15 is above every disagreement five
#: seasons of closes contain, and a pair past it is not a price — it is
#: two snapshots of different games, or one market read against the
#: wrong side. Ethan's Giants card scores 0.199 and is refused; his
#: Vikings card scores 0.083 and is NOT — that one is a price that is
#: merely old, which this bar cannot see and does not pretend to.
SPREAD_COHERENCE = 0.15

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
#:
#: RAISED FROM 0.30 ON 2026-09-06, Ethan's call, after the paper book's
#: first honest scoreboard. 402 settled rows, and the 45-60% band was
#: 184 of them at -7.68%:
#:
#:     band        n    said     hit      roi
#:     45%-60%    184   53.3%   49.5%   -7.68%
#:     60%-75%    154   66.1%   71.4%   +3.91%
#:     75%-101%    64   84.8%   76.6%   -6.00%
#:
#: THE ARITHMETIC THAT DOES NOT DEPEND ON THE SAMPLE. A 53.3% pick at
#: -110 needs 52.4% to break even. The margin is nine tenths of a point,
#: which is inside every error bar this model has — `selectionfit`
#: measures a 9-10 point over-claim on the bets we choose. A band that
#: thin cannot be bet into a vig, and a 45-60% row is not "most likely"
#: by any reading of the words on the page.
#:
#: WHAT THE SAMPLE DOES NOT SAY, recorded because it was nearly quoted as
#: if it did. Dropping that band takes the settled record to +1.00%, at
#: +/-9.5%. Cutting the SAME 402 rows by market instead of by band gives
#: -2.15% for the ranked shelves against -3.90% for the unranked ones.
#: Two cuts of one sample, disagreeing in sign, both inside noise. The
#: ROI evidence establishes nothing; the naming argument above is the
#: whole case.
#:
#: WHAT IT COSTS, PUT TO ETHAN BEFORE IT SHIPPED AND ACCEPTED. The
#: 45-60% band IS the game-lines shelf: spread (84 rows, said 55.0%),
#: total (71, 55.1%) and team_total (35, 54.7%) are 190 rows against the
#: band's 184. So this floor removes about half of the shelf he asked
#: for on 2026-09-02 — "I don't see spread bets, I don't see anything
#: like that I just asked you to do" — and shipped as labelled leans.
#: Those three are also exactly the markets `GAME_RANK_MEASURED` puts at
#: 0.49, a coin flip: the record and the ranking measurement agree about
#: which shelves these are. He was shown the collision and chose 0.55
#: everywhere rather than scoping it to props.
MIN_PROB = 0.55

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


def engine_credible(row: dict) -> bool:
    """The ENGINE's own credibility test, on the engine's own numbers.

    THE CHECK ABOVE CANNOT CATCH WHAT THIS CATCHES, and the reason is
    arithmetic rather than an oversight. `betting.temper_edge` shrinks
    the published claim toward the market:

        hit = fair + shrink x (raw - fair)

    so `hit - fair` is at most `shrink x (raw - fair)`, and with shrink
    at or below 0.5 a row needs a RAW disagreement above 20 points
    before the shrunk gap can exceed the 10-point cap. Every row with a
    raw gap between 10 and 20 points — exactly the band the engine
    calls a modelling or data error — sails through a check made on the
    shrunk number. The check looked like a guard and could not fire on
    the rows it existed for.

    Ethan found one on a phone, 2026-09-02: Zack Gelof, UNDER 4.5 total
    bases at -200, "MODEL 73%", projection 1.7, none of his last ten
    games clearing 4.5 — sitting on the Most Likely board while its own
    card printed `betting.IMPLAUSIBLE_EDGE_REASON` in red. The model was
    RIGHT: P(under 4.5) on a 1.7 projection is about 96%, and 73% is
    what 96% becomes after being shrunk toward a market number that
    cannot be a real price for that line. The board then ranked the
    shrink artefact as a top pick.

    So this asks what the engine asked: is the RAW claim within
    MAX_CREDIBLE_EDGE of the book's de-vigged number? A row that has no
    raw claim (the touchdown chain, game cards) answers True and is
    judged by `_credible` on what it does carry.
    """
    # NOT ON A ROW RANKED ON THE MARKET'S NUMBER. Ethan, 2026-09-08:
    # "we have player props just barely any money lines." A football
    # moneyline row ranks on the book's de-vigged number (GAME_RANK_MARKET)
    # because that number sorts winners better than the model's; the
    # row's claim IS the market's, and this bar was still refusing it
    # whenever the model's own rating sat more than ten points away.
    # Measured 2026-09-08 on this box's NFL closes (`gamerank
    # --raw-bar`, 1,356 quoted games on the ratings the build ships):
    #
    #     favourites the board could carry (fair >= 55%, price >= -250)   681
    #     …refused here for the model's raw disagreement                   207   30%
    #     the market's number on the rows kept:     claimed 61.4%  landed 64.3%
    #     the market's number on the rows refused:  claimed 61.4%  landed 62.3%
    #     refused minus kept, 95% by game                        [-9.8%, +5.7%]
    #     by size of the disagreement: 10-15 pts +2.2 · 15-20 -0.6 · 20-30 -1.9
    #
    # and college the same day (2,729 games): 1,066 eligible, 401 refused
    # (38%); kept claimed 62.2% landed 60.2%; refused claimed 64.0%
    # landed 63.8%; 95% [-4.3%, +7.8%].
    #
    # The market lands where it claims on the games the model disputes,
    # at every size of dispute — which is what `gamecal` had already
    # said of the same model from the other side (the slope of its
    # disagreement against the close, -0.057 +/- 0.135: nothing). A bar
    # that removes three rows in ten and changes nothing measurable is
    # not a bar; it is a shelf a third empty. The model's own rating
    # stays on the row (`engine_raw_prob`) and the note prints it.
    if row.get("prob_source") == "market":
        return True
    # ONLY the engine's pre-shrink claim. This board's own `raw_prob` is
    # the display number before the mixture, which is a different
    # quantity measured against a different thing — falling back to it
    # would refuse honest rows for a disagreement the engine never had.
    raw, fair = row.get("engine_raw_prob"), row.get("fair_prob")
    if raw is None or fair is None:
        return True
    try:
        return abs(float(raw) - float(fair)) <= MAX_CREDIBLE_EDGE
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
    if market in GAME_MARKETS:
        return GAME_RANK_AUC.get(sport, {}).get(market)
    if sport == "nfl":
        return RANK_AUC.get(market)
    if sport == "cfb" and market == "anytime_td":
        return CFB_TD_AUC
    return None


def rankable(market: str, sport: str = "nfl") -> bool:
    """Has this market been SHOWN to rank, not merely modelled?"""
    return (rank_auc(sport, market) or 0.0) >= MIN_RANK_AUC


def measured_auc(sport: str, market: str):
    """The measured figure for a GAME market whether or not it cleared
    the floor: the box's own store first (gamerank --save writes
    sub-floor numbers too), then the shipped table. None = never
    measured, which is a different fact from measured-and-failed."""
    from .rankfit import rank_auc as _fitted
    got = _fitted(sport, market)
    if got is not None:
        return got
    return GAME_RANK_MEASURED.get(sport, {}).get(market)


#: The word a lean note uses for each market, plural.
_GAME_WORDS = {"spread": "spreads", "total": "totals",
               "team_total": "team totals", "moneyline": "moneylines"}


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

    IT MATTERED MOST WHERE IT WAS CHECKED LEAST. When this was written,
    college football's entire likelihood board was watch rows — cfb_build
    called `build([], rows, watch)` with no props at all — so every
    refusal added to this module protected the NFL prop board and left
    the whole college board ungated. Measured 2026-08-30, all of these
    published: an 8% row on a board whose floor is 30%, a -97 price no
    book can post, and a `proxy` quote the model invented.

    THAT SENTENCE IS NO LONGER TRUE, and it is left standing above with
    its tense corrected rather than deleted, because it is the reason
    this function exists. cfb_build passes its props and its game cards
    now, so college answers to all three makers. What has not changed is
    the lesson: a bar applied on one of several paths is not a bar.

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
    # THE PRODUCT REFUSAL (Ethan, 2026-09-01 — see HEAVIEST_PRICE): the
    # board shows who's most likely to DO something, priced like a bet.
    #
    # AN UNDER IS ADMITTED AGAIN, and the history is worth keeping. The
    # ban went in on 09-01 beside the price cap, aimed at the first MLB
    # night's rows — unders at -300 to -1800, "the most likely outcome
    # of most baseball nights" — and the CAP is what answered that
    # complaint: every one of those rows is heavier than -250. The
    # under rule swept the rest out with them, and a day later Ethan,
    # 2026-09-02: "all I see us is doing overs, but we have no unders
    # ... there is more bets that we can salvage." The measurement
    # agrees with him: an AUC is symmetric, so a market whose over
    # ranks at 0.77 ranks its under at 0.77 — 1 - P(over) is the same
    # ordering read from the other end (pinned in
    # tests/test_likely_gamelines.py). `from_prop` shows the under's
    # own probability; this bar holds it to the same cap, floor and
    # credibility as an over.
    if int(row["odds"]) < HEAVIEST_PRICE:
        return f"heavier than {HEAVIEST_PRICE} — chalk, not a pick"
    if not _credible(prob, row.get("implied_prob")):
        return "the shown probability disagrees with the market by more than we credit"
    # EACH REFUSAL NAMES ITS OWN NUMBER. Three different questions are
    # asked of three different probabilities here, and until 2026-09-08
    # two of them answered in sentences a reader could not tell apart —
    # "disagrees with the market by more than we credit" and "the model
    # and the market disagree by more than we credit", the same words in
    # a different order. On the droplet's census they printed as two
    # lines splitting 98 refused rows between them, and the one thing a
    # census exists to say — WHICH bar killed the board — was the one
    # thing those two lines could not. They say which number now: the
    # SHOWN probability, the model's OWN READ, the RAW claim.
    #
    # A row that RANKS on a market number still carries the model's own
    # read as its card, and a model that disagrees with the book by more
    # than we credit is our error wherever the row is sorted — the
    # Gelof guard, asked of the number the card prints.
    if (row.get("prob_source") in ("market", "sharp") and row.get("win_prob") is not None
            and not _credible(float(row["win_prob"]), row.get("implied_prob"))):
        return "the model's own read disagrees with the market by more than we credit"
    # …and the same question asked of the claim BEFORE the shrink, which
    # is the only place a big disagreement is still visible. See
    # `engine_credible`.
    if not engine_credible(row):
        return "the raw model claim, before the shrink, disagrees with the market by more than we credit"
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


def _spread_disagrees(row: dict, sport: str) -> bool:
    """Does this moneyline contradict its own game's posted spread?

    Both numbers are read for the HOME side, so the comparison does not
    depend on which side the card took. False whenever either number is
    missing, or the sport has no registered win curve — an unmeasurable
    row is not a refused one.
    """
    from .gamebets import spread_win_prob
    spread = row.get("game_spread")
    fair = row.get("fair_prob")
    if spread is None or fair is None:
        return False
    from_spread = spread_win_prob(sport, spread)
    if from_spread is None:
        return False
    try:
        fair = float(fair)
        # `fair_prob` is the de-vigged number for the side the CARD took.
        home = row.get("home") or ""
        took = row.get("team") or row.get("pick") or ""
        is_home = row.get("pick_is_home")
        if is_home is None:
            is_home = bool(home) and took == home
        from_price = fair if is_home else 1.0 - fair
    except (TypeError, ValueError):
        return False
    return abs(from_price - float(from_spread)) > SPREAD_COHERENCE


def _refuse(census, why: str):
    """Count a maker's refusal and return None.

    THE HALF OF THE FUNNEL THAT WAS NEVER COUNTED. `build`'s census fills
    from `keep`, which only sees rows a maker has already agreed to
    build. Everything the makers themselves turn away — an unmeasured
    market, a proxy price, a conditional, a live game — returned a bare
    None and left no trace, so a board that came out empty because its
    makers refused every row looked exactly like a board with nothing to
    say. On the college card of 2026-09-03 that was 440 prop rows
    refused before the counter could see one of them, and a census that
    reported {}.

    The census is the answer to "why is this board short tonight", and it
    could only ever answer for the rows that got far enough to be asked.
    """
    if census is not None:
        census[why] = census.get(why, 0) + 1
    return None


def _best_rung(row: dict, market: str, fits=None) -> dict | None:
    """The likeliest priced number on the prop's alternate ladder, or None.

    THE LADDER IS WHERE "MOST LIKELY" IS FOR SALE. A main line is hung
    where the book thinks the coin is fair, so the calibrated number at
    it sits near 50% and a board asking for 55% at no heavier than -250
    had nothing to show (2026-09-07: 303 rows, 215 under the floor,
    none shown). The same books hang the same stat at other numbers —
    a back over 40.5 at -220 rather than over 62.5 at -110 — and those
    are the rows Ethan asked for: "whatever gives us props and picks
    every single day".

    Every rung is held to the bars the main line is held to, at the
    rung's own numbers: the mixture's probability AT THAT LINE (or the
    sharp book's de-vigged fair there when the market has no fit), the
    55% floor, the -250 cap, a price a book could post, and the
    credibility bar against the rung's own de-vigged price. The best
    price per (line, side) across the bettable books is what is shown,
    exactly as the main line is shopped. Sharp-book rungs are never
    shown (nobody here can bet them) and only ever price. Highest
    probability wins.
    """
    from .odds import devig_two_way, is_sharp_book
    alts = row.get("alt_lines") or []
    if not alts:
        return None
    sharp: dict[float, tuple[float, float]] = {}
    for ln in row.get("alt_sharp_lines") or []:
        try:
            if ln.get("over_odds") and ln.get("under_odds"):
                sharp[float(ln["line"])] = devig_two_way(int(ln["over_odds"]),
                                                         int(ln["under_odds"]))
        except (TypeError, ValueError):
            continue
    best_price: dict[tuple[float, str], tuple[int, str, dict]] = {}
    for ln in alts:
        try:
            line = float(ln.get("line"))
        except (TypeError, ValueError):
            continue
        book = str(ln.get("book") or "")
        if not book or book.lower() == "proxy" or is_sharp_book(book):
            continue
        for side, key in (("over", "over_odds"), ("under", "under_odds")):
            try:
                odds = int(ln.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if not odds or not _sane(odds) or odds < HEAVIEST_PRICE:
                continue
            prev = best_price.get((line, side))
            if prev is None or odds > prev[0]:
                best_price[(line, side)] = (odds, book, ln)
    best = None
    for (line, side), (odds, book, ln) in best_price.items():
        p_over = display_prob(market, row.get("projection"), line,
                              row.get("recent_values"), fits=fits)
        source = "mixture"
        if p_over is None:
            pair = sharp.get(line)
            if pair is None:
                continue
            p_over, source = pair[0], "sharp"
        p = 1.0 - float(p_over) if side == "under" else float(p_over)
        if p < MIN_PROB:
            continue
        fair_over, fair_under = devig_two_way(int(ln.get("over_odds") or 0),
                                              int(ln.get("under_odds") or 0))
        fair = fair_under if side == "under" else fair_over
        if not _credible(p, fair):
            continue
        cand = {"line": line, "side": side, "book": book, "odds": odds,
                "prob": p, "fair": fair, "source": source}
        if best is None or p > best["prob"]:
            best = cand
    return best


def from_prop(row: dict, bettable, fits=None,
              sport: str = "nfl", census: dict | None = None) -> dict | None:
    """One likelihood row from a published prop row, or None.

    `row` is what `pipeline._rec_to_dict` already produces for EVERY
    prop, recommended or not — the likelihood board is a different cut of
    the same evaluation, not a second model. Building it any other way
    would let the two pages disagree about the same player.

    ``census`` counts each refusal by reason — see `_refuse`.
    """
    market = row.get("market") or ""
    if not rankable(market, sport):
        return _refuse(census, "no measured ranking for this market yet")
    prob = row.get("hit_prob")
    # A SHARP-ANCHORED CARD'S `hit_prob` IS THE SHARP BOOK'S FAIR, and
    # a sharp line is hung where that book thinks the coin is fair, so
    # the number sits at 50-53% for every prop it quotes. Judged on it,
    # every such prop is "under the likelihood floor" before the model
    # is consulted, and the board shows only what the sharp book did
    # not quote. Ethan, 2026-09-07: "it just shows 2 tight end reception
    # props. there is no rushing props for running backs or any
    # recieving props for wr." This board asks the MODEL who is likely
    # to hit — `raw_prob` is the model's own read of the side on an
    # anchored card (see `betting.Recommendation.raw_prob`) — and the
    # mixture below recomputes the shown number from the projection
    # either way. The sharp fair stays on the row as `sharp_fair`.
    if row.get("sharp_anchored") and row.get("raw_prob") is not None:
        prob = row.get("raw_prob")
    if prob is None or float(prob) < MIN_PROB:
        # THE LADDER BEFORE THE FLOOR. A main line is hung where the book
        # thinks the coin is fair, so its number sits near 50% — and this
        # refusal fired on that number before `_best_rung` below was
        # ever consulted. The ladders (2026-09-07) exist for exactly the
        # row this turned away: the same stat at a lower number, priced
        # heavier, where "most likely" is actually for sale. Ethan,
        # 2026-09-08, off the droplet's census: 363 rows, 212 of them
        # here, none on the board, none on a rung — the ladders were
        # bought, carried, and never looked at, because every rung test
        # fixture started at 0.56. A main line under the floor asks its
        # ladder first; the floor's refusal is for a row whose every
        # number is under it. `has_market` still gates the ladder, since
        # a proxy-priced row has no real rungs to show.
        rung = (_best_rung(row, market, fits)
                if prob is not None and row.get("has_market") else None)
        if rung is not None:
            return _row_from(row, market, sport, bettable, prob, rung=rung)
        return _refuse(census, "under the likelihood floor")
    if not row.get("has_market"):
        return _refuse(census, "no real book price")
    if not _sane(row.get("odds")):
        return _refuse(census, "not a price a book could post")
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
        # The mixture is P(over); an UNDER row shows its complement.
        # Every yardage line a book hangs is a half-number, so there
        # is no push to subtract — the same convention `hit_prob`
        # already arrived with (betting.choose_side: under_win =
        # 1 - p_over_at_under).
        under = str(row.get("side") or "").lower() == "under"
        shown = 1.0 - float(fitted) if under else float(fitted)
        source = "mixture"
    # COUNTED, LIKE EVERY OTHER REFUSAL. These two were bare `return
    # None`s, and they are the two the mixture creates: a row that
    # cleared the floor on its raw claim and fell under it once
    # calibrated, and a row the calibration walked away from the book.
    # On a night the board came out empty the census said "under the
    # likelihood floor: 4" and the other hundred refusals were invisible
    # — the half of the funnel `_refuse` exists to count, uncounted
    # again one function later. Ethan, 2026-09-07: "so what changed."
    # The census has to be able to answer that.
    # THE LADDER, judged beside the main line. A rung that is likelier
    # than the main number — or the only one of the two to clear the
    # bars — is what the row shows; the main number stays on the row
    # as `main_line` so the card can say which book number the rung
    # stands beside. See `_best_rung`.
    rung = _best_rung(row, market, fits)
    main_ok = shown >= MIN_PROB and _credible(shown, row.get("fair_prob"))
    if rung is not None and (not main_ok or rung["prob"] > shown):
        return _row_from(row, market, sport, bettable, prob, rung=rung)
    if shown < MIN_PROB:
        return _refuse(census, "under the likelihood floor after calibration")
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
        return _refuse(census, "the shown probability disagrees with the market by more than we credit")
    return _row_from(row, market, sport, bettable, prob, shown=shown, source=source)


def _row_from(row: dict, market: str, sport: str, bettable, prob,
              shown: float | None = None, source: str = "model",
              rung: dict | None = None) -> dict:
    """The likelihood row, from the main line or from a rung of the ladder."""
    if rung is not None:
        side, line, book, odds = rung["side"], rung["line"], rung["book"], rung["odds"]
        shown, source = rung["prob"], rung["source"]
        # The rung's own de-vigged price is what the shown number is
        # judged against (`admissible`'s credibility bar reads
        # `implied_prob`); the engine's pre-shrink claim is still judged
        # against the MAIN line's fair, where it was made.
        implied = round(float(rung["fair"]), 4)
        ev = None
    else:
        side, line, book, odds = (row.get("side", ""), row.get("line"),
                                  row.get("book", ""), row.get("odds"))
        implied = row.get("fair_prob")
        ev = row.get("ev_per_unit")
    return {
        # WHICH MAKER BUILT IT — "prop", "td" or "game" — so the page,
        # the journal and the lint branch on a flag rather than on the
        # absence of a position or a line.
        "kind": "prop",
        "player": row.get("player", ""), "team": row.get("team", ""),
        "opponent": row.get("opponent", ""),
        "market": market, "market_label": row.get("market_label", market),
        "side": side, "line": line,
        "book": book, "odds": odds,
        "model_prob": round(float(shown), 4),
        # WHICH NUMBER THE READER IS LOOKING AT. A page that silently
        # swapped its probability source would be the opposite of the
        # point.
        "prob_source": source,
        # WHICH NUMBER ON THE BOOK'S LADDER. "alt" rows carry the main
        # line beside them so the card can say what the rung stands
        # next to; the journal and the grader read `line`/`side`/`odds`
        # and so grade the rung itself.
        "rung": "alt" if rung is not None else "main",
        "main_line": row.get("line"), "main_odds": row.get("odds"),
        "main_book": row.get("book", ""), "main_side": row.get("side", ""),
        "raw_prob": round(float(prob), 4),
        # THE PRE-SHRINK CLAIM AND THE BOOK'S OWN NUMBER, carried so the
        # one bar can ask the engine's question (see `engine_credible`).
        # `raw_prob` above is this board's own raw display number, which
        # is a different thing from the engine's pre-shrink claim, so
        # the engine's travels under its own name.
        "engine_raw_prob": row.get("raw_prob"),
        # THE SHARP BOOK'S OWN NUMBER, beside the model's, when the card
        # was priced from a sharp pair. The floor above was asked of the
        # model; a reader deserves to see the number it was not asked of.
        "sharp_anchored": bool(row.get("sharp_anchored")),
        "sharp_fair": row.get("sharp_fair"),
        "fair_prob": row.get("fair_prob"),
        "implied_prob": implied,
        "projection": row.get("projection"),
        "ev_per_unit": ev,
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
        "kind": "td",
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


def from_game_bet(row: dict, sport: str = "nfl",
                  census: dict | None = None) -> dict | None:
    """One likelihood row from a priced game bet, or None.

    `row` is the card the edge board already built — `gamebets._game_bet`,
    `gamebets.moneyline_to_dict`, cfb_build.to_game_bet — so this is, once
    more, a different cut of the same evaluation and not a second model.
    `win_prob` is the model's probability of the side the card took and
    `fair_prob` the book's de-vigged number for that side; both are on
    the card, and `admissible` holds them to the same cap, floor and
    credibility bar as every player row.

    THE MARKET HAS TO HAVE RANKED. `GAME_RANK_AUC` (or the box's own
    store) says which game markets the model has been shown to sort;
    today that is the moneyline and nothing else, because spreads and
    totals measured as a coin flip against the close. A spread card
    handed in here comes back None, and that is the board working.

    THE LIKELY SIDE, NOT THE PRICED SIDE. The edge card backs whichever
    side has the edge, and on a moneyline that is the dog more often
    than not — the first end-to-end run put "CHI ML +190, 37%" on a
    board called Most Likely, with the 63% favourite nowhere on it. A
    moneyline is two-way with no push, so the other side's probability
    is on the card already (1 - win_prob, 1 - fair_prob); its price is
    now too (`MoneylineRec.home_odds` / `away_odds`). When the card's
    pick sits under 50% the row is built for the favourite. A dog card
    without the other price (a stale payload) is refused rather than
    shown as "likely". Spreads and totals would need the same flip the
    day they rank, and their cards do not carry the other price yet —
    noted here so it is not rediscovered.

    HOLDS, NOT PICKS: a card on an in-play market a pre-game model
    cannot price (`live`), and a college conditional waiting on a
    starter (`conditional`) — the same reading the injury hold gives a
    listed player. A card the edge board refused as not credible still
    arrives here with `credible` False and a Pass grade; `admissible`
    refuses it again on the numbers, which is the one bar doing its job.

    THE ROW WEARS THE CARD'S SHAPE (win_prob, fair_prob, edge, grade,
    headline, matchup …) beside the board's own keys, so the game-bet
    page can draw a flipped row it will not find among the edge cards.
    """
    from .gamebets import expected_value
    market = row.get("bet_type") or row.get("market") or ""
    if market not in GAME_MARKETS:
        return _refuse(census, "not a game market this board carries")
    # MEASURED IS THE BAR FOR A GAME MARKET, not ranked (see
    # GAME_RANK_MEASURED). A market with a figure is shown with it; a
    # market with none is not shown at all.
    model_auc = measured_auc(sport, market)
    if model_auc is None:
        return _refuse(census, "this game market has never been measured")
    if row.get("has_market") is False:
        return _refuse(census, "no real book price")
    if row.get("live"):
        return _refuse(census, "the game is already under way")
    # …AND ONE THAT HAS FINISHED, which `live` says nothing about. Every
    # producer sets `live` as `state == "live"`, so a FINAL game answers
    # False to it and sailed onto a board called Most Likely To Hit with
    # a settled result and a pre-game probability. `rules.game_has_started`
    # is the wider fact — live OR final, "once a pre-game projection is
    # stale" — and it was computed in every `_finish_bet` and thrown away.
    # Counted separately from `live` because "still playing" and "already
    # over" are different answers to "why is this not on the board".
    if row.get("started"):
        return _refuse(census, "the game has already been played")
    if row.get("conditional"):
        return _refuse(census, "a conditional, which is a hold and not a pick")
    # THE CARD'S TWO NUMBERS, READ TOGETHER (see SPREAD_COHERENCE). A
    # moneyline is checked against the same game's posted spread, because
    # a book prices both off one opinion and ours came from two feeds.
    if market == "moneyline" and _spread_disagrees(row, sport):
        # ONE LINE, ONE LITERAL, deliberately: a census label split
        # across two source lines is one that neither a reader nor this
        # module's own label linter (tests/test_census_labels.py) can
        # find whole.
        return _refuse(census, "the moneyline disagrees with this game’s own spread by more than any book has")
    # WHICH NUMBER ORDERS THE ROW — see `ranking_number`. `prob` is the
    # ranking number from here on; `prob_model` is the model's own read
    # for the same side, kept on the row and the card as the model's.
    prob, source, auc = ranking_number(sport, market, row, model_auc)
    if prob is None:
        return _refuse(census, "no probability")
    ranked = float(auc) >= MIN_RANK_AUC
    fair = row.get("fair_prob")
    prob_model = row.get("win_prob")
    prob_model = prob if prob_model is None else float(prob_model)
    home, away = row.get("home", "") or "", row.get("away", "") or ""
    team = row.get("team") or ""
    side = row.get("side", "") or ""
    line = row.get("line")
    odds = row.get("odds")
    label = row.get("pick_label") or row.get("headline") or ""
    # The model's own claim before the market haircut, when the maker
    # carries one. See MoneylineRec.raw_win_prob.
    raw_claim = row.get("engine_raw_prob")
    try:
        raw_claim = None if raw_claim is None else float(raw_claim)
    except (TypeError, ValueError):
        raw_claim = None
    flipped, backed, backed_odds = False, label, odds
    if prob < 0.5:
        # THE LIKELY SIDE. Every game market here is two-way, so the
        # other side is 1 - p at the other side's price (`other_odds`
        # on every card since 2026-09-02; the moneyline also carries
        # both prices by name). A card without it is refused rather
        # than shown as "likely" from the wrong end.
        if market == "moneyline":
            other_odds = row.get("away_odds") if team == home else row.get("home_odds")
            other_odds = row.get("other_odds") if other_odds is None else other_odds
            team = away if team == home else home
            label = f"{team} ML"
        elif market == "spread":
            other_odds = row.get("other_odds")
            team = away if team == home else home
            line = None if line is None else -float(line)
            label = f"{team} {line:+g}" if line is not None else f"{team}"
        else:                                   # total, team_total
            other_odds = row.get("other_odds")
            side = "Under" if str(side).lower().startswith("o") else "Over"
            label = (f"{side} {line:g}" if market == "total"
                     else f"{team} {side} {line:g}") if line is not None else side
        if not team and market != "total":
            return _refuse(census, "the likely side has no team on the card")
        if other_odds is None or fair is None:
            return _refuse(census, "the other side's price is missing")
        odds, prob, fair, flipped = other_odds, 1.0 - prob, 1.0 - float(fair), True
        prob_model = 1.0 - prob_model
        # THE PRE-SHRINK CLAIM FLIPS WITH THE SIDE. Every market here is
        # two-way, so the model's raw number for the other side is
        # 1 - raw. Left unflipped it would be compared against the OTHER
        # side's fair by `engine_credible`, which is a guard reading two
        # numbers about different teams.
        if raw_claim is not None:
            raw_claim = 1.0 - raw_claim
    if prob < MIN_PROB:
        return _refuse(census, "under the likelihood floor")
    # The card's edge and EV are the MODEL's, as on every card: the
    # ranking number is what orders the board, not what the card claims.
    edge = None if fair is None else round(prob_model - float(fair), 4)
    try:
        ev = round(expected_value(prob_model, int(odds)), 4)
    except (TypeError, ValueError):
        ev = None
    reasons = list(row.get("reasons") or [])
    # THE EDGE BOARD'S REFUSAL IS NOT THIS BOARD'S. Ethan, 2026-09-08,
    # with the Vikings card on screen: a green "67% · the likely side"
    # headline sitting over a red "Model disagrees with the market by
    # more than 10% — a rating error, not an edge". Both sentences were
    # true of their own board and the card carried them together, which
    # is the same self-contradiction the Gelof card had in reverse.
    #
    # A row that ranks on the MARKET's number is not staking our rating,
    # and the disagreement it names was measured to carry nothing
    # against the close (`engine_credible`, `gamerank --raw-bar`). The
    # row says what it IS doing in `rank_note`, which prints the model's
    # own number and why it does not bar the row. So the staking
    # refusal comes off, by name rather than by matching text.
    if source == "market":
        from .gamebets import RATING_ERROR_REASON, RATING_ERROR_REASON_EFFICIENT
        gone = {RATING_ERROR_REASON, RATING_ERROR_REASON_EFFICIENT}
        reasons = [r for r in reasons if r not in gone]
    if flipped:
        try:
            at = f" at {int(backed_odds):+d}"
        except (TypeError, ValueError):
            at = ""
        reasons.insert(0, f"The likely side. The edge board backed {backed}{at} "
                          f"on price; this is the side the same numbers say "
                          f"lands more often ({prob:.0%}).")
    # WHAT THE FIGURE MEANS, on the row. A ranked market's number is a
    # ranking; a measured-below-floor market's number is the model's
    # lean at this line, and the row says which it is rather than
    # letting a shelf header speak for it.
    if not ranked:
        rank_note = (
            f"Shown as the model’s lean at this number. Sorting "
            f"{_GAME_WORDS.get(market, market)} across games measured at "
            f"{float(auc):.2f} against the close — a coin flip — so the "
            f"percentage is a read on this game, not a ranking.")
    elif source == "market":
        # THE MODEL'S OWN NUMBER, not the book's under the word "model".
        # `prob_model` is the card's `win_prob`, and on a football
        # moneyline the measured haircut prices that AT the market
        # (gamecal: the disagreement carries nothing), so it is the
        # market's number twice over. The pre-shrink claim is the
        # model's own read, and it is what a reader means by "the
        # model" (tests/test_game_claim.py, the MIN -220 card).
        own = prob_model if raw_claim is None else raw_claim
        rank_note = (
            f"Ranked on the market’s number, {prob:.0%}: the book’s de-vigged "
            f"price sorts {sport.upper()} winners at {float(auc):.2f} measured, "
            f"against {float(model_auc):.2f} for the model’s own. The model’s "
            f"own rating has this side at {own:.0%}.")
        if (raw_claim is not None and fair is not None
                and abs(raw_claim - float(fair)) > MAX_CREDIBLE_EDGE):
            rank_note += (
                " That disagreement does not bar the row: measured against "
                "the close, the market’s number lands the same on the games "
                "the model disputes as on the ones it agrees with, and the "
                "model’s disagreement with the close carries no information "
                "(engine.gamecal, engine.gamerank --raw-bar).")
    elif source == "sharp":
        rank_note = (
            f"Ranked on the sharp book’s fair, {prob:.0%} — a market number, "
            f"which sorts {sport.upper()} winners at {float(auc):.2f} measured.")
    else:
        rank_note = ""
    return {
        # WHAT KIND OF ROW THIS IS, said once, so the page, the journal
        # and the lint branch on a flag rather than on the absence of a
        # position. `player` carries the pick label because every reader
        # of this board keys on it; the journal re-derives the team or
        # matchup it needs from the fields below.
        "kind": "game",
        "player": label, "team": team or home,
        "opponent": (away if (team or home) == home else home),
        "home": home, "away": away,
        "matchup": row.get("matchup", "") or f"{away} @ {home}",
        "pick_label": label, "pick": team or "",
        "pick_is_home": (team == home) if team else None,
        "headline": label,
        "bet_type": market, "market": market,
        "market_label": row.get("market_label", market),
        # THE ENGINE'S OWN NUMBER, for the engine's own question. Without
        # it `engine_credible` answered True for every game row — the
        # Gelof guard was blind to this whole board (Ethan, 2026-09-03:
        # "none of these teams are favored to win on any sports book").
        #
        # ONLY ON A MARKET THAT CLAIMS A RANKING, and that is a product
        # decision, not a technicality. The bar exists to stop a row
        # being presented as a LIKELIHOOD RANKING while the engine does
        # not credit its own number. An unranked spread or total makes
        # no such claim — it ships labelled "the model's lean at this
        # number" because Ethan asked to see those (2026-09-02), and the
        # model there disagrees with the close by 30 points as a matter
        # of course. Feeding those to this bar would empty both shelves
        # and silently reverse his call.
        "engine_raw_prob": raw_claim if ranked else None,
        "side": side, "line": line,
        # A game card carries no book name on the NFL path; the journal
        # has always written these as the shopped-best price.
        "book": row.get("book") or "best", "odds": odds,
        "model_prob": round(prob, 4),
        "prob_source": source,
        "raw_prob": round(prob, 4),
        "implied_prob": None if fair is None else round(float(fair), 4),
        "projection": None,
        "ev_per_unit": ev,
        "bettable": True,
        "rank_auc": round(float(auc), 4),
        "ranked": ranked,
        "rank_note": rank_note,
        "reasons": reasons,
        "game_script": row.get("game_script"),
        "recent_values": [],
        "game_date": row.get("date", "") or "", "kickoff": row.get("kickoff", "") or "",
        "date": row.get("date", "") or "",
        "headshot": "", "position": "", "usage_role": "",
        "injury_status": "",
        "warnings": list(row.get("warnings") or []),
        # The card shape, for the game-bet page. NOT a stake: this board
        # ranks and never sizes, and a flipped row is not on the edge
        # board at all.
        "win_prob": round(prob_model, 4),
        "fair_prob": None if fair is None else round(float(fair), 4),
        "edge": edge,
        "has_market": True, "live": False, "credible": True,
        "grade": "Likely", "quality": None, "confidence": None,
        "stake_units": 0.0, "recommended": False,
        "flipped": flipped,
    }


#: The kinds of row the board is built from, in the order the makers run.
KINDS = ("td", "prop", "game")


def _funnel() -> dict:
    return {"offered": 0, "kept": 0, "duplicate": 0, "shown": 0, "refused": {}}


def build(props: list, td_picks=None, td_watch=None, sport: str = "nfl",
          limit: int = LIMIT, fits=None, census: dict | None = None,
          game_bets=None, census_by_kind: dict | None = None) -> list:
    """The likelihood board: every rankable market, ordered by probability.

    ORDERED BY PROBABILITY AND NOTHING ELSE. Sorting by EV, or breaking
    ties on it, would quietly rebuild the edge board under a different
    name — which is the exact failure this page exists to correct.

    `census` is filled with {reason: count} across every row the board
    turned away, as before. `census_by_kind` is filled with the same
    refusals split by the kind of row — "td", "prop", "game" — each
    with how many rows were OFFERED, how many the bar KEPT, how many
    were a DUPLICATE of a row already seated, how many were SHOWN once
    the caps ran, and the refusals by reason. Ethan, 2026-09-08: "we
    have player props just barely any money lines or touchdown." The
    flat census could not say where the moneylines and the scorers
    went: "under the likelihood floor: 212" is one line for three
    different shelves, and a shelf whose rows were never offered at all
    prints nothing. Offered / kept / shown per kind is the funnel that
    answers him — a "td" line reading offered 0 is an empty feed, one
    reading offered 40 and refused 40 under the floor is the floor.
    """
    from .calibrate import is_reliable

    def bettable(market):
        return is_reliable(sport, market)

    out = []
    seen = set()
    funnel = {k: _funnel() for k in KINDS}

    def keep(got, kind: str) -> bool:
        """The one gate. Every row passes through here or does not ship."""
        why = admissible(got)
        if why:
            _refuse(funnel[kind]["refused"], why)
            return False
        funnel[kind]["kept"] += 1
        return True

    funnel["td"]["offered"] = len(td_picks or []) + len(td_watch or [])
    for row in (td_picks or []) + (td_watch or []):
        got = from_watch(row, sport=sport)
        key = (got["player"], got["team"], "anytime_td")
        if key in seen:
            funnel["td"]["duplicate"] += 1
            continue
        if not keep(got, "td"):
            continue
        seen.add(key)
        out.append(got)
    funnel["prop"]["offered"] = len(props or [])
    for row in props or []:
        got = from_prop(row, bettable, fits=fits, sport=sport,
                        census=funnel["prop"]["refused"])
        # `from_prop` already refuses on the same grounds and returns
        # None; it stays as a cheap pre-filter because the mixture work
        # below it is not cheap. `keep` is what actually decides — but
        # the pre-filter now counts what it turned away into the same
        # census, so the funnel adds up whichever of the two said no.
        if got is None:
            continue
        key = (got["player"], got["team"], got["market"])
        if key in seen:
            funnel["prop"]["duplicate"] += 1
            continue
        if not keep(got, "prop"):
            continue
        seen.add(key)
        out.append(got)
    # THE THIRD MAKER, same bar. Game cards arrive from the edge board's
    # own pricing (`pipeline._game_bets`, `mlb.pipeline._game_bets`,
    # cfb_build.build_plays); a market the model has not been shown to
    # rank never leaves `from_game_bet`, and everything that does answers
    # to `keep` like every other row.
    funnel["game"]["offered"] = len(game_bets or [])
    for row in game_bets or []:
        got = from_game_bet(row, sport=sport, census=funnel["game"]["refused"])
        if got is None:
            continue
        key = ("game", got["matchup"], got["market"], got["team"], got["side"])
        if key in seen:
            funnel["game"]["duplicate"] += 1
            continue
        if not keep(got, "game"):
            continue
        seen.add(key)
        out.append(got)
    out.sort(key=lambda r: -float(r["model_prob"] or 0.0))
    # TWO CAPS, ONE ORDER. Player rows keep LIMIT; game rows keep
    # GAME_LIMIT; the survivors are one list in probability order, so a
    # 63% favourite still sits above a 55% catch and a Sunday's eighty
    # game leans cannot push the player rows off (see GAME_LIMIT).
    players = _cut_players([r for r in out if r.get("kind") != "game"], limit)
    games = [r for r in out if r.get("kind") == "game"][:GAME_LIMIT]
    out = sorted(players + games, key=lambda r: -float(r["model_prob"] or 0.0))
    # WHY THE BOARD IS THE SIZE IT IS, handed back to a caller that asked
    # for it. An empty college Saturday has several causes and a census
    # that only reaches stdout is one nobody has the morning they need
    # it. Filled in place rather than returned, so no existing caller
    # has to change and no row carries metadata that would follow it
    # into the journal.
    for r in out:
        funnel[r.get("kind") or "prop"]["shown"] += 1
    refused: dict = {}
    for kind in KINDS:
        for why, n in funnel[kind]["refused"].items():
            refused[why] = refused.get(why, 0) + n
    if census is not None:
        census.update(refused)
    if census_by_kind is not None:
        census_by_kind.update(funnel)
    return out


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
