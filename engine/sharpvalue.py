"""Where a book a reader can bet prices a prop better than the sharp book's fair.

Ethan, 2026-10-29: "think like a pro sports better ... use the data and
resources we have", then "Ok keep going". From today the NBA and NHL boards
read the sharp book's price as their market (engine/nba/prob.sharp_fair,
nhl_build._sharp_pair). The same pair answers the question a pro's screen
opens on: is any book I can bet paying more than the sharp book's fair
price? No model is in that number; it is one market against a sharper
one. The football boards already price it (`betting.sharp_anchor_for`, a
card's "Sharp anchor" line); this is the same arithmetic for a row that
already carries the sharp fair, both sides, at the same number only.

THE BANDS are the game cards' (`gamebets.SHARP_MIN_EV`, `SHARP_SUSPECT_EV`,
`SHARP_MAX_EV`): under 2% is noise; past 15% is a broken price and is not
shown; between 7% and 15% is shown with its warning, because a gap that
big usually means the sharp book moved on news the other quote has not
caught yet.

Standard library only.
"""

from __future__ import annotations


def _get(q, key):
    return q.get(key) if isinstance(q, dict) else getattr(q, key, None)


def sharp_value(fair_over, quotes, line) -> dict | None:
    """``{"side", "odds", "book", "fair", "ev", "suspect"}``: the side whose
    best price at a bettable book in ``quotes``, at ``line``, beats the sharp
    book's fair (``fair_over``: its de-vigged chance of the over) by
    SHARP_MIN_EV to SHARP_MAX_EV, the better of the two when both do; None
    when neither does."""
    from .gamebets import SHARP_MAX_EV, SHARP_MIN_EV, SHARP_SUSPECT_EV
    from .odds import american_to_decimal, is_quotable, is_sharp_book
    try:
        fo, at = float(fair_over), float(line)
    except (TypeError, ValueError):
        return None
    if not 0.0 < fo < 1.0:
        return None
    best = None
    for side, fair, key in (("OVER", fo, "over_odds"), ("UNDER", 1.0 - fo, "under_odds")):
        top = None
        for q in quotes or []:
            try:
                if abs(float(_get(q, "line")) - at) > 1e-9:
                    continue
                odds = int(_get(q, key) or 0)
            except (TypeError, ValueError):
                continue
            book = str(_get(q, "book") or "")
            if not odds or not is_quotable(odds) or is_sharp_book(book) or book.lower() == "proxy":
                continue
            if top is None or odds > top[0]:                # a higher American price pays more, either sign
                top = (odds, book)
        if top is None:
            continue
        ev = fair * american_to_decimal(top[0]) - 1.0
        if SHARP_MIN_EV <= ev <= SHARP_MAX_EV and (best is None or ev > best["ev"]):
            best = {"side": side, "odds": top[0], "book": top[1], "fair": round(fair, 4),
                    "ev": round(ev, 4), "suspect": ev > SHARP_SUSPECT_EV}
    return best


def note(v: dict, sharp_book: str = "") -> str:
    """The card's line for it."""
    who = sharp_book or "the sharp book"
    odds = f"{v['odds']:+d}"
    side = str(v["side"]).lower()
    text = (f"Beats {who}: {v['book']} {odds} on the {side} pays more than {who}'s fair "
            f"({v['fair']:.0%}), {v['ev']:+.1%} EV on the price alone")
    if v.get("suspect"):
        text += (" — a gap this big usually means news moved the sharp price first; "
                 "check the number still stands")
    return text
