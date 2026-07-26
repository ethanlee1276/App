"""Scalpy pipeline — minutes first, distribution, clamp, gate, discipline.

Evaluates every prop both ways against the de-vigged market, but bets
almost nothing: max 4 picks a slate (a model producing 10 qualifying plays
a night isn't selective, it's miscalibrated), max 2 tied to one game, and
when nothing clears the gate the output is "No qualifying plays at current
lines" plus the near-miss report — the 3 closest edges and exactly what
would need to change. A no-bet night is a correct output, not a failure.
"""

from __future__ import annotations

from .minutes import (base_minutes, project_minutes, minutes_grade,
                      blowout_prob, GRADE_STAKE)
from .prob import (p_over, sd_for, devig, market_hold, humility_clamp,
                   approval_gate, break_even, ev_per_unit, _dec,
                   CLAMP_W_DEFAULT, HIGH_HOLD)

MAX_PICKS_PER_SLATE = 4
MAX_PICKS_PER_GAME = 2
THIN_SAMPLE = 10
CLAMP_W_THIN = 0.15

MARKET_LABELS = {"pts": "Points", "reb": "Rebounds", "ast": "Assists",
                 "fg3m": "3-Pointers Made", "pra": "Pts+Reb+Ast"}


def _rate_per_min(minutes: list[float], values: list[float]) -> float | None:
    pairs = [(m, v) for m, v in zip(minutes, values) if m > 0]
    if len(pairs) < 3:
        return None
    tm = sum(m for m, _ in pairs)
    return (sum(v for _, v in pairs) / tm) if tm > 0 else None


def evaluate_prop(prop: dict) -> dict:
    """One prop → a pick card, a near-miss, or a skip (with the reason)."""
    stat = prop["market"]
    label = MARKET_LABELS.get(stat, stat)
    minutes = prop.get("minutes") or []
    values = prop.get("values") or []
    base = base_minutes(minutes)
    rate = _rate_per_min(minutes, values)
    if base is None or rate is None:
        return {"kind": "skip", "why": "thin sample — under 3 usable games"}

    spread = float(prop.get("spread", 0.0))
    grade = minutes_grade(prop.get("is_starter", False), spread,
                          sample_games=len(minutes),
                          restriction=prop.get("restriction", False),
                          role_uncertain=prop.get("role_uncertain", False))
    proj_min = project_minutes(base, spread, prop.get("is_starter", False),
                               prop.get("is_favorite", False),
                               prop.get("rest", "1day"),
                               recent_high=max(minutes) if minutes else None)
    proj = round(rate * proj_min, 2)

    over_odds, under_odds = int(prop["over_odds"]), int(prop["under_odds"])
    line = float(prop["line"])
    p_model_over = p_over(stat, proj, line)
    mkt_over, mkt_under = devig(over_odds, under_odds)
    hold = market_hold(over_odds, under_odds)

    # Take the side where the model sees more than the market does.
    if p_model_over - mkt_over >= (1 - p_model_over) - mkt_under:
        side, p_model, p_market, odds = "OVER", p_model_over, mkt_over, over_odds
    else:
        side, p_model, p_market, odds = ("UNDER", 1 - p_model_over,
                                         mkt_under, under_odds)

    w = CLAMP_W_THIN if len(minutes) < THIN_SAMPLE else \
        float(prop.get("clamp_w", CLAMP_W_DEFAULT))
    p_final, clamp_note = humility_clamp(p_model, p_market, w)
    if p_final is None:
        return {"kind": "skip", "why": clamp_note, "player": prop["player"],
                "market": label}

    fails = approval_gate(p_final, odds, hold, grade,
                          high_hold_market=stat == "fg3m")
    card = {
        "player": prop["player"], "team": prop.get("team", ""),
        "opponent": prop.get("opponent", ""),
        "market": stat, "market_label": label, "line": line,
        "side": side, "odds": odds, "book": prop.get("book", ""),
        "p_model": round(p_model, 4), "p_market": round(p_market, 4),
        "p_final": p_final, "w": w,
        "break_even": break_even(odds),
        "edge": round(p_final - break_even(odds), 4),
        "ev": ev_per_unit(p_final, odds), "hold": hold,
        "minutes_grade": grade, "stake_mult": GRADE_STAKE[grade],
        "proj_minutes": proj_min, "base_minutes": base,
        "projection": proj, "sd": round(sd_for(stat, proj), 2),
        "blowout_prob": blowout_prob(spread),
        "kill_if": ("late scratch, minutes restriction, or lineup change "
                    "touching this player → automatic void"),
        "clamp_note": clamp_note,
    }
    if fails:
        return {"kind": "near_miss", **card, "fails": fails}
    stake = 0.25 * max(0.0, (p_final * (_dec(odds) - 1.0) - (1 - p_final))
                       / (_dec(odds) - 1.0))
    card["stake_units"] = round(min(stake, 0.03) * 20 * GRADE_STAKE[grade], 2)
    return {"kind": "pick", **card}


def run_nba_slate(props: list[dict], meta: dict | None = None) -> dict:
    picks, misses, skips = [], [], []
    for prop in props:
        r = evaluate_prop(prop)
        if r["kind"] == "pick":
            picks.append(r)
        elif r["kind"] == "near_miss":
            misses.append(r)
        else:
            skips.append(r)

    picks.sort(key=lambda p: -p["ev"])
    # Discipline: 4 per slate, 2 per game — selectivity is the model.
    chosen, per_game = [], {}
    for p in picks:
        gkey = tuple(sorted((p["team"], p["opponent"])))
        if len(chosen) >= MAX_PICKS_PER_SLATE:
            break
        if per_game.get(gkey, 0) >= MAX_PICKS_PER_GAME:
            continue
        per_game[gkey] = per_game.get(gkey, 0) + 1
        chosen.append(p)

    # Near-miss report: the 3 closest, with what would need to change.
    misses.sort(key=lambda m: -(m["ev"]))
    near = []
    for m in misses[:3]:
        near.append({**m, "what_would_change":
                     "; ".join(m["fails"][:2]) or "—"})

    return {
        "sport": "nba",
        "picks": chosen,
        "no_qualifying": not chosen,
        "near_misses": near,
        "counts": {"props_analyzed": len(props), "picks": len(chosen),
                   "near_misses": len(misses), "skipped": len(skips)},
        "meta": meta or {},
    }
