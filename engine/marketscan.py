"""Cross-book market scanner — arbitrage, middles, and low-hold pairs.

Shopping several books for the same market creates three structural plays
that need no model at all, just price comparison:

  * **arbitrage** — best Over at one book + best Under at another whose
    implied probabilities sum below 100%: locked profit whichever way the
    game goes. Rare across US books and short-lived, so the scanner reports
    honestly rather than promising them nightly.
  * **middles** — Over at a LOW line and Under at a HIGHER line: if the
    result lands between them both bets win; outside the window one wins
    and one loses, costing only the vig. Cheap lottery tickets with capped
    downside.
  * **low holds** — two-sided quotes whose combined juice is nearly zero.
    Not profit by themselves, but the cheapest markets to bet through
    (promo turnover, hedges) and a tell that a market is sharp.

Pure price math over the multi-book lines already attached to each prop —
sport-agnostic, so NFL and MLB both feed it. One-sided quotes (HR overs)
never enter: a pair needs both real sides.
"""

from __future__ import annotations

from .odds import american_to_decimal

MAX_ROWS = 20
LOW_HOLD_MAX = 0.025          # ≤2.5% combined juice counts as "low hold"
MIDDLE_WORST_CASE = -0.15     # max acceptable loss (per 1u+1u) for a middle


def _dec(odds) -> float | None:
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return american_to_decimal(o)


def scan_recommendations(recs: list[dict]) -> dict:
    """Scan every prop's multi-book lines. Returns
    ``{"arbs": [...], "middles": [...], "low_holds": [...]}``."""
    arbs: list[dict] = []
    middles: list[dict] = []
    low_holds: list[dict] = []

    for r in recs:
        lines = r.get("all_lines") or []
        if len(lines) < 2 or r.get("has_market") is False:
            continue
        label = f"{r.get('player', '')} {r.get('market_label', r.get('market', ''))}"

        # Best over / under per line value, across books.
        overs: dict[float, tuple[float, int, str]] = {}
        unders: dict[float, tuple[float, int, str]] = {}
        for ln in lines:
            point = ln.get("line")
            if point is None:
                continue
            point = float(point)
            do = _dec(ln.get("over_odds"))
            du = _dec(ln.get("under_odds"))
            if do and (point not in overs or do > overs[point][0]):
                overs[point] = (do, int(ln["over_odds"]), ln.get("book", ""))
            if du and (point not in unders or du > unders[point][0]):
                unders[point] = (du, int(ln["under_odds"]), ln.get("book", ""))

        for lo, (do, oo, ob) in overs.items():
            for lu, (du, uo, ub) in unders.items():
                if lu == lo:
                    inv = 1.0 / do + 1.0 / du
                    base = {
                        "bet": label,
                        "over": {"line": lo, "odds": oo, "book": ob},
                        "under": {"line": lu, "odds": uo, "book": ub},
                    }
                    if inv < 1.0:
                        # Locked profit; stake split proportional to inverse
                        # decimal prices returns the same amount either way.
                        arbs.append({**base,
                                     "profit_pct": round(1.0 / inv - 1.0, 4),
                                     "stake_over_pct": round((1.0 / do) / inv, 3)})
                    elif inv - 1.0 <= LOW_HOLD_MAX:
                        low_holds.append({**base,
                                          "hold_pct": round(inv - 1.0, 4)})
                elif lu > lo:
                    # Middle window: result strictly between the lines wins
                    # both. Betting 1u each: worst case one wins, one loses.
                    worst = min(do, du) - 2.0
                    if worst < MIDDLE_WORST_CASE:
                        continue
                    middles.append({
                        "bet": label,
                        "over": {"line": lo, "odds": oo, "book": ob},
                        "under": {"line": lu, "odds": uo, "book": ub},
                        "gap": round(lu - lo, 1),
                        "both_win_return": round(do + du - 2.0, 3),
                        "worst_case": round(worst, 3),
                    })

    arbs.sort(key=lambda a: -a["profit_pct"])
    middles.sort(key=lambda m: (-m["gap"], -m["worst_case"]))
    low_holds.sort(key=lambda h: h["hold_pct"])
    return {"arbs": arbs[:MAX_ROWS], "middles": middles[:MAX_ROWS],
            "low_holds": low_holds[:MAX_ROWS]}
