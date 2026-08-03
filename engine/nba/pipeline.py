"""Scalpy pipeline — minutes first, distribution, clamp, gate, discipline.

Evaluates every prop both ways against the de-vigged market, but bets
almost nothing: max 4 picks a slate (a model producing 10 qualifying plays
a night isn't selective, it's miscalibrated), max 2 tied to one game, and
when nothing clears the gate the output is "No qualifying plays at current
lines" plus the near-miss report — the 3 closest edges and exactly what
would need to change. A no-bet night is a correct output, not a failure.
"""

from __future__ import annotations

from ..hoops import NBA, LeagueTuning
from .minutes import (base_minutes, project_minutes, minutes_grade,
                      blowout_prob, GRADE_STAKE)
from .prob import (p_over, sd_for, devig, market_hold, humility_clamp,
                   approval_gate, required_edge, break_even, ev_per_unit,
                   _dec, CLAMP_W_DEFAULT, HIGH_HOLD)
from .quality import (usage_stability, stability_blocks, quality_score,
                      grade_label, kelly_stake, apply_exposure_caps)

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


def evaluate_prop(prop: dict, tune: LeagueTuning = NBA) -> dict:
    """One prop → a pick card, a near-miss, or a skip (with the reason)."""
    stat = prop["market"]
    label = MARKET_LABELS.get(stat, stat)
    minutes = prop.get("minutes") or []
    values = prop.get("values") or []
    base = base_minutes(minutes, tune)
    rate = _rate_per_min(minutes, values)
    if base is None or rate is None:
        return {"kind": "skip", "why": "thin sample — under 3 usable games"}

    # §5 — a volatile role is unbettable at any modeled edge. This comes
    # before the pricing on purpose: the whole projection is minutes × a
    # rate, so if the minutes are a coin flip there is nothing here to
    # price and computing an edge from it only makes the fiction look
    # numerate.
    stability = usage_stability(minutes)
    volatile = stability_blocks(minutes, tune)
    if volatile:
        return {"kind": "skip", "why": volatile, "player": prop["player"],
                "market": label}

    spread = float(prop.get("spread", 0.0))
    grade = minutes_grade(prop.get("is_starter", False), spread,
                          sample_games=len(minutes),
                          restriction=prop.get("restriction", False),
                          role_uncertain=prop.get("role_uncertain", False),
                          tune=tune)
    proj_min = project_minutes(base, spread, prop.get("is_starter", False),
                               prop.get("is_favorite", False),
                               prop.get("rest", "1day"),
                               recent_high=max(minutes) if minutes else None,
                               tune=tune)
    # Player memory (engine/playerfit.py): the record's earned correction
    # for players this model persistently misreads — same store, same
    # restraints (shrinkage, ±15% clamp, causal adoption) as every sport.
    from ..playerfit import mult_for as pf_mult
    pmult = pf_mult(tune.key, stat, prop["player"])
    proj = round(rate * proj_min * pmult, 2)

    over_odds, under_odds = int(prop["over_odds"]), int(prop["under_odds"])
    line = float(prop["line"])
    # Temperature (engine/calibrate.py), applied BEFORE the side is chosen
    # — an uncalibrated probability would still decide OVER vs UNDER (see
    # engine/mlb/betting.py, the same doctrine). Keyed by tune.key, so the
    # WNBA's fit never leaks onto the NBA or the reverse.
    from ..calibrate import apply_temperature, correction_for
    _t, _b = correction_for(tune.key, stat)
    p_model_over = apply_temperature(p_over(stat, proj, line, tune), _t, _b)
    mkt_over, mkt_under = devig(over_odds, under_odds)
    hold = market_hold(over_odds, under_odds)

    # Take the side where the model sees more than the market does.
    if p_model_over - mkt_over >= (1 - p_model_over) - mkt_under:
        side, p_model, p_market, odds = "OVER", p_model_over, mkt_over, over_odds
    else:
        side, p_model, p_market, odds = ("UNDER", 1 - p_model_over,
                                         mkt_under, under_odds)

    w = CLAMP_W_THIN if len(minutes) < tune.thin_sample else \
        float(prop.get("clamp_w", CLAMP_W_DEFAULT))
    p_final, clamp_note = humility_clamp(p_model, p_market, w)
    if p_final is None:
        return {"kind": "skip", "why": clamp_note, "player": prop["player"],
                "market": label}

    fails = approval_gate(p_final, odds, hold, grade,
                          high_hold_market=stat == "fg3m",
                          stat=stat, tune=tune)
    # The other two self-tuning gates, in parity with every engine: a
    # market whose calibration fit ran to its boundary closed itself, and
    # the loss-pattern miner's closed slices veto matching picks.
    from ..calibrate import is_reliable
    from ..losspatterns import veto as lp_veto
    if not is_reliable(tune.key, stat):
        fails = fails + ["this market's calibration fit hit the edge of its "
                         "search range — closed by its own fit"]
    _block = lp_veto(tune.key, stat, side=side, odds=odds, prob=p_final,
                     book=prop.get("book"), horizon_days=0)
    if _block:
        fails = fails + [_block]
    need = required_edge(stat, hold, tune, high_hold_market=stat == "fg3m")
    tier = (tune.market_tier or {}).get(stat, 2)
    # §8 — the five context components, each a restatement of something
    # measured. Freshness is what the build could actually confirm about
    # availability; movement and matchup score half when the feed that
    # would answer them is absent, rather than assuming the best case.
    score = quality_score(
        edge=p_final - break_even(odds), required=need, minutes_grade=grade,
        stability=stability["score"],
        freshness=float(prop.get("freshness", 0.5)),
        movement=float(prop.get("movement_fit", 0.5)),
        matchup=float(prop.get("matchup_fit", 0.5)),
        schedule=float(prop.get("schedule_fit", 0.5)),
        tune=tune)
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
        "projection": proj, "sd": round(sd_for(stat, proj, tune), 2),
        "blowout_prob": blowout_prob(spread, tune=tune),
        "league": tune.key,
        "required_edge": need,
        "market_tier": tier,
        "grade_score": score,
        "grade_label": grade_label(score, tune),
        "stability": stability,
        "kill_if": ("late scratch, minutes restriction, or lineup change "
                    "touching this player → automatic void"),
        "clamp_note": clamp_note,
    }
    # "Below 70: no bet, no leans" — but only where a league's tuning says
    # the grade is the authority. The NBA board predates this grade and is
    # calibrated; bolting a new bar onto it because another league's spec
    # asked for one would be a silent re-tune of a working model.
    if tune.min_grade is not None and score < tune.min_grade:
        fails = fails + [f"grade {score} below the {tune.min_grade} bar — "
                         f"no bet, no leans"]
    if fails:
        return {"kind": "near_miss", **card, "fails": fails}
    if tune.grade_weights:
        frac = kelly_stake(p_final, odds, score, tier, tune)
    else:
        stake = 0.25 * max(0.0, (p_final * (_dec(odds) - 1.0) - (1 - p_final))
                           / (_dec(odds) - 1.0))
        frac = min(stake, tune.cap_per_play)
    card["stake_fraction"] = frac
    card["stake_units"] = round(frac * 20 * GRADE_STAKE[grade], 2)
    return {"kind": "pick", **card}


def run_nba_slate(props: list[dict], meta: dict | None = None,
                  tune: LeagueTuning = NBA) -> dict:
    picks, misses, skips = [], [], []
    for prop in props:
        r = evaluate_prop(prop, tune)
        if r["kind"] == "pick":
            picks.append(r)
        elif r["kind"] == "near_miss":
            misses.append(r)
        else:
            skips.append(r)

    # Rank by the grade where a league has one — the grade already contains
    # the edge at 40% plus everything EV alone can't see, so ordering by raw
    # EV would put a volatile-role play with a fat number above a settled
    # one with a slightly smaller edge.
    picks.sort(key=lambda p: (-p.get("grade_score", 0), -p["ev"])
               if tune.grade_weights else (-p["ev"], 0))
    # Discipline: 4 per slate, 2 per game — selectivity is the model.
    chosen, per_game = [], {}
    for p in picks:
        gkey = tuple(sorted((p["team"], p["opponent"])))
        if len(chosen) >= tune.max_picks_per_slate:
            break
        if per_game.get(gkey, 0) >= tune.max_picks_per_game:
            continue
        per_game[gkey] = per_game.get(gkey, 0) + 1
        chosen.append(p)

    # §8 bankroll caps: 2% a play, 5% a game, 12% a slate. The count limits
    # above cap the NUMBER of positions; these cap the MONEY, and in a
    # low-limit league where a moved line is hard to re-bet, that is the
    # constraint that actually binds.
    if tune.grade_weights:
        chosen = apply_exposure_caps(chosen, tune)
        for p in chosen:
            p["stake_units"] = round(p.get("stake_fraction", 0.0) * 20
                                     * GRADE_STAKE[p["minutes_grade"]], 2)
        chosen = [p for p in chosen if p["stake_units"] > 0]

    # Near-miss report: the 3 closest, with what would need to change.
    misses.sort(key=lambda m: -(m["ev"]))
    near = []
    for m in misses[:3]:
        near.append({**m, "what_would_change":
                     "; ".join(m["fails"][:2]) or "—"})

    return {
        "sport": tune.key,
        # An uncalibrated league grades but does not bet: its tuning was
        # fitted somewhere else, and borrowed numbers have to earn the
        # right to stake money the same way every other sampler here does.
        "probation": tune.probation,
        "tuning": {"inherited_from": tune.inherited_from,
                   "calibrated": tune.calibrated, "note": tune.note},
        "picks": chosen,
        "no_qualifying": not chosen,
        "near_misses": near,
        "counts": {"props_analyzed": len(props), "picks": len(chosen),
                   "near_misses": len(misses), "skipped": len(skips)},
        # WHY each prop died, tallied. The counts above say how many were
        # analyzed and how many survived; the difference was a number with
        # no story attached, which on an empty board is the only thing
        # anybody wants to know. Skips carry their own reason already and
        # near-misses carry the gate they failed — both were computed and
        # then thrown away.
        "gate_census": _census(skips, misses),
        "meta": meta or {},
    }


#: Reasons are written as prose for the card ("thin sample — under 3 usable
#: games"), which makes a poor tally key. Collapse to the part before the
#: dash, which is the category.
def _reason_key(text: str) -> str:
    """Strip the NUMBERS out, keep the category.

    Reasons are written for a card, so they carry this prop's own figures:
    "edge -1.7% < required 4.5% over break-even 52.4%". Tallied verbatim,
    every prop becomes its own row and the census turns into a list — two
    hundred rows reading 1. What a reader wants is "edge under required:
    186", so the digits go and the sentence stays.
    """
    import re
    head = str(text or "other").split("—")[0].split("(")[0]
    head = re.sub(r"[-+]?\d[\d,.]*%?", "", head)          # drop the figures
    head = re.sub(r"[<>=]+", "", head)
    head = re.sub(r"\s+", " ", head).strip(" .,:;").lower()
    return (head or "other")[:60]


def _census(skips: list, misses: list) -> dict:
    out: dict = {}
    for r in skips:
        k = _reason_key(r.get("why"))
        out[k] = out.get(k, 0) + 1
    for m in misses:
        # The FIRST failure is the one to report: a prop that fails three
        # gates is not three findings, and counting it three times would
        # make the census sum to more than the props analyzed.
        fails = m.get("fails") or ["failed a gate"]
        k = _reason_key(fails[0])
        out[k] = out.get(k, 0) + 1
    return out


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
                           dates_map: dict | None = None,
                           tune: LeagueTuning = NBA) -> list[dict]:
    """Every evaluable prop as a shared-schema recommendation dict.

    ``lines_map``: {(player, market): [line dicts]} — the multi-book quotes
    the Scanner needs (Scalpy itself only keeps the best two-way price).
    ``dates_map``: {player: [ISO dates, newest first]} for real log labels.

    ``tune`` is NOT optional in practice. This layer is what the seven
    shared pages actually render, and it used to call ``evaluate_prop``
    with the default — so the WNBA board displayed every prop graded
    against NBA tuning: a 48-minute game, the NBA's gate, no tier bars.
    Scalpy's own ``picks`` were right and the page beside them was not.
    """
    out = []
    for prop in props:
        r = evaluate_prop(prop, tune)
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
        edge = r["p_final"] - r["p_market"]
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
            # Confidence feeds the site's min-confidence slider (default
            # 6.0). A raw p_final x 10 put real PICKS at 5.5-6.5 — hidden by
            # the default slider on the page that exists to show them. Picks
            # scale 7-9 with edge; passes keep the raw scale (below 7).
            "confidence": (round(7.0 + min(max(edge, 0.0), 0.05) * 40, 1)
                           if pick else
                           round(min(6.9, r["p_final"] * 10), 1)),
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
