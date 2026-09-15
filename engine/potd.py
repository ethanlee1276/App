"""The Pick of the Day: one pick per sport, per day, at close to even money.

Ethan, 2026-09-15: "I want too to a 'Pick of the day' for each sport
where we find 1 pick that is guaranteed to hit. It can be a money line
or a game total or an over or under or whatever we want ... We want the
price of the prop too fall in between -190 and +190 so we can basically
have a 'one props doubles money' type of hit."

THE WORD "GUARANTEED" IS NOT BUILT HERE, and the disagreement is
recorded rather than quietly ignored, because somebody reading this in
six months needs to know it was raised. No bet is guaranteed. A page
that tells a paying reader otherwise turns one ordinary loss into a
broken promise, and this module would be the thing that made the
promise. What is built instead is the strongest single pick the boards
can defend on the day, in the band he asked for, with its own record
beside it so the claim is checkable rather than asserted.

THE BAND DECIDES THE TRADE, NOT US. His two goals pull against each
other and the prices say by how much: -190 is the market claiming 65.5%
and paying 0.53 units, +190 is the market claiming 34.5% and paying
1.90. To find a 70% pick at +190 we would have to be right that the
market is wrong by thirty-five points, and the standing lesson of this
codebase (see `betting.MAX_CREDIBLE_EDGE`, and every card that has ever
claimed a huge edge at a sharp number) is that when our number disagrees
with the market that violently, ours is the one that is wrong. So
`MIN_PROB` below is the knob between "almost always hits" and "doubles
your money", and the arithmetic of what moving it costs is written out
on the constant.

WHERE THE CANDIDATES COME FROM. The Most Likely board, and nothing
else. That board is already calibrated, already priced off real books,
already deduped, and already carries a measured ranking score per sport
and market (`likely.rank_auc`). Ethan asked to "use our current models
too find this pick but obv gonna have too tighten up for this specific
idea only" — so this is a tightening pass over that board's output
rather than a second model, and it cannot drift away from the numbers
the rest of the site shows.

A DAY WITH NOTHING GOOD ENOUGH SAYS SO. `build` still returns the best
in-band candidate on such a day, flagged `below_bar` with the reason it
fell short, so the page is never blank — the pattern the boards already
use (`likely.RESERVE_MIN_PROB`). It is NOT journaled. The record this
feature keeps has to answer "how do the picks that qualified do", and a
book padded with rows the selector itself refused would answer a
different question on exactly the thinnest days.
"""

from __future__ import annotations

from .betting import MAX_CREDIBLE_EDGE

#: The price band, Ethan's own numbers. Not a quality bar — it is the
#: product definition, which is why a row outside it is disqualified
#: outright rather than shown as a near miss: "the most likely thing on
#: the card today is a -400 favourite" is not this feature having a
#: quiet day, it is a different feature.
MIN_ODDS = -190
MAX_ODDS = 190

#: THE CONFIDENCE FLOOR, and the knob between his two goals.
#:
#: Read it against `MAX_CREDIBLE_EDGE` (0.10), because the two together
#: decide which prices can ever qualify. A pick must clear this floor
#: AND sit within ten points of the book's own de-vigged number, so the
#: market's implied probability must itself be at least MIN_PROB - 0.10:
#:
#:     floor 0.58  ->  implied >= 0.48  ->  prices out to +108
#:     floor 0.60  ->  implied >= 0.50  ->  prices out to +100
#:     floor 0.62  ->  implied >= 0.52  ->  prices out to -108
#:     floor 0.65  ->  implied >= 0.55  ->  prices out to -122
#:
#: 0.60 is chosen because it is the highest floor that still leaves the
#: even-money end of his band reachable: at exactly +100 a qualifying
#: pick doubles the stake, which is the thing he asked for in as many
#: words. Raising it buys confidence and costs the plus-money half of
#: the band; lowering it does the reverse. Nothing else in this module
#: has to move with it.
MIN_PROB = 0.60

#: A market has to have shown it can rank this outcome better than a
#: coin flip before one pick a day rides on it. `likely.rank_auc` is the
#: measured figure per sport and market; the markets this codebase has
#: measured at 0.49 (see `GAME_RANK_MEASURED`) are exactly the ones a
#: showcase pick must never come from, and an unmeasured market is not
#: a pass by default — it is the same unknown wearing a blank.
MIN_RANK_AUC = 0.55

#: Every reason `disqualify` can give. A row refused for one of these is
#: never shown, not even as a near miss: it is missing something the
#: page needs (a price, a probability), or it is outside the product's
#: own definition (the band), or it is a bet nobody could still place.
HARD_REASONS = (
    "no probability",
    "no real market price",
    "price a book could not have posted",
    "priced outside the even-money band",
    "no market number to check the model against",
    "the player is carrying an injury designation",
    "the game has already started",
    "the board itself says this did not clear its bar",
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
    number the band exists to make large. Decimal odds minus the stake,
    off the same converter, for the reason `implied` gives."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    from .odds import american_to_decimal
    return american_to_decimal(o) - 1.0


def in_band(odds) -> bool:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return False
    # A price between -100 and +100 does not exist on an American board;
    # anything claiming to be there is a broken quote, not a coin flip.
    if -100 < o < 100:
        return False
    return MIN_ODDS <= o <= MAX_ODDS


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
    if row.get("model_prob") is None:
        return "no probability"
    # The Most Likely board ships rows from below its own floor when
    # nothing cleared, labelled, so the page is never blank
    # (`likely.RESERVE_MIN_PROB`). A row its own maker says did not
    # qualify cannot be the pick of the day on any reading.
    if row.get("reserve"):
        return "the board itself says this did not clear its bar"
    book = str(row.get("book") or "").strip().lower()
    if not book or book == "proxy":
        return "no real market price"
    odds = row.get("odds")
    if implied(odds) is None:
        return "price a book could not have posted"
    if not in_band(odds):
        return "priced outside the even-money band"
    if row.get("implied_prob") is None:
        return "no market number to check the model against"
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
    prob = float(row["model_prob"])
    if prob < MIN_PROB:
        return "under the confidence floor"
    fair = row.get("implied_prob")
    if fair is not None and abs(prob - float(fair)) > MAX_CREDIBLE_EDGE:
        return "the model disagrees with the market by more than we credit"
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
    """Sort key, best first: confidence, then the better price.

    THE PROBABILITY IS ROUNDED TO WHOLE POINTS BEFORE IT SORTS, and that
    is the whole point of the tie-break rather than an accident of
    formatting. 66.1% and 66.4% are the same claim about the world made
    twice; treating them as ranked is false precision, and it would hand
    the day to whichever row happened to round up while a materially
    better price sat one line below. Equal confidence, better payout —
    which is Ethan's "doubles money" served wherever it costs nothing.
    """
    prob = round(float(row.get("model_prob") or 0.0), 2)
    return (-prob, -(payout(row.get("odds")) or 0.0))


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
    three numbers this feature exists to show together."""
    prob = float(row.get("model_prob") or 0.0)
    fair = row.get("implied_prob")
    out = dict(row)
    out.update({
        "model_prob": round(prob, 4),
        "implied_prob": None if fair is None else round(float(fair), 4),
        # What a unit returns if it lands. The reason the band exists.
        "payout_units": round(payout(row.get("odds")) or 0.0, 3),
        # How far our number sits from the book's, in points. Small on
        # purpose: `MAX_CREDIBLE_EDGE` caps it, and a reader seeing a
        # large one here would be looking at a bug.
        "edge_points": None if fair is None
        else round((prob - float(fair)) * 100.0, 1),
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
        "min_prob": MIN_PROB,
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
            f"{round(float(pick.get('model_prob') or 0) * 100)}%, "
            f"pays {pick.get('payout_units')}u")
