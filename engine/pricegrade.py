"""The price grade: Green, Yellow, Red (step AAB, 2026-11-20).

Ethan's own instructions (NFL Prop Bot v3.1, section 2) grade a leg's price
against its take-at price, "the price whose break-even equals the leg's final
number":

    Green   "book price at or better than take-at"
    Yellow  "up to 2 points of probability worse than take-at"
    Red     "more than 2 points worse"

On 20 November they said yes to showing it on the NBA's and hockey's picks.

WHY THOSE TWO LEAGUES. The grade sets our number against the price, so it
belongs where our number has held up against the price. On the public receipts
to 20 November (player props at -250 or better, each pick once, a chance of
60% or better):

    NBA   Green   673 picks hit 62.6%, the price needed 61.2%, +2.6% a bet
          Yellow  399 picks hit 66.9%, needed 66.5%, +0.3%
          Red     804 picks hit 67.5%, needed 68.7%, -1.6%
    NHL   Green 1,010 picks hit 66.5%, needed 65.4%, +1.9%
          Yellow  542 picks hit 68.8%, needed 67.6%, +1.9%
          Red     744 picks hit 66.9%, needed 68.8%, -2.6%

A red-priced pick hit as often as a green one in both leagues; what the grade
sorted was the money. Under 60% it sorted nothing: every grade made money, and
the NBA's Red-priced picks at 50-60% hit 66.9% where we said 57.3% (614), our
number being the one that ran low. So it is a label about price, never a
reason to take a pick down (v3.1's "Red: never posted" is not adopted: every
pick stays), and each card says what picks at its own chance and grade have
done on our record (`record`, the board's own books), which is the line to
read beside the colour.

In football the same grade marked the picks we had overrated: the NFL's Green
props at 60% or better hit 54.6% where we said 71.7% (2,232), college's 53.4%
where we said 72.7% (1,133). Football's numbers have since been tied to their
prices (the NFL's to the books' fair chance, pricetrust; college's capped at
its own price, likelyboard.hold_to_own_price), so a grade there would only
read back the books' cut. It is off (GRADE_SPORTS).

Standard library only. `stamp` and `record` never raise.
"""
from __future__ import annotations

import os

#: The leagues whose picks carry the grade (Ethan, 2026-11-20: yes to the NBA and hockey).
GRADE_SPORTS = ("nba", "nhl")
#: "0", "off", "no" or "false" turns the grade off everywhere.
ENV = "QB_PRICE_GRADE"
#: Yellow reaches this far past the take-at price, in probability (v3.1: "up to 2 points").
YELLOW_MAX = 0.02
GRADES = ("green", "yellow", "red")
LABELS = {"green": "Green price", "yellow": "Yellow price", "red": "Red price"}
#: The heaviest price a take-at is ever said as (gamereport.TAKE_CAP, the method's price gate).
TAKE_CAP = -250
#: Chance bands the grade's record is read in (likelyboard.BANDS, the record check's own).
BANDS = ((0.30, 0.45), (0.45, 0.60), (0.60, 0.75), (0.75, 1.01))
#: Settled picks a grade needs in a band before its card says how they did (likelyboard.RECORD_MIN_N).
RECORD_MIN_N = 20
#: The journal's books the record reads (likelyboard.RECORD_CATEGORIES), one copy of a pick across them.
RECORD_CATEGORIES = ("likely", "matchup_td", "matchup_prop", "td_scenario", "board", "bold")
LEAGUE_WORDS = {"nba": "NBA", "nhl": "NHL", "cbb": "college basketball", "wnba": "WNBA", "nfl": "NFL",
                "cfb": "college football", "mlb": "MLB"}


def on(sport) -> bool:
    if os.environ.get(ENV, "").strip().lower() in ("off", "0", "no", "false"):
        return False
    return str(sport or "").lower() in GRADE_SPORTS


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def need(odds):
    """The chance a bet at these American odds needs to break even, the book's cut left in; None for no price."""
    o = _num(odds)
    if not o:
        return None
    return (-o) / (-o + 100.0) if o < 0 else 100.0 / (o + 100.0)


def take_at(prob):
    """The American price whose break-even is ``prob``, never heavier than TAKE_CAP; None without a chance."""
    p = _num(prob)
    if p is None or not 0.0 < p < 1.0:
        return None
    fair = -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p
    return int(round(max(fair, TAKE_CAP)))


def american(odds) -> str:
    o = _num(odds)
    if o is None:
        return ""
    o = int(round(o))
    return f"+{o}" if o > 0 else str(o).replace("-", "−")


def grade_of(prob, odds):
    """"green", "yellow" or "red" for our chance against a price; None where either is missing."""
    p, n = _num(prob), need(odds)
    if p is None or n is None or not 0.0 < p < 1.0:
        return None
    gap = n - p
    return "green" if gap <= 1e-9 else "yellow" if gap <= YELLOW_MAX + 1e-9 else "red"


def _band(p: float):
    for lo, hi in BANDS:
        if lo <= p < hi:
            return lo
    return None


def record(conn, sport: str) -> dict:
    """``{(grade, band): {"n", "hits", "units"}}`` over the league's settled player picks with a price
    and a chance, one copy of a pick across the journal's books: how each grade has done at each
    chance, at one unit a pick. {} without a journal; never raises."""
    out: dict = {}
    try:
        marks = ",".join("?" * len(RECORD_CATEGORIES))
        rows = conn.execute(
            f"SELECT date, player, market, side, line, hit_prob, odds, status FROM bets "
            f"WHERE sport=? AND category IN ({marks}) AND status IN ('won','lost') "
            f"AND hit_prob IS NOT NULL AND odds IS NOT NULL", (str(sport or "").lower(), *RECORD_CATEGORIES)).fetchall()
    except Exception:                                        # noqa: BLE001
        return out
    seen = set()
    for r in rows:
        k = (r[0], r[1], r[2], str(r[3] or "").lower(), r[4])
        if k in seen or not r[1]:
            continue
        seen.add(k)
        p, g = _num(r[5]), grade_of(r[5], r[6])
        band = _band(p) if p is not None else None
        if g is None or band is None:
            continue
        o = float(r[6])
        cell = out.setdefault((g, band), {"n": 0, "hits": 0, "units": 0.0})
        cell["n"] += 1
        won = r[7] == "won"
        cell["hits"] += 1 if won else 0
        cell["units"] += ((100.0 / -o) if o < 0 else (o / 100.0)) if won else -1.0
    return out


def record_words(rec: dict | None, sport: str, grade: str, prob) -> str:
    """"NBA picks at this chance and a red price: 67% of 804 hit, −1.6% a bet", once RECORD_MIN_N have settled."""
    p = _num(prob)
    band = _band(p) if p is not None else None
    cell = (rec or {}).get((grade, band)) if band is not None else None
    if not cell or cell["n"] < RECORD_MIN_N:
        return ""
    roi = cell["units"] / cell["n"]
    league = LEAGUE_WORDS.get(str(sport or "").lower(), "our")
    return (f"{league} picks at this chance and a {grade} price: {cell['hits'] / cell['n']:.0%} of "
            f"{cell['n']:,} hit, {'+' if roi >= 0 else '−'}{abs(roi) * 100:.1f}% a bet")


def grade(prob, odds, sport: str = "", rec: dict | None = None) -> dict | None:
    """A pick's price grade: ``{"grade", "label", "gap", "need", "take_at", "words"}``, or None where
    it has no price or no chance. ``gap`` is how far the price's break-even sits over our number (0 or
    less on a Green price); ``take_at`` the price our number is worth (a card says it once, in its own
    words); ``words`` the grade said whole, with the record's line where it can speak."""
    g = grade_of(prob, odds)
    if g is None:
        return None
    p, n = float(prob), need(odds)
    gap = n - p
    price = american(odds)
    if g == "green":
        words = f"{LABELS[g]}: {price} needs {n:.0%} to break even and our number is {p:.0%}"
    else:
        pts = gap * 100.0
        words = (f"{LABELS[g]}: {price} needs {n:.0%} to break even, {pts:.1f} point{'' if round(pts, 1) == 1.0 else 's'} "
                 f"over our {p:.0%}")
    said = record_words(rec, sport, g, p)
    return {"grade": g, "label": LABELS[g], "gap": round(gap, 4), "need": round(n, 4), "take_at": take_at(p),
            "words": words + (f". {said}" if said else "")}


def gradable(r: dict) -> bool:
    """A player prop with a real price that is a bet (a read has no price to grade)."""
    if not isinstance(r, dict) or r.get("kind") == "game" or r.get("market") == "anytime_td":
        return False
    if r.get("bettable") is False or str(r.get("book") or "").lower() == "proxy" or r.get("has_market") is False:
        return False
    return need(r.get("odds")) is not None and _num(r.get("model_prob")) is not None


def stamp(rows, sport: str, rec: dict | None = None) -> dict:
    """Hang ``price_grade`` on each gradable row of a graded league (and take it off every other row);
    returns ``{"on", "rows", "green", "yellow", "red"}`` for the board and the heartbeat."""
    live = on(sport)
    out = {"on": live, "rows": 0, "green": 0, "yellow": 0, "red": 0}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        try:
            g = grade(r.get("model_prob"), r.get("odds"), sport, rec) if live and gradable(r) else None
        except Exception:                                    # noqa: BLE001
            g = None
        if g is None:
            r.pop("price_grade", None)
            continue
        r["price_grade"] = g
        out["rows"] += 1
        out[g["grade"]] += 1
    return out
