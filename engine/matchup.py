"""Matchup analyzer.

Compares the prop's player against the specific defensive strength he'll face
and against game script (spread/total). Produces a multiplier and reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    DefenseProfile, Prop, Game,
    PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS,
)
from .statmath import clamp


@dataclass
class MatchupEffect:
    multiplier: float
    reasons: list[str] = field(default_factory=list)


def _defense_factor(defense: DefenseProfile, prop: Prop) -> tuple[float, str]:
    """Pick the relevant 'vs position' multiplier for this prop."""
    if prop.market == PASS_YDS:
        return defense.vs_qb, "pass defense"
    if prop.market == RUSH_YDS:
        rank = defense.rush_rank
        note = f"ranked {rank}{_ord(rank)} vs the run"
        return defense.vs_rb_rush, note
    if prop.market in {REC_YDS, RECEPTIONS}:
        role = prop.usage_role
        if role in {"wr1"}:
            return defense.vs_wr1, "vs WR1"
        if role in {"wr2"}:
            return defense.vs_wr2, "vs WR2"
        if role in {"slot"}:
            return defense.vs_slot, "vs slot receivers"
        if role in {"te"}:
            return defense.vs_te, "vs tight ends"
        return defense.vs_rb_recv, "vs pass-catching backs"
    return 1.0, ""


def _ord(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def evaluate_matchup(prop: Prop, defense: DefenseProfile, game: Game,
                     measured_context: bool = False) -> MatchupEffect:
    """``measured_context`` says the caller is ALSO pricing engine.teamcontext
    (NFL Phase 2). Two of the adjustments below are hand-tuned stand-ins for
    exactly what that layer measures — the spread-derived game script
    approximates the team's pass rate, and the total-derived play bump
    approximates its pace — so running both stacks a measurement on top of a
    guess at the same effect. When the measured version is present these
    stand down; the DEFENSIVE factor always stays, because nothing in
    teamcontext prices the opponent."""
    mult = 1.0
    reasons: list[str] = []

    factor, note = _defense_factor(defense, prop)
    factor = clamp(factor, 0.80, 1.25)
    mult *= factor
    if factor >= 1.06:
        reasons.append(f"Favorable defensive matchup — opponent {note} ({factor - 1:+.0%} vs avg)")
    elif factor <= 0.94:
        reasons.append(f"Tough defensive matchup — opponent {note} ({factor - 1:+.0%} vs avg)")

    # Game script from the spread. A team favored by a lot leans on the run
    # late (helps RB rush), while a big underdog throws more (helps pass game).
    is_home = prop.team == game.home
    team_spread = game.spread if is_home else -game.spread   # negative = favored

    if measured_context:
        # PROE and pace are being priced for real; stop guessing at them.
        return MatchupEffect(multiplier=mult, reasons=reasons)

    if prop.market == RUSH_YDS:
        if team_spread <= -4:
            mult *= 1.06
            reasons.append(f"Team favored by {abs(team_spread):.0f} — positive rushing script")
        elif team_spread >= 6:
            mult *= 0.95
            reasons.append("Team is an underdog — fewer rushing attempts likely")
    if prop.market in {PASS_YDS, REC_YDS, RECEPTIONS}:
        if team_spread >= 6:
            mult *= 1.05
            reasons.append("Underdog script — elevated pass volume")

    # High total => more plays, more production for everyone.
    if game.total >= 48:
        mult *= 1.03
        reasons.append(f"High game total ({game.total:.0f}) — up-tempo, more opportunities")
    elif game.total <= 39:
        mult *= 0.97
        reasons.append(f"Low game total ({game.total:.0f}) — fewer scoring chances")

    return MatchupEffect(multiplier=mult, reasons=reasons)
