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

#: THE CEILING ON A DISAGREEMENT WE WILL BET.
#:
#: Not a new number: it is `gamebets.SHARP_SUSPECT_EV`, imported so there
#: is one definition of "this gap is too big to believe". Past it,
#: `gamebets._sharpify` already sets grade Pass and stake 0.0 and writes
#: the reason onto the card — "a disagreement this big between books
#: usually means the sharp side repriced on news (scratch, injury,
#: weather) and this quote is stale, not free money".
#:
#: SO THE SITE ALREADY REFUSED TO STAKE THESE EVERYWHERE BUT HERE. The
#: edge board puts nothing on them. This feature took them at a full
#: unit and led the front page with them, which is the contradiction
#: that matters more than any backtest: one product, two answers to
#: whether the same price is trustworthy.
#:
#: AND THE MEASUREMENTS AGREE, twice, on two different samples of the
#: same data (droplet, 2026-09-16, MLB):
#:
#:   potd_backtest        under 4%  +71.4% (9)   4-7%  +47.1% (9)
#:                        7-15%      -7.2% (27)
#:   backtest_sharp_anchor  <4%     +29.3%       4-8% +17.0%
#:                        8-15%     -16.8%
#:
#: The first is one pick a day; the second is every price disagreement
#: on the board. Same direction, independently. 27 of the 45 picks in
#: that replay — sixty per cent — came from the losing bucket, because
#: `rank_key` sorts on the biggest edge and the biggest edges live here.
#:
#: A QUALITY BAR, NOT A HARD REFUSAL. The bet is real and placeable, so
#: a day whose only candidate is a suspect gap shows it as a lean with
#: this reason attached rather than going blank — the same treatment
#: every other `shortfall` row gets.
from .gamebets import SHARP_SUSPECT_EV as MAX_EV                # noqa: E402

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

#: WHAT A READER IS ACTUALLY BEING TOLD TO DO. One unit, flat, on the
#: day's pick and nothing on any other day.
#:
#: Ethan, 2026-09-15: the card "should say whether to bet". It did not.
#: It said a percentage, a fair, an edge and a payout, and left the one
#: question a reader came with — do I put money on this? — to be
#: inferred from which colour the border was. A lean and a pick were
#: told apart by a warning stripe and a sentence six lines down.
#:
#: FLAT, AND NOT A KELLY FRACTION, on purpose. This feature publishes
#: ONE pick a day chosen on the strength of the witness rather than the
#: size of the edge (`rank_key`), and the edges it clears are small by
#: construction — 2% to maybe 6%. Sizing those by Kelly would swing the
#: stake by a factor of three on differences this module has already
#: said it will not treat as ranked (`rank_key` rounds the edge to whole
#: points before sorting). A flat unit is also the shape the record
#: below the card is kept in, so the two agree.
STAKE_UNITS = 1.0

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
    # GAME MARKETS ONLY, and it is asked first because no other bar can
    # rescue a row this one turns away.
    #
    # Ethan, 2026-09-15: "i do want the pick of the day to be moneylines
    # and spreads only for all sports ... feels like relying on one
    # player is more volitole and risky instead of relying on a whole
    # team." Half right, and the other half is the stronger argument. A
    # single bet's variance is p(1-p) whatever it is about, so a 60%
    # player prop and a 60% moneyline are equally bumpy. What a player
    # really carries is ESTIMATION error we cannot see — ejected, pulled
    # after four innings, rested, a hamstring in the first.
    #
    # THE DECIDING REASON IS THE EVIDENCE LADDER. `exchangefair.MARKETS`
    # is moneyline and nothing else, because the exchange lists game
    # winners; and a sharp book's player-prop coverage is thin to absent.
    # So a player prop is structurally stuck near the bottom of
    # `EVIDENCE` — and `shortfall` refuses a model-only row outright.
    # The selector was choosing the day's headline from a pool most of
    # which could never meet the standard it holds them to. On the MLB
    # board of 2026-09-15: 52 rows, 0 sharp, 0 market, 0 exchange.
    #
    # Props keep their own boards — Most Likely, Long Shots, the props
    # scanner. They stop being eligible for the day's name.
    from .ledger import is_game_row
    if not is_game_row(row):
        return "a player prop — the day’s pick is game markets only"
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
    if ev > MAX_EV:
        return "the gap is too big to trust — the sharp side has probably moved"
    fair = fair_prob(row)
    if fair is not None and fair < MIN_FAIR:
        return "more likely to lose than to win, even at a good price"
    # THE RANKING BAR IS A STATEMENT ABOUT OUR MODEL, so it is asked of
    # the rows our model is the witness for.
    #
    # Ethan, 2026-09-16: "do what's best to make this pick of the day
    # feature the best it can be", on learning that his spreads-and-
    # totals decision was in practice moneylines only.
    #
    # `MIN_RANK_AUC` is `likely.rank_auc` — measured by replaying OUR
    # pricer over stored closes. On spreads and totals it reads 0.49 to
    # 0.50 in both football leagues, so it refused every one of them.
    # But this module never selects on our model's ranking: `shortfall`
    # refuses a model-only row outright two checks above, and what
    # reaches here is a row priced against an exchange's mid or a sharp
    # book's de-vigged pair. "Our spread model cannot rank covers" is
    # true and says nothing whatever about Pinnacle's number.
    #
    # AND RANKING IS THE WRONG QUESTION FOR THIS FEATURE. A board that
    # sorts by probability needs to know a market can be ordered. This
    # selector buys a PRICE DISAGREEMENT: a 50/50 outcome bought at +100
    # is +EV whether or not anybody can say which side lands. A spread
    # sits near 50% by construction — the book moves the number until
    # the money splits — which is precisely why nothing ranks it and
    # precisely why it can still be mispriced.
    #
    # WHAT STILL HOLDS, and it is most of the bar: the model tier is
    # refused above; `MIN_EV` wants 2% against the sharp fair; `MIN_FAIR`
    # wants the pick likelier to win than lose by that fair, which on a
    # spread is a real cut since half of them sit under it; and the
    # `market` tier below keeps the ranking bar, because a de-vigged
    # consensus is a number WE compute from a field WE choose, so our own
    # measurement does speak to it.
    #
    # NOT MEASURED, AND SAID PLAINLY: the sharp-anchor method has been
    # replayed on moneylines (docs/PICK_OF_THE_DAY.md §8) and never on
    # spreads or totals, because no sharp spread pair is stored to replay.
    # `potd_backtest.py` inherits that gap. This opens the markets on the
    # method's logic, not on a measurement of these markets.
    if evidence(row) not in ("exchange", "sharp"):
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


#: Where a build leaves the rows `likely.build`'s display caps dropped,
#: for `attach` to select over and then remove. Underscored because it is
#: a hand-off between two steps of one build and never a published field.
POOL_KEY = "_potd_pool"


def _same_row(row: dict, card: dict) -> bool:
    """Is this board row the one `_card` was built from?

    `_card` copies the row and adds fields, so identity is lost by the
    time `attach` wants to seat it. The journal's own key is the right
    comparison — it is what `relock` will look this pick up by, so a
    match here is exactly a match there.
    """
    from .ledger import potd_row_key
    a, b = potd_row_key(row), potd_row_key(card)
    return a is not None and b is not None and tuple(a) == tuple(b)


def verdict(payload: dict) -> dict:
    """The call, in the one shape both the page and the log read.

    ``{"call": "bet"|"no bet", "stake": units, "why": reason}`` — and on
    a bet, the book and price it is at.

    THE CARD LEADS WITH THIS. Everything else this module publishes is
    the working: the fair, whose fair it is, what the price implies, the
    edge, the payout, the record. A reader who reads none of it is still
    entitled to the answer, and until 2026-09-16 the card did not state
    one — it showed a lean and the day’s pick in the same furniture and
    distinguished them with a border colour and a sentence below the
    fold.

    A LEAN IS "NO BET", WITHOUT SOFTENING. `build` shows the best row on
    the board when nothing cleared, because a blank page tells a paying
    reader nothing; `ledger.log_pick_of_the_day` refuses to journal it.
    Those two facts already say the product does not stand behind it, so
    the call it gets here is the same call an empty board gets. The
    reason travels in `why` and the page prints it.

    PURE, AND OVER THE PUBLISHED PAYLOAD rather than over a row, so the
    answer cannot disagree with what was published: `relock` re-points
    the card at a pick chosen hours earlier, and a verdict derived from
    the board’s live rows could then say "bet" about a row the card is
    no longer showing.
    """
    pick = (payload or {}).get("pick")
    if not isinstance(pick, dict) or not pick:
        why = str((payload or {}).get("note") or "").strip()
        return {"call": "no bet", "stake": 0.0,
                "why": why or "no pick today"}
    below = str(pick.get("below_bar") or "").strip()
    if below:
        return {"call": "no bet", "stake": 0.0, "why": below}
    return {"call": "bet", "stake": STAKE_UNITS, "why": "",
            "book": str(pick.get("book") or ""),
            "odds": pick.get("odds")}


def relock(payload: dict, most_likely, locked_key, journal_pick=None) -> dict:
    """`_repoint` below, with the call recomputed over what it landed on.

    THE VERDICT IS DERIVED LAST, ALWAYS. Re-pointing can turn a card
    that led with "BET" into one showing nothing at all (the locked row
    left the board and the journal could not be read), and a verdict
    carried over from `build` would then still say bet. One line, here,
    rather than five inside `_repoint`’s branches.
    """
    out = _repoint(payload, most_likely, locked_key, journal_pick)
    out["verdict"] = verdict(out)
    return out


def _repoint(payload: dict, most_likely, locked_key, journal_pick=None) -> dict:
    """The published card, re-pointed at the pick this sport ALREADY
    LOCKED today. A new dict; ``payload`` is not touched.

    Ethan, 2026-09-15, looking at the MLB page: "the mlb is still showing
    the angles +1.5 as the pick of the day. idk if thats right or it
    should have been replaced."

    It was not right. The journal had locked Spencer Jones OVER 0.5 total
    bases that morning. By the evening his price had run from inside the
    band out to -180, `choose` refused him on price like any other row,
    and `build` fell through to its best-available lean — LAA +1.5. So
    the page showed one pick and the record held another, and nothing
    anywhere connected the two. A reader who saw the morning's pick had
    no way to find out what happened to it.

    THE LOCK WAS A VETO AND NOT A MEMORY, which is half a lock. It could
    refuse the board's new favourite; it could not produce the old one.
    `day_top_pick` had the same hole from the other side: it correctly
    declined a league whose board had moved on, then handed the day to a
    below-bar lean, which is exempt from locking precisely because
    nothing journals it. An unrecorded lean displacing a recorded claim
    is the exact churn `log_pick_of_the_day` was given a lock to stop.

    WHY THE BOARD ROW IS PREFERRED over the journaled one. The journal
    stores what a bet needs to settle — player, market, side, line, book,
    price. It does not store which witness stood behind the fair, and
    a card that has to say "model" because the tier was never written
    down would understate a pick that qualified on a sharp one. The row
    on the board carries all of it and carries TODAY'S price, so when the
    locked pick is still on the board — it usually is, refused on price
    rather than gone — the card is rebuilt from it in full. The journal
    is the fallback for the day the row really does leave.

    THE PRICE IS ALLOWED TO BE OUTSIDE THE BAND HERE, and that is the
    point rather than a leak. The bars choose the pick; once chosen, the
    claim stands at whatever the market does to it afterwards. `_card`
    computes, it does not refuse — `choose` is the only gate, and it has
    already run. What the card gains is `locked`, so the page can say
    the price has moved since the pick was made instead of pretending
    this is a fresh recommendation at -180.
    """
    out = dict(payload or {})
    if not locked_key:
        return out
    want = tuple(locked_key)
    from .ledger import potd_row_key
    current = out.get("pick")
    if isinstance(current, dict) and not current.get("below_bar"):
        got = potd_row_key(current)
        if got is not None and tuple(got) == want:
            # Already the locked pick. Say so on the card rather than
            # leaving the reader to infer it from the record page.
            out["pick"] = {**current, "locked": True}
            return out
    # The board has moved on. Find the locked row where it still lives.
    for row in (most_likely or []):
        if not isinstance(row, dict):
            continue
        got = potd_row_key(row)
        if got is not None and tuple(got) == want:
            card = _card(row)
            card["locked"] = True
            out["pick"] = card
            out["relocked"] = ("the board moved on; this is the pick this "
                               "sport locked earlier today")
            return out
    if isinstance(journal_pick, dict) and journal_pick:
        out["pick"] = {**journal_pick, "locked": True, "off_board": True}
        out["relocked"] = ("the board no longer carries this row; shown from "
                           "the journal at the price it was locked at")
        return out
    # LOCKED, AND NOWHERE TO BE FOUND. Not a case to paper over with the
    # lean that happened to be underneath it: the sport has a claim on
    # the record for today, and a card showing something else would make
    # the page and the record disagree silently, which is the bug this
    # function exists for.
    out["pick"] = None
    out["relocked"] = ("this sport locked a pick today that is no longer on "
                       "the board and could not be read back from the journal")
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
    elif near is not None:
        out["pick"] = _card(near, below=shortfall(near))
    else:
        out["pick"] = None
        out["note"] = ("No pick today: " + (
            "the board had no rows" if not rows
            else "nothing on the board is in the band at a real price"))
    # ONE EXIT, so the call cannot be attached to two of the three
    # outcomes and forgotten on the third — which is how a page ends up
    # leading with "BET" on a day the engine declined.
    out["verdict"] = verdict(out)
    return out


def attach(result: dict, sport: str, now=None, cut=None) -> str:
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

    ``cut`` IS THE REST OF THE BOARD — the rows `likely.build` refused a
    SEAT rather than refusing on the merits (`likely.build`'s own `cut`
    argument). Ethan, 2026-09-16: "I think the selector should see the
    full game list so no prop or game is left unscanned."

    WHY THE SEAT WAS THE WRONG GATE FOR THIS. `GAME_LIMIT` keeps the
    twenty LIKELIEST game rows, and this module's band exists to throw
    the likeliest rows away — no in-band price can imply more than 58.8%.
    So the cap was discarding, by construction, the part of the board
    this feature shops in: a sharp-anchored +130 dog with a real edge
    sits at position 21 on a probability ranking and was never
    considered. The two rankings answer different questions and the cap
    only ever meant to answer the page's.

    NOTHING IS WAIVED. Every row in `cut` already cleared `likely
    .admissible` and every refusal in `from_prop` / `from_game_bet`, and
    it still has to clear `disqualify` and `shortfall` here. The pool
    grew; the bars did not move. Props in it are refused on the first
    line of `disqualify` (game markets only), which is why this takes
    the whole cut rather than a filtered one — the market policy lives
    in one place and the pool does not need to know it.
    """
    # WHERE THE CUT ROWS COME FROM, and why they arrive on the result.
    #
    # `cut` is the explicit door and is what tests use. The builds use
    # the key: NFL assembles its board inside `engine.pipeline` and calls
    # this from `nfl_build`, so there is no local variable to hand over —
    # the two are a dict apart. One mechanism for all five leagues beats
    # four explicit arguments and one smuggled key.
    #
    # POPPED, NOT READ. These rows are deliberately NOT on the published
    # board (`GAME_LIMIT` is a real page-weight decision and the MLB
    # payload is already 8 MB), so the key must not survive to
    # `gate.publish`. Popping here makes that structural rather than a
    # thing five builds each have to remember — see
    # `test_the_pool_never_reaches_the_published_board`.
    pool_key = result.pop(POOL_KEY, None)
    if cut is None:
        cut = pool_key
    try:
        seated = result.get("most_likely") or []
        pool = list(seated) + [r for r in (cut or []) if isinstance(r, dict)]
        result["pick_of_the_day"] = build(
            pool, sport, str(result.get("date") or ""), now=now)
    except Exception as exc:                                  # noqa: BLE001
        result["pick_of_the_day_error"] = str(exc)
        return f"pick of the day: error — {exc}"
    got = result["pick_of_the_day"]
    pick = got.get("pick")
    # A PICK FROM BEYOND THE CAP IS SEATED ON THE BOARD.
    #
    # Everything downstream finds the day's pick by looking for its row
    # among `most_likely`: `ledger.relock_potd` re-points the card at it
    # every build, the card's door opens the row's page, and the Live
    # tab maps the journal row back through the board. A pick that is
    # not there still works — `relock` falls back to the journal and
    # says `off_board` — but that fallback exists to DESCRIBE a rare
    # accident, and left alone this change would have made it the
    # normal state of every widened pick: a card reading "shown from the
    # journal at the price it was locked at" every night, with a price
    # that never refreshes.
    #
    # One row, appended rather than inserted, so the board's own
    # probability order is untouched for every reader that assumes it.
    # NEVER RAISES, like everything else in this function. A board whose
    # `most_likely` is not a list is not a reason to take down a build
    # that has already priced everything else — and the cost of failing
    # here is small and already handled: `relock` falls back to the
    # journal row and says `off_board`, which is precisely the case that
    # fallback was written for.
    try:
        if isinstance(pick, dict) and isinstance(seated, list) \
                and not any(r is pick for r in seated):
            for row in (cut or []):
                if row is pick or (isinstance(row, dict)
                                   and _same_row(row, pick)):
                    seated.append(row)
                    result["most_likely"] = seated
                    got["from_beyond_the_cap"] = True
                    break
    except Exception:                                         # noqa: BLE001
        pass
    if pick is None:
        return f"pick of the day: NO BET ({got.get('note', 'no candidate')})"
    where = f"{pick.get('player', '')} {pick.get('market_label') or pick.get('market', '')}".strip()
    if pick.get("below_bar"):
        return (f"pick of the day: NO BET — below the bar: {where} "
                f"({pick['below_bar']}); shown, not recorded")
    # THE LOG LEADS WITH THE CALL for the same reason the card does: the
    # operator reading `journalctl` is asking the same question the
    # reader is, and "pick of the day: TOR Moneyline at -118" does not
    # answer it on a day the engine declined.
    return (f"pick of the day: BET "
            f"{got.get('verdict', {}).get('stake', STAKE_UNITS):g}u on "
            f"{where} at {pick.get('odds')} — "
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
        out["verdict"] = verdict(out)
        return out
    out["pick"] = winner
    out["sport"] = winner.get("sport", "")
    # THE SAME CALL THE PER-LEAGUE CARD MAKES, over the row that won the
    # cross-board comparison. Derived here rather than copied off the
    # league board, because a below-bar lean can win this comparison on
    # a day no league cleared — and the league it came from published
    # "no bet" about that very row.
    out["verdict"] = verdict(out)
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
