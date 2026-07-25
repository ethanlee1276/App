"""MLB matchup analyzer.

Hitters: platoon advantage vs the opposing starter's handedness, that
starter's quality against the batter's side (SLG allowed), the opposing
bullpen's strength (bad bullpens surrender production in innings 6-9), and
batting-order slot (plate-appearance volume).

Pitchers (strikeout props): the opposing lineup's strikeout rate and the
pitcher's own K%.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    MLBGame, MLBProp, Pitcher,
    HITTER_MARKETS, STRIKEOUTS,
)
from ..statmath import clamp

LEAGUE_SLG = 0.400
LEAGUE_K_RATE = 0.22

# Batting-order slot → plate-appearance volume multiplier (top of the order
# bats ~15% more often than the bottom over a season).
LINEUP_SPOT_PA = {1: 1.05, 2: 1.04, 3: 1.02, 4: 1.01, 5: 1.00,
                  6: 0.99, 7: 0.97, 8: 0.96, 9: 0.95}


@dataclass
class MatchupEffect:
    multiplier: float
    reasons: list[str] = field(default_factory=list)


def _hitter_matchup(prop: MLBProp, game: MLBGame) -> MatchupEffect:
    mult = 1.0
    reasons: list[str] = []

    starter: Pitcher | None = game.pitchers.get(prop.opponent)
    if starter:
        if prop.platoon_factor != 1.0:
            # The player's OWN measured split vs this hand beats the generic
            # rule-of-thumb bump — never stack the two.
            mult *= prop.platoon_factor
            if prop.platoon_note:
                reasons.append(prop.platoon_note)
        else:
            # Platoon: L vs R (or R vs L) is the classic advantage; switch
            # hitters always have it.
            adv = (prop.bats == "S") or (prop.bats != starter.throws)
            if adv:
                mult *= 1.04
                reasons.append(f"Platoon edge — {prop.bats}HB vs {starter.throws}HP "
                               f"({starter.name})")

        # Starter's quality against this batter's side. Tempered (×0.35)
        # because books price obvious splits in — edges come from the sum of
        # small angles, not one huge multiplier.
        side_slg = (starter.slg_allowed_vs_l if prop.bats in ("L", "S")
                    else starter.slg_allowed_vs_r)
        factor = clamp(side_slg / LEAGUE_SLG, 0.80, 1.30)
        mult *= 1.0 + (factor - 1.0) * 0.35
        if factor >= 1.12:
            reasons.append(f"{starter.name} allows .{side_slg * 1000:.0f} SLG to "
                           f"{'lefties' if prop.bats in ('L', 'S') else 'righties'}")
        elif factor <= 0.90:
            reasons.append(f"Tough draw — {starter.name} holds "
                           f"{'lefties' if prop.bats in ('L', 'S') else 'righties'} "
                           f"to .{side_slg * 1000:.0f} SLG")

    # Opposing bullpen: bad pens give production back late.
    pen = game.bullpen_rank.get(prop.opponent)
    if pen:
        if pen >= 24:
            mult *= 1.03
            reasons.append(f"Opposing bullpen ranks {pen}th — late-inning upside")
        elif pen <= 6:
            mult *= 0.98
            reasons.append(f"Opposing bullpen ranks {pen}{_ord(pen)} — strong late relief")

    # Lineup slot → PA volume.
    if prop.lineup_spot:
        pa = LINEUP_SPOT_PA.get(prop.lineup_spot, 1.0)
        mult *= pa
        if prop.lineup_spot <= 2:
            reasons.append(f"Batting {prop.lineup_spot}{_ord(prop.lineup_spot)} — "
                           f"extra plate appearances")

    return MatchupEffect(clamp(mult, 0.88, 1.15), reasons)


def _pitcher_matchup(prop: MLBProp, game: MLBGame) -> MatchupEffect:
    mult = 1.0
    reasons: list[str] = []

    opp_k = game.team_k_rate.get(prop.opponent, LEAGUE_K_RATE)
    factor = clamp(opp_k / LEAGUE_K_RATE, 0.80, 1.25)
    mult *= 1.0 + (factor - 1.0) * 0.5
    if factor >= 1.08:
        reasons.append(f"{prop.opponent} strikes out {opp_k:.0%} of the time "
                       f"({(factor - 1) * 100:+.0f}% vs league)")
    elif factor <= 0.92:
        reasons.append(f"{prop.opponent} rarely strikes out ({opp_k:.0%}) — K upside capped")

    me = game.pitchers.get(prop.team)
    if me and me.k_rate >= 0.27:
        mult *= 1.03
        reasons.append(f"Elite swing-and-miss stuff ({me.k_rate:.0%} K rate)")

    return MatchupEffect(clamp(mult, 0.88, 1.12), reasons)


def evaluate_matchup(prop: MLBProp, game: MLBGame) -> MatchupEffect:
    if prop.market in HITTER_MARKETS:
        return _hitter_matchup(prop, game)
    if prop.market == STRIKEOUTS:
        return _pitcher_matchup(prop, game)
    return MatchupEffect(1.0)


def _ord(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
