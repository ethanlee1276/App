"""CFB pipeline — the shared spine, with the college-specific dial on top.

Deliberately NOT a new projection engine. §3 says the decision framework is
the same one every sport here uses, and §5 says the power rating is
opponent-adjusted efficiency — which is what ``engine.teamrates`` already
builds from ingested results, and ``engine.gamebets`` already prices into
moneyline/spread/total. Rebuilding that for college football would be
copying working code to make it worse.

What this module adds is everything the NFL spine does not know:

* which games the market is actually watching, and therefore how much of
  the edge to assume is error (§3.5, §8);
* a per-tier bar to clear rather than one number (§3.6);
* the two refusals — unconfirmed quarterback, unverified December roster
  (§2.3, §2.4) — which withhold a play instead of shading it;
* the 0–100 grade with CFB's weights, information certainty raised to 20%
  because this sport's reporting is the weakest (§9);
* the caps that stop a 60-game Saturday turning into eight mediocre bets
  (§9).

A no-play Saturday is the expected output far more often than not, and
saying so is the rule (§11).
"""

from __future__ import annotations

from .model import (attention_tier, haircut_edge, min_edge_for, grade,
                    grade_label, GradeInput, kelly_stake, apply_caps,
                    blocking_conditions, MIN_GRADE, LOW, MARQUEE)

MARKET_LABELS = {"side": "Spread", "total": "Total", "moneyline": "Moneyline",
                 "team_total": "Team total", "prop": "Player prop"}


def _dec(odds: int) -> float:
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / abs(odds))


def break_even(odds: int) -> float:
    return round(1.0 / _dec(odds), 4)


def devig(odds_a: int, odds_b: int) -> tuple[float, float]:
    """Multiplicative de-vig — the default the spec names (§3.2)."""
    qa, qb = 1.0 / _dec(odds_a), 1.0 / _dec(odds_b)
    return round(qa / (qa + qb), 4), round(qb / (qa + qb), 4)


def volatility(game: dict, tier: str, tags: list[str]) -> str:
    """§8 — CFB baseline volatility runs higher than the NFL at every tier.

    Rivalry chaos, blowout frequency and 19-year-olds widen the
    distribution; this is what the stake and the simulation have to respect.
    """
    score = 1                                    # everything starts MEDIUM-ish
    if "rivalry" in tags:
        score += 1
    if tier == LOW:
        score += 1                               # thin data, wild talent gaps
    if abs(float(game.get("spread") or 0)) >= 21:
        score += 1                               # blowout range
    if not game.get("qb_confirmed"):
        score += 1
    return ["LOW", "MEDIUM", "HIGH", "EXTREME"][min(3, score)]


def evaluate_play(play: dict) -> dict:
    """One priced market → a published play, or a pass with the reason.

    ``play`` carries the market (odds both ways), the model's probability,
    and the game context. The model probability is an INPUT — produced by
    the shared ratings/pricing layer — because the college-specific work
    is deciding whether that number is worth betting, not recomputing it.
    """
    game = play.get("game") or {}
    market = play.get("market", "side")
    tier = attention_tier(game)
    odds, opp_odds = int(play["odds"]), int(play["opposing_odds"])
    p_model = float(play["p_model"])

    p_market, _ = devig(odds, opp_odds)
    raw = p_model - p_market
    cut = haircut_edge(raw, tier)
    bar = min_edge_for(tier, market)
    tags = [t for t in (play.get("situational_tags") or [])]

    base = {
        "game": game.get("label") or f"{game.get('away','?')} @ {game.get('home','?')}",
        "game_id": game.get("game_id", ""),
        "market": market, "market_label": MARKET_LABELS.get(market, market),
        "selection": play.get("selection", ""),
        "line": play.get("line"), "odds": odds, "book": play.get("book", ""),
        "attention_tier": tier,
        "p_market": p_market, "p_model": round(p_model, 4),
        "edge_raw": round(raw, 4), "edge": cut, "required_edge": bar,
        "break_even": break_even(odds),
        "volatility": volatility(game, tier, tags),
        "situational_tags": tags,
        "kickoff": game.get("kickoff", ""),
        "conference": game.get("home_conference", ""),
        # §11.8 — the conditions, stated with the play rather than assumed.
        "conditions": {
            "qb_confirmed": bool(game.get("qb_confirmed")),
            "participation_verified": bool(game.get("participation_verified")),
            "weather_checked": bool(game.get("weather_checked")),
            "as_of": game.get("as_of", ""),
        },
        "risks": play.get("risks") or [],
    }

    if cut < bar:
        return {**base, "kind": "pass", "grade": 0, "grade_label": "Pass",
                "why": (f"edge {cut:+.1%} after the {tier} haircut is under "
                        f"this tier's {bar:.1%} bar")}

    # §2.3 says the refusal PUBLISHES A CONDITIONAL — "IF the starter
    # plays" — not nothing. So a blocked play is graded on the certainty it
    # would have once the condition clears, and only then held. Grading it
    # on today's ignorance instead would bury the very games worth checking:
    # the unconfirmed quarterback is why the number is soft in the first
    # place, so penalising the grade for it AND gating on it would mean the
    # board never surfaces a single game worth a phone call.
    blocks = blocking_conditions(game, market)
    certainty = float(play.get("information_certainty", 0.0))
    if blocks:
        certainty = float(play.get("information_certainty_confirmed", certainty))

    g = grade(GradeInput(
        edge_after_haircut=cut, tier=tier,
        information_certainty=certainty,
        attention_fit=float(play.get("attention_fit", 0.0)),
        situational_fit=float(play.get("situational_fit", 0.0)),
        matchup_fit=float(play.get("matchup_fit", 0.0)),
        environment_fit=float(play.get("environment_fit", 0.0))))
    card = {**base, "grade": g, "grade_label": grade_label(g)}
    if g < MIN_GRADE:
        return {**card, "kind": "pass",
                "why": f"grade {g} below the {MIN_GRADE} bar — no bet, no leans"}

    # Kelly runs on the POST-haircut edge (§9), which is the whole point of
    # haircutting: stake the number you believe, not the one you hoped for.
    p_staked = min(0.99, break_even(odds) + cut)
    stake = kelly_stake(p_staked, odds, tier, g,
                        drawdown=bool(play.get("drawdown")))
    if blocks:
        # A conditional carries everything a play does EXCEPT the stake, so
        # it can be acted on the moment the condition clears — and so that
        # no renderer can mistake it for a bet that was sized.
        return {**card, "kind": "hold", "grade_label": "Conditional",
                "why": "; ".join(blocks),
                "conditions_pending": blocks,
                "stake_if_confirmed": stake,
                "graded_as_if_confirmed": True}
    card["stake_fraction"] = stake
    return {**card, "kind": "play"}


def run_cfb_slate(plays: list[dict], meta: dict | None = None) -> dict:
    """A Saturday → the published card, the holds, and the pass list."""
    evaluated = [evaluate_play(p) for p in plays]
    published = [c for c in evaluated if c["kind"] == "play"]
    holds = [c for c in evaluated if c["kind"] == "hold"]
    passes = [c for c in evaluated if c["kind"] == "pass"]

    holds.sort(key=lambda p: (-p["grade"], -p["edge"]))
    published = apply_caps(published)
    # A play the caps trimmed to nothing is not a play.
    dropped = [p for p in published if p.get("stake_fraction", 0) <= 0]
    published = [p for p in published if p.get("stake_fraction", 0) > 0]
    published.sort(key=lambda p: (-p["grade"], -p["edge"]))
    passes += [{**p, "kind": "pass",
                "why": p.get("cap_note") or "no room under the slate cap"}
               for p in dropped]

    # §11 — the closest misses, so a no-play slate still says something.
    near = sorted((p for p in passes if p.get("edge", 0) > 0),
                  key=lambda p: -(p["edge"] - p.get("required_edge", 0)))[:3]

    return {
        "sport": "cfb",
        "plays": published,
        "holds": holds,
        "pass_list": passes,
        "near_misses": near,
        "no_qualifying": not published,
        "exposure": round(sum(p["stake_fraction"] for p in published), 5),
        "counts": {"priced": len(plays), "published": len(published),
                   "held": len(holds), "passed": len(passes)},
        "by_tier": {t: sum(1 for p in published if p["attention_tier"] == t)
                    for t in (MARQUEE, "standard", LOW)},
        "meta": meta or {},
    }
