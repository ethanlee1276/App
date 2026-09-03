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


# Game-script tilt from the spread, per point rather than a cliff. The
# first version was a step function — nothing until 4 points, then a 5-6%
# jump — which priced a 5.5-point favorite exactly like a pick'em and a
# 6-point underdog exactly like a 14-point one. A 7-point underdog now
# projects to trail and throw (+2.8% pass volume) and to shelve the run
# (-4.2%); a touchdown favorite leans the other way. Rush moves more per
# point than pass — trailing teams abandon the run faster than leading
# teams abandon the pass. Bounded tight because the spread's information
# mostly already lives in the defensive and context numbers; this is the
# volume residue, not a second matchup model.
#: Game script from the spread, per point.
#:
#: The PASS side survives measurement: receptions climb from 0.979 for a
#: big favourite to 1.027 for a big underdog, mostly one direction, +5%
#: end to end — which is what SCRIPT_CLAMP already permits. It is the
#: one hand-set constant in this file that the data supports as it
#: stands.
#:
#: The RUSH side does not, and is no longer applied. See the note in
#: `evaluate_matchup`.
SCRIPT_COEF_PASS = 0.004
SCRIPT_COEF_RUSH = 0.006
SCRIPT_CLAMP = (0.95, 1.05)

#: The league's mean game total over the five ingested seasons — the
#: point at which the pace term does nothing.
TOTAL_BASELINE = 44.6

#: Per point of total, per market. Only rush_yds is applied: it is the
#: one market whose buckets fall at EVERY step rather than only at the
#: ends. See the long note in `evaluate_matchup` for why pass_yds is
#: measured here and deliberately left at zero.
TOTAL_COEF = {RUSH_YDS: -0.0098}

#: Bounded like the script term. At the measured slope this binds only
#: past a total of about 50, which is where the sample thins anyway.
TOTAL_CLAMP = (0.95, 1.05)


@dataclass
class MatchupEffect:
    multiplier: float
    reasons: list[str] = field(default_factory=list)


#: How much of a defence's own yards-allowed rating actually reaches an
#: individual player.
#:
#: `DefenseProfile` stores "yards allowed versus league average", and
#: this module used to apply it whole: a defence giving up 20% more
#: rushing multiplied the projection by 1.20. But a defence is not a
#: dial on one player. Part of its rating is the schedule it has faced,
#: part is game script, part is noise on a handful of games — and only
#: the remainder is a real effect on the back lining up against it.
#:
#: Measured by regressing a player's production against his own prior
#: form on that defence's walk-forward rating, five seasons:
#:
#:     rush_yds    n= 9,387   slope 0.48
#:     receptions  n=13,196   slope 0.30
#:     rec_yds     n=16,803   slope 0.24
#:     pass_yds    n= 2,035   slope -0.06
#:
#: The slope IS the coefficient that minimises squared error, so
#: applying the raw rating is using 1.0 where the data says 0.24 to
#: 0.48. A defence rated 20% generous moves a runner 10%, a receiver 5%.
#:
#: pass_yds gets nothing. Its slope is negative and smaller than its own
#: standard error, so the honest reading is that a defence's passing
#: rating does not predict an individual quarterback's yardage — his own
#: team's pass rate and the game script drive it, and a good defence
#: forcing an opponent to throw cuts the other way.
DEFENSE_TRANSFER = {
    RUSH_YDS: 0.48,
    RECEPTIONS: 0.30,
    REC_YDS: 0.24,
    PASS_YDS: 0.0,
}

#: For a market with no measurement of its own — the middle of the three
#: that have one, rather than the most generous.
DEFENSE_TRANSFER_DEFAULT = 0.30


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
    # Shrunk to the share that actually transfers before the clamp sees
    # it — see DEFENSE_TRANSFER. The clamp stays where it was and now
    # almost never binds, which is the point: it was catching an
    # over-applied factor rather than bounding a reasonable one.
    transfer = DEFENSE_TRANSFER.get(prop.market, DEFENSE_TRANSFER_DEFAULT)
    factor = 1.0 + transfer * (factor - 1.0)
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
        # MEASURED AND NOT APPLIED. The idea is sound football — a
        # favourite leads late and runs the clock — but five seasons do
        # not show it. Production against the player's own prior form,
        # bucketed by his team's spread, reads 1.103, 1.219, 1.184,
        # 1.104, 1.167, 1.340 from big favourite to big underdog: the
        # ends differ by 21% and nothing in between agrees, and the ends
        # are the thinnest buckets. An end-to-end number on a series that
        # doubles back is not an effect size, and this one pointed the
        # opposite way to the rule anyway — the big UNDERDOGS ran for
        # most.
        #
        # SCRIPT_COEF_RUSH is kept so the measurement has something to
        # name, and so re-enabling it is a one-line change if a season
        # with cleaner data disagrees.
        script = 1.0
    elif prop.market in {PASS_YDS, REC_YDS, RECEPTIONS}:
        script = clamp(1.0 + SCRIPT_COEF_PASS * team_spread, *SCRIPT_CLAMP)
    else:
        script = 1.0
    mult *= script
    if abs(script - 1.0) >= 0.02:
        role = "underdog" if team_spread > 0 else "favorite"
        vol = "run volume" if prop.market == RUSH_YDS else "pass volume"
        reasons.append(
            f"Game script: {abs(team_spread):.1f}-pt {role} — projected "
            f"{'trailing' if team_spread > 0 else 'leading'} script leans "
            f"{vol} {'up' if script > 1.0 else 'down'} (×{script:.2f})")

    # THE GAME TOTAL, AND IT DOES NOT MEAN WHAT THIS ASSUMED.
    #
    # The rule here was "high total => more plays, more production for
    # everyone": +3% at 48 and above, -3% at 39 and below, every market.
    # Regressed against five seasons of production versus a player's own
    # prior form, no market has a positive relationship with the total:
    #
    #     rush_yds    -0.0098 per point   t=-1.8    buckets fall every step
    #     pass_yds    -0.0224 per point   t=-2.5    n=2,035
    #     rec_yds     -0.0052 per point   t=-1.5    buckets wander
    #     receptions  +0.0015 per point   t=+1.0    buckets wander
    #
    # A high total is not primarily more plays. It is two offences
    # expected to score efficiently, and often a wide spread with a
    # leader shortening the game. The old bump had the sign backwards
    # for rushing and applied a boost to three markets that show none.
    #
    # Applied only where the bucket series is MONOTONE, which is rush_yds
    # alone. pass_yds carries the larger t but its buckets wander, its
    # sample is a fifth the size, and four markets were tested — a t of
    # 2.5 is not a finding at that width, and a counter-intuitive sign is
    # exactly where a marginal number should be trusted least.
    coef = TOTAL_COEF.get(prop.market, 0.0)
    # MEASURED, NOT TRUTHY. `Game.total` defaults to 44.0 and
    # TOTAL_BASELINE is 44.6, so an unposted game did not fall through
    # neutral — it applied a silent x1.006 to every rushing projection,
    # under the 2% bar that would have printed a reason admitting it.
    if coef and getattr(game, "total_is_posted", False):
        pace = clamp(1.0 + coef * (game.total - TOTAL_BASELINE), *TOTAL_CLAMP)
        mult *= pace
        if abs(pace - 1.0) >= 0.02:
            reasons.append(
                f"Game total {game.total:.0f} — measured, a higher total "
                f"means FEWER rushing yards, not more (×{pace:.2f})")

    return MatchupEffect(multiplier=mult, reasons=reasons)
