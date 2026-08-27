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

**Red-zone usage, and the note that used to sit here.** This docstring
said for a long time that true red-zone usage — goal-line carries,
carries inside the 5, end-zone targets — "lives in play-by-play data
this project doesn't ingest", called them the single best predictors of
touchdowns, and named wiring them in as the highest-value upgrade
available. That upgrade landed: the nightly ingest stores ``rz_car``,
``rz_tgt`` and ``i5_car`` from play-by-play, `engine.nflusage
.red_zone_usage` turns them into ``RedZoneUsage(measured=True)`` per
player, and `nfl_build` hands them to this model through
``build_usage_maps``.

The note is kept rather than deleted because a stale "we cannot see X"
is worse than no note at all — it tells a reader to go build something
that already exists, which is a mistake this project has made. A player
with no play-by-play rows still falls back to `infer_red_zone`, and
``measured=False`` is what the card reads to say so.

**What it still cannot see:** defensive personnel and pre-snap
alignment, which is where the remaining goal-line signal lives.

**How well it works.** Measured 2026-08-27 by `engine.tdbacktest` over
four seasons and 17,785 player-weeks, walked forward: Brier 0.1459
against an always-guess 0.1594. Its probabilities were too spread out —
it claimed 4.9% in the bottom band where 9.2% actually scored, and
65.4% at the top where 57.9% did — so the market carries a fitted
temperature now (`fit_calibration`), which brings the worst band from
7.5 points off to 1.4.
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

#: Below this many TD-history games the position baseline does the
#: talking and the card says so. The slate builder's prior-season top-up
#: (engine/sources/nflverse.TD_CARRY_GAMES) keys off the SAME number, so
#: "thin" and "worth carrying for" cannot drift apart.
TD_THIN_GAMES = 4

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


def script_td_multiplier(game: Game, team: str,
                         position: str) -> tuple[float, list[str]]:
    """Game script as arithmetic, not adjective.

    The model always SAID "Favoured — positive game script" on favourites'
    cards, but the sentence carried no number — the reason list mentioned
    a factor the rate never contained (Ethan, 2026-08-25: "we should be
    using the game script... to determine who will score a touchdown").

    The mechanism, per position:

      * RBs ride the script hardest. A team expected to lead runs at the
        goal line and runs out the clock — about +1% TD equity per point
        of spread, capped near a two-score game because a 20-point
        favourite doesn't run twice as hot as a 10-point one.
      * Pass catchers move gently the OTHER way. Trailing teams throw
        more, but between the 20s and against soft shells — volume up,
        red-zone quality down — so the drag on a heavy favourite's WRs
        is real and small.
      * QBs sit out: rushing QB touchdowns follow designed red-zone
        packages, which the role share already carries.

    The implied-total factor upstream already prices HOW MUCH a team
    scores; this prices HOW — which is why the caps are tight. Doubling
    up on the total would count the same points twice.
    """
    lead = -game.spread if team == game.home else game.spread
    pos = (position or "").upper()
    reasons: list[str] = []
    if pos == "RB":
        mult = clamp(1.0 + 0.010 * lead, 0.88, 1.12)
    elif pos in ("WR", "TE"):
        mult = clamp(1.0 - 0.004 * lead, 0.95, 1.05)
    else:
        return 1.0, reasons
    if abs(lead) >= 3.0 and abs(mult - 1.0) >= 0.02:
        side = "favoured" if lead > 0 else "underdog"
        reasons.append(
            f"Game script: {side} by {abs(lead):.0f} — "
            f"{(mult - 1) * 100:+.0f}% TD equity for a {pos}")
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
    script_mult, script_reasons = script_td_multiplier(game, team, pos)

    # Ceiling reflects reality: even a bell-cow goal-line back on a big favourite
    # tops out near a 2-in-3 chance to find the end zone.
    rate = team_tds * base_share * rz_mult * def_mult * wx_mult * script_mult
    rate = clamp(rate, 0.005, 1.15)
    prob = prob_at_least_one(rate)

    reasons = [
        f"Team implied total {implied:.1f} → {team_tds:.2f} expected offensive TDs",
        f"Share of team TDs from {share_src}",
    ]
    if rz.rz_touch_share:
        reasons.append(f"Red-zone touch share ~{rz.rz_touch_share:.0%} "
                       f"({rz.opportunities:.1f} expected chances)")
    # Script replaces the old adjective ("Favoured — positive game
    # script"): that sentence appeared on every favourite's card while
    # the rate contained no such factor — a reason describing math that
    # was not being done.
    reasons += def_reasons + wx_reasons + script_reasons

    caveats = []
    if not rz.measured:
        caveats.append("Red-zone usage inferred from overall opportunity share "
                       "(play-by-play not ingested) — the biggest source of error here")
    if samples < TD_THIN_GAMES:
        caveats.append(f"Thin touchdown history ({samples} games) — position baseline used")

    return prob, {
        "reasons": reasons, "caveats": caveats,
        "opportunities": rz.opportunities,
        "primary_reason": reasons[0] if not def_reasons else def_reasons[0],
        "data_quality": 0.85 if not rz.measured else 1.0,
        "implied_total": implied,
    }


#: The watchlist's own price sanity: shorter than -400 the book is
#: calling it near-certain and there is nothing left to say about it;
#: past +1500 the quote is stale or mis-lined (nobody is 15/1 to score
#: whom a book bothered to price). Deliberately WIDER than NFL_TD_ODDS
#: on the juiced side — that is the whole point of the list.
TD_WATCH_ODDS = (-400, 1500)

#: How many most-likely scorers ride below the value picks.
TD_WATCH_LIMIT = 5


def td_watchlist(candidates: list[dict], limit: int = TD_WATCH_LIMIT
                 ) -> list[dict]:
    """The week's most likely scorers, ranked by model probability —
    REGARDLESS of the value window.

    Ethan, 2026-08-26: "there is players more guaranteed to get
    touchdowns with lines at -200 and shit but if those players are
    gonna get a touchdown in that specific game no matter what their
    line is, we should be showing it" — his example a bell-cow back at
    -260 whose game script screams goal-line volume. He is right, and
    the fix is NOT loosening the value bar: a -260 the model has at 74%
    is a fair price, not an edge, and journaling it as a pick would be
    betting juice for the thrill. It is the same split the MLB board
    already carries (hr_watchlist): the VALUE list answers "what is
    mispriced", this list answers "who is most likely", and each says
    which it is. Price and EV are shown honestly, so a likely scorer at
    a fair or losing price reads as exactly that — insight, never a
    journaled bet.
    """
    from .odds import american_to_decimal
    from .longshots import calibrated_prob
    rows: list[dict] = []
    for c in candidates:
        odds = c.get("odds")
        try:
            odds = int(odds)
        except (TypeError, ValueError):
            continue
        if not odds or not in_odds_window(odds, TD_WATCH_ODDS):
            continue
        if (c.get("book") or "").lower() == "proxy":
            continue
        prop, game, opp = c["prop"], c["game"], c["opponent"]
        raw_prob, info = td_probability(prop, game, opp,
                                        c.get("opportunity_share", 0.15),
                                        c.get("red_zone"))
        # The SAME tempering + market shrink the value picks get — the
        # MLB watchlist once used raw probabilities and inflated EV past
        # the broken-price guard, silently emptying itself.
        prob, implied = calibrated_prob("nfl", ANYTIME_TD, raw_prob, odds,
                                        c.get("under_odds"))
        if prob * american_to_decimal(odds) - 1.0 > 0.60:
            continue                   # a broken price, not an edge
        rows.append({
            "player": prop.player, "team": prop.team,
            "opponent": prop.opponent, "book": c.get("book", ""),
            "odds": odds,
            "model_prob": round(prob, 4),
            "implied_prob": round(implied, 4),
            "ev_per_unit": round(prob * american_to_decimal(odds) - 1.0, 4),
            "primary_reason": info["primary_reason"],
            # TDs per game, most recent first — the spark at line 0.5.
            "recent_values": [g.value for g in prop.logs][:12],
            "caveats": info["caveats"][:1],
            "game_date": getattr(game, "date", ""),
            "kickoff": getattr(game, "kickoff", ""),
            "headshot": getattr(prop, "headshot", "") or "",
        })
    rows.sort(key=lambda r: -r["model_prob"])
    return rows[:limit] if limit else rows


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
            # The same photo the prop board shows for this player. Read off
            # the prop with getattr rather than attribute access: a Prop
            # built by an older path (or a test fixture) has no headshot,
            # and a long-shot board is not worth crashing over a picture.
            headshot=getattr(prop, "headshot", "") or "",
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
