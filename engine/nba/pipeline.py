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


# --- shared-schema adapter --------------------------------------------------
# The seven shared pages (Recommended, Edge Board, Scanner, Trending,
# Players, Record) all read one slate shape. This maps Scalpy's cards into
# it WITHOUT changing Scalpy's identity: kind=pick → recommended, grade
# Play; near-miss → Pass with its gate failures as the warnings; skips
# (thin samples) carry no numbers and are dropped. "edge" keeps the shared
# meaning (model probability minus the de-vigged fair), and the humility
# clamp's note rides in the reasons.

def _avg(vals, n=None):
    xs = vals[:n] if n else vals
    return round(sum(xs) / len(xs), 2) if xs else None


def shared_recommendations(props: list[dict],
                           lines_map: dict | None = None,
                           dates_map: dict | None = None) -> list[dict]:
    """Every evaluable prop as a shared-schema recommendation dict.

    ``lines_map``: {(player, market): [line dicts]} — the multi-book quotes
    the Scanner needs (Scalpy itself only keeps the best two-way price).
    ``dates_map``: {player: [ISO dates, newest first]} for real log labels.
    """
    out = []
    for prop in props:
        r = evaluate_prop(prop)
        if r["kind"] == "skip":
            continue
        vals = [float(v) for v in (prop.get("values") or [])]
        dates = (dates_map or {}).get(prop["player"]) or []
        recent3, prior = _avg(vals, 3), _avg(vals[3:]) if len(vals) > 3 else None
        trend, delta = "flat", 0.0
        if recent3 is not None and prior:
            delta = round(recent3 - prior, 2)
            rel = delta / prior if prior else 0.0
            trend = "up" if rel > 0.10 else "down" if rel < -0.10 else "flat"
        pick = r["kind"] == "pick"
        grade = "Play" if pick else "Pass"
        warnings = [] if pick else [f"Approval gate: {f}" for f in r.get("fails", [])]
        reasons = [f"Projected {r['proj_minutes']} min × per-minute rate → "
                   f"{r['projection']} {r['market_label'].lower()}",
                   f"Minutes grade {r['minutes_grade']} · blowout risk "
                   f"{r['blowout_prob']:.0%}"]
        if r.get("clamp_note"):
            reasons.append(r["clamp_note"])
        out.append({
            "player": r["player"], "team": r.get("team", ""),
            "opponent": r.get("opponent", ""),
            "market": r["market"], "market_label": r["market_label"],
            "position": "", "usage_role": f"minutes {r['minutes_grade']}",
            "headshot": "",
            "side": r["side"], "book": r.get("book", ""),
            "line": r["line"], "odds": r["odds"],
            "projection": r["projection"],
            "proj_low": round(r["projection"] - r["sd"], 1),
            "proj_high": round(r["projection"] + r["sd"], 1),
            "hit_prob": r["p_final"], "fair_prob": r["p_market"],
            "edge": round(r["p_final"] - r["p_market"], 4),
            "ev_per_unit": r["ev"],
            "confidence": round(r["p_final"] * 10, 1),
            "stake_units": r.get("stake_units", 0.0),
            "grade": grade, "has_market": True,
            "recent_values": vals[:12],
            "trend": trend, "trend_delta": delta,
            "recommended": pick, "warnings": warnings,
            "headline": f"{r['player']} {r['side']} {r['line']:g} {r['market_label']}",
            "summary": (f"Model {r['p_final']:.0%} vs market {r['p_market']:.0%} "
                        f"after the humility clamp — needs {r['break_even']:.0%} "
                        f"to break even at {r['odds']:+d}."),
            "reasons": reasons,
            "all_lines": (lines_map or {}).get((r["player"], r["market"]), []),
            "logs": [{"week": i + 1,
                      "date": dates[i] if i < len(dates) else "",
                      "opponent": "", "value": v, "home": 1}
                     for i, v in enumerate(vals[:20])],
            "form": {"last1": _avg(vals, 1), "last3": _avg(vals, 3),
                     "last5": _avg(vals, 5), "last10": _avg(vals, 10),
                     "season": _avg(vals), "career": _avg(vals),
                     "vs_opponent": None},
        })
    # Shared ordering: recommended first, then confidence, then edge.
    out.sort(key=lambda x: (x["recommended"], x["confidence"], x["edge"]),
             reverse=True)
    return out
