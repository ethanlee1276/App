"""Bet the right market, not the obvious one.

The model already produces a full six-outcome distribution for every fight
— A by KO, A by submission, A by decision, and the same for B — plus the
probability the fight reaches the scorecards. Until now all of that was
computed and then thrown away, because only the moneyline was ever priced.

§3.8 is blunt about the cost: books derive method props lazily off the
moneyline, so the moneyline is the one number they have thought about and
the method props are the ones they haven't. A model that says "A wins 70%,
mostly by knockout" is looking at a -280 moneyline with no edge and a
+190 "A by KO/TKO" against its own 45% — and betting the moneyline.

So this module takes the distribution and prices *everything it implies*,
then picks the market with the best edge rather than the market that
happens to be most famous.

**Where there is no book price, it publishes the fair one anyway.** MMA
prop menus are thin and our odds feed carries moneylines far more reliably
than method markets. Saying "our number on A by KO is +145, go and see
what your book has" is the actionable half of the translation step, and
withholding it because the feed was incomplete would throw away the whole
point. Those lines are labelled unpriced and can never be staked or
journaled — a fair value is a thing to shop, not a bet.

Tiers and their bars are §9 and §3.6: moneylines and the distance market
are tier 1, method props tier 2 with higher vig and a higher bar, exotics
tier 3 and rarely worth it. And a prelim fighter's moneyline clears a
higher bar than a main-card one — the line is softer, but so is our data.
"""

from __future__ import annotations

# §9 — the market menu, by tier.
TIER_1 = ("moneyline", "distance")
TIER_2 = ("method", "fighter_finish")
TIER_3 = ("round", "exact_round", "exotic")

MARKET_TIER = {
    "moneyline": 1, "distance": 1,
    "method": 2, "fighter_finish": 2,
    "round": 3, "exact_round": 3, "exotic": 3,
}

# §3.6 — minimum edge AFTER the haircut.
MIN_EDGE = {
    "moneyline": 0.040,        # main-card, well-covered fighters
    "distance": 0.050,
    "method": 0.050,
    "fighter_finish": 0.050,
    "round": 0.080,
    "exact_round": 0.080,
    "exotic": 0.080,
}
# Prelims, debuts, short notice, international-only records: the line is
# softer and so is our data, and the second half is why the bar goes UP.
THIN_DATA_MIN_EDGE = 0.060

# §10 — "there is no genuinely LOW-volatility MMA bet." A -600 favourite
# still gets knocked out.
VOLATILITY = {
    "moneyline": "MEDIUM", "distance": "MEDIUM",
    "method": "HIGH", "fighter_finish": "HIGH",
    "round": "EXTREME", "exact_round": "EXTREME", "exotic": "EXTREME",
}

METHOD_LABEL = {"ko": "KO/TKO", "sub": "Submission", "dec": "Decision"}


def _dec_odds(odds: int) -> float:
    return 1.0 + (100.0 / abs(odds) if odds < 0 else odds / 100.0)


def break_even(odds: int) -> float:
    return round(1.0 / _dec_odds(odds), 4)


def fair_odds(p: float) -> int:
    """American odds for a probability — the number to go shopping with."""
    p = min(max(float(p), 0.0001), 0.9999)
    if p >= 0.5:
        return -int(round(100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


def min_edge_for(market: str, thin_data: bool = False) -> float:
    """The bar this market has to clear after the haircut."""
    base = MIN_EDGE.get(market, 0.08)
    if thin_data and market == "moneyline":
        return THIN_DATA_MIN_EDGE
    return base


def thin_data_fight(a: dict, b: dict, prices: dict | None = None) -> bool:
    """§3.6 / §6 — is this the softer-line, worse-data half of the card?

    Prelims are not identified in the odds feed, so the readable proxies
    are the ones that actually drive the penalty: few tracked UFC fights,
    a short-notice booking, or a debut.
    """
    thin = min(int(a.get("ufc_fights", 0) or 0),
               int(b.get("ufc_fights", 0) or 0)) < 5
    short = bool(a.get("short_notice") or b.get("short_notice"))
    debut = min(int(a.get("ufc_fights", 0) or 0),
                int(b.get("ufc_fights", 0) or 0)) <= 1
    return bool(thin or short or debut)


def implied_markets(joint: dict, name_a: str, name_b: str) -> list[dict]:
    """Every market the outcome distribution can price.

    Round and exact-round markets are deliberately absent: pricing them
    needs a round-by-round hazard the dossiers have no data for (finish
    TIMES are not tracked), and asserting one would put an invented shape
    into the highest-vig markets on the board. §9 calls those tier 3 and
    rare anyway.
    """
    p_a = joint["a_ko"] + joint["a_sub"] + joint["a_dec"]
    p_b = joint["b_ko"] + joint["b_sub"] + joint["b_dec"]
    out = [
        {"market": "moneyline", "selection": name_a, "p": round(p_a, 4)},
        {"market": "moneyline", "selection": name_b, "p": round(p_b, 4)},
        {"market": "distance", "selection": "Goes the distance",
         "p": round(joint["distance"], 4)},
        {"market": "distance", "selection": "Doesn't go the distance",
         "p": round(1.0 - joint["distance"], 4)},
    ]
    for who, name in (("a", name_a), ("b", name_b)):
        for m in ("ko", "sub", "dec"):
            out.append({"market": "method",
                        "selection": f"{name} by {METHOD_LABEL[m]}",
                        "p": round(joint[f"{who}_{m}"], 4)})
        out.append({"market": "fighter_finish",
                    "selection": f"{name} by finish (KO or SUB)",
                    "p": round(joint[f"{who}_ko"] + joint[f"{who}_sub"], 4)})
    return out


def price_market(row: dict, book_odds: int | None, haircut_p: float | None,
                 thin_data: bool = False, book: str = "") -> dict:
    """One implied market against its book price, or its fair value.

    ``haircut_p`` is the post-clamp probability where one exists (the
    moneyline has a de-vigged market number to clamp toward). Method props
    usually do not, so the raw model probability carries a heavier haircut
    of its own — §3.5 says trust roughly half the raw edge on moneylines
    and *less* on props, and a prop with no market to clamp against is the
    least anchored number on the board.
    """
    market = row["market"]
    p_raw = float(row["p"])
    p = haircut_p if haircut_p is not None else p_raw
    card = {
        "market": market, "market_tier": MARKET_TIER.get(market, 3),
        "selection": row["selection"],
        "p_model": round(p_raw, 4), "p_used": round(p, 4),
        "volatility": VOLATILITY.get(market, "EXTREME"),
        "required_edge": min_edge_for(market, thin_data),
        "fair_odds": fair_odds(p),
        "book": book,
    }
    if book_odds is None:
        card.update(priced=False, odds=None, edge=None, ev=None,
                    note=("no book price in our feed — this is our fair "
                          "number, go and shop it"))
        return card
    be = break_even(int(book_odds))
    card.update(priced=True, odds=int(book_odds), break_even=be,
                edge=round(p - be, 4),
                ev=round(p * (_dec_odds(int(book_odds)) - 1.0) - (1.0 - p), 4))
    return card


def best_market(cards: list[dict]) -> dict | None:
    """The priced market with the largest edge OVER ITS OWN BAR.

    Not the largest raw edge: a +6% method prop that needs 5% is a better
    bet than a +5% moneyline that needs 4%, and comparing raw edges across
    tiers would systematically push money into the highest-vig markets.
    """
    priced = [c for c in cards
              if c.get("priced") and c.get("edge") is not None]
    if not priced:
        return None
    return max(priced, key=lambda c: c["edge"] - c["required_edge"])


# --- §9 correlation ---------------------------------------------------------
def correlation_flags(picks: list[dict]) -> list[str]:
    """Positive and incoherent pairings across the card.

    The card-level warning matters most: five underdog bets on one card is
    not five independent positions, it is one large bet on chaos.
    """
    flags: list[str] = []
    by_fight: dict = {}
    for p in picks:
        by_fight.setdefault(p.get("fight", ""), []).append(p)

    for fight, rows in by_fight.items():
        if len(rows) < 2:
            continue
        markets = {r.get("market") for r in rows}
        sels = " · ".join(r.get("selection", "") for r in rows)
        if "moneyline" in markets and "distance" in markets:
            flags.append(f"{fight}: moneyline + distance on one fight — "
                         f"correlated, counted as combined exposure ({sels})")
        elif "method" in markets or "fighter_finish" in markets:
            flags.append(f"{fight}: two positions on one fight — combined "
                         f"exposure applies ({sels})")

    dogs = [p for p in picks if (p.get("odds") or 0) > 0]
    if len(dogs) >= 3:
        flags.append(f"{len(dogs)} underdog positions on one card — that is "
                     f"not {len(dogs)} independent bets, it is one bet on a "
                     f"night of upsets. Card exposure is the cap that matters")
    return flags


def incoherent(a: dict, b: dict) -> str:
    """Why these two positions contradict each other, or ''."""
    fa, fb = a.get("fight"), b.get("fight")
    if not fa or fa != fb:
        return ""
    sa = (a.get("selection") or "").lower()
    sb = (b.get("selection") or "").lower()
    dist_a = a.get("market") == "distance" and "doesn't" not in sa
    dist_b = b.get("market") == "distance" and "doesn't" not in sb
    fin_a = "by ko" in sa or "by submission" in sa or "by finish" in sa
    fin_b = "by ko" in sb or "by submission" in sb or "by finish" in sb
    if (dist_a and fin_b) or (dist_b and fin_a):
        return ("backs the fight reaching the scorecards and a finish in the "
                "same fight — these cannot both win")
    if "by decision" in sa and dist_b and "doesn't" in sb:
        return "a decision cannot happen inside the distance"
    if "by decision" in sb and dist_a and "doesn't" in sa:
        return "a decision cannot happen inside the distance"
    return ""
