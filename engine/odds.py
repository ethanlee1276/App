"""Sportsbook odds math: American odds, implied probability, de-vigging and
converting an edge into an expected-value figure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import SportsbookLine


def american_to_prob(odds: int) -> float:
    """Convert American odds to the book's implied probability (with vig)."""
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def american_to_decimal(odds: int) -> float:
    if odds < 0:
        return 1.0 + 100.0 / (-odds)
    return 1.0 + odds / 100.0


#: Assumed hold when a market is quoted on one side only.
#:
#: THE ONE DEFINITION. This was 1.05 here and 1.06 in `engine.longshots`
#: — the same concept under the same name with two values — and the split
#: was the worst way round. Four modules import the longshots one and
#: reason about it in prose (`devigfit`, `tdbook`, `cfb.tds`, `pipeline`
#: all say "6%"), while the function that actually computes a fair price
#: — `devig_two_way`, right below — quietly used 5%. The documented rule
#: and the enforced rule were different numbers.
#:
#: Standardised on 1.06, the documented one. 1.05 was undocumented and
#: further from the measurement: `engine.devigfit` puts the real shopped
#: hold on one-sided touchdown props near 8.6%, so both are guesses on
#: the low side and 1.05 was the lower.
#:
#: THE DIRECTION IS OPPOSITE IN THE TWO PATHS, which is why one number
#: serving both is delicate and worth saying out loud:
#:
#:   here          fair = implied / hold, and `betting.pick_side` takes
#:                 edge = model - fair. A wider hold LOWERS fair and
#:                 RAISES edge — permissive.
#:   longshots     `calibrated_prob` shrinks the model TOWARD implied. A
#:                 wider hold lowers implied and drags the model down,
#:                 cutting EV and publishing fewer picks — conservative.
#:                 That module's own note says so.
#:
#: So moving this 1.05 -> 1.06 loosens the recommendation board very
#: slightly (about 0.2 points of edge on a one-sided +400) and leaves the
#: long-shot board untouched, since that path already used 1.06. Small,
#: real, and in the direction the measurement points — but a pricing
#: change riding on a consistency fix, so it is stated rather than
#: buried.
#:
#: Neither number should be doing this work for long. The fix is for the
#: MEASUREMENT to reach this function, which is what `hold` below is for.
ONE_SIDED_HOLD = 1.06


def devig_two_way(over_odds: int, under_odds: int,
                  hold: float | None = None) -> tuple[float, float]:
    """Remove the vig from a two-way market, returning fair (over, under)
    probabilities that sum to 1.0.

    A missing side (odds of 0/None — e.g. home-run markets are quoted
    Over-only) de-vigs the quoted side with an assumed hold instead of
    pretending a fabricated opposite price is information.

    ``hold`` lets a caller that knows the sport and market supply the
    MEASURED one-sided hold (`longshots.one_sided_hold`) instead of the
    assumption. Without it the longshot board priced off a measurement
    the recommendation board could not see, so the same one-sided prop
    carried two different fair prices depending on which page asked —
    the failure engine/holdwatch exists to end, reappearing one level
    below it. Ignored entirely on a two-sided market, where both prices
    are real and nothing has to be assumed.

    ``hold`` may also be an `engine.devig.Devig` measured off the board
    being priced (the market-sum method). A Devig carries HOW the
    overround is shared out across prices, not just how big it is — a
    float flattens that, which is exactly the wrongness engine/devig's
    `as_devig` docstring warns about. The Devig devigs the quoted OVER;
    a one-sided UNDER (a market shape the HR/TD boards never produce)
    falls back to its overall multiplier.
    """
    dv = hold if hasattr(hold, "fair") else None
    hold = ONE_SIDED_HOLD if (dv or not hold) else float(hold)
    # An arithmetically impossible pair — the fabricated-under classic,
    # "over +850 / under -110" summing to 63% — is treated as one-sided
    # on the over, exactly as longshots._price and the scanner treat it.
    # This path did not check, and "devigging" the corrupt pair INFLATED
    # both fairs at once: the under's toward certainty (which is how
    # 'Under 0.5 Home Runs' reached the best-bets board, 2026-09-01)
    # and the over's by half again.
    if over_odds and under_odds and not pair_is_sane(over_odds, under_odds):
        under_odds = 0
    if not under_odds and over_odds:
        raw = american_to_prob(over_odds)
        fair_over = min(0.99, dv.fair(raw) if dv else raw / hold)
        return fair_over, 1.0 - fair_over
    if not over_odds and under_odds:
        raw = american_to_prob(under_odds)
        div = (1.0 + getattr(dv, "overround", 0.0)) if dv else hold
        fair_under = min(0.99, raw / max(div, 1.0))
        return 1.0 - fair_under, fair_under
    if not over_odds and not under_odds:
        return 0.5, 0.5
    p_over = american_to_prob(over_odds)
    p_under = american_to_prob(under_odds)
    total = p_over + p_under
    if total <= 0:
        return 0.5, 0.5
    return p_over / total, p_under / total


def expected_value(model_prob: float, odds: int, stake: float = 1.0) -> float:
    """EV of a 1-unit bet given the model's true win probability."""
    dec = american_to_decimal(odds)
    win = (dec - 1.0) * stake
    return model_prob * win - (1.0 - model_prob) * stake


@dataclass
class BestLine:
    book: str
    line: float
    odds: int
    fair_prob: float      # de-vigged implied probability at this book


#: A field of fewer than this many books is not a consensus, it is a
#: coincidence. Below it :func:`consensus_fair` returns None rather than
#: a number that would read as the market's opinion.
MIN_CONSENSUS_BOOKS = 3


def consensus_fair(lines: list[SportsbookLine], line: float | None = None
                   ) -> tuple[float, int] | None:
    """The FIELD's de-vigged fair for the over, and how many books it is.

    ``best_over_line`` de-vigs the book being bet, which makes the
    benchmark move with the outlier: the further out of line a price is,
    the more likely it is selected AND the lower its own fair, so the edge
    grows with the outlier before the model has said anything. That is a
    structural loop, and this is the number that closes it — the market's
    opinion, taken from every book quoting the same number rather than
    from the one we happened to shop to.

    Median, not mean: one stale book should not define a field, which is
    the same reason the close-picker uses one.

    ``line`` restricts the field to books quoting that number, because a
    fair at 1.5 and a fair at 2.5 are opinions about different events and
    averaging them is not a consensus about either.

    NOTHING PRICES FROM THIS YET. It is journaled as evidence so the
    question "would measuring against the field have been better?" can be
    answered from the record instead of argued about. See bookcheck.py.
    """
    fairs = []
    for ln in lines:
        if (ln.book or "").lower() == "proxy":
            continue                      # a proxy is not a market opinion
        if line is not None and ln.line != line:
            continue
        fair_over, _ = devig_two_way(ln.over_odds, ln.under_odds)
        if 0.0 < fair_over < 1.0:
            fairs.append(fair_over)
    if len(fairs) < MIN_CONSENSUS_BOOKS:
        return None
    fairs.sort()
    n = len(fairs)
    med = fairs[n // 2] if n % 2 else (fairs[n // 2 - 1] + fairs[n // 2]) / 2.0
    return med, n


#: American odds cannot fall strictly between -100 and +100. The two
#: scales meet at even money and there is nothing between them left to
#: express: a book quotes that price +100, or -100, never -97. Anything
#: inside the gap was never posted by anyone. It is a decimal price
#: stored as American, a percentage, a truncated string.
#:
#: Zero is separate and legitimate — it is this codebase's sentinel for
#: a side the book does not quote at all (see devig_two_way), and is not
#: a corrupt price.
DEAD_ZONE = (-100, 100)

#: How far one book's implied probability may sit BELOW the median of
#: the OTHER books quoting the same bet before its price is not shopped,
#: in probability points. Measured, not chosen: Ethan, 2026-09-04, Cam
#: Edwards to score — Hard Rock -155 (60.8%) against FanDuel -260,
#: DraftKings -270 and Caesars -280 (the others' median 73.0%), a gap of
#: 12.2 points, read from the droplet's own cached payload on 09-05. An
#: ordinary shopping spread between books on a favourite is 2-5 points;
#: a price this far off the field is a stale or mis-posted quote at one
#: book, and the shop selected for it exactly the way it selects for a
#: dead-zone digit: the outlier is, by construction, the best number.
OUTLIER_GAP = 0.10

#: Fewer books than this is not a field to be an outlier from.
OUTLIER_MIN_BOOKS = 3


def field_outliers(odds_list) -> list[bool]:
    """One flag per quote: is this price an outlier against the others?

    Leave-one-out: each quote is measured against the MEDIAN implied
    probability of the other quotable prices, so the outlier itself
    never drags the field toward it. A quote that is not a real price
    (``is_quotable`` False, the unquoted-side 0 included) is never an
    outlier and never part of anyone else's field. With fewer than
    ``OUTLIER_MIN_BOOKS`` quotable prices nothing is flagged: two books
    that disagree are a disagreement, not a consensus and a stray.
    """
    probs = []
    for o in odds_list:
        try:
            probs.append(american_to_prob(int(o)) if is_quotable(o) else None)
        except (TypeError, ValueError):
            probs.append(None)
    real = [p for p in probs if p is not None]
    if len(real) < OUTLIER_MIN_BOOKS:
        return [False] * len(probs)
    out = []
    for i, p in enumerate(probs):
        if p is None:
            out.append(False)
            continue
        others = sorted(q for j, q in enumerate(probs) if j != i and q is not None)
        m = len(others)
        med = others[m // 2] if m % 2 else (others[m // 2 - 1] + others[m // 2]) / 2.0
        out.append(med - p > OUTLIER_GAP)
    return out


def is_quotable(odds) -> bool:
    """Is this a price a book could actually have posted?

    ``american_to_prob`` converts a dead-zone number without complaint:
    -97 comes back 49.2%, right in the middle of the range where nothing
    downstream has any reason to question it. Worse, it then WINS the
    best-price shop — -97 pays better than -105 — so a corrupted digit
    does not merely survive, it is selected for, and the smaller implied
    probability it carries is booked as edge the model did not find.

    False for 0 as well: an unquoted side is not a price. Callers that
    must keep the unquoted-side sentinel use ``shoppable`` instead.
    """
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return False
    return not (DEAD_ZONE[0] < o < DEAD_ZONE[1])


def shoppable(odds) -> bool:
    """``is_quotable``, but the unquoted-side sentinel 0 passes.

    Line shopping runs over both sides at once, and an Over-only market
    carries under_odds of 0 on every book. Dropping those rows would
    delete the market rather than clean it.
    """
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return False
    return o == 0 or is_quotable(o)


#: Books nobody here can bet, matched loosely on purpose.
#:
#: THREE COPIES OF THIS PREDICATE EXISTED AND ONE PATH HAD NONE. The
#: quotes carry display names ("Pinnacle"), `oddsapi.SHARP_BOOKS` carries
#: API keys ("pinnacle"), and a strict comparison between the two answers
#: False forever — the most expensive kind of wrong, because it looks
#: like a finding about the market. `linemoves._is_sharp` and
#: `booksharp.compare_to_the_list` each carried their own copy of the
#: loose match and now share this one, so the function that REFUSES to
#: shop a sharp book and the report that NAMES the sharp books cannot
#: drift apart about which book is which.
def is_sharp_book(book: str) -> bool:
    """Is this the sharp reference rather than a book a user can bet?

    `oddsapi.SHARP_BOOKS` says it in its own comment: "Books a user can
    actually bet at (Pinnacle doesn't take US action); the sharp
    reference must never be quoted as the price to take."
    """
    try:
        from .sources.oddsapi import SHARP_BOOKS
    except Exception:                                       # noqa: BLE001
        SHARP_BOOKS = {"pinnacle"}
    b = (book or "").strip().lower().replace(" ", "")
    if not b:
        return False
    return any(s.lower().replace(" ", "") in b for s in SHARP_BOOKS if s)


def _without_outliers(lines, price_of):
    """The lines minus the outliers, judged within each line value."""
    keep = []
    by_line: dict = {}
    for ln in lines:
        by_line.setdefault(ln.line, []).append(ln)
    for group in by_line.values():
        flags = field_outliers([price_of(ln) for ln in group])
        keep.extend(ln for ln, bad in zip(group, flags) if not bad)
    return keep


def best_over_line(lines: list[SportsbookLine], hold: float | None = None) -> BestLine:
    """Pick the most bettor-friendly OVER line across books.

    We prefer the lowest line, breaking ties by the best (highest) odds. This
    is the "shop for the best number" step every sharp bettor does.
    """
    best: BestLine | None = None
    # A corrupt price is not shopped. It would win: the tie-break below
    # takes the highest odds, and a dead-zone number is by construction
    # better than any real one on its side of even money.
    clean = [ln for ln in lines if shoppable(ln.over_odds)]
    # AND A PRICE NOBODY HERE CAN TAKE IS NOT SHOPPED EITHER, for the
    # same reason and with the same shape. Every other price parser in
    # `sources.oddsapi` drops the sharp reference — `parse_event_lines`,
    # `parse_event_h2h`, `parse_event_totals`, `parse_event_spreads` —
    # but `parse_event_scorers` never did, and its quotes become
    # SportsbookLines at 0.5 for every anytime-touchdown prop in both
    # football leagues. A sharp book runs a thinner margin, so on a
    # favourite its price is by construction the highest American number
    # on the board and wins this `max` outright: the card then prints,
    # and the likelihood board's -250 chalk cap then measures, a price
    # at a book that does not take the action.
    #
    # THE DE-VIG STILL SEES IT. `devig.board_fair` takes the MEDIAN
    # de-vigged price across every book that quoted the player, and a
    # sharp book belongs in that median — dropping it there would make
    # the consensus worse. The refusal is about which price we tell
    # someone to TAKE, which is this function and nothing else.
    #
    # Falls back to the full field when nothing bettable is left, the
    # same doctrine as the dead-zone filter above and as
    # `betting.pick_side`'s implausible-quote filter: a market where
    # every book looks unusable still returns a line to display, and the
    # caller's own gate is what refuses to price it. Dropping the player
    # instead would turn a bad price into an empty board, which is the
    # failure that reads as an ordinary result.
    bettable = [ln for ln in clean if not is_sharp_book(ln.book)]
    # AND A PRICE OFF THE FIELD IS NOT SHOPPED, for the third time with
    # the same shape (see OUTLIER_GAP): among the books quoting the SAME
    # line — a lower line carries a worse price on purpose and is not
    # comparable — a quote sitting further under the others' median than
    # the gap is left out of the shop. Falls back to the field when the
    # rule would leave nothing, like the two refusals above it.
    field = bettable or clean or lines
    field = _without_outliers(field, lambda ln: ln.over_odds) or field
    for ln in field:
        fair_over, _ = devig_two_way(ln.over_odds, ln.under_odds, hold)
        cand = BestLine(ln.book, ln.line, ln.over_odds, fair_over)
        if best is None:
            best = cand
            continue
        if ln.line < best.line or (ln.line == best.line and ln.over_odds > best.odds):
            best = cand
    assert best is not None
    return best


def best_under_line(lines: list[SportsbookLine], hold: float | None = None) -> BestLine:
    """Pick the most bettor-friendly UNDER line across books.

    Mirror image of ``best_over_line``: for an under you want the *highest*
    line (more cushion), breaking ties by the best (highest) under odds.
    """
    best: BestLine | None = None
    clean = [ln for ln in lines if shoppable(ln.under_odds)]
    # The same refusal as the over side; see `best_over_line`.
    bettable = [ln for ln in clean if not is_sharp_book(ln.book)]
    field = bettable or clean or lines
    field = _without_outliers(field, lambda ln: ln.under_odds) or field
    for ln in field:
        _, fair_under = devig_two_way(ln.over_odds, ln.under_odds, hold)
        cand = BestLine(ln.book, ln.line, ln.under_odds, fair_under)
        if best is None:
            best = cand
            continue
        if ln.line > best.line or (ln.line == best.line and ln.under_odds > best.odds):
            best = cand
    assert best is not None
    return best


# A book's two sides must sum to MORE than 100% — that sum minus one is
# its margin, which is how it makes money. A pair summing meaningfully
# below 100% is not a gift, it is corrupt data: most often an over-only
# prop (home runs) whose absent under got filled with a placeholder.
# Measured on harvested rows: Caesars showing "over +850 / under -110"
# on a home run, which implies 10.5% + 52.4% = 63% and reads as a 37%
# arbitrage against itself.
#
# Genuine cross-book arbitrage exists but is small — a 5% cushion admits
# every real one while rejecting fabrications.
PAIR_SANITY_FLOOR = 0.95


def pair_is_sane(over_odds, under_odds) -> bool:
    """False when a single book's over/under pair is arithmetically
    impossible, i.e. the two sides imply less than PAIR_SANITY_FLOOR."""
    try:
        o, u = int(over_odds), int(under_odds)
    except (TypeError, ValueError):
        return False
    if not o or not u:          # 0 = side not offered
        return False
    return (american_to_prob(o) + american_to_prob(u)) >= PAIR_SANITY_FLOOR
