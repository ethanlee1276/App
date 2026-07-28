"""NFL anytime-touchdown model.

A touchdown is an *opportunity* event, so the model is built from how often a
player is in position to score rather than from how often he recently did:

    expected TDs = baseline TD rate
                 × (team's implied total ÷ league average)   ← game script
                 × opportunity share vs the player's own norm
                 × matchup (defence's TDs allowed to the position)
                 × weather (only where it plausibly suppresses scoring)
                 × injury/role adjustments

then ``P(scores) = 1 − e^(−expected TDs)``.

**What this model cannot see.** True red-zone usage — goal-line carries,
carries inside the 5, end-zone targets — lives in play-by-play data this project
doesn't ingest. Those are the single best predictors of touchdowns, and without
them the engine leans on *opportunity share* and *team implied total* as
proxies. Every pick says so. Wiring in play-by-play would be the highest-value
upgrade to this model, and the interface here (``RedZoneUsage``) is shaped to
accept it without changing the callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Game, Prop, Team, ANYTIME_TD, MARKET_LABELS
from .longshots import (
    LongShot, NFL_TD_ODDS, NFL_AVG_TEAM_POINTS, NFL_AVG_TEAM_OFF_TDS,
    prob_at_least_one, in_odds_window, build_pick, select,
)
from .statmath import clamp

# Share of a team's offensive touchdowns a position group typically takes, used
# only as a fallback when a player has no touchdown history of his own.
POSITION_TD_SHARE = {
    "RB": 0.34, "WR": 0.22, "TE": 0.14, "QB": 0.10,
}

# Opportunity share a *typical starter* at each position commands. The baseline
# above describes that player, so a role is scaled against this rather than
# given a flat floor — otherwise a WR3 at an 8% target share inherits most of a
# WR1's touchdown equity, which is exactly the "lottery ticket" the strategy
# says to avoid.
POSITION_TYPICAL_SHARE = {
    "RB": 0.45, "WR": 0.22, "TE": 0.16, "QB": 0.10,
}


@dataclass
class RedZoneUsage:
    """Red-zone opportunity for a player.

    ``measured`` is False when these numbers are inferred from overall usage
    rather than read from play-by-play — the model still uses them, but the
    pick is flagged so nobody mistakes a proxy for a measurement.
    """
    carries_inside_5: float = 0.0
    carries_inside_10: float = 0.0
    targets_inside_10: float = 0.0
    rz_touch_share: float = 0.0      # 0..1 share of team red-zone touches
    measured: bool = False

    @property
    def opportunities(self) -> float:
        """Expected red-zone chances per game."""
        return self.carries_inside_10 + self.targets_inside_10


def team_implied_total(game: Game, team: str) -> float:
    """Points a team is expected to score, from the spread and total.

    ``Game.spread`` is the home spread and negative when home is favoured, so
    the favourite's implied total is half the total plus half the spread margin.
    """
    half = game.total / 2.0
    if team == game.home:
        return half - game.spread / 2.0
    return half + game.spread / 2.0


def expected_team_tds(implied_total: float) -> float:
    """Offensive touchdowns a team scoring ``implied_total`` points is worth."""
    return max(0.0, implied_total) * (NFL_AVG_TEAM_OFF_TDS / NFL_AVG_TEAM_POINTS)


def infer_red_zone(prop: Prop, opportunity_share: float) -> RedZoneUsage:
    """Approximate red-zone usage from overall workload.

    A genuine proxy, not a measurement: a player's share of red-zone work
    correlates with his share of overall work, but goal-line roles are often
    concentrated in a specific back, which this cannot see.
    """
    pos = (prop.position or "").upper()
    share = clamp(opportunity_share, 0.0, 1.0)
    if pos == "RB":
        return RedZoneUsage(carries_inside_5=share * 1.1, carries_inside_10=share * 2.0,
                            targets_inside_10=share * 0.4, rz_touch_share=share,
                            measured=False)
    if pos in ("WR", "TE"):
        return RedZoneUsage(carries_inside_10=share * 0.1,
                            targets_inside_10=share * 1.6, rz_touch_share=share,
                            measured=False)
    return RedZoneUsage(carries_inside_10=share * 0.8, rz_touch_share=share, measured=False)


def historical_td_rate(prop: Prop) -> tuple[float, int]:
    """Touchdowns per game from the player's logs, and the sample size.

    Game logs carry the market's stat (yards/receptions), so a dedicated
    ``anytime_td`` log is used when present; otherwise the position baseline
    fills in and the caller discounts confidence for the weak sample.
    """
    if prop.market == ANYTIME_TD and prop.logs:
        vals = [g.value for g in prop.logs]
        return (sum(vals) / len(vals)), len(vals)
    return 0.0, 0


def weather_td_multiplier(game: Game, position: str) -> tuple[float, list[str]]:
    """Weather only suppresses scoring when it's genuinely severe."""
    w = game.weather
    reasons: list[str] = []
    if w is None or w.dome:
        return 1.0, ["Indoors — weather is not a factor"]
    mult = 1.0
    if w.wind_mph >= 20 and position in ("WR", "TE", "QB"):
        mult *= 0.93
        reasons.append(f"Wind {w.wind_mph:.0f} mph — passing touchdowns suppressed")
    if w.snow:
        mult *= 0.94
        reasons.append("Snow — scoring environment degraded, run-leaning script")
    elif w.rain:
        mult *= 0.97
        reasons.append("Rain — modest drag on the passing game")
    if w.temp_f <= 20:
        mult *= 0.96
        reasons.append(f"{w.temp_f:.0f}°F — cold suppresses scoring")
    return mult, reasons


def defense_td_multiplier(opponent: Team, position: str) -> tuple[float, list[str]]:
    """How generous the defence is to this position, from its profile."""
    d = opponent.defense
    reasons: list[str] = []
    if position == "RB":
        val = d.vs_rb_rush
        label = "run defence"
    elif position == "TE":
        val = d.vs_te
        label = "coverage vs tight ends"
    elif position == "QB":
        val = d.vs_qb
        label = "defence vs quarterbacks"
    else:
        val = d.vs_wr1
        label = "coverage vs top receivers"
    mult = clamp(val, 0.80, 1.25)
    if mult >= 1.06:
        reasons.append(f"Soft {label} — {(mult - 1) * 100:+.0f}% vs average")
    elif mult <= 0.94:
        reasons.append(f"Tough {label} — {(mult - 1) * 100:+.0f}% vs average")
    return mult, reasons


def td_probability(prop: Prop, game: Game, opponent: Team,
                   opportunity_share: float,
                   red_zone: Optional[RedZoneUsage] = None) -> tuple[float, dict]:
    """Model P(player scores a touchdown), plus the reasoning behind it."""
    pos = (prop.position or "").upper()
    team = prop.team
    implied = team_implied_total(game, team)
    team_tds = expected_team_tds(implied)

    rz = red_zone or infer_red_zone(prop, opportunity_share)

    # Player's share of his team's touchdowns. History and the role baseline are
    # *blended* by sample size rather than chosen between: a player with six
    # scoreless games is evidence of a low rate, not missing data, so falling
    # back to the position baseline there would badly overrate a backup.
    hist_rate, samples = historical_td_rate(prop)
    baseline = POSITION_TD_SHARE.get(pos, 0.15)
    typical = POSITION_TYPICAL_SHARE.get(pos, 0.20)
    role_share = clamp(baseline * clamp(opportunity_share / typical, 0.15, 2.2),
                       0.01, 0.60)
    if samples:
        w = clamp(samples / 10.0, 0.0, 0.7)
        hist_share = clamp(hist_rate / max(NFL_AVG_TEAM_OFF_TDS, 0.1), 0.0, 0.60)
        base_share = clamp(w * hist_share + (1 - w) * role_share, 0.01, 0.55)
        share_src = (f"{hist_rate:.2f} TD/game over {samples} games, "
                     f"blended with the {pos or 'role'} baseline")
    else:
        base_share = role_share
        share_src = f"{pos or 'role'} baseline scaled by {opportunity_share:.0%} opportunity share"

    # Red-zone work converts opportunity into touchdowns — but the share above
    # already reflects the player's role, so this is a gentle nudge, not a
    # second full helping of the same signal.
    rz_mult = clamp(0.90 + 0.4 * (rz.rz_touch_share - 0.25), 0.85, 1.15) \
        if rz.rz_touch_share else 1.0

    def_mult, def_reasons = defense_td_multiplier(opponent, pos)
    wx_mult, wx_reasons = weather_td_multiplier(game, pos)

    # Ceiling reflects reality: even a bell-cow goal-line back on a big favourite
    # tops out near a 2-in-3 chance to find the end zone.
    rate = team_tds * base_share * rz_mult * def_mult * wx_mult
    rate = clamp(rate, 0.005, 1.15)
    prob = prob_at_least_one(rate)

    favored = (game.spread < 0 and team == game.home) or (game.spread > 0 and team == game.away)
    reasons = [
        f"Team implied total {implied:.1f} → {team_tds:.2f} expected offensive TDs",
        f"Share of team TDs from {share_src}",
    ]
    if rz.rz_touch_share:
        reasons.append(f"Red-zone touch share ~{rz.rz_touch_share:.0%} "
                       f"({rz.opportunities:.1f} expected chances)")
    reasons += def_reasons + wx_reasons
    if favored:
        reasons.append("Favoured — positive game script for goal-line volume")

    caveats = []
    if not rz.measured:
        caveats.append("Red-zone usage inferred from overall opportunity share "
                       "(play-by-play not ingested) — the biggest source of error here")
    if samples < 4:
        caveats.append(f"Thin touchdown history ({samples} games) — position baseline used")

    return prob, {
        "reasons": reasons, "caveats": caveats,
        "opportunities": rz.opportunities,
        "primary_reason": reasons[0] if not def_reasons else def_reasons[0],
        "data_quality": 0.85 if not rz.measured else 1.0,
        "implied_total": implied,
    }


def build_td_longshots(candidates: list[dict], limit: int = 6,
                       per_game: int = 2) -> list[LongShot]:
    """Rank anytime-touchdown picks.

    ``candidates`` = ``[{prop, game, opponent, opportunity_share, odds, book,
    under_odds?, red_zone?}]``. Applies the strategy's odds window and the
    1–2-per-game concentration cap.
    """
    picks: list[LongShot] = []
    for c in candidates:
        odds = int(c["odds"])
        if not in_odds_window(odds, NFL_TD_ODDS):
            continue
        prop, game, opp = c["prop"], c["game"], c["opponent"]
        prob, info = td_probability(prop, game, opp,
                                    c.get("opportunity_share", 0.15),
                                    c.get("red_zone"))
        pick = build_pick(
            player=prop.player, team=prop.team, opponent=prop.opponent,
            market=ANYTIME_TD, label=MARKET_LABELS[ANYTIME_TD],
            book=c.get("book", ""), odds=odds, model_prob=prob,
            under_odds=c.get("under_odds"),
            opportunities=info["opportunities"], opp_target=2.0,
            primary_reason=info["primary_reason"], reasons=info["reasons"],
            caveats=info["caveats"], sport="nfl", data_quality=info["data_quality"],
        )
        if pick:
            pick.game_date = getattr(game, "date", "")
            pick.game_kickoff = getattr(game, "kickoff", "")
            pick.live = bool(getattr(game, "live", None) and game.live.state == "live")
            snap = c.get("snap_share")
            if snap is not None:
                pick.reasons.append(
                    f"On the field for {snap:.0%} of offensive snaps "
                    f"(measured, recent weeks)")
            picks.append(pick)

    return select(picks, per_key_cap=per_game,
                  key=lambda p: tuple(sorted((p.team, p.opponent))), limit=limit)
