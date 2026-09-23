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

from .models import Injury, Prop, RUSH_YDS, REC_YDS, RECEPTIONS

# Statuses that make a player's own projection unreliable.
CONCERN_STATUSES = {"QUESTIONABLE", "DOUBTFUL", "GTD"}
RULED_OUT = {"OUT", "IR", "DOUBTFUL"}


@dataclass
class InjuryEffect:
    multiplier: float
    reasons: list[str] = field(default_factory=list)
    player_concern: str = ""     # non-empty if the prop's player is dinged
    #: His team's starting quarterback is out or benched (engine/qbchange):
    #: the card under the pick. None when his quarterback is playing.
    qb_card: dict | None = None


def player_injury_status(prop: Prop, injuries: list[Injury]) -> str:
    for inj in injuries:
        if inj.player == prop.player and inj.status in CONCERN_STATUSES | RULED_OUT:
            return inj.status
    return ""


@dataclass(frozen=True)
class KnockOn:
    """One knock-on rule: a ruled-out player in ``roles`` on ``side`` ("opp"
    = the prop's opponent, "own" = his own team) moves a prop on
    ``positions`` × ``markets`` by ``mult``. ``usage`` narrows it to those
    usage roles (empty = any). ``measured`` says whether engine/injuryfit.py
    has the number or it is still the hand-set one."""
    key: str
    side: str
    roles: frozenset
    positions: frozenset
    markets: frozenset
    mult: float
    why: str
    usage: frozenset = frozenset()
    measured: bool = True


#: THE KNOCK-ON RULES, measured 2026-09-23 (`python3 injuryfit.py`, 2022-2024
#: regular seasons: the injury reports and depth charts this build reads,
#: each player's game against his own average before it, flagged games
#: against the rest). They were all hand-set until then, and the scan
#: that asked "is every input doing what it says" found most of them
#: bigger than the games show:
#:
#:   rule                          hand-set   measured (± SE, flagged games)
#:   starting CB out → WR yards      ×1.09     ×1.03 ± .03  (702)
#:   starting CB out → WR catches    ×1.09     ×1.06 ± .03  (690)
#:   starting CB out → TE yds+catches ×1.09    ×1.03 ± .03  (666)
#:   interior DL out → RB rushing    ×1.06     ×1.02 ± .05  (281)
#:   own tackle out  → QB passing    ×0.95     ×1.00 ± .03  (154)  — dropped
#:   own tackle out  → WR yards      ×0.95     ×0.96 ± .04  (507)
#:
#: A rule fires ONCE however many of the roles are out: the measurement is
#: "any starting corner out", and multiplying per corner compounded a
#: number that was already too big. The slot-corner rule is the one left
#: hand-set: it could never fire before 2026-09-23 (every receiver was
#: "wr1"), and three seasons hold 33 of its games — ×1.25 ± .12, too few
#: to set a number from, and on the side of the rule.
KNOCK_ONS = (
    KnockOn("cb_out_wr_yds", "opp", frozenset({"elite_cb", "cb1"}), frozenset({"WR"}),
            frozenset({REC_YDS}), 1.03, "Opponent CB {who} out — coverage downgrade"),
    KnockOn("cb_out_wr_rec", "opp", frozenset({"elite_cb", "cb1"}), frozenset({"WR"}),
            frozenset({RECEPTIONS}), 1.06, "Opponent CB {who} out — coverage downgrade"),
    KnockOn("cb_out_te", "opp", frozenset({"elite_cb", "cb1"}), frozenset({"TE"}),
            frozenset({REC_YDS, RECEPTIONS}), 1.03, "Opponent CB {who} out — coverage downgrade"),
    KnockOn("slot_out_wr2", "opp", frozenset({"slot_cb"}), frozenset({"WR"}),
            frozenset({REC_YDS, RECEPTIONS}), 1.08, "Opposing slot CB {who} out — slot matchup opens up",
            usage=frozenset({"slot", "wr2"}), measured=False),
    KnockOn("dl_out_rb", "opp", frozenset({"dt", "nt"}), frozenset({"RB"}),
            frozenset({RUSH_YDS}), 1.02, "Opponent DT {who} out — interior run lanes improve"),
    KnockOn("ol_out_wr", "own", frozenset({"LT", "OT"}), frozenset({"WR"}),
            frozenset({REC_YDS}), 0.96, "Own OL injury ({who}) raises pressure — passing risk"),
)


def evaluate_injuries(prop: Prop, injuries: list[Injury]) -> InjuryEffect:
    mult = 1.0
    reasons: list[str] = []

    concern = player_injury_status(prop, injuries)
    out = [i for i in injuries if i.status in RULED_OUT]
    for rule in KNOCK_ONS:
        if prop.market not in rule.markets or prop.position not in rule.positions:
            continue
        if rule.usage and prop.usage_role not in rule.usage:
            continue
        side = prop.opponent if rule.side == "opp" else prop.team
        who = [i.player for i in out if i.team == side and i.role in rule.roles]
        if who:
            mult *= rule.mult
            reasons.append(rule.why.format(who=" and ".join(who)))

    return InjuryEffect(multiplier=mult, reasons=reasons, player_concern=concern)
