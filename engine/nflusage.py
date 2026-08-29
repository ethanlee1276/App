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


def volume_roles(conn, season: int | None = None,
                 upto_week: int | None = None) -> dict:
    """``{(initial, lastname, team): {market: role}}`` where each role is
    ``{"opp_per_game", "eff", "opp_market", "n_weeks"}``.

    The usage bridge's data: per outcome market, the player's average
    opportunities over the most recent ``VOL_WEEKS`` weeks (the role held
    NOW) times season-long per-opportunity efficiency (the stable rate) is
    a second baseline the projection can weigh against thin or stale
    outcome logs. Players under ``MIN_EFF_OPPS`` season opportunities get
    no role at all — an absent bridge, not a noisy one.

    ``upto_week`` keeps only weeks STRICTLY BEFORE it, which is what makes
    this measurable at all.

    WHY IT HAD TO EXIST. Live, this reads a database holding only games
    that have been played, so "the whole season" and "everything so far"
    are the same set and the distinction never came up. A backtest replays
    week 7 with all 22 weeks on disk, so the same call would hand the
    model its own answers. `engine/backtest.py` avoided that the only way
    it could — by passing no usage at all — and the result was that every
    calibration fitted through the walk, and every AUC measured from it,
    described a model the live board does not run: at four games of log
    the bridge supplies half the projection's base (`USAGE_PRIOR_GAMES`).
    Fitting on one model and applying to another is the same mistake as
    fitting against a proxy line, one level further up.
    """
    if season is None:
        found = [latest_season(conn, m) for m in sorted(set(OPP_BY_MARKET.values()))]
        found = [s for s in found if s is not None]
        season = max(found) if found else None
    if season is None:
        return {}
    markets = tuple(OPP_BY_MARKET) + tuple(sorted(set(OPP_BY_MARKET.values())))
    sql = ("SELECT player, team, period, market, value FROM player_game_logs "
           "WHERE sport='nfl' AND season=? AND market IN (%s)"
           % ",".join("?" * len(markets)))
    args: list = [season, *markets]
    if upto_week is not None:
        # CAST, because `period` is a zero-padded string ('001'..'022') and
        # a string comparison puts '010' below '7'. The one place that
        # silently returns the wrong weeks rather than none.
        sql += " AND CAST(period AS INTEGER) < ?"
        args.append(int(upto_week))
    per: dict = {}
    for r in conn.execute(sql, args):
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


def xfp_roles(conn, season: int | None = None,
              upto_week: int | None = None) -> dict:
    """``{short_key: {"xfp_pg", "xfp_share", "n_weeks"}}``.

    Expected fantasy points per game, and — the useful half — that
    player's SHARE of his team's total, which is a direct reading of how
    much of an offence's scoring opportunity belongs to him.

    Measured on held-out seasons it orders a touchdown better than
    anything else in the database, including the player's own touchdown
    rate (AUC 0.696 against 0.672) and well ahead of red-zone carries
    (0.576). It has been ingested for five seasons and read only by the
    fantasy waiver board; `engine.touchdowns` never saw it.

    The share, not the level, because the level says a workhorse on a bad
    offence and a complementary back on a great one are the same player,
    and for scoring they are not.
    """
    if season is None:
        season = latest_season(conn, "xfp")
    if season is None:
        return {}
    sql = ("SELECT player, team, period, value FROM player_game_logs "
           "WHERE sport='nfl' AND season=? AND market='xfp'")
    args: list = [season]
    if upto_week is not None:
        # CAST for the reason volume_roles gives: `period` is zero-padded
        # TEXT and an uncast comparison silently matches every row.
        sql += " AND CAST(period AS INTEGER) < ?"
        args.append(int(upto_week))
    per: dict = {}
    team_week: dict = {}
    for r in conn.execute(sql, args):
        val = float(r["value"] or 0.0)
        key = _short_key(r["player"], r["team"])
        per.setdefault(key, {})[r["period"]] = val
        tk = (r["team"], r["period"])
        team_week[tk] = team_week.get(tk, 0.0) + val

    out: dict = {}
    for key, weeks in per.items():
        if len(weeks) < 2:
            continue
        recent = sorted(weeks, reverse=True)[:VOL_WEEKS]
        pg = sum(weeks[w] for w in recent) / len(recent)
        shares = []
        for w in recent:
            total = team_week.get((key[2], w)) or 0.0
            if total > 0:
                shares.append(weeks[w] / total)
        if not shares:
            continue
        out[key] = {"xfp_pg": round(pg, 3),
                    "xfp_share": round(sum(shares) / len(shares), 4),
                    "n_weeks": len(weeks)}
    return out


#: Box-score markets that prove a player actually touched the ball, and
#: the play-by-play aggregates that should therefore exist for him.
_BOX_MARKETS = ("carries", "targets", "rush_yds", "rec_yds", "receptions")
_PBP_MARKETS = ("xfp", "rz_car", "rz_tgt", "i5_car")


def join_audit(conn, season: int | None = None, min_touches: float = 20.0) -> list:
    """Players with real production whose play-by-play rows never join.

    THE CHECK THAT SHOULD HAVE EXISTED FIRST. `player_game_logs` holds
    two feeds under one schema — the weekly box score writing "Chris
    Godwin Jr." and the play-by-play writing "C.Godwin" — joined only by
    `fantasy._short_key`. When that key is wrong the rows do not
    disappear and nothing errors; the player simply has no measured
    usage, and every model that asks about him gets a confident answer
    built on nothing. It took a touchdown card missing an explanation to
    notice, and by then it had been true for 32 players a season.

    So: anyone with at least `min_touches` carries plus targets whose key
    finds no play-by-play row. Zero-production special-teamers are
    excluded by that floor rather than by name, because they genuinely
    have no play-by-play and reporting them would bury the real misses.

    Returns ``[(player, team, touches)]``, worst first. Empty is the
    healthy answer.
    """
    if season is None:
        season = latest_season(conn, "carries")
    if season is None:
        return []
    box: dict = {}
    for r in conn.execute(
            "SELECT player, team, SUM(value) v FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market IN ('carries','targets') "
            "GROUP BY player, team", (season,)):
        box[_short_key(r["player"], r["team"])] = (
            r["player"], r["team"], float(r["v"] or 0.0))
    pbp = {_short_key(r["player"], r["team"]) for r in conn.execute(
        "SELECT DISTINCT player, team FROM player_game_logs WHERE sport='nfl' "
        "AND season=? AND market IN (%s)" % ",".join("?" * len(_PBP_MARKETS)),
        (season, *_PBP_MARKETS))}
    out = [v for k, v in box.items()
           if k not in pbp and v[2] >= min_touches]
    return sorted(out, key=lambda r: -r[2])


def build_usage_maps(conn, season: int | None = None,
                     upto_week: int | None = None) -> dict:
    """All three maps in one call — what nfl_build hands the pipeline. Empty
    maps (nothing ingested yet) leave the model exactly as it was.

    ``season``/``upto_week`` are for the replay, which must see only what
    had happened. Live callers pass neither and get today's database,
    which is already only what has happened."""
    return {"red_zone": red_zone_usage(conn), "snap": snap_shares(conn),
            "volume": volume_roles(conn, season, upto_week),
            "xfp": xfp_roles(conn, season, upto_week)}
