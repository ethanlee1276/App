"""Market tiers, volatility ratings and the unified 0–100 bet quality grade.

Implements §3, §8 and §10 of docs/NFL_MODEL.md:

- Markets are tiered by how beatable they are. Tier 1 (count props) gets the
  smallest haircut and the lowest bar; Tier 3 (touchdowns) gets the deepest
  haircut and the highest bar, because most of a big raw edge in a rare-event
  market is model error, not alpha.
- Every play carries a volatility rating — the same edge is worth more in a
  stable market than a volatile one.
- ONE 0–100 quality score per play, weighted exactly as the spec demands:
  post-haircut edge 40% · usage stability 15% · market movement 15% ·
  game-script fit 10% · matchup fit 10% · weather/context 10%.
  A+ (90+) max stake · A (80–89) standard · B+ (70–79) minimum ·
  below 70 no bet — and no "Leans". A lean is a bet that failed the filter
  published anyway; the tier was deleted, not renamed.
"""

from __future__ import annotations

from .statmath import clamp

# --- §8: market tiers --------------------------------------------------------
# Tier 1 — count props (receptions today; attempts/carries/completions when
# the odds feed carries them). Tier 2 — yardage, efficiency-contaminated.
# Tier 3 — touchdowns, quarantined on the long-shot board.
MARKET_TIER = {
    "receptions": 1,
    "pass_yds": 2, "rush_yds": 2, "rec_yds": 2,
    "anytime_td": 3,
    # Game lines, since the 0–100 grade became the ONE gate (Ethan,
    # 2026-09-02: "1. 0-100"). Tier 1 is `engine/parlays.TIER`'s standing
    # classification — "the numbers a book prices most carefully and we
    # price most carefully" — so the §3 minimum edge is 2.5%.
    "moneyline": 1, "spread": 1, "total": 1, "team_total": 1,
    # The other long-shot market, Tier 3 with anytime_td for the same
    # reason §8 gives: high vig, rare event, most of a raw edge is error.
    "home_runs": 3, "pass_td": 3,
}

# §3 step 5: how much of a raw model-vs-market disagreement we trust.
TIER_SHRINK = {1: 0.50, 2: 0.45, 3: 0.30}

# §3 step 6: minimum POST-haircut edge (vs the devigged fair prob) to bet.
#
# RE-TUNED 2026-07-29 (operator call): the minimum must sit INSIDE the
# believable window, or the tier is mathematically closed rather than
# disciplined. The credibility guard treats raw disagreement over 10% as
# bad data, so the largest believable post-haircut edge is
# 10% × shrink — 5.0% in Tier 1, 4.5% in Tier 2. The spec's original 4%
# Tier 2 minimum left a half-point sliver (raw 8.9–10.0%), which produced
# one pick on a full ten-game slate: a closed door wearing a bar's
# clothes. 3% gives Tier 2 a real window (raw 6.7–10%) while still
# demanding twice the vig's worth of edge. Tier 3 stays at 6% — above its
# own believable ceiling ON PURPOSE: touchdown/HR markets are quarantined
# on the Long Shots board with its own measured tier, never main picks.
TIER_MIN_EDGE = {1: 0.025, 2: 0.030, 3: 0.060}

#: THE WINDOW THE BAR ACTUALLY LEAVES, and why it needs a function rather
#: than the arithmetic in the comment above.
#:
#: That comment computes the largest believable post-haircut edge as
#: ``MAX_CREDIBLE_EDGE × shrink`` — 5.0% in Tier 1, 4.5% in Tier 2 — and
#: sets each bar inside it. That was exact on 2026-07-29 and it is not
#: exact now: `engine.selectionfit` shipped on 2026-08-12 and
#: `betting.evaluate_prop` applies its haircut to `edge` IMMEDIATELY
#: AFTER the tier shrink and BEFORE this bar is compared. So the window
#: the bar has to sit inside is narrower than the comment's arithmetic
#: by however much the live haircut is worth, and nothing re-derives it.
#:
#: Measured against the shipped code (see tests/test_bar_reachable.py):
#: at a haircut worth 2.5 probability points, Tier 2 — pass_yds, the only
#: Tier 2 market the NFL still prices — cannot produce a bet at ANY book
#: price between .30 and .70. At 4.2 points neither tier can, anywhere in
#: that range. The over-claim that motivated the haircut was measured at
#: 9-10 points.
#:
#: This is the failure the 2026-07-29 re-tune was written to prevent —
#: "the tier is mathematically closed rather than disciplined" — arriving
#: by a different door, and it is invisible: a closed tier and a tier
#: that merely found nothing both render as "no qualifying plays". The
#: bars are an operator call and this does not change them. It makes the
#: closure SAYABLE.
def best_possible_edge(market: str, shift: float = 0.0,
                       fair: float = 0.50) -> float:
    """The largest edge a CREDIBLE prop in this market can still show.

    The chain a real row walks, at its most favourable point: a raw
    disagreement exactly at the credibility ceiling, shrunk by the
    market's tier, then moved by the live selection haircut.
    """
    from .betting import MAX_CREDIBLE_EDGE
    from .selectionfit import shift_prob
    hit = fair + tier_shrink(market) * min(MAX_CREDIBLE_EDGE,
                                           max(0.0, 0.999 - fair))
    return (hit - fair) + (shift_prob(hit, shift) - hit)


def bar_reachable(sport: str, market: str, fair: float = 0.50,
                  shift: float | None = None) -> tuple[bool, float, float]:
    """``(reachable, best_possible_edge, the bar)`` for this market.

    ``reachable`` False means no prop in this market can clear its own
    minimum however good the read is — the board is not being selective,
    it is shut. Tier 3 answers False BY DESIGN (touchdown and home-run
    markets are quarantined to the Long Shots board, see TIER_MIN_EDGE);
    callers that only care about the main board should skip Tier 3.
    """
    if shift is None:
        from .selectionfit import shift_for
        shift = shift_for(sport)
    best = best_possible_edge(market, shift, fair)
    bar = tier_min_edge(market)
    return best >= bar, best, bar


def unreachable_markets(sport: str, markets, fair: float = 0.50) -> list[str]:
    """Which of these markets cannot clear their own bar right now.

    Tier 3 is excluded: it is shut on purpose and reporting it every
    cycle would bury the one case worth reading.
    """
    out = []
    for m in markets or ():
        if market_tier(m) == 3:
            continue
        ok, _best, _bar = bar_reachable(sport, m, fair)
        if not ok:
            out.append(m)
    return out

VOLATILITY = {
    "receptions": "LOW",
    "pass_yds": "MEDIUM",          # lowest CV of the yardage family
    "rush_yds": "HIGH", "rec_yds": "HIGH",
    "anytime_td": "EXTREME",
}

GRADE_BANDS = (("A+", 90), ("A", 80), ("B+", 70))

# §10 bankroll caps: 2u max on any single play (1u = 1% bankroll), stepped
# down with the grade — minimum-stake grades cannot take maximum-stake sizes.
STAKE_CAP_U = {"A+": 2.0, "A": 1.0, "B+": 0.5}

_ORDER = {"Pass": 0, "B+": 1, "A": 2, "A+": 3}


def market_tier(market: str) -> int:
    return MARKET_TIER.get(market, 2)


def tier_shrink(market: str) -> float:
    return TIER_SHRINK[market_tier(market)]


def tier_min_edge(market: str) -> float:
    return TIER_MIN_EDGE[market_tier(market)]


def volatility(market: str) -> str:
    return VOLATILITY.get(market, "HIGH")


def letter(score: float) -> str:
    for name, floor in GRADE_BANDS:
        if score >= floor:
            return name
    return "Pass"


def quality_score(*, edge: float, market: str, side: str,
                  favored, spread_abs: float,
                  matchup_mult: float, weather_mult: float,
                  cv: float, cv_typical: float, sample_games: int,
                  movement_pts: float | None = None) -> tuple[int, list[str]]:
    """The unified grade. Returns ``(score 0–100, component notes)``.

    ``favored`` is True/False for the player's team, or None when no spread
    is posted. ``cv`` is the player's own week-to-week coefficient of
    variation in this stat; ``cv_typical`` is the market's normal level, so
    a rotation-driven player scores badly in EVERY market, not just smooth
    ones. ``movement_pts`` is None until line-movement snapshots exist —
    a neutral 8/15, adjusted later by apply_movement().
    """
    tier = market_tier(market)
    notes: list[str] = []

    # Edge (40): the tier minimum earns two-thirds credit; 1.5× the minimum
    # earns full credit. (Re-tuned 2026-07-29 with the minimums above: the
    # old half-credit scaling meant a gate-passing edge with neutral
    # context still graded below 70 — the edge gate and the quality gate
    # were double-charging for the same caution, and the credibility cap
    # makes "twice the minimum" unreachable in Tier 2 anyway.)
    edge_pts = clamp(edge / (1.5 * TIER_MIN_EDGE[tier]), 0.0, 1.0) * 40.0

    # Usage stability (15): §5's "who to avoid" filter. Week-to-week CV
    # relative to what this market normally shows, times sample depth.
    sample_q = clamp(sample_games / 8.0, 0.3, 1.0)
    var_q = clamp(cv_typical / cv, 0.4, 1.0) if cv > 0 else 1.0
    stability_pts = 15.0 * sample_q * var_q
    if var_q < 0.7:
        notes.append("Volatile week-to-week role — stability discount applied")

    # Market movement (15): neutral until snapshots say otherwise.
    move_pts = 8.0 if movement_pts is None else clamp(movement_pts, 0.0, 15.0)

    # Game-script fit (10): §7 logic. Rushing overs want a favorite (leading
    # teams run); passing overs want a dog or a close spread (trailing teams
    # throw). Unders invert. No spread posted → neutral.
    script_pts = 6.0
    if favored is not None:
        over = side == "OVER"
        wants_favored = (market == "rush_yds") == over   # rush OVER / pass UNDER
        fits = favored == wants_favored
        big = spread_abs >= 7.0
        script_pts = (9.0 if not big else 10.0) if fits else (4.0 if big else 6.0)
        if not fits and big:
            notes.append("Game script leans against this side of the number")

    # Matchup fit (10): does the opponent-adjusted multiplier agree with the
    # side we're taking?
    def _fit(mult: float) -> float:
        over = side == "OVER"
        if (mult >= 1.03) == over and abs(mult - 1.0) >= 0.03:
            return 10.0
        if abs(mult - 1.0) < 0.03:
            return 6.0
        return 3.0
    matchup_pts = _fit(matchup_mult)
    if matchup_pts <= 3.0:
        notes.append("Matchup adjustment points the other way")

    # Weather/context (10): a dome or calm day is mildly positive certainty.
    weather_pts = 7.0 if abs(weather_mult - 1.0) < 0.01 else _fit(weather_mult)
    if weather_pts <= 3.0:
        notes.append("Weather works against this side")

    total = edge_pts + stability_pts + move_pts + script_pts + matchup_pts + weather_pts
    return int(round(clamp(total, 0.0, 100.0))), notes


# --- the same score for the boards that used to grade in words --------------
#
# Ethan, 2026-09-02, closing the NFL readiness audit's first Ask: "1. 0-100".
# Until then `quality_score` above graded the prop board and TWO other
# ladders graded everything else — `betting._grade`'s Strong Play / Play /
# Pass on game lines and `longshots._grade`'s Strong Play / Play / Lean /
# Pass on the long-shot boards — three vocabularies on one site, which is
# the loophole §10 names ("two systems that can disagree"). The long-shot
# ladder also published Leans at 1.5% of edge, the thing §10 says is "how
# discipline dies in public".
#
# So: one score, §10's weights, for every board. A component a board has
# no measurement for takes the NEUTRAL value the prop score already uses
# for the same situation — movement 8/15 with no snapshots, script 6/10
# with no spread, weather 7/10 on a calm day — rather than a number
# invented for the occasion. Stability has no neutral in the prop score
# (a prop always has a sample), so a game bet, which has no per-player
# usage to be stable, takes the same 8/15 movement uses. The consequence
# is stated rather than hidden: with every context component neutral a
# game bet tops out at 75, B+, the minimum stake — which is also what
# §10 says about a bet nothing but its edge recommends.
NEUTRAL = {"stability": 8.0, "movement": 8.0, "script": 6.0,
           "matchup": 6.0, "weather": 7.0}


def _edge_points(edge: float, market: str) -> float:
    """§10's 40: the tier minimum earns two-thirds, 1.5× the minimum all."""
    return clamp(edge / (1.5 * tier_min_edge(market)), 0.0, 1.0) * 40.0


def game_bet_score(edge: float, market: str) -> int:
    """The unified grade for a side or a total — edge, and neutral context."""
    total = (_edge_points(edge, market) + NEUTRAL["stability"]
             + NEUTRAL["movement"] + NEUTRAL["script"] + NEUTRAL["matchup"]
             + NEUTRAL["weather"])
    return int(round(clamp(total, 0.0, 100.0)))


def longshot_score(edge: float, market: str, opportunities: float,
                   opp_target: float, data_quality: float = 1.0) -> int:
    """The unified grade for a touchdown or home-run pick.

    ``edge`` is the GRADED edge (`longshots.build_pick`: the model over the
    cheaper of the consensus and the price). Usage stability is the one
    context component these boards measure — expected chances against
    the target a full-role player carries, discounted by the quality of
    the red-zone data behind it, exactly the two discounts the old
    confidence formula applied. Everything else is neutral.
    """
    opp_q = clamp(opportunities / opp_target, 0.0, 1.0) if opp_target > 0 else 0.0
    stability = 15.0 * opp_q * clamp(data_quality, 0.7, 1.0)
    total = (_edge_points(edge, market) + stability + NEUTRAL["movement"]
             + NEUTRAL["script"] + NEUTRAL["matchup"] + NEUTRAL["weather"])
    return int(round(clamp(total, 0.0, 100.0)))


def apply_movement(rec: dict, with_us: bool, steam: bool) -> None:
    """Fold observed line movement into an already-graded pick (§4).

    Movement WITH the pick raises the score (and can raise the letter, though
    never the stake — sizing stays conservative). Sharp movement AGAINST the
    pick is treated as the market pricing information we don't have: the
    score drops, and if it falls below 70 the pick is rejected outright.
    """
    if rec.get("quality") is None:
        return
    delta = (7.0 if steam else 4.0) * (1.0 if with_us else -1.0)
    # Stamped HERE rather than recomputed by the journal, for the same
    # reason ledger.py reads the calibration correction in the process that
    # priced the pick: what gets recorded has to be what was applied. A
    # second copy of this arithmetic somewhere else would drift, and the
    # column exists precisely so the veto can be checked against outcomes.
    rec["move_delta"] = delta
    rec["move_steam"] = 1.0 if steam else 0.0
    q = int(round(clamp(rec["quality"] + delta, 0.0, 100.0)))
    rec["quality"] = q
    rec["confidence"] = round(q / 10.0, 1)
    new = letter(q)
    old = rec.get("grade", "Pass")
    if new == "Pass" and old != "Pass":
        rec["grade"] = "Pass"
        rec["recommended"] = False
        rec["stake_units"] = 0.0
        # The rejection itself, so a `loose` row can be told apart from a
        # prop that merely graded low. Without it the bucket says "quality
        # 66/70" and the cause is gone.
        rec["move_rejected"] = True
        rec.setdefault("warnings", []).append(
            "Sharp movement against the pick dropped its quality below 70 — "
            "rejected: model edge that fights fresh sharp money is usually "
            "stale data, not genius")
    elif _ORDER.get(new, 0) > _ORDER.get(old, 0) and old != "Pass":
        rec["grade"] = new
