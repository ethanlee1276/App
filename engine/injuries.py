"""Injury engine.

Two jobs:
  1. Flag whether the *prop's own player* has an injury concern (used by the
     rules engine to suppress recommendations we can't trust).
  2. Compute knock-on multipliers: an opposing elite CB ruled OUT lifts a WR's
     projection; a team's LT OUT raises the pressure on its QB and shaves
     passing production, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Injury, Prop, PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS

# Statuses that make a player's own projection unreliable.
CONCERN_STATUSES = {"QUESTIONABLE", "DOUBTFUL", "GTD"}
RULED_OUT = {"OUT", "IR", "DOUBTFUL"}


@dataclass
class InjuryEffect:
    multiplier: float
    reasons: list[str] = field(default_factory=list)
    player_concern: str = ""     # non-empty if the prop's player is dinged


def player_injury_status(prop: Prop, injuries: list[Injury]) -> str:
    for inj in injuries:
        if inj.player == prop.player and inj.status in CONCERN_STATUSES | RULED_OUT:
            return inj.status
    return ""


def evaluate_injuries(prop: Prop, injuries: list[Injury]) -> InjuryEffect:
    mult = 1.0
    reasons: list[str] = []

    concern = player_injury_status(prop, injuries)

    for inj in injuries:
        if inj.status not in RULED_OUT:
            continue
        opposing = inj.team == prop.opponent
        same = inj.team == prop.team

        # Opponent's elite/slot corner out -> receiver projections up.
        if opposing and inj.role in {"elite_cb", "cb1"} and prop.market in {REC_YDS, RECEPTIONS}:
            mult *= 1.09
            reasons.append(f"Opponent CB {inj.player} ({inj.status}) — coverage downgrade")
        if opposing and inj.role == "slot_cb" and prop.usage_role in {"slot", "wr2"}:
            mult *= 1.08
            reasons.append(f"Opposing slot CB {inj.player} out — slot matchup opens up")

        # Opponent interior D-line out -> more room to run.
        if opposing and inj.role in {"dt", "nt"} and prop.market == RUSH_YDS:
            mult *= 1.06
            reasons.append(f"Opponent DT {inj.player} out — interior run lanes improve")

        # Prop team's own LT out -> more pressure on the QB, passing down.
        if same and inj.role in {"LT", "OT"} and prop.market in {PASS_YDS, REC_YDS}:
            mult *= 0.95
            reasons.append(f"Own OL injury ({inj.player}) raises pressure — passing risk")

    return InjuryEffect(multiplier=mult, reasons=reasons, player_concern=concern)
