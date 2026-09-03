"""Where did tonight's props die? One count per first-failing gate.

"878 analyzed → 1 recommended" is a number a reader has to trust. The
same line with a funnel under it is a number they can check, and the
difference is the whole trust question — an empty board and a broken
board look identical without one.

MLB has had this since its own thin nights forced the question, and the
front end renders whatever `gate_census` a board publishes. NFL and CFB
never emitted one, which is why this module exists rather than a third
copy of the counting: with the football season opening, a quiet Sunday
board would have said "nothing qualified" and offered nothing to check.

WHY THIS COUNTS `checks` RATHER THAN RE-DERIVING THE GATES. MLB's census
recomputes each threshold from the row's edge, tier and quality — it
predates the checks list and has to. Recomputing is a second
implementation of the rules that can drift from the first, and a funnel
that disagrees with the decision it explains is worse than no funnel.
Every rule decision already publishes an ORDERED list of conditions with
pass/fail on each (engine/rules.condition), so the first failing one IS
the answer, by construction.

THE FIRST FAILURE, NOT EVERY FAILURE: a prop that misses three gates is
one death, not three, or the census would sum past the props analyzed
and read as a rendering fault.
"""

from __future__ import annotations

#: Gate key → the words the board shows. Anything not named here falls
#: back to the raw key, so a new gate appears in the funnel the day it is
#: added rather than being silently swallowed.
GATE_WORDS = {
    "grade": "model graded it a Pass",
    "pregame": "game already started — this model prices pre-game only",
    "confidence": "confidence under the threshold",
    "edge": "edge under the minimum",
    "juice": "priced too rich to be worth laying",
    "health": "an injury designation on him",
    "kelly": "the price already matches our number (no stake)",
    "lineup": "waiting on the lineup card",
}

#: Counted before any gate, because the model never got a say.
NO_PRICE = "no_real_price"


def census(rows: list[dict], skip=None, sport: str = "") -> dict:
    """``{bucket: count}`` over a board's recommendation rows.

    ``skip(row)`` optionally excludes rows that belong to another board
    (the long-shot markets, say) so their working-as-intended deaths do
    not read as a broken model.

    ``sport`` enables the calibration bucket. A market whose fit ran to
    the edge of the search grid is refused wholesale by
    `betting.evaluate_prop`, and every prop in it dies the same death —
    so counting them under a generic gate turns the single most important
    fact about a thin board into a shrug. On 2026-08-29 the NFL board
    recommended 0 of 285 with rush_yds and rec_yds both closed exactly
    this way, and the printout said only "0 recommended". MLB's own
    census has named these since its thin nights; this is that idea, in
    the module both boards share.

    THE PRICE COMES FIRST, and this counter had it the other way round.
    A prop in a closed market that no book ever quoted is BOTH unpriced
    and closed, and the order decides which fact gets reported. Counting
    calibration first charged the model for props it was never asked
    about: `NO_PRICE`'s own comment three lines above the loop says
    "counted before any gate, because the model never got a say", MLB's
    census has always taken them in that order, and the front end sorts
    `no_real_price` into "never reached the model" while every other
    bucket sits under "priced and rejected — N props reached the model".
    So an unpriced rushing prop counted here was displayed as one the
    model had priced and refused. It had not been priced by anybody.

    That matters because this number is the one being read. NFL, on the
    droplet 2026-09-03: no real price 64 · calibration 169 · grade 44,
    and Ethan reading it as "the rushing/receiving fits are the single
    biggest reason NFL shows zero picks". Any part of the 169 that never
    carried a book line belongs in the 64, and moving it does not change
    a single bet — it changes which explanation the board offers for
    having none.

    The NAMES are gathered from every row in a closed market, priced or
    not. The count says how many props the closure actually killed
    tonight; the list says which markets are shut, which stays true on a
    night when nothing in them was quoted anyway.
    """
    out: dict = {"recommended": 0, NO_PRICE: 0}
    closed: set = set()
    is_reliable = None
    if sport:
        from .calibrate import is_reliable as _rel
        is_reliable = _rel
    for r in rows or []:
        if skip is not None and skip(r):
            continue
        if r.get("recommended"):
            out["recommended"] += 1
            continue
        shut = (is_reliable is not None and r.get("market")
                and not is_reliable(sport, r["market"]))
        if shut:
            closed.add(r.get("market_label") or r.get("market"))
        if r.get("has_market") is False:
            # WHICH markets go unpriced matters: books post a line for
            # most starters but scorer markets for a handful, so a big
            # count here is usually the shape of the books' menu rather
            # than a broken join. Named, it is checkable.
            out[NO_PRICE] += 1
            by = out.setdefault("no_price_markets", {})
            label = r.get("market_label") or r.get("market") or "?"
            by[label] = by.get(label, 0) + 1
            continue
        if shut:
            out["calibration"] = out.get("calibration", 0) + 1
            continue
        failed = next((c.get("key") for c in (r.get("checks") or [])
                       if not c.get("passed")), None)
        key = failed or "held_by_rules"
        out[key] = out.get(key, 0) + 1
    if closed:
        # NAMED, because "calibration 172" is a mystery and "rush_yds and
        # rec_yds are closed until their fits come off the boundary" is
        # something to act on.
        out["calibration_markets"] = sorted(closed)
    return out


def reason_key(text: str) -> str:
    """Strip the NUMBERS out of a pass reason, keep the category.

    Reasons are written for a card, so they carry that pick's own
    figures: "edge -1.7% < required 4.5% over break-even 52.4%". Tallied
    verbatim, every pick becomes its own row and the census turns into a
    list — two hundred rows reading 1. What a reader wants is "edge
    under required: 186", so the digits go and the sentence stays.

    Lifted here from engine/nba/pipeline, which wrote it first and now
    calls it, because CFB's board needs exactly the same bucketing and a
    second copy would drift.
    """
    import re
    head = str(text or "other").split("\u2014")[0].split("(")[0]
    head = re.sub(r"[-+]?\d[\d,.]*%?", "", head)           # drop the figures
    head = re.sub(r"[<>=]+", "", head)
    head = re.sub(r"\s+", " ", head).strip(" .,:;").lower()
    return (head or "other")[:60]


def census_from_reasons(published: list, passed: list, held=None) -> dict:
    """``{bucket: count}`` for a board whose rejections carry a ``why``
    sentence rather than a checks list — the shape CFB and the hoops
    boards publish.
    """
    out: dict = {"recommended": len(published or [])}
    if held:
        out["held_by_rules"] = len(held)
    for p in passed or []:
        k = reason_key(p.get("why"))
        out[k] = out.get(k, 0) + 1
    return out
