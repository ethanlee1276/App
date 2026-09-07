"""The WNBA spec's §5 stability filter and §8 grade, as measurements.

Two ideas from the college and NFL work carry straight over, and one is
new to this league.

**A volatile role is unbettable at any edge (§5).** The projection is
minutes × a per-minute rate. If the minutes are a coin flip the projection
is fiction, and the edge computed from it is fiction with a decimal point.
So role volatility is measured — the coefficient of variation of recent
minutes — and above a threshold the play is refused rather than shaded.
This is the filter that removes bench players on deep teams and anyone in
an unsettled rotation battle, which in a 7-8 player rotation is exactly
where a model most wants to fool itself.

**The grade is 40% edge and 60% context (§8).** That makes the five
context components the things that actually decide what gets bet, which
makes them the easiest place in the system to cheat: numbers between 0 and
1, invisible on the page. Every one here is a restatement of something the
build measured. Where a fact is missing the component scores half and says
so, rather than assuming the best case.

**Minutes certainty carries 20% because minutes are the king input**, and
freshness 15% because the timing window on an availability report is where
this league's profit actually lives. Both are the spec's weights, not a
re-derivation.

The grade only GATES where a league's tuning says it does
(``LeagueTuning.min_grade``). The NBA board predates this and is
calibrated; bolting a new bar onto a working model because a different
league's spec asked for one would be a silent re-tune, so the NBA reports
the grade and keeps its own approval gate as the authority.
"""

from __future__ import annotations

from ..hoops import NBA, LeagueTuning

# How volatile a role can be before it is a coin flip rather than a role.
DEFAULT_MAX_CV = 0.35
# Minutes below which "stable" means nothing — a deep bench player who
# reliably plays 12 minutes is not a bettable role, he is a rounding error.
STABILITY_MIN_MINUTES = 12.0


def usage_stability(minutes: list[float], window: int = 8) -> dict:
    """§5 Usage Stability Score from week-to-week minutes variance.

    Returns the coefficient of variation, a 0-1 score for the grade, and
    whether the role is too volatile to bet. A short sample is treated as
    unstable, not as stable — three games of data is not evidence of a
    settled role.
    """
    vals = [float(m) for m in (minutes or [])[:window] if m is not None]
    if len(vals) < 4:
        return {"cv": None, "score": 0.25, "volatile": True, "samples": len(vals),
                "note": f"only {len(vals)} game(s) of minutes — role unproven"}
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return {"cv": None, "score": 0.0, "volatile": True, "samples": len(vals),
                "note": "no minutes in the recent window"}
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    cv = (var ** 0.5) / mean
    # A CV of 0 scores 1.0 and the threshold scores 0.5, so the component
    # degrades smoothly instead of falling off a cliff at the gate.
    score = max(0.0, min(1.0, 1.0 - cv / (2 * DEFAULT_MAX_CV)))
    return {"cv": round(cv, 3), "score": round(score, 3),
            "volatile": cv > DEFAULT_MAX_CV or mean < STABILITY_MIN_MINUTES,
            "samples": len(vals), "mean_minutes": round(mean, 1),
            "note": (f"minutes vary {cv:.0%} week to week over {len(vals)} "
                     f"games (mean {mean:.1f})")}


def stability_blocks(minutes: list[float], tune: LeagueTuning = NBA) -> str:
    """The refusal string when a role is too volatile to bet, else ''."""
    if tune.stability_max_cv is None:
        return ""
    st = usage_stability(minutes)
    if st["cv"] is None:
        return f"role unproven — {st['note']}"
    if st["cv"] > tune.stability_max_cv:
        return (f"role volatility {st['cv']:.0%} over the "
                f"{tune.stability_max_cv:.0%} bar — the projection assumes a "
                f"role this player does not reliably have")
    if st.get("mean_minutes", 0) < STABILITY_MIN_MINUTES:
        return (f"{st['mean_minutes']:.1f} minutes a game — too small a role "
                f"to project a stat line from")
    return ""


def edge_score(edge: float, required: float) -> float:
    """Edge as 0-1, measured against THIS market's own bar.

    Scaling by the tier's requirement is the point: +3.2% has cleared a
    tier-1 bar and missed a tier-3 one, and they must not score the same.
    """
    if edge <= 0 or required <= 0:
        return 0.0
    if edge < required:
        return round(0.5 * edge / required, 4)
    return round(min(1.0, 0.5 + 0.5 * (edge - required) / (2 * required)), 4)


MINUTES_GRADE_SCORE = {"A": 1.0, "B": 0.75, "C": 0.45, "D": 0.0}


def quality_score(edge: float, required: float, minutes_grade: str,
                  stability: float, freshness: float, movement: float,
                  matchup: float, schedule: float,
                  tune: LeagueTuning = NBA) -> int:
    """The §8 unified 0-100 grade.

    Minutes certainty is the AND of two different things — how confident we
    are in the role (the A-D minutes grade) and how stable that role has
    actually been (the measured CV) — because a starter in an unsettled
    rotation and a bench player with a fixed job fail in opposite ways and
    both need catching.
    """
    weights = tune.grade_weights or {}
    if not weights:
        return 0
    minutes_certainty = (MINUTES_GRADE_SCORE.get(minutes_grade, 0.0)
                         * max(0.0, min(1.0, stability)))
    parts = {
        "edge": edge_score(edge, required),
        "minutes_certainty": minutes_certainty,
        "freshness": max(0.0, min(1.0, freshness)),
        "movement": max(0.0, min(1.0, movement)),
        "matchup": max(0.0, min(1.0, matchup)),
        "schedule": max(0.0, min(1.0, schedule)),
    }
    return int(round(sum(parts.get(k, 0.0) * w for k, w in weights.items())))


def grade_label(score: int, tune: LeagueTuning = NBA) -> str:
    """A+/A/B+/Pass. There is no Lean tier — 'below 70: no bet, no leans'."""
    bar = tune.min_grade or 70
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= bar:
        return "B+"
    return "Pass"


def kelly_stake(p: float, odds: int, score: int, tier: int,
                tune: LeagueTuning = NBA) -> float:
    """Fraction of bankroll. Quarter Kelly; half only for an A+ in tier 1."""
    b = (odds / 100.0 if odds > 0 else 100.0 / abs(odds))
    if b <= 0:
        return 0.0
    full = (p * b - (1 - p)) / b
    if full <= 0:
        return 0.0
    frac = 0.50 if (score >= 90 and tier == 1) else 0.25
    return round(min(full * frac, tune.cap_per_play), 5)


def apply_exposure_caps(picks: list[dict], tune: LeagueTuning = NBA) -> list[dict]:
    """§8 per-game and per-slate caps, applied in grade order.

    Trimming best-first means the cap costs the worst play that was going
    to be made rather than a random one. Correlated plays on one game share
    the game cap, which is what stops a single blowout from taking three
    positions with it.
    """
    out, per_game, total = [], {}, 0.0
    for p in sorted(picks, key=lambda x: -x.get("grade_score", 0)):
        stake = p.get("stake_fraction", 0.0)
        gkey = tuple(sorted((p.get("team", ""), p.get("opponent", ""))))
        room_game = max(0.0, tune.cap_per_game - per_game.get(gkey, 0.0))
        room_slate = max(0.0, tune.cap_per_slate - total)
        allowed = round(min(stake, room_game, room_slate), 5)
        if allowed <= 0:
            out.append({**p, "stake_fraction": 0.0, "capped": True,
                        "cap_note": "game or slate cap reached — no room left"})
            continue
        per_game[gkey] = per_game.get(gkey, 0.0) + allowed
        total += allowed
        out.append({**p, "stake_fraction": allowed,
                    "capped": allowed < stake - 1e-9,
                    "cap_note": ("trimmed by the game/slate cap"
                                 if allowed < stake - 1e-9 else "")})
    return out
