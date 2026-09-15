"""The Pick of the Day: one pick per sport, priced the way a sharp prices it.

Ethan, 2026-09-15: "we'll keep working on it so we can have a model that
picks one pick for the pick of the day ... I want it to be a 50-50 money
flip, basically, either from 80% to 100% flip of your money. And we need
to look at other pro sports bettors' logic and models ... So we need to
figure out the models they're using and implement that."

THE WORD "GUARANTEED" IS NOT BUILT HERE. No bet is guaranteed, the
disagreement was raised once, and Ethan's call stands on everything else
in this module — the band, the daily cadence, the showcase framing. What
the page may not do is promise a paying reader a certainty, because the
first loss then reads as a lie rather than as variance, and this module
would be the thing that made the promise. `tests/test_potd_card.py`
holds that line, and the banned list there is why this module is named
for a pick rather than for a lock. The marketing word is Ethan's to
choose anywhere the numbers are not; the numbers stay true.

WHAT THE BAND COSTS, MEASURED BEFORE ANYTHING WAS BUILT ON IT. The
payout floor below is 0.70 units — "$100 on it, I wanna make at least
$70" — which is -142, which is the market claiming at most 58.8%. So a
main-market favourite inside this band CANNOT be a 68% pick; the price
forbids it. Replaying every stored schedule close (4,431 games with a
two-way moneyline), the best moneyline on the slate inside the band goes:

    nfl  109 picks   56 won   51.4%   the price implied 55.4%   -7.1% ROI
    cfb  242 picks  122 won   50.4%   the price implied 52.0%   -4.4% ROI

Both land within one standard deviation of what the price already said.
That is the finding this module is built on: near even money in an
efficient main market you are buying a coin flip at a small loss, and no
amount of confidence-ranking changes it. Drop the floor to 0.53 (-190)
and the same selector hits 66.1% / 62.0% — the ten to fifteen points the
payout costs, and the trade is Ethan's to make. All of it is one
constant apart (`MIN_PAYOUT`).

SO THE PICK CANNOT BE A FAVOURITE, IT HAS TO BE A DISAGREEMENT. That is
also what the professionals actually do, once the marketing is stripped
off. The public +EV method — Unabated, OddsJam, Outlier, Sharp Lines all
describe the same three steps — is: take a SHARP book's two-way price
(Pinnacle is the reference because it runs a 2-3% margin and welcomes
winners, so its number is priced by the sharpest money), REMOVE THE VIG
to get a fair probability, and bet only where a book you can actually
reach prices that outcome worse than the sharp fair. The edge is the gap
between two books, never between a model and the world.

This codebase already built that machinery for the Edge board
(`betting.sharp_anchor_for`, `gamebets.sharp_anchor_two_way`,
`odds.devig_two_way`, `odds.consensus_fair`). What it never had was a
surface that selected on it alone. That is this module now.

AND ONE RUNG ABOVE THE SHARP BOOK, added 2026-09-15: an EXCHANGE. Step
two of that method — remove the vig — is the step that needs an
assumption, and an exchange skips it. Two people take opposite sides of
a contract at a price they both chose; the mid is the probability with
no margin baked in and nothing to strip. `engine/exchangefair` hangs it
on the rows it can match, guarded on the only thing that matters (is
there a real, tight, liquid book behind that mid), and `EVIDENCE` ranks
it first.

WHY OUR OWN MODEL IS NOT ALLOWED TO BE THE EVIDENCE, which is the change
Ethan asked for in as many words ("we shouldn't use that 70%"). It is
not a style preference — it is measured. `likely.GAME_RANK_MEASURED`
against `likely.GAME_RANK_MARKET`:

    nfl moneyline   model 0.677   the market's own de-vigged number 0.722
    cfb moneyline   model 0.752   the market's own de-vigged number 0.791
    spreads, totals, team totals  0.492-0.504 — a coin flip, both leagues

The market ranks winners better than we do, and on the derived markets
we cannot rank at all. A pick chosen because OUR number disagrees with
the price is therefore a pick chosen by the weaker of the two opinions
in the room. `EVIDENCE` below ranks the tiers accordingly and
`shortfall` refuses the model-only tier outright.

THE DE-VIG METHOD BARELY MATTERS IN THIS BAND, which is worth writing
down because the literature argues about it constantly. Multiplicative,
additive, power and Shin diverge on longshots — that is the whole
favourite-longshot-bias argument — and converge on the middle of the
board. At -110/-110 they are identical; across the 0.70-1.90 payout
band they disagree by about a point at the plus-money end and well
under one everywhere else. `odds.devig_two_way` is
multiplicative and stays that way here. A power de-vig is the right
argument to have on the touchdown ladders (`engine/devig` already had
it), not on a coin flip.

WHERE THE CANDIDATES COME FROM. The Most Likely board, as before: it is
already calibrated, already priced off real books, already deduped, and
already carries `sharp_anchored` / `sharp_fair` / `implied_prob` /
`prob_source` / `rank_auc` per row. This is a selection pass over that
board, not a second model, so it cannot drift away from the numbers the
rest of the site shows.

HOW WE FIND OUT IF THIS IS REAL, in weeks rather than years. Win-loss on
one pick a day is noise for a very long time — the industry's own rule
of thumb is 500-1,000 graded plays before a record means anything, which
at one a day is three years. Closing-line value grades the DECISION at
kickoff, accrues on every pick including the losers, and is the metric
the sharp side actually keeps. The potd book flows into
`clvboard.scoreboard(conn, category="potd")` for free. If these picks do
not beat the close, this module is wrong and that page will say so.

A DAY WITH NOTHING GOOD ENOUGH SAYS SO. `build` still returns the best
in-band candidate, flagged `below_bar` with the reason, so the page is
never blank — the pattern the boards already use
(`likely.RESERVE_MIN_PROB`). It is NOT journaled: the record this
feature keeps has to answer "how do the picks that qualified do", and a
book padded with rows the selector refused would answer a different
question on exactly the thinnest days.
"""

from __future__ import annotations

#: THE BAND, in units returned on a one-unit stake — Ethan's own words
#: rather than a translation of them into American odds, because the
#: payout IS the product definition and the odds are the incidental
#: spelling. He said it twice and the second time was the clearer one:
#:
#:   2026-09-15, first   "from 80% to 100% flip of your money"
#:   2026-09-15, second  "I just wanted it to be a guaranteed for the
#:                        day like I'm putting 100 bucks on it. I wanna
#:                        make at least $70 ... I feel like my wording
#:                        is kind of fucked up a little bit"
#:
#: The reworded one is a FLOOR on the winnings, not a window, and it is
#: the better spec: $70 on $100 is 0.70 units, which is -143. A row
#: outside the band is disqualified rather than shown as a near miss —
#: "the strongest thing on the card is a -400 favourite" is not this
#: feature having a quiet day, it is a different feature.
#:
#: WHAT THE FLOOR BUYS, MEASURED, because it is the one knob that
#: matters and the arithmetic is unkind. The floor decides how much
#: favourite the pick may buy, and the market prices that almost exactly:
#:
#:     floor          price    the most it can imply    it actually hit
#:     1.00  ($100)    +100         50.0%                    —
#:     0.70  ($70)     -143         58.8%              51.4% / 50.4%
#:     0.60  ($60)     -167         62.5%              53.2% / 55.4%
#:     0.53  ($53)     -190         65.4%              66.1% / 62.0%
#:
#: (NFL / CFB, one pick per slate, every stored close — see
#: docs/PICK_OF_THE_DAY.md §2.) So his floor costs about ten points of
#: hit rate against -190, and no selector can buy them back: nobody
#: sells a 65% outcome for 70 cents.
#:
#: THAT TABLE IS ABOUT PICKING A FAVOURITE, WHICH IS NOT WHAT THIS DOES.
#: The band only says which prices may be shopped; `shortfall` still
#: demands a real disagreement with a sharp fair. A wider band is
#: therefore MORE candidates and more chances at a real edge, not a
#: weaker pick — which is why the plus-money end is left open and
#: `MIN_FAIR` does the work of keeping the pick a favourite.
MIN_PAYOUT = 0.70
MAX_PAYOUT = 1.90

#: The same band as American odds, derived once so nothing can drift.
#: Rounded INWARD — a price must clear the payout test itself, and these
#: exist for the page to print and for the census to read. -143 pays
#: 0.699 and is OUT by a thousandth; -142 pays 0.704 and is in.
MIN_ODDS = -142
MAX_ODDS = 190

#: HOW GOOD THE EVIDENCE IS, highest first. This is the ranking key, and
#: it is deliberately not the edge size: a 3% gap against Pinnacle's
#: de-vigged close is worth more than a 6% gap against our own model,
#: because the measurements above say our model is the weaker witness.
#:
#:   exchange  a real two-sided order book on a regulated exchange
#:           (`engine/exchangefair`, off `sources/kalshi`). RANKED ABOVE
#:           THE SHARP BOOK, and the reason is an assumption rather than
#:           a preference: de-vigging Pinnacle means assuming HOW its
#:           margin is spread across the two sides, and the
#:           favourite-longshot literature says books do not price that
#:           way. An exchange has no margin to strip — two people took
#:           opposite sides at a price they both chose — so its mid IS
#:           the probability, with nothing assumed. It is guarded hard
#:           (two-sided book, tight, liquid) because a number from an
#:           exchange is only better than a book's if the book behind it
#:           is real.
#:   sharp   a sharp book quoted this market two ways and we de-vigged
#:           it; the fair is a number the sharpest money in the world
#:           agreed on, and the price we take is at a book Ethan can
#:           reach. This is the professional method, unmodified.
#:   market  no sharp quote, but the field is deep enough to de-vig a
#:           consensus (`odds.MIN_CONSENSUS_BOOKS`); the fair is the
#:           market's own opinion and the edge is line-shopping.
#:   model   only our number disagrees with the price. Measured weaker
#:           than the market on every market we have measured, so this
#:           tier can never be the pick — see `shortfall`.
EVIDENCE = ("exchange", "sharp", "market", "model")

#: The +EV bar, in probability points of the fair. The retail +EV tools
#: quote 1-3% as the working range and the low end of that is where the
#: bet stops surviving the price moving against you between the pull and
#: the placement. 2% is the middle of the published range and roughly
#: twice the shopped hold on a -110 pair.
MIN_EV = 0.02

#: A pick this feature is named after should at least be more likely to
#: happen than not, by the number we are trusting. Inside the band the
#: price itself implies at most 55.6%, so this bites on the plus-money
#: half: a +100 shot our fair calls 48% can be +EV and still is not a
#: thing to put one name on for the day.
MIN_FAIR = 0.50

#: A market has to have shown it can rank this outcome better than a
#: coin flip before one pick a day rides on it. `likely.rank_auc` is the
#: measured figure per sport and market; the markets measured at 0.49
#: (see `likely.GAME_RANK_MEASURED`) are exactly the ones a showcase
#: pick must never come from, and an unmeasured market is not a pass by
#: default — it is the same unknown wearing a blank.
MIN_RANK_AUC = 0.55

#: Every reason `disqualify` can give. A row refused for one of these is
#: never shown, not even as a near miss: it is missing something the
#: page needs, or it is outside the product's own definition, or it is a
#: bet nobody could still place.
HARD_REASONS = (
    "no fair probability to price against",
    "no real market price",
    "price a book could not have posted",
    "the payout is outside the even-money band",
    "the player is carrying an injury designation",
    "the game has already started",
)


def implied(odds) -> float | None:
    """The break-even probability an American price implies, with the
    book's margin still in it. None on anything unreadable.

    `odds.american_to_prob` DOES THE ARITHMETIC, and this is a guard
    around it rather than a second copy of it. The first draft of this
    module carried its own one-liner and had the plus-money case
    inverted — +190 came back 65.5% instead of 34.5%, which would have
    made every underdog on the board look like the safest bet of the
    day. The converter that four other modules already agree on has
    been right the whole time.
    """
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    from .odds import american_to_prob
    return american_to_prob(o)


def payout(odds) -> float | None:
    """Units returned on a one-unit stake, the winnings alone — the
    number the band is written in. Decimal odds minus the stake, off the
    same converter, for the reason `implied` gives."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    from .odds import american_to_decimal
    return american_to_decimal(o) - 1.0


def in_band(odds) -> bool:
    """Does this price pay between 80% and 100% of the stake?

    THE PAYOUT IS THE TEST, not the American number, so the two spellings
    can never disagree — `MIN_ODDS`/`MAX_ODDS` are for printing. A price
    between -100 and +100 does not exist on an American board; anything
    claiming to be there is a broken quote, not a coin flip.
    """
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return False
    if -100 < o < 100:
        return False
    pay = payout(o)
    if pay is None:
        return False
    return MIN_PAYOUT - 1e-9 <= pay <= MAX_PAYOUT + 1e-9


def evidence(row: dict) -> str:
    """Which witness is telling us this price is wrong: "sharp",
    "market" or "model".

    Read off the fields the Most Likely board already sets, rather than
    recomputed here, so this can never disagree with what the card shows
    the reader. `sharp_anchored` is set by `betting.sharp_anchor_for`
    when a sharp book quoted the same market two ways at the same line;
    `prob_source` is set by `likely.ranking_number` and reads "market"
    when the board ranked on the book's de-vigged number because that
    number measures better than ours.
    """
    # ASKED FIRST because it is the fair with nothing assumed in it.
    # `exchangefair.attach` only sets this on a market it could match to
    # a real, tight, liquid two-sided book, so its presence IS the
    # quality check — the guards live where the data is, not here.
    if row.get("exchange_fair") is not None:
        return "exchange"
    if row.get("sharp_anchored") and row.get("sharp_fair") is not None:
        return "sharp"
    if row.get("prob_source") in ("sharp", "anchored"):
        return "sharp"
    if row.get("prob_source") == "market" and row.get("implied_prob") is not None:
        return "market"
    return "model"


def fair_prob(row: dict) -> float | None:
    """The probability this pick is priced against — the best witness
    available, matching `evidence` exactly.

    NOT THE MODEL'S NUMBER unless the model is all there is, and a row
    that gets there is refused by `shortfall` anyway. The pairing is
    kept in one function so a future edit cannot leave `evidence`
    saying "sharp" while the EV is computed off something else.
    """
    tier = evidence(row)
    if tier == "exchange":
        val = row.get("exchange_fair")
    elif tier == "sharp":
        val = row.get("sharp_fair")
        if val is None:
            val = row.get("win_prob")
        if val is None:
            val = row.get("model_prob")
    elif tier == "market":
        val = row.get("implied_prob")
    else:
        val = row.get("model_prob")
    try:
        p = float(val)
    except (TypeError, ValueError):
        return None
    return p if 0.0 < p < 1.0 else None


def edge(row: dict) -> float | None:
    """Expected value of a one-unit stake, in units. The professional
    number: fair probability times what the price pays, minus the stake.

    Positive means the book is charging less than the fair says it
    should. `odds.expected_value` does exactly this arithmetic and is
    reused rather than restated.
    """
    fair = fair_prob(row)
    odds = row.get("odds")
    if fair is None or implied(odds) is None:
        return None
    from .odds import expected_value
    return expected_value(fair, int(float(odds)))


def _started(row: dict, now=None) -> bool:
    """Has this row's game kicked off? The SAME rule the journal refuses
    on (`rules.game_has_started`, and `clock_says_started` under it), so
    a pick the page is still showing cannot be one the journal would
    refuse to record."""
    if row.get("live") or row.get("started"):
        return True
    from .rules import clock_says_started
    return clock_says_started(row.get("game_date") or row.get("date") or "",
                              row.get("kickoff") or "", now=now)


def disqualify(row: dict, now=None) -> str:
    """"" if this row could be the pick, else why it can never be today.

    Split from `shortfall` below on purpose. These are the refusals that
    make a row unshowable — no price, no number, not in the band, not
    placeable any more — and `build` will not fall back to one of them
    on a quiet day. The quality bars live in `shortfall`, and a row that
    fails only those is worth showing with the reason attached.
    """
    if fair_prob(row) is None:
        return "no fair probability to price against"
    book = str(row.get("book") or "").strip().lower()
    if not book or book == "proxy":
        return "no real market price"
    # A sharp book is the reference, never the ticket: Pinnacle does not
    # take US action, so a price quoted there is not a bet Ethan can
    # place. `odds.is_sharp_book` is the same check the ladder makes.
    from .odds import is_sharp_book
    if is_sharp_book(book):
        return "no real market price"
    odds = row.get("odds")
    if implied(odds) is None:
        return "price a book could not have posted"
    if not in_band(odds):
        return "the payout is outside the even-money band"
    # Asked again here although `likely.admissible` already refuses any
    # designation: a rule enforced in one place is not a rule, which is
    # this codebase's most-repeated lesson and is written into
    # `likely.admissible`'s own docstring.
    if str(row.get("injury_status") or "").strip():
        return "the player is carrying an injury designation"
    if _started(row, now):
        return "the game has already started"
    return ""


def shortfall(row: dict) -> str:
    """"" if this row clears the quality bars, else which one it missed.

    A row failing only these is still a real, placeable bet at a real
    price in the band — it just is not good enough to be the one pick
    the day is named after. `build` shows the best of them when nothing
    qualifies, and journals none of them.
    """
    # THE FIRST BAR IS WHOSE OPINION THIS IS, and it comes first because
    # it is the one Ethan changed. Our model measures 0.677 where the
    # market measures 0.722 (NFL moneylines) and 0.752 against 0.791
    # (CFB); on spreads and totals it measures nothing at all. A price
    # only our model disputes is not evidence of a mispriced game, it is
    # evidence of a model that is behind the market.
    # THE RESERVE, ADMITTED ON A DIFFERENT BASIS THAN IT WAS REFUSED.
    #
    # `likely` ships rows from below its own 55% floor, labelled, so its
    # page is never blank (`likely.RESERVE_MIN_PROB`). Until 2026-09-15
    # this module refused every one of them outright — "the board itself
    # says this did not clear its bar" — and that was answering the
    # wrong question. `likely.MIN_PROB` asks "is this MOST LIKELY?"; a
    # 53% sharp-anchored price at +100 is not, and is +6% EV, which is
    # precisely this feature's product. Selecting on another board's
    # product bar starved this one exactly where the band bites: no
    # in-band price can imply more than 58.8%, so the rows nearest the
    # band are the rows `likely` is likeliest to have cut.
    #
    # WHAT IS NOT WAIVED, and it is the whole safety of this. A reserve
    # row reaches the pick ONLY with a sharp or market witness — the
    # model tier is refused one line above, and the reserve band is
    # measured AT A LOSS on the model's own ranking (45-60% went -7.68%
    # over 184 settled rows, `likely.RESERVE_MIN_PROB`). That figure is
    # why this is not a general loosening: it admits these rows on a
    # sharper book's disagreement, never on our number, and the card
    # says `from_reserve` so a reader is told which they are looking at.
    # Whether that basis pays is untested here and the potd book's own
    # CLV is what will answer it (docs/PICK_OF_THE_DAY.md §7).
    #
    # ASKED BEFORE THE MODEL BAR, AND THAT ORDER IS LOAD-BEARING. The
    # first draft asked it after, where `evidence(row) == "model"` had
    # already returned — so the branch was unreachable and the widening
    # was resting on a line that could never run. Caught by
    # `test_a_reserve_row_needs_a_sharper_witness_than_us`. Asking first
    # also names the more specific truth: this row was cut upstream, and
    # our own number is not the thing that could put it back.
    if row.get("reserve") and evidence(row) == "model":
        return "the board itself says this did not clear its bar"
    if evidence(row) == "model":
        return "only our own model disputes this price"
    ev = edge(row)
    if ev is None:
        return "no fair probability to price against"
    if ev < MIN_EV:
        return "the price is not far enough off the fair to be worth it"
    fair = fair_prob(row)
    if fair is not None and fair < MIN_FAIR:
        return "more likely to lose than to win, even at a good price"
    auc = row.get("rank_auc")
    if auc is None:
        return "this market has never been measured"
    if float(auc) < MIN_RANK_AUC:
        return "this market ranks no better than a coin flip"
    # `bettable` is `calibrate.is_reliable` — whether this market's
    # probabilities have earned the right to be bet rather than read.
    # A showcase pick is a bet.
    if not row.get("bettable"):
        return "this market's probabilities are not reliable enough to bet"
    return ""


def refuse(row: dict, now=None) -> str:
    """Why this row is not the pick, hard reasons first. "" if it is a
    candidate."""
    return disqualify(row, now) or shortfall(row)


def rank_key(row: dict) -> tuple:
    """Sort key, best first: the strength of the WITNESS, then the size
    of the edge, then the better price.

    EVIDENCE OUTRANKS EDGE SIZE, and that inversion is the whole lesson
    of this module. Sorting on edge alone hands every day to whichever
    row has the loudest disagreement, and the loudest disagreements come
    from the weakest witness — a model that thinks a game is 12 points
    off the market is much more often wrong than the market is. Ranking
    on the tier first means a sharp-anchored 2.5% beats a consensus 5%,
    which is the order the measurements support.

    THE EDGE IS ROUNDED TO WHOLE POINTS BEFORE IT SORTS. 2.6% and 2.9%
    are the same claim about the world made twice; treating them as
    ranked is false precision, and it would hand the day to whichever
    row happened to round up while a materially better price sat one
    line below. Equal edge, better payout — which is Ethan's "flip of
    your money" served wherever it costs nothing.
    """
    tier = evidence(row)
    rank = EVIDENCE.index(tier) if tier in EVIDENCE else len(EVIDENCE)
    ev = round(float(edge(row) or 0.0), 2)
    return (rank, -ev, -(payout(row.get("odds")) or 0.0))


def choose(rows, now=None) -> tuple:
    """``(pick, best_below_bar, census)`` over a board's rows.

    ``pick`` is the best row clearing every bar, or None. ``best_below``
    is the best row that cleared the hard refusals and missed only a
    quality bar, or None. ``census`` counts every refusal by reason, so
    a day with no pick can say which gate was binding rather than
    shrugging — the funnel `likely.build` keeps, for the same reason.
    """
    census: dict = {}
    good, near = [], []
    for row in rows or []:
        hard = disqualify(row, now)
        if hard:
            census[hard] = census.get(hard, 0) + 1
            continue
        soft = shortfall(row)
        if soft:
            census[soft] = census.get(soft, 0) + 1
            near.append(row)
            continue
        good.append(row)
    good.sort(key=rank_key)
    near.sort(key=rank_key)
    return (good[0] if good else None,
            near[0] if near else None,
            census)


def _card(row: dict, below: str = "") -> dict:
    """The row as the page draws it: the board's own fields, plus the
    numbers this feature exists to show together."""
    fair = fair_prob(row)
    ev = edge(row)
    imp = implied(row.get("odds"))
    out = dict(row)
    out.update({
        # THE FAIR IS THE HEADLINE NUMBER, not the model's. Which
        # witness it came from is on the card beside it, because a
        # reader is entitled to know whether "56%" is Pinnacle's opinion
        # or ours.
        "fair_prob": None if fair is None else round(fair, 4),
        "evidence": evidence(row),
        # THE PRICE'S OWN BREAK-EVEN, under its own name. This used to
        # overwrite `implied_prob`, which on a `likely` row is the
        # DE-VIGGED fair (`likely._row_from`) and is what `fair_prob`
        # reads for the market tier — so the card was stomping the
        # number the selection had just been made on with a different
        # quantity that happens to look like it. Both now travel.
        "price_implied": None if imp is None else round(imp, 4),
        "from_reserve": bool(row.get("reserve")),
        # The model's own read still travels, clearly labelled as
        # context rather than as the reason — the policy every
        # sharp-anchored card on the site already follows.
        "model_prob": (None if row.get("model_prob") is None
                       else round(float(row["model_prob"]), 4)),
        # What a unit returns if it lands. The reason the band exists.
        "payout_units": round(payout(row.get("odds")) or 0.0, 3),
        # The edge, in units per unit staked, and in probability points
        # against the price. Small on purpose: a large one here would
        # mean the sharp fair and the shopped price had drifted apart
        # further than any real market allows, which is a bug.
        "ev_units": None if ev is None else round(ev, 4),
        "edge_points": (None if (fair is None or imp is None)
                        else round((fair - imp) * 100.0, 1)),
        # EMPTY ON A QUALIFYING PICK, and the reason on every other.
        # The page reads this one field to decide whether it is showing
        # the day's pick or the day's best available.
        "below_bar": below,
    })
    return out


def build(most_likely, sport: str, date: str, now=None) -> dict:
    """The day's pick for one sport, in the shape the board publishes.

    Never raises on a missing board: no rows is a day with no pick and
    a census that says the board was empty, which is a true statement
    about what we know rather than an exception a caller has to guard.
    """
    import datetime as _dt
    rows = [r for r in (most_likely or []) if isinstance(r, dict)]
    pick, near, census = choose(rows, now)
    out = {
        "sport": sport,
        "date": date,
        "generated_at": _dt.datetime.now(_dt.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "considered": len(rows),
        "census": census,
        "band": [MIN_ODDS, MAX_ODDS],
        "payout_band": [MIN_PAYOUT, MAX_PAYOUT],
        "min_ev": MIN_EV,
    }
    if pick is not None:
        out["pick"] = _card(pick)
        return out
    if near is not None:
        out["pick"] = _card(near, below=shortfall(near))
        return out
    out["pick"] = None
    out["note"] = ("No pick today: " + (
        "the board had no rows" if not rows
        else "nothing on the board is in the band at a real price"))
    return out


def attach(result: dict, sport: str, now=None) -> str:
    """Put the day's pick on a finished board. Returns a build-log line.

    ONE HOOK, CALLED FROM EVERY BUILD, for the reason
    `livepicks.attach_tracker` exists: five builds each assembling this
    inline is five chances for one of them to drift, and the drift shows
    up as a sport whose Pick of the Day quietly uses a different bar.

    NEVER RAISES. A board that cannot produce a pick is a day without
    one, which is a fact the page can render; an exception here would
    take down a build that had already priced everything else. The
    failure lands in the JSON as `pick_of_the_day_error`, where the page
    can see it, rather than only in a log the launcher swallows.
    """
    try:
        result["pick_of_the_day"] = build(
            result.get("most_likely") or [], sport,
            str(result.get("date") or ""), now=now)
    except Exception as exc:                                  # noqa: BLE001
        result["pick_of_the_day_error"] = str(exc)
        return f"pick of the day: error — {exc}"
    got = result["pick_of_the_day"]
    pick = got.get("pick")
    if pick is None:
        return f"pick of the day: none ({got.get('note', 'no candidate')})"
    where = f"{pick.get('player', '')} {pick.get('market_label') or pick.get('market', '')}".strip()
    if pick.get("below_bar"):
        return (f"pick of the day: BELOW THE BAR — {where} "
                f"({pick['below_bar']}); shown, not recorded")
    return (f"pick of the day: {where} at {pick.get('odds')} — "
            f"{pick.get('evidence')} fair "
            f"{round(float(pick.get('fair_prob') or 0) * 100)}%, "
            f"{pick.get('ev_units'):+.3f}u EV, pays "
            f"{pick.get('payout_units')}u")


#: Leagues the cross-board top pick considers, in the order a tie is broken.
#: NOT a ranking of how good each league's picks are — that would be an
#: assertion of exactly the kind this module refuses. It is a stable
#: order so that two picks identical on every measured quantity resolve
#: the same way on every run, instead of the answer depending on which
#: board finished writing first.
TOP_PICK_LEAGUES = ("nfl", "cfb", "mlb", "nba", "wnba")


def _pick_is_today(pick_of_the_day: dict, today: str) -> bool:
    """Is this board's pick for the day we are actually in?

    THE FAILURE THIS EXISTS FOR. Every board publishes its own file on
    its own schedule, and a league out of season — or one whose build
    threw — leaves a perfectly well-formed `pick_of_the_day` on disk
    from whenever it last ran. A cross-board chooser with no date check
    would happily crown a pick from a game that finished on Saturday and
    present it as today's, and nothing about the card would look wrong. This is the same shape as the stale price ceiling
    (`oddsapi.price_is_showable`) one layer up.
    """
    got = str((pick_of_the_day or {}).get("date") or "").strip()
    return bool(got) and got == str(today or "").strip()


def day_top_pick(boards: dict, today: str, now=None, locked=None) -> dict:
    """The one pick across EVERY league, or the reason there is not one.

    Ethan, 2026-09-15: "a model that picks one pick for the pick of the
    day, which is a guaranteed lock for the day." Singular, and for the
    DAY rather than for a league — `build` above produces one per sport,
    so a reader on the MLB page and a reader on the NFL page were being
    shown different "picks of the day" and neither was the day's.

    NOT NAMED FOR THE WORD HE USED, and the reason is at the top of this
    module: no bet is guaranteed, and "lock of the day" is on the banned
    list `tests/test_potd_card.py` keeps precisely so the page cannot
    promise a paying reader a certainty. The first draft of this feature
    was called `lock_of_the_day` end to end and would have put those
    four words on the card — the banned-list test did not catch it only
    because it scoped itself to the one renderer that existed when it
    was written. That gap is closed there; this is the same decision
    applied to the thing it was made about. What this IS is a
    comparative — the highest-ranked pick on the whole site today —
    which is a claim the ranking can actually support.

    WHY THIS IS A COMPARISON AND NOT A NEW MODEL. `rank_key` already
    orders picks on three quantities that know nothing about which sport
    they came from: which witness stands behind the fair, how big the
    edge is in points, and what the price pays. Nothing in it needs a
    per-league calibration, so the cross-board answer is the same
    comparator applied to a longer list. A separate cross-sport bar
    would be a second set of numbers to keep honest, measured on
    nothing.

    ``boards`` is ``{sport: published board dict}``. Returns the card
    plus the league it came from, the runners-up, and a census of every
    league that offered nothing and why.

    A QUALIFYING PICK ALWAYS BEATS A BELOW-BAR ONE, whatever the tiers
    say. `build` publishes its best available when nothing clears, so a
    below-bar row is on the board by design; letting one outrank a pick
    that cleared every gate would quietly undo the gates.

    ``locked`` IS THE CLAIM EACH LEAGUE ALREADY MADE — `ledger.
    locked_potd_keys`, the first qualifying pick journaled for each sport
    today. Pass it and a qualifying pick is considered ONLY if it is that
    pick.

    WHY THAT IS NOT OPTIONAL POLISH. The boards rebuild all day. Without
    it this function ranks whatever is on them at the moment it runs, so
    the day’s top pick could be an MLB bet at noon and, after that bet
    lost, an NFL one at eight — with nothing anywhere recording the first
    claim. That is choosing after seeing how the day is going, and it is
    the precise failure `ledger.log_pick_of_the_day` was given a lock to
    prevent one level down. Re-deriving a second lock here would be worse
    than none: two locks that disagree disagree invisibly.

    BELOW-BAR LEANS ARE EXEMPT, because they are not claims. Nothing
    journals them (`log_pick_of_the_day` refuses a `below_bar` row) and
    nothing records them, so there is no lock for them to match and the
    page still shows the strongest thing available on a day when no
    league cleared its bar.
    """
    import datetime as _dt
    clear: list = []
    below: list = []
    census: dict = {}

    def _tally(why: str) -> None:
        census[why] = census.get(why, 0) + 1

    order = {s: i for i, s in enumerate(TOP_PICK_LEAGUES)}
    seen = sorted((boards or {}).items(),
                  key=lambda kv: (order.get(kv[0], len(order)), kv[0]))
    for sport, board in seen:
        if not isinstance(board, dict):
            _tally(f"{sport}: no board")
            continue
        if board.get("pick_of_the_day_error"):
            _tally(f"{sport}: the board could not choose a pick")
            continue
        potd = board.get("pick_of_the_day") or {}
        pick = potd.get("pick")
        if not isinstance(pick, dict):
            _tally(f"{sport}: {potd.get('note') or 'no pick on the board'}")
            continue
        if not _pick_is_today(potd, today):
            _tally(f"{sport}: the board has not rebuilt today "
                   f"(its pick is dated {potd.get('date') or 'nothing'})")
            continue
        entry = dict(pick)
        entry["sport"] = sport
        if pick.get("below_bar"):
            below.append(entry)
            continue
        if locked is not None:
            from .ledger import potd_row_key
            want = locked.get(sport)
            got = potd_row_key(pick)
            if want is None:
                _tally(f"{sport}: nothing locked for today yet")
                continue
            if got is None or tuple(got) != tuple(want):
                # THE BOARD HAS MOVED ON AND THE CLAIM HAS NOT. The
                # league is showing a different pick than the one it
                # journaled this morning; the journaled one is what we
                # said, so the board's current favourite does not get to
                # stand in for it.
                _tally(f"{sport}: the board has changed its pick since "
                       f"the one it locked today")
                continue
        clear.append(entry)

    clear.sort(key=lambda p: (rank_key(p), order.get(p["sport"], len(order))))
    below.sort(key=lambda p: (rank_key(p), order.get(p["sport"], len(order))))

    out = {
        "date": str(today or ""),
        "generated_at": (now or _dt.datetime.now(_dt.timezone.utc))
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "leagues_seen": len(seen),
        "candidates": len(clear) + len(below),
        "census": census,
        "band": [MIN_ODDS, MAX_ODDS],
        "min_ev": MIN_EV,
    }
    winner = clear[0] if clear else (below[0] if below else None)
    if winner is None:
        out["pick"] = None
        out["sport"] = ""
        out["note"] = ("No top pick today: " + (
            "no league published a board" if not seen
            else "no league had a pick in the band"))
        return out
    out["pick"] = winner
    out["sport"] = winner.get("sport", "")
    # THE ONES IT BEAT, so the choice can be argued with. A single card
    # with nothing beside it is indistinguishable from a card chosen at
    # random, and this feature's entire claim is that the ORDER means
    # something.
    out["runners_up"] = [p for p in (clear + below) if p is not winner][:4]
    if winner.get("below_bar"):
        out["note"] = ("Nothing cleared the bar in any league today — this "
                       "is the best available, shown and not recorded.")
    return out


def top_pick_line(top: dict) -> str:
    """The build-log sentence. Never raises, never returns "".

    A cross-board step that prints nothing on a day it chose nothing is
    the failure `lineledger.record_note` and the rankings section were
    both dragged out of. The empty case gets the census.
    """
    try:
        pick = (top or {}).get("pick")
        if not pick:
            why = ", ".join(f"{k}" for k in sorted((top or {})
                                                   .get("census") or {}))
            return ("top pick: none — "
                    + (why or (top or {}).get("note", "no candidates")))
        where = (f"{pick.get('player', '')} "
                 f"{pick.get('market_label') or pick.get('market', '')}").strip()
        head = (f"top pick: {(top.get('sport') or '').upper()} "
                f"{where} at {pick.get('odds')}")
        if pick.get("below_bar"):
            return f"{head} — BELOW THE BAR ({pick['below_bar']}); shown, not recorded"
        # THE TIER IS RECOMPUTED IF THE CARD DID NOT CARRY IT. `_card`
        # always sets `evidence`, so this only fires on a card assembled
        # somewhere else — and "None fair 60%" in a build log is worse
        # than useless, because it reads like a measured absence.
        tier = pick.get("evidence") or evidence(pick)
        return (f"{head} — {tier} fair "
                f"{round(float(pick.get('fair_prob') or 0) * 100)}%, "
                f"beat {len(top.get('runners_up') or [])} other league pick(s)")
    except Exception as exc:                                  # noqa: BLE001
        return f"top pick: could not be described — {type(exc).__name__}: {exc}"
