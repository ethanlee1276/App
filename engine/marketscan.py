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

from .odds import american_to_decimal, PAIR_SANITY_FLOOR

MAX_ROWS = 20
LOW_HOLD_MAX = 0.02           # ≤2% combined juice counts as "low hold" (spec)
MIDDLE_WORST_CASE = -0.15     # max acceptable loss (per 1u+1u) for a middle
ARB_SUSPECT = 0.05            # a 5%+ "arb" is a stale line or a void risk


def _dec(odds) -> float | None:
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return american_to_decimal(o)


def outcome_distributions(recs: list[dict]) -> dict[str, dict[int, float]]:
    """Per-market empirical distribution of integer game outcomes, pooled
    from every prop's own game logs on the slate.

    This is what lets middles be ranked by EV instead of window width: the
    probability mass INSIDE the window is what a middle is worth, and a
    1-point window on a dense number beats a 3-point window in dead space."""
    counts: dict[str, dict[int, int]] = {}
    for r in recs:
        market = r.get("market", "")
        for lg in r.get("logs") or []:
            v = lg.get("value") if isinstance(lg, dict) else getattr(lg, "value", None)
            if v is None:
                continue
            b = counts.setdefault(market, {})
            iv = int(round(float(v)))
            b[iv] = b.get(iv, 0) + 1
    out: dict[str, dict[int, float]] = {}
    for market, b in counts.items():
        total = sum(b.values())
        if total >= 200:                    # need real mass to trust the shape
            out[market] = {k: v / total for k, v in b.items()}
    return out


def _window_probs(dist: dict[int, float], lo: float, lu: float
                  ) -> tuple[float, float, float]:
    """(P below over-line, P inside the middle window, P above under-line)."""
    p_low = sum(p for v, p in dist.items() if v < lo)
    p_mid = sum(p for v, p in dist.items() if lo < v < lu)
    p_high = sum(p for v, p in dist.items() if v > lu)
    return p_low, p_mid, p_high


def scan_recommendations(recs: list[dict]) -> dict:
    """Scan every prop's multi-book lines. Returns
    ``{"arbs": [...], "middles": [...], "low_holds": [...]}``."""
    arbs: list[dict] = []
    middles: list[dict] = []
    low_holds: list[dict] = []
    dists = outcome_distributions(recs)

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
                    # A pair implying far below 100% is not a windfall, it
                    # is corrupt data when BOTH sides come from the same
                    # book: no book prices its own market at a guaranteed
                    # loss. Sample data surfaced "Kyle Tucker over +318 /
                    # under -110, both DraftKings" as a 31% arbitrage.
                    # Cross-book pairs are left alone even when large —
                    # those are stale lines, which ARB_SUSPECT flags and
                    # still shows so the user can judge.
                    # No book prices its own market at a guaranteed loss,
                    # at ANY size — so a same-book pair implying under 100%
                    # is corrupt regardless of how small the "profit" looks.
                    # Cross-book pairs are left alone even when large: those
                    # are stale lines, which ARB_SUSPECT flags and still
                    # shows so the user can judge for themselves.
                    if ob == ub and inv < 1.0:
                        continue
                    base = {
                        "bet": label,
                        "over": {"line": lo, "odds": oo, "book": ob},
                        "under": {"line": lu, "odds": uo, "book": ub},
                    }
                    if inv < 1.0:
                        # Locked profit; stake split proportional to inverse
                        # decimal prices returns the same amount either way.
                        profit = 1.0 / inv - 1.0
                        arbs.append({**base,
                                     "profit_pct": round(profit, 4),
                                     "stake_over_pct": round((1.0 / do) / inv, 3),
                                     # A 5%+ "arb" is almost never free money —
                                     # it's a stale line, a market mismatch, or
                                     # a leg about to be voided.
                                     "suspect": profit >= ARB_SUSPECT})
                    elif inv - 1.0 <= LOW_HOLD_MAX:
                        hold = inv - 1.0
                        low_holds.append({**base,
                                          "hold_pct": round(hold, 4),
                                          # The number that actually matters
                                          # for promo turnover.
                                          "cost_per_1k": round(hold * 1000, 2)})
                elif lu > lo:
                    # Middle window: result strictly between the lines wins
                    # both. Betting 1u each: worst case one wins, one loses.
                    worst = min(do, du) - 2.0
                    if worst < MIDDLE_WORST_CASE:
                        continue
                    entry = {
                        "bet": label,
                        "over": {"line": lo, "odds": oo, "book": ob},
                        "under": {"line": lu, "odds": uo, "book": ub},
                        "gap": round(lu - lo, 1),
                        "both_win_return": round(do + du - 2.0, 3),
                        "worst_case": round(worst, 3),
                    }
                    # EV from the sport's REAL outcome distribution: the mass
                    # inside the window is what a middle is worth. A 1-point
                    # window on a dense number beats a wide window in dead
                    # space — so rank by EV, never by width.
                    dist = dists.get(r.get("market", ""))
                    if dist:
                        p_low, p_mid, p_high = _window_probs(dist, lo, lu)
                        ev = (p_mid * (do + du - 2.0)
                              + p_low * (du - 2.0) + p_high * (do - 2.0))
                        entry["middle_prob"] = round(p_mid, 4)
                        entry["ev_per_unit"] = round(ev / 2.0, 4)  # per 1u staked
                    middles.append(entry)

    arbs.sort(key=lambda a: -a["profit_pct"])
    # EV-ranked when measured; unmeasured markets fall to the bottom.
    middles.sort(key=lambda m: -(m.get("ev_per_unit")
                                 if m.get("ev_per_unit") is not None else -9))
    low_holds.sort(key=lambda h: h["hold_pct"])
    return {"arbs": arbs[:MAX_ROWS], "middles": middles[:MAX_ROWS],
            "low_holds": low_holds[:MAX_ROWS]}


# --- stale lines ------------------------------------------------------------
# Measured on 30,448 harvested quotes: when a book prices a prop at least
# STALE_GAP_PT below the consensus of the other books, taking that price
# beat the eventual closing consensus 64.8% of the time, averaging +1.49
# points of CLV (z = 11.6). Crucially that is NOT the convergence rate —
# an outlier regresses toward the field 77.5% of the time for purely
# statistical reasons, which proves nothing. Beating the close cannot be
# manufactured by mean reversion, which is why this section exists and
# why the threshold is set where the CLV was measured.
STALE_GAP_PT = 0.01        # 1 probability point
STALE_MIN_BOOKS = 3        # a consensus needs a crowd


STALE_LIMIT = 25           # a board, not a database dump


def stale_quotes(recs: list[dict], gap: float = STALE_GAP_PT,
                 limit: int = STALE_LIMIT) -> list[dict]:
    """Books currently pricing a side cheaper than the rest of the field.

    No forecast is involved: the claim is only that this book disagrees
    with every other book, and that historically the disagreement
    resolves in the taker's favour."""
    from .odds import american_to_prob
    out: list[dict] = []
    for r in recs:
        if r.get("has_market") is False:
            continue
        for point, side in (("over_odds", "OVER"), ("under_odds", "UNDER")):
            by_line: dict[float, list[tuple[str, int]]] = {}
            for ln in r.get("all_lines") or []:
                pt, odds = ln.get("line"), ln.get(point)
                if pt is None or not odds:
                    continue
                by_line.setdefault(float(pt), []).append(
                    (ln.get("book", ""), int(odds)))
            for pt, quotes in by_line.items():
                if len(quotes) < STALE_MIN_BOOKS:
                    continue
                probs = {b: american_to_prob(o) for b, o in quotes}
                for book, o in quotes:
                    others = [v for b, v in probs.items() if b != book]
                    consensus = sum(others) / len(others)
                    edge = consensus - probs[book]
                    if edge < gap:
                        continue
                    out.append({
                        "bet": f"{r.get('player', '')} {side} {pt} "
                               f"{r.get('market_label', r.get('market', ''))}",
                        "book": book, "odds": o, "side": side, "line": pt,
                        "implied": round(probs[book], 4),
                        "consensus": round(consensus, 4),
                        "gap_pts": round(edge * 100, 2),
                        "books_compared": len(quotes),
                        "fair_odds": _prob_to_american(consensus),
                    })
    # One flag per prop-side, keeping the biggest gap. With seven books
    # quoting every prop, flagging each cheap book separately produced 911
    # rows on a 1,016-prop board — technically all above threshold, and
    # useless as something to act on. The measured CLV came from taking
    # THE best price available, not from every quote below consensus.
    best: dict[tuple, dict] = {}
    for d in out:
        k = (d["bet"], d["side"])
        if k not in best or d["gap_pts"] > best[k]["gap_pts"]:
            best[k] = d
    ranked = sorted(best.values(), key=lambda d: -d["gap_pts"])
    for d in ranked:
        d["total_found"] = len(ranked)
    return ranked[:limit] if limit else ranked


def _prob_to_american(p: float) -> int:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -round((p / (1 - p)) * 100) if p >= 0.5 else round(((1 - p) / p) * 100)


# --- favourite-longshot bias -----------------------------------------------
# Measured on 27,226 settled quotes joined to real outcomes: the cost of
# backing the OVER rises monotonically as the price lengthens. Both ends
# lose to the vig, but longshots lose 2.6x as much — the books shade big
# payouts far harder than short ones, which is the oldest documented
# inefficiency in betting markets and is alive in baseball props.
#
# (implied-probability floor, label, measured flat-stake ROI of backing
# the over in that band)
PRICE_BANDS = (
    (0.00, "+900 and out", -0.285),
    (0.10, "+400 to +900", -0.207),
    (0.20, "+185 to +400", -0.114),
    (0.35, "+100 to +185", -0.099),
    (0.50, "-100 to -185", -0.069),
    (0.65, "-185 and shorter", -0.056),
)
# Below this implied probability the measured cost is more than double
# the short end — the board should say so out loud.
LONGSHOT_MAX_PROB = 0.35


def band_for(odds: int) -> tuple[str, float]:
    """(label, measured historical ROI of backing the over) for a price."""
    from .odds import american_to_prob
    p = american_to_prob(int(odds))
    label, roi = PRICE_BANDS[0][1], PRICE_BANDS[0][2]
    for floor, lb, r in PRICE_BANDS:
        if p >= floor:
            label, roi = lb, r
    return label, roi


def longshot_warnings(recs: list[dict]) -> list[dict]:
    """Plus-money props on today's board, with what that price band has
    actually cost historically.

    This is an avoidance rule, not a play: no forecast is involved and
    none is needed. A +900 prop has cost 28.5 cents per dollar staked
    before anyone forms a view on the player."""
    from .odds import american_to_prob
    out: list[dict] = []
    for r in recs:
        if r.get("has_market") is False:
            continue
        odds = r.get("odds")
        if odds is None:
            continue
        p = american_to_prob(int(odds))
        if p >= LONGSHOT_MAX_PROB:
            continue
        label, roi = band_for(int(odds))
        out.append({
            "bet": f"{r.get('player', '')} {r.get('side', 'OVER')} "
                   f"{r.get('line', '')} "
                   f"{r.get('market_label', r.get('market', ''))}",
            "book": r.get("book", ""), "odds": int(odds),
            "implied": round(p, 4), "band": label,
            "measured_roi": roi,
            "grade": r.get("grade", ""),
        })
    out.sort(key=lambda d: d["implied"])
    return out
