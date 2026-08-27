"""College football — where the edge lives, and what it costs to claim it.

The decision spine is shared with every other sport here: devig, edge,
haircut, Kelly, CLV. What is rebuilt is everything that makes CFB its own
market, and one idea drives most of it.

**Attention is the axis.** ~134 FBS teams play 60+ games most Saturdays.
No book prices a Wednesday MAC game with the care it gives Ohio State –
Michigan, so the softness is a function of the spotlight. That single fact
inverts the usual tier order — in the NFL props are the soft spot, in CFB
the *unwatched full-game markets* are the core product — and it turns the
haircut from a constant into a dial: assume half your edge is error where
the market is sharp, far less where the number is genuinely lazy.

Everything else follows from taking young players and thin reporting
seriously: a QB whose status is unconfirmed cannot be graded final, and in
December a roster can be gutted by opt-outs and the portal between the
last game and the bowl. Both are gates, not adjustments — the model
refuses rather than guesses.

What this module deliberately does NOT do is invent the talent layer.
Recruiting composites, blue-chip ratio and returning production are real
edges (§6) and they need a real source; where that data is absent the
model says the prior is missing rather than substituting a number.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

# --- §8 market tiers, driven by attention ----------------------------------
MARQUEE, STANDARD, LOW = "marquee", "standard", "low"

# §3.5 — "the haircut is a dial, not a constant". The fraction of the raw
# edge assumed to be model error. Sharp markets get the full 50%.
HAIRCUT = {MARQUEE: 0.50, STANDARD: 0.35, LOW: 0.25}

# §3.6 — minimum edge AFTER the haircut.
#
# WHAT THESE BARS ACTUALLY PASS, measured 2026-08-27 once college
# football had closing lines to be graded against (engine/sources/
# cfblines) and `engine.gamecal` had replaced the flat 0.5 market shrink
# with a measured one. Every FBS game from 2022-25 with fifteen games of
# prior history on both sides — 2,055 of them — priced through the real
# path:
#
#     spread      every edge exactly 0.00%   → 0 plays at any tier
#     total       biggest edge +4.7%         → 73 low, 1 standard, 0 marquee
#
# The spread is zero BY CONSTRUCTION: its measured shrink is 0.0, so
# every disagreement collapses onto the market. That is the honest
# output of a model whose side beat the college close 48.4% of the time.
#
# The 73 that survive on totals went 41-30-2, 57.7% against the 52.4% a
# -110 line needs, +10.2% ROI. Encouraging and NOT proven: the shrink
# was fitted on the same games. Re-fitted on 2022-23 alone the slope is
# +0.088 ± 0.114 — an error bar wider than the estimate — and it selects
# five plays across 2024-25, which settles nothing either way.
#
# So the expectation to hold, and the reason the board is quiet rather
# than broken: college GAME bets are a couple of low-attention totals a
# season. The college volume is on the touchdown board.
MIN_EDGE = {MARQUEE: 0.040, STANDARD: 0.030, LOW: 0.025}
MIN_EDGE_PROP = 0.040          # every attention tier: thin menus, heavy vig

# §9 — grade weights, summing to 100.
GRADE_WEIGHTS = {"edge": 40, "information": 20, "attention_fit": 10,
                 "situational": 10, "matchup": 10, "environment": 10}
MIN_GRADE = 70                 # "Below 70: no bet, no leans."

# §9 — bankroll caps as fractions of bankroll.
CAP_PER_PLAY = 0.02
CAP_PER_GAME = 0.05
CAP_PER_SLATE = 0.12
DRAWDOWN_TRIGGER = 0.10        # a 10% drawdown halves stakes
KELLY_FRACTION = 0.25          # quarter Kelly default
KELLY_FRACTION_MAX = 0.50      # half Kelly: A+ in a Tier 1 (low-attention) spot

# The power conferences. Everything else is Group of Five or independent,
# which is where the spec says the soft numbers live.
POWER_CONFERENCES = {"SEC", "Big Ten", "Big 12", "ACC"}

# §7 — situational tags. Named because the spec is explicit that these are
# priced deliberately rather than narrated after the fact.
SITUATIONAL_TAGS = ("letdown", "lookahead", "rivalry", "sandwich",
                    "body_clock", "short_week", "eliminated", "bowl_eligible")

VOLATILITY = ("LOW", "MEDIUM", "HIGH", "EXTREME")


def attention_tier(game: dict) -> str:
    """How hard the market is looking at this game.

    Not a proxy for quality — a proxy for how many sharp dollars have
    already corrected the number. A ranked SEC game on Saturday afternoon
    is priced by everyone; a Tuesday MAC game is priced by a model and a
    few specialists.
    """
    home_conf = (game.get("home_conference") or "").strip()
    away_conf = (game.get("away_conference") or "").strip()
    both_power = home_conf in POWER_CONFERENCES and away_conf in POWER_CONFERENCES
    ranked = bool(game.get("home_rank")) + bool(game.get("away_rank"))
    weeknight = (game.get("weekday") or "").lower() not in ("saturday", "")

    # A weeknight game is a low-attention game almost by definition — that
    # is why the MACtion slate exists as a betting market at all.
    if weeknight and ranked < 2:
        return LOW
    if both_power and ranked >= 1:
        return MARQUEE
    if ranked >= 2:
        return MARQUEE
    if both_power:
        return STANDARD
    if not home_conf and not away_conf:
        return STANDARD              # unknown conferences: don't claim softness
    return LOW if not (home_conf in POWER_CONFERENCES
                       or away_conf in POWER_CONFERENCES) else STANDARD


def haircut_edge(raw_edge: float, tier: str) -> float:
    """§3.5 — shrink the edge by how sharp this market is."""
    return round(raw_edge * (1.0 - HAIRCUT.get(tier, 0.5)), 5)


def min_edge_for(tier: str, market: str = "side") -> float:
    """§3.6 — the bar this bet has to clear after the haircut."""
    if market == "prop":
        return MIN_EDGE_PROP
    return MIN_EDGE.get(tier, MIN_EDGE[MARQUEE])


# --- §2 the two refusals ----------------------------------------------------
def december_window(kickoff_iso: str) -> bool:
    """Bowl season, where a roster can be gutted between the last game and
    the bowl by opt-outs, the portal and a coaching change."""
    try:
        d = _dt.date.fromisoformat((kickoff_iso or "")[:10])
    except ValueError:
        return False
    return d.month == 12 or (d.month == 1 and d.day <= 20)


def blocking_conditions(game: dict, market: str = "side") -> list[str]:
    """Reasons this bet cannot be graded final yet.

    These are gates, not penalties. §2.3 and §2.4 are written as refusals
    because the alternative — pricing a game whose quarterback might not
    play — is the error that ends credibility, and it is entirely
    avoidable by waiting.
    """
    out = []
    qb_relevant = market in ("side", "total", "prop", "team_total")
    if qb_relevant and not game.get("qb_confirmed"):
        who = game.get("qb_uncertain_team") or "a starting QB"
        out.append(f"{who} status unconfirmed — the starter-to-backup gap in "
                   f"CFB is routinely 4–7+ points, so the whole game reprices")
    if december_window(game.get("kickoff", "")) and not game.get("participation_verified"):
        out.append("December game with participation unverified — opt-outs, "
                   "portal departures and staff changes gut bowl rosters")
    return out


# --- §9 the grade -----------------------------------------------------------
@dataclass
class GradeInput:
    edge_after_haircut: float
    tier: str
    information_certainty: float = 0.0   # 0–1: QB/injury/roster confirmed
    attention_fit: float = 0.0           # 0–1: is the edge plausible here?
    situational_fit: float = 0.0         # 0–1
    matchup_fit: float = 0.0             # 0–1
    environment_fit: float = 0.0         # 0–1


def _edge_score(edge: float, tier: str) -> float:
    """Edge as a 0–1 score, measured against THIS tier's bar.

    Scaling by the tier's own minimum is the point: +2.6% in a Tuesday MAC
    game has cleared its bar and +2.6% in a marquee game has not, so they
    must not score the same."""
    bar = MIN_EDGE.get(tier, MIN_EDGE[MARQUEE])
    if edge <= 0:
        return 0.0
    # At the bar → 0.5; at three times the bar → 1.0.
    return round(min(1.0, 0.5 * edge / bar if edge < bar else
                     0.5 + 0.5 * (edge - bar) / (2 * bar)), 4)


def grade(g: GradeInput) -> int:
    """The 0–100 Unified Bet Quality Grade of §9."""
    parts = {
        "edge": _edge_score(g.edge_after_haircut, g.tier),
        "information": max(0.0, min(1.0, g.information_certainty)),
        "attention_fit": max(0.0, min(1.0, g.attention_fit)),
        "situational": max(0.0, min(1.0, g.situational_fit)),
        "matchup": max(0.0, min(1.0, g.matchup_fit)),
        "environment": max(0.0, min(1.0, g.environment_fit)),
    }
    return int(round(sum(parts[k] * w for k, w in GRADE_WEIGHTS.items())))


def grade_label(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B+"
    return "Pass"


# --- §9 staking -------------------------------------------------------------
def _dec(odds: int) -> float:
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / abs(odds))


def kelly_stake(p: float, odds: int, tier: str, score: int,
                drawdown: bool = False) -> float:
    """Fraction of bankroll to risk. Quarter Kelly, half only for A+ in a
    Tier 1 spot, capped per play, halved inside a drawdown."""
    b = _dec(odds) - 1.0
    if b <= 0:
        return 0.0
    full = (p * b - (1 - p)) / b
    if full <= 0:
        return 0.0
    frac = (KELLY_FRACTION_MAX if (score >= 90 and tier == LOW)
            else KELLY_FRACTION)
    stake = min(full * frac, CAP_PER_PLAY)
    # Halve AFTER the cap, not before. "Halve stakes until the peak is
    # recovered" is about real exposure, and any play whose raw Kelly
    # already exceeds the 2% ceiling would otherwise be halved to a number
    # still above it — the drawdown rule doing nothing precisely when it
    # matters most.
    if drawdown:
        stake *= 0.5
    return round(stake, 5)


def apply_caps(plays: list[dict]) -> list[dict]:
    """§9 — 5% per game and 12% per slate, applied in grade order.

    With 60+ games on the board, the slate cap is the structural defence
    against this sport's version of volume bleed: eight pretty-good numbers
    instead of three great ones. Trimming in grade order means the cap
    costs you the worst play you were going to make, not a random one.
    """
    out, per_game, total = [], {}, 0.0
    for p in sorted(plays, key=lambda x: -x.get("grade", 0)):
        stake = p.get("stake_fraction", 0.0)
        gkey = p.get("game_id") or p.get("game") or ""
        room_game = max(0.0, CAP_PER_GAME - per_game.get(gkey, 0.0))
        room_slate = max(0.0, CAP_PER_SLATE - total)
        allowed = round(min(stake, room_game, room_slate), 5)
        trimmed = allowed < stake - 1e-9
        if allowed <= 0:
            out.append({**p, "stake_fraction": 0.0, "capped": True,
                        "cap_note": "slate or game cap reached — no room left"})
            continue
        per_game[gkey] = per_game.get(gkey, 0.0) + allowed
        total += allowed
        out.append({**p, "stake_fraction": allowed, "capped": trimmed,
                    "cap_note": ("trimmed by the game/slate cap" if trimmed
                                 else "")})
    return out
