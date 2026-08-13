"""MLB home-run model.

Home runs are a rare event driven by contact quality meeting an environment, so
the model is a Poisson rate built from the things that actually produce them,
never from a hitter's recent home-run count:

    expected HR = baseline HR rate per plate appearance
                × plate appearances (from lineup spot)
                × contact quality (barrel / hard-hit / xSLG vs SLG)
                × platoon edge and the pitcher's power suppression
                × park home-run factor
                × weather (wind direction relative to the park, temperature)

then ``P(hits one) = 1 − e^(−expected HR)``.

Weather deserves the emphasis it gets: wind blowing out at 15 mph is worth more
than most hitter-vs-pitcher edges, and it's one of the few factors the market is
sometimes slow to price. Wind direction is resolved *relative to each park's
orientation* (see ``engine.mlb.parks``), so "out to left at Wrigley" means what
it should rather than a raw compass bearing.

Where a Statcast profile is missing the model falls back to season rate alone
and says so on the pick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import MLBProp, MLBGame, HOME_RUNS, MARKET_LABELS
from .parks import get_park
from ..longshots import (
    LongShot, MLB_HR_ODDS, prob_at_least_one, in_odds_window, build_pick, select,
)
from ..statmath import clamp

# Plate appearances by lineup spot — the top of the order simply bats more.
PA_BY_SPOT = {1: 4.6, 2: 4.5, 3: 4.4, 4: 4.3, 5: 4.2,
              6: 4.0, 7: 3.9, 8: 3.8, 9: 3.7}

# Clubs file the official card with MLB roughly this long before first pitch;
# our own confirmation reads that same feed, so this is when the caveat below
# can clear at the earliest.
LINEUP_POSTS_BEFORE_H = 3


def _lineup_eta(game) -> str:
    """"not confirmed yet" invites the obvious question — WHEN will it be?

    Without an answer the warning reads as "we failed to check", when the
    truth is that the lineup does not exist anywhere yet: nobody has it,
    including the book taking the bet. Naming the hour turns a worry into a
    time to come back.
    """
    import datetime as _dt
    k = (getattr(game, "kickoff", "") or "").replace("Z", "+00:00")
    try:
        first = _dt.datetime.fromisoformat(k)
    except ValueError:
        return "not confirmed yet"
    if first.tzinfo is not None:
        first = first.astimezone()
    eta = first - _dt.timedelta(hours=LINEUP_POSTS_BEFORE_H)
    when = eta.strftime("%-I:%M %p").lower().replace("am", "AM").replace("pm", "PM")
    return (f"lineups post around {when}, ~{LINEUP_POSTS_BEFORE_H}h before "
            f"first pitch, and this clears itself then")
DEFAULT_PA = 4.0

LEAGUE_HR_PER_PA = 0.033        # ~3.3% of plate appearances
LEAGUE_BARREL = 0.075
LEAGUE_HARD_HIT = 0.40


def plate_appearances(spot: int) -> float:
    return PA_BY_SPOT.get(spot, DEFAULT_PA)


def contact_multiplier(prop: MLBProp) -> tuple[float, list[str], bool]:
    """Power from quality of contact — barrels are the best single HR predictor."""
    sc = prop.statcast
    if sc is None:
        return 1.0, ["No Statcast profile — season home-run rate only"], False

    mult, reasons = 1.0, []
    if sc.barrel_pct is not None:
        ratio = sc.barrel_pct / LEAGUE_BARREL
        mult *= clamp(ratio ** 0.6, 0.70, 1.45)
        if sc.barrel_pct >= 0.12:
            reasons.append(f"Elite barrel rate {sc.barrel_pct:.1%} "
                           f"({ratio:.2f}× league) — top-tier power profile")
        elif sc.barrel_pct <= 0.05:
            reasons.append(f"Low barrel rate {sc.barrel_pct:.1%} — power profile is thin")
    if sc.hard_hit_pct is not None:
        mult *= clamp((sc.hard_hit_pct / LEAGUE_HARD_HIT) ** 0.4, 0.80, 1.30)
        if sc.hard_hit_pct >= 0.45:
            reasons.append(f"Hard-hit rate {sc.hard_hit_pct:.1%} — above the 45% power threshold")
    if sc.xslg is not None and sc.slg is not None:
        gap = sc.xslg - sc.slg
        if gap >= 0.040:
            mult *= 1.06
            reasons.append(f"xSLG {sc.xslg:.3f} well above SLG {sc.slg:.3f} — "
                           f"underlying power ahead of results")
        elif gap <= -0.040:
            mult *= 0.95
            reasons.append(f"SLG {sc.slg:.3f} ahead of xSLG {sc.xslg:.3f} — "
                           f"results running hot, regression risk")
    return clamp(mult, 0.60, 1.45), reasons, True


def pitcher_multiplier(prop: MLBProp, game: MLBGame) -> tuple[float, list[str]]:
    """The starter's power suppression, including the platoon edge."""
    pitcher = game.pitchers.get(prop.opponent)
    if pitcher is None:
        return 1.0, ["Starting pitcher not yet announced"]

    reasons: list[str] = []
    bats = (prop.bats or "R").upper()
    throws = (pitcher.throws or "R").upper()
    slg_allowed = pitcher.slg_allowed_vs_l if bats == "L" else pitcher.slg_allowed_vs_r
    mult = clamp((slg_allowed / 0.400) ** 0.9, 0.70, 1.45)
    if slg_allowed >= 0.450:
        reasons.append(f"{pitcher.name} allows {slg_allowed:.3f} SLG to {bats}HB — "
                       f"home-run prone in this split")
    elif slg_allowed <= 0.350:
        reasons.append(f"{pitcher.name} suppresses power to {bats}HB "
                       f"({slg_allowed:.3f} SLG allowed)")

    # Platoon advantage — the player's OWN measured power split when the
    # official season numbers carry a real sample; the flat ±6%/5% guess
    # only when they don't. Some hitters genuinely can't touch lefties and
    # some have no split at all — a flat bump treats them identically.
    platoon_applied = False
    off = getattr(prop, "platoon_official", None)
    side = (off or {}).get("vl" if throws == "L" else "vr")
    other = (off or {}).get("vr" if throws == "L" else "vl")
    if side and other:
        pa_s, pa_o = side.get("pa", 0), other.get("pa", 0)
        rate_all = ((side.get("hr", 0) + other.get("hr", 0)) / (pa_s + pa_o)
                    if pa_s + pa_o else 0.0)
        if pa_s >= 40 and pa_s + pa_o >= 150 and rate_all > 0:
            raw = (side.get("hr", 0) / pa_s) / rate_all
            w = pa_s / (pa_s + 130.0)         # shrink thin sides hard
            pm = clamp(1.0 + (raw - 1.0) * w, 0.75, 1.30)
            mult *= pm
            platoon_applied = True
            reasons.append(
                f"Measured power split: {side.get('hr', 0)} HR in {pa_s} PA "
                f"vs {throws}HP ({(pm - 1) * 100:+.0f}% vs his overall rate)")
    if not platoon_applied:
        if bats != throws and bats in ("L", "R"):
            mult *= 1.06
            reasons.append(f"Platoon edge — {bats}HB vs {throws}HP")
        elif bats == throws:
            mult *= 0.95
            reasons.append(f"Same-side matchup — {bats}HB vs {throws}HP")

    # An elite strikeout pitcher removes contact chances entirely.
    if pitcher.k_rate >= 0.28:
        mult *= 0.90
        reasons.append(f"High-strikeout starter ({pitcher.k_rate:.0%} K rate) — fewer balls in play")
    return clamp(mult, 0.60, 1.55), reasons


def park_weather_multiplier(game: MLBGame) -> tuple[float, list[str], list[str]]:
    """Park home-run factor plus wind and temperature."""
    park = get_park(game.park)
    w = game.weather
    reasons: list[str] = []
    caveats: list[str] = []

    mult = clamp(park.hr_factor, 0.75, 1.35)
    if park.hr_factor >= 1.10:
        reasons.append(f"{park.name} plays big for home runs "
                       f"({(park.hr_factor - 1) * 100:+.0f}% HR factor)")
    elif park.hr_factor <= 0.92:
        reasons.append(f"{park.name} suppresses home runs "
                       f"({(park.hr_factor - 1) * 100:+.0f}% HR factor)")
    if park.altitude_ft >= 3000:
        reasons.append(f"Altitude {park.altitude_ft:,} ft — thin air carries the ball")
    if park.key == "generic":
        caveats.append("Ballpark not in the park database — neutral factors used")

    if w is not None and not getattr(w, "roof_closed", False):
        direction = (getattr(w, "wind_dir_rel", "") or "").lower()
        speed = getattr(w, "wind_mph", 0.0) or 0.0
        if direction == "out" and speed >= 8:
            bump = clamp(1.0 + 0.012 * speed, 1.0, 1.22)
            mult *= bump
            reasons.append(f"Wind blowing OUT at {speed:.0f} mph — "
                           f"{(bump - 1) * 100:+.0f}% to home-run probability")
        elif direction == "in" and speed >= 8:
            cut = clamp(1.0 - 0.010 * speed, 0.82, 1.0)
            mult *= cut
            reasons.append(f"Wind blowing IN at {speed:.0f} mph — knocks balls down")
        temp = getattr(w, "temp_f", 70.0)
        if temp >= 85:
            mult *= 1.05
            reasons.append(f"{temp:.0f}°F — warm, thin air helps carry")
        elif temp <= 50:
            mult *= 0.93
            reasons.append(f"{temp:.0f}°F — cold, heavy air kills carry")
    elif w is not None and getattr(w, "roof_closed", False):
        reasons.append("Roof closed — weather-neutral conditions")

    return clamp(mult, 0.65, 1.70), reasons, caveats


def hr_probability(prop: MLBProp, game: MLBGame) -> tuple[float, dict]:
    """Model P(hitter homers), with the reasoning behind it."""
    pa = plate_appearances(prop.lineup_spot or 0)

    # Baseline rate per plate appearance from the player's own history, pulled
    # toward league average so a small sample can't dominate.
    logs = [g.value for g in prop.logs] if prop.logs else []
    if logs:
        hr_per_game = sum(logs) / len(logs)
        raw_rate = hr_per_game / DEFAULT_PA
        # Regress toward league average: even a full season of home runs is a
        # small sample for a ~3%-per-PA event, so half weight is the ceiling.
        weight = clamp(len(logs) / 40.0, 0.0, 0.5)
        base_rate = weight * raw_rate + (1 - weight) * LEAGUE_HR_PER_PA
        src = f"{hr_per_game:.2f} HR/game over {len(logs)} games"
    else:
        base_rate = LEAGUE_HR_PER_PA
        src = "league-average home-run rate (no game logs)"

    contact_m, contact_r, has_statcast = contact_multiplier(prop)
    pitch_m, pitch_r = pitcher_multiplier(prop, game)
    env_m, env_r, env_caveats = park_weather_multiplier(game)

    # Cap the *combined* adjustment rather than each part: three independent
    # 1.4x factors would otherwise compound to nearly 3x, which no real
    # home-run edge justifies.
    total_mult = clamp(contact_m * pitch_m * env_m, 0.45, 2.4)
    # The ceiling is deliberately loose so it almost never binds — a clamp that
    # binds makes different conditions produce identical numbers.
    rate = clamp(base_rate * pa * total_mult, 0.002, 0.50)
    prob = prob_at_least_one(rate)

    reasons = [f"Baseline from {src}; {pa:.1f} expected plate appearances "
               f"batting {prop.lineup_spot or '?'}"]
    reasons += contact_r + pitch_r + env_r

    caveats = list(env_caveats)
    if not has_statcast:
        caveats.append("No Statcast contact data — power profile is inferred from results only")
    if not getattr(game, "lineups_confirmed", True):
        caveats.append("Projected from the team's last lineup — "
                       + _lineup_eta(game)
                       + "; verify he's starting before betting")
    elif prop.lineup_spot in (0, None):
        caveats.append("Lineup spot unconfirmed — plate appearances estimated")

    primary = (contact_r or env_r or pitch_r or reasons)[0]
    return prob, {
        "reasons": reasons, "caveats": caveats, "opportunities": pa,
        "primary_reason": primary,
        "data_quality": 1.0 if has_statcast else 0.8,
    }


def hr_watchlist(candidates: list[dict], limit: int | None = 10) -> list[dict]:
    """Tonight's most likely home runs — every real-priced HR over, ranked by
    the model's probability (hitter power × pitcher × park × weather × plate
    appearances).

    This is the "who could go deep tonight" board the Long Shots page shows
    even when no strict value pick clears the bar: the price and EV are
    displayed honestly, so a likely homer at a fair (no-value) price reads as
    exactly that — insight, not a guaranteed bet."""
    from ..odds import american_to_decimal
    from ..longshots import calibrated_prob
    rows: list[dict] = []
    for c in candidates:
        odds = c.get("odds")
        # Plus-money, real, plausible 1+ HR prices only: nobody is +1500 to
        # homer, so anything longer is a stale or mis-lined quote.
        if not odds or not (100 < int(odds) <= 1500):
            continue
        if (c.get("book") or "").lower() == "proxy":     # real prices only
            continue
        prop, game = c["prop"], c["game"]
        raw_prob, info = hr_probability(prop, game)
        odds = int(odds)
        # The SAME tempering + market shrink the value picks get — a raw
        # probability here once inflated EV past the broken-price guard and
        # silently emptied the entire watchlist.
        under = c.get("under_odds") or None
        prob, implied = calibrated_prob("mlb", HOME_RUNS, raw_prob, odds, under)
        if prob * american_to_decimal(odds) - 1.0 > 0.60:
            # A claimed +60% EV on a homer market is a broken price, not an
            # edge — same too-good-to-be-true guard as the sharp anchor.
            continue
        rows.append({
            "player": prop.player, "team": prop.team,
            "opponent": prop.opponent, "book": c.get("book", ""),
            "odds": odds,
            "model_prob": round(prob, 4),
            "implied_prob": round(implied, 4),
            "ev_per_unit": round(prob * american_to_decimal(odds) - 1.0, 4),
            "primary_reason": info["primary_reason"],
            "recent_values": [g.value for g in prop.logs][:12],
            "caveats": info["caveats"][:1],
            "game_date": getattr(game, "date", ""),
            "kickoff": getattr(game, "kickoff", ""),
        })
    rows.sort(key=lambda r: -r["model_prob"])
    return rows if limit is None else rows[:limit]


# Measured on the first 214 settled home-run bets. The model ranks: split
# by its own claimed probability, the bottom two quartiles returned -37%
# and -39% while the top two returned +10.8% and +11.1% (z = 2.09), and
# the price cut agrees independently — +399-and-shorter made +39%,
# +700-and-out lost 35%. Everything the model rates below ~12% burns.
#
# So the board stops betting the tail it cannot pick. PROVISIONAL: the
# threshold was chosen after seeing these results, on 108 profitable
# bets, so it is fitted to its own sample and needs forward confirmation
# before it means anything. It is set at the measured boundary rather
# than optimised past it, deliberately.
MIN_MODEL_PROB = 0.12


def build_hr_longshots(candidates: list[dict], limit: int = 3,
                       per_team: int = 1,
                       min_prob: float = MIN_MODEL_PROB) -> list[LongShot]:
    """Rank home-run picks.

    ``candidates`` = ``[{prop, game, odds, book, under_odds?}]``. Applies the
    strategy's +250..+650 odds window, the measured ``min_prob`` floor and
    the one-per-team cap, and returns at most ``limit`` picks.
    """
    picks: list[LongShot] = []
    for c in candidates:
        odds = int(c["odds"])
        if not in_odds_window(odds, MLB_HR_ODDS):
            continue
        prop, game = c["prop"], c["game"]
        prob, info = hr_probability(prop, game)
        # The tail the model cannot pick — see MIN_MODEL_PROB.
        if prob < min_prob:
            continue
        pick = build_pick(
            player=prop.player, team=prop.team, opponent=prop.opponent,
            market=HOME_RUNS, label=MARKET_LABELS[HOME_RUNS],
            book=c.get("book", ""), odds=odds, model_prob=prob,
            under_odds=c.get("under_odds"),
            opportunities=info["opportunities"], opp_target=4.5,
            primary_reason=info["primary_reason"], reasons=info["reasons"],
            caveats=info["caveats"], sport="mlb", data_quality=info["data_quality"],
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
            picks.append(pick)

    return select(picks, per_key_cap=per_team, key=lambda p: p.team, limit=limit)
