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
    from ..losspatterns import minutes_until
    # THE PRE-GAME MODEL MUST NOT PRICE AN IN-PLAY MARKET, and this board
    # was the one place that rule was never written down.
    #
    # `engine/pipeline.py` refuses a started game through
    # `config.block_live_games`, and `engine/mlb/pipeline.py` has its own
    # copy. Scalpy had neither. On 2026-08-09 the WNBA slate tipped at
    # 12:30, 3:00 and 3:30 and the board was still offering recommended
    # picks on all three at 8pm, priced off pre-game numbers for games
    # that were over. Nothing in the payload even said they had started —
    # see `_live_block` in nba_build.py for the other half of that.
    #
    # Blocked rather than warned. A warning on a card is advice; a bet
    # placed on a finished game is a loss with no story, and every other
    # engine here treats it as a refusal.
    _lead = minutes_until(prop.get("kickoff") or prop.get("commence_time"))
    if _lead is not None and _lead <= 0:
        fails = fails + ["game already started — this is a pre-game model "
                         "and cannot price an in-play market"]
    _block = lp_veto(tune.key, stat, side=side, odds=odds, prob=p_final,
                     book=prop.get("book"), horizon_days=0,
                     lead_min=_lead)
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
    from ..staking import to_units
    card["stake_units"] = to_units(frac, odds, mult=GRADE_STAKE[grade])
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

    _why: list[str] = []
    # §8 bankroll caps: 2% a play, 5% a game, 12% a slate. The count limits
    # above cap the NUMBER of positions; these cap the MONEY, and in a
    # low-limit league where a moved line is hard to re-bet, that is the
    # constraint that actually binds.
    if tune.grade_weights:
        chosen = apply_exposure_caps(chosen, tune)
        from ..staking import to_units
        for p in chosen:
            p["stake_units"] = to_units(p.get("stake_fraction", 0.0),
                                        p.get("odds", -110),
                                        mult=GRADE_STAKE[p["minutes_grade"]])
        chosen = [p for p in chosen if p["stake_units"] > 0]

    # PROBATION, ENFORCED — the same gap the CFB board had. The return
    # value below has always carried `"probation": tune.probation` with
    # the comment "An uncalibrated league grades but does not bet", and
    # the page has always drawn the banner. Nothing read the flag: the
    # Kelly sizes above were written whatever it said, so WNBA (which is
    # `calibrated=False`, inheriting the NBA's fitted numbers) published
    # staked picks underneath a banner promising it did not stake.
    #
    # After the caps and the zero-stake drop, so a withheld size cannot
    # be mistaken for a cap trim and the picks keep their grades — the
    # grades being the entire point of a probation board.
    if tune.probation:
        from ..probation import unstake as _unstake
        _why = [f"this league's fitted numbers are the "
                f"{tune.inherited_from.upper()} model's, not its own — "
                f"borrowed numbers do not get to size a bet"
                if tune.inherited_from else
                "this league's numbers have not been fitted to its own "
                "results, so any stake would be Kelly on a borrowed spread"]
        # BOTH size fields in one pass — the bankroll fraction and the
        # unit count. Two calls would have the second overwrite the
        # first's record of what the size would have been.
        chosen = _unstake(chosen, _why,
                          stake_keys=("stake_fraction", "stake_units"))

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
        "probation_reasons": _why,
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
    """Shared with CFB, which needs the identical bucketing — the body
    moved to engine/census.reason_key rather than being copied. See it
    for why the digits come out."""
    from ..census import reason_key
    return reason_key(text)


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


#: How many faces the last `shared_recommendations` call actually joined,
#: and how many it looked for. Read by nba_build so a board that quietly
#: stops showing photos says so in the build output instead of being
#: noticed by eye three weeks later.
FACE_JOIN = {"want": 0, "got": 0}


def _norm(name: str) -> str:
    from ..sources.oddsapi import normalize_name
    return normalize_name(name or "")


#: id(assets) → normalised index. Built once per board rather than
#: re-normalising a hundred names for every prop on the slate.
_NORM_CACHE: dict = {}


def _norm_index(assets: dict) -> dict:
    key = id(assets)
    hit = _NORM_CACHE.get(key)
    if hit is None or hit[0] is not len(assets):
        hit = (len(assets), {_norm(n): row for n, row in assets.items()})
        _NORM_CACHE.clear()          # one board at a time; never grows
        _NORM_CACHE[key] = hit
    return hit[1]


def _face(assets, player: str) -> str:
    """This player's headshot URL, or "" — joined on a NORMALISED name.

    THE EXACT LOOKUP FAILED SILENTLY. `player_assets` is keyed by the name
    in ESPN's box score and a recommendation carries the name from the
    odds feed, and the two disagree about apostrophes, accents, periods
    and suffixes — "A'ja Wilson" against "Aja Wilson", "Nneka Ogwumike"
    against "Nneka Ogwumike Jr.". Ethan ingested 100 of 105 WNBA photos on
    2026-08-10 and every card still drew initials.

    `normalize_name` is the join key the rest of this repo already uses
    for exactly this (`records_from_ledger`, `_bet_team`, the settle
    path). It folds case, accents, punctuation and suffixes and nothing
    else — it does NOT fuzzy match, so two different players can never
    collide into one face.
    """
    FACE_JOIN["want"] += 1
    if not assets:
        return ""
    a = assets.get(player)
    if a is None:
        a = _norm_index(assets).get(_norm(player or ""))
    url = (a or {}).get("headshot", "")
    if url:
        FACE_JOIN["got"] += 1
    return url


def shared_recommendations(props: list[dict],
                           lines_map: dict | None = None,
                           dates_map: dict | None = None,
                           tune: LeagueTuning = NBA,
                           assets: dict | None = None) -> list[dict]:
    """Every evaluable prop as a shared-schema recommendation dict.

    ``lines_map``: {(player, market): [line dicts]} — the multi-book quotes
    the Scanner needs (Scalpy itself only keeps the best two-way price).
    ``dates_map``: {player: [ISO dates, newest first]} for real log labels.

    ``assets``: {player: {espn_id, headshot}} from `db.player_assets`, so a
    prop can carry the player's photo. ESPN's box score ships the URL
    beside the athlete and the hoops ingest now stores it; this is only the
    lookup. Absent, every face falls back to the initials avatar — which is
    what the board did before, so an old database is not a broken one.

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
            # Was hardcoded "". The field has been on this record all along
            # and nothing ever filled it, so every NBA and WNBA prop drew
            # the initials avatar while ESPN was handing us the photo URL
            # in the same payload the stat line came from.
            "headshot": _face(assets, r["player"]),
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
