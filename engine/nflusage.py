"""Measured NFL roles from ingested logs — red-zone usage and snap shares.

The anytime-touchdown model has always carried a confession: true red-zone
usage lives in play-by-play this project ingests but never read, so the
model inferred it from overall volume and flagged every pick with "the
biggest source of error here". This module ends that. It reads the
per-week red-zone rows the play-by-play ingest already stores (rz_tgt /
rz_car / i5_car) and the snap-share rows the weekly ingest now stores,
and hands the pipeline per-player measured roles:

* :func:`red_zone_usage` — expected red-zone chances per game and the
  player's share of his TEAM's red-zone touches, ``measured=True``;
* :func:`snap_shares` — average offensive snap share, the cleanest
  "is he actually on the field" signal volume stats can't provide.

Join key: play-by-play abbreviates names ("P.Mahomes") while slates carry
full names, so both maps key on the fantasy layer's ``(initial, lastname,
team)`` short key — team included, which is what keeps A.J. Brown and
Amon-Ra St. Brown apart (the collision that once sent Amon-Ra to New
England in the offseason layer).

Standard library only; reads the history DB the ingests already fill.
"""

from __future__ import annotations

from .fantasy import _short_key
from .touchdowns import RedZoneUsage

# Recent-role windows, in distinct weeks with data. Roles change with
# injuries and game plans; a season-long average smears September's back
# over December's.
RZ_WEEKS = 6
SNAP_WEEKS = 5

# --- the usage bridge's volume roles ----------------------------------------
# Each yardage/catch market's OPPORTUNITY stat. Volume is stickier than
# production week to week — coordinators hand out targets and carries on
# purpose, while yards bounce — so the bridge estimates a player as
# "recent volume × season-long per-opportunity efficiency" and lets the
# projection blend that against observed outcomes by sample size.
OPP_BY_MARKET = {
    "receptions": "targets",
    "rec_yds": "targets",
    "rush_yds": "carries",
    "pass_yds": "pass_att",
}
VOL_WEEKS = 4
# Efficiency needs a real denominator: below these season totals a per-
# opportunity rate is one screen pass wearing a trend costume, and the
# player simply has no volume role rather than a junk one.
MIN_EFF_OPPS = {"targets": 12, "carries": 20, "pass_att": 60}


def latest_season(conn, market: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(season) FROM player_game_logs WHERE sport='nfl' "
        "AND market=?", (market,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def red_zone_usage(conn, season: int | None = None) -> dict:
    """``{(initial, lastname, team): RedZoneUsage(measured=True)}``.

    Per player: per-game averages over his most recent ``RZ_WEEKS`` weeks
    with red-zone rows. ``rz_touch_share`` is his average red-zone touches
    over his team's average in the same weeks — the number the TD model
    calls the single best predictor it couldn't see.
    """
    season = season or latest_season(conn, "rz_tgt")
    if season is None:
        return {}
    per_player: dict = {}
    team_weeks: dict = {}
    for r in conn.execute(
            "SELECT player, team, period, market, value FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market IN "
            "('rz_tgt', 'rz_car', 'i5_car')", (season,)):
        wk = per_player.setdefault((r["player"], r["team"]), {}) \
                       .setdefault(r["period"], {})
        wk[r["market"]] = float(r["value"] or 0)
        if r["market"] in ("rz_tgt", "rz_car"):
            tw = team_weeks.setdefault(r["team"], {})
            tw[r["period"]] = tw.get(r["period"], 0.0) + float(r["value"] or 0)

    out: dict = {}
    for (player, team), weeks in per_player.items():
        recent = sorted(weeks, reverse=True)[:RZ_WEEKS]
        if not recent:
            continue
        n = len(recent)
        tgt = sum(weeks[w].get("rz_tgt", 0.0) for w in recent) / n
        i5 = sum(weeks[w].get("i5_car", 0.0) for w in recent) / n
        # rz_car (all inside-20 carries) is a newer market — older ingests
        # only have the inside-5 slice, which is still a floor, not zero.
        car = sum(max(weeks[w].get("rz_car", 0.0), weeks[w].get("i5_car", 0.0))
                  for w in recent) / n
        team_avg = [team_weeks.get(team, {}).get(w, 0.0) for w in recent]
        team_touches = sum(team_avg) / n if n else 0.0
        share = (tgt + car) / team_touches if team_touches > 0 else 0.0
        out[_short_key(player, team)] = RedZoneUsage(
            carries_inside_5=round(i5, 2),
            carries_inside_10=round(car, 2),
            targets_inside_10=round(tgt, 2),
            rz_touch_share=round(min(share, 1.0), 3),
            measured=True,
        )
    return out


def snap_shares(conn, season: int | None = None) -> dict:
    """``{(initial, lastname, team): avg offensive snap share (0-1)}`` over
    each player's most recent ``SNAP_WEEKS`` weeks."""
    season = season or latest_season(conn, "snap_pct")
    if season is None:
        return {}
    per_player: dict = {}
    for r in conn.execute(
            "SELECT player, team, period, value FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market='snap_pct'", (season,)):
        per_player.setdefault((r["player"], r["team"]), {})[r["period"]] = \
            float(r["value"] or 0)
    out: dict = {}
    for (player, team), weeks in per_player.items():
        recent = sorted(weeks, reverse=True)[:SNAP_WEEKS]
        if recent:
            out[_short_key(player, team)] = round(
                sum(weeks[w] for w in recent) / len(recent), 3)
    return out


def volume_roles(conn, season: int | None = None) -> dict:
    """``{(initial, lastname, team): {market: role}}`` where each role is
    ``{"opp_per_game", "eff", "opp_market", "n_weeks"}``.

    The usage bridge's data: per outcome market, the player's average
    opportunities over his most recent ``VOL_WEEKS`` weeks (the role he
    holds NOW) times his season-long per-opportunity efficiency (the
    stable rate) is a second baseline the projection can weigh against
    thin or stale outcome logs. Players under ``MIN_EFF_OPPS`` season
    opportunities get no role at all — an absent bridge, not a noisy one.
    """
    if season is None:
        found = [latest_season(conn, m) for m in sorted(set(OPP_BY_MARKET.values()))]
        found = [s for s in found if s is not None]
        season = max(found) if found else None
    if season is None:
        return {}
    markets = tuple(OPP_BY_MARKET) + tuple(sorted(set(OPP_BY_MARKET.values())))
    per: dict = {}
    for r in conn.execute(
            "SELECT player, team, period, market, value FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market IN (%s)"
            % ",".join("?" * len(markets)), (season, *markets)):
        per.setdefault((r["player"], r["team"]), {}) \
           .setdefault(r["period"], {})[r["market"]] = float(r["value"] or 0)

    out: dict = {}
    for (player, team), weeks in per.items():
        roles: dict = {}
        for market, opp in OPP_BY_MARKET.items():
            with_opp = [w for w in weeks if opp in weeks[w]]
            if len(with_opp) < 2:
                continue
            recent = sorted(with_opp, reverse=True)[:VOL_WEEKS]
            opp_pg = sum(weeks[w][opp] for w in recent) / len(recent)
            paired = [w for w in with_opp if market in weeks[w]]
            tot_opp = sum(weeks[w][opp] for w in paired)
            if tot_opp < MIN_EFF_OPPS[opp]:
                continue
            eff = sum(weeks[w][market] for w in paired) / tot_opp
            roles[market] = {"opp_per_game": round(opp_pg, 2),
                            "eff": round(eff, 3),
                            "opp_market": opp,
                            "n_weeks": len(with_opp)}
        if roles:
            out[_short_key(player, team)] = roles
    return out


def build_usage_maps(conn) -> dict:
    """All three maps in one call — what nfl_build hands the pipeline. Empty
    maps (nothing ingested yet) leave the model exactly as it was."""
    return {"red_zone": red_zone_usage(conn), "snap": snap_shares(conn),
            "volume": volume_roles(conn)}
