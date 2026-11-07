"""One player's full fantasy profile — the dossier page, in data.

Ethan, 2026-08-18, with a competitor's player-page render: "Follow this
exact render." The render's sections map onto data this repo actually
holds, and the mapping is the module:

  * Season stat tiles with position ranks  -> the ingested game logs,
    ranked among same-position players with a real sample.
  * Fantasy points by week                 -> nflverse's own fp_ppr,
    stored per player-game since the lineup optimiser landed.
  * Utilization                            -> snap_pct, per-game volume.
  * "Advanced" metrics                     -> the ones WE measure: air
    yards, aDOT (air yards / target), expected fantasy points. The
    render's EPA/CPOE panel is play-by-play nobody here ingests, and a
    dash is not allowed to cosplay as a metric — the section shows what
    is real and nothing else.
  * Matchup strength + upcoming game       -> the cached nflverse
    schedule, with defenses ranked by the fantasy points per game they
    ALLOW to the player's position in our own logs.

Same honest-degradation contract as statlogs: no DB, empty dict; a
machine with logs fills everything its logs can fill.
"""

from __future__ import annotations

import os
from collections import defaultdict

from . import db as _db

#: Season-tile and game-log columns per position: (market, short label).
POSITION_STATS = {
    "QB": (("pass_yds", "Pass yds"), ("pass_td", "Pass TD"),
           ("pass_int", "INT"), ("rush_yds", "Rush yds"),
           ("rush_td", "Rush TD"), ("fp_ppr", "PPR pts")),
    "RB": (("carries", "Carries"), ("rush_yds", "Rush yds"),
           ("rush_td", "Rush TD"), ("targets", "Targets"),
           ("receptions", "Rec"), ("rec_yds", "Rec yds"),
           ("fp_ppr", "PPR pts")),
    "WR": (("targets", "Targets"), ("receptions", "Rec"),
           ("rec_yds", "Rec yds"), ("rec_td", "Rec TD"),
           ("carries", "Carries"), ("fp_ppr", "PPR pts")),
    "TE": (("targets", "Targets"), ("receptions", "Rec"),
           ("rec_yds", "Rec yds"), ("rec_td", "Rec TD"),
           ("fp_ppr", "PPR pts")),
}
POSITION_STATS["FB"] = POSITION_STATS["RB"]

#: A defense needs this many games against the position before its rank
#: is evidence rather than one Thursday.
MIN_DEF_GAMES = 3

#: A season rank is only claimed among players with a real sample.
MIN_RANK_GAMES = 3

GAMELOG_WEEKS = 8
WEEKLY_N = 10


def profile(player: str, db_path=None, today: str | None = None) -> dict:
    path = str(db_path or _db.DEFAULT_DB)
    if not player or not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        return _build(conn, player, today)
    finally:
        conn.close()


def _build(conn, player: str, today: str | None) -> dict:
    latest = conn.execute(
        "SELECT team, position, season FROM player_game_logs "
        "WHERE sport='nfl' AND player=? AND position != '' "
        "ORDER BY season DESC, period DESC LIMIT 1", (player,)).fetchone()
    if not latest:
        return {}
    team, pos = latest["team"], (latest["position"] or "").upper()
    season = int(latest["season"])
    stats = POSITION_STATS.get(pos) or POSITION_STATS["WR"]

    rows = conn.execute(
        "SELECT period, opponent, home, market, value FROM player_game_logs "
        "WHERE sport='nfl' AND player=? AND season=?",
        (player, season)).fetchall()
    by_week: dict[str, dict] = defaultdict(dict)
    meta: dict[str, dict] = {}
    for r in rows:
        by_week[r["period"]][r["market"]] = float(r["value"])
        meta[r["period"]] = {"opponent": r["opponent"],
                            "home": bool(r["home"])}
    weeks = sorted(by_week)
    games = sum(1 for w in weeks if "fp_ppr" in by_week[w]) or len(weeks)

    out = {
        "player": player, "team": team, "position": pos, "season": season,
        "games": games,
        "headshot": _face(conn, player),
        "bio": {},                        # filled by the roster payload,
                                          # browser-side — it is already
                                          # a web/data file.
        "season_stats": _season_tiles(conn, player, pos, season,
                                      stats, by_week, games),
        "weekly": _weekly(by_week, meta, weeks),
        "gamelog": _gamelog(conn, team, season, stats, by_week, meta, weeks),
        "utilization": _utilization(pos, by_week, games),
    }
    ranks, def_n = _defense_ranks(conn, pos, season)
    out["schedule"] = _schedule(team, season, weeks, ranks, def_n)
    return out


def _face(conn, player: str) -> str:
    try:
        r = conn.execute("SELECT headshot FROM player_assets "
                         "WHERE sport='nfl' AND player=?",
                         (player,)).fetchone()
        return (r["headshot"] if r else "") or ""
    except Exception:                                        # noqa: BLE001
        return ""


def _season_tiles(conn, player, pos, season, stats, by_week, games) -> list:
    """Totals with position ranks, computed against the same logs."""
    tiles = []
    for market, label in stats:
        vals = [w.get(market) for w in by_week.values()]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        total = round(sum(vals), 1)
        # Rank BY TOTAL among same-position players with a sample. One
        # query per tile is fine: the page asks for one player at a time.
        peers = conn.execute(
            "SELECT player, SUM(value) AS t, COUNT(*) AS g "
            "FROM player_game_logs WHERE sport='nfl' AND season=? "
            "AND market=? AND position=? GROUP BY player "
            "HAVING g >= ?", (season, market, pos, MIN_RANK_GAMES)).fetchall()
        rank = n = None
        if len(peers) >= 5:
            # INT and fumbles would want ascending; every market this
            # module ships counts UP, interceptions included on purpose —
            # the tile says "5th in INT" and means volume, so the label
            # carries it honestly rather than the sort lying about it.
            ordered = sorted(peers, key=lambda p: -(p["t"] or 0))
            n = len(ordered)
            for i, p in enumerate(ordered):
                if p["player"] == player:
                    rank = i + 1
                    break
        tiles.append({"market": market, "label": label, "total": total,
                      "per_game": round(total / games, 1) if games else None,
                      "rank": rank, "of": n})
    return tiles


def _weekly(by_week, meta, weeks) -> list:
    out = []
    for w in weeks:
        fp = by_week[w].get("fp_ppr")
        if fp is None:
            continue
        m = meta.get(w) or {}
        out.append({"week": int(w), "fp": round(fp, 1),
                    "opponent": m.get("opponent", ""),
                    "home": m.get("home", True)})
    return out[-WEEKLY_N:]


def _gamelog(conn, team, season, stats, by_week, meta, weeks) -> list:
    """The last weeks as table rows, with the game's own final score."""
    cols = [m for m, _ in stats if m != "fp_ppr"][:3]
    out = []
    for w in reversed(weeks[-GAMELOG_WEEKS:]):
        m = meta.get(w) or {}
        row = {"week": int(w), "opponent": m.get("opponent", ""),
               "home": m.get("home", True),
               "fp": by_week[w].get("fp_ppr"),
               "cols": [by_week[w].get(c) for c in cols]}
        g = conn.execute(
            "SELECT home, away, home_score, away_score FROM games "
            "WHERE sport='nfl' AND season=? AND period=? "
            "AND (home=? OR away=?) AND home_score IS NOT NULL",
            (season, w, team, team)).fetchone()
        if g:
            ours = g["home_score"] if g["home"] == team else g["away_score"]
            theirs = g["away_score"] if g["home"] == team else g["home_score"]
            row["result"] = f"{'W' if ours > theirs else 'L' if ours < theirs else 'T'} {int(ours)}-{int(theirs)}"
        out.append(row)
    return {"columns": cols, "rows": out}


def _utilization(pos, by_week, games) -> dict:
    def pg(market):
        vals = [w.get(market) for w in by_week.values()]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    snap_vals = [w.get("snap_pct") for w in by_week.values()]
    snap_vals = [v for v in snap_vals if v is not None]
    u = {"snap_pct": round(100 * sum(snap_vals) / len(snap_vals))
         if snap_vals else None}
    if pos == "QB":
        # No air yards for a passer: the ingested market is RECEIVING air
        # yards, and a quarterback's honest zero reads as a broken stat.
        u["rows"] = [("Pass attempts / game", pg("pass_att")),
                     ("Rush attempts / game", pg("carries"))]
    else:
        tgt, ay = pg("targets"), pg("air_yards")
        u["rows"] = [("Targets / game", tgt),
                     ("Carries / game", pg("carries")),
                     ("Air yards / game", ay),
                     ("aDOT", round(ay / tgt, 1) if ay and tgt else None)]
    u["rows"] = [(k, v) for k, v in u["rows"] if v is not None]
    u["xfp_pg"] = pg("xfp")
    u["fp_pg"] = pg("fp_ppr")
    return u


def _defense_ranks(conn, pos, season) -> tuple[dict, int]:
    """{defense: rank} by fantasy points per game ALLOWED to ``pos``.

    Rank 1 allows the least — the render colours high ranks as soft
    matchups and so does the page."""
    rows = conn.execute(
        "SELECT opponent, period, SUM(value) AS fp "
        "FROM player_game_logs WHERE sport='nfl' AND season=? "
        "AND market='fp_ppr' AND position=? AND opponent != '' "
        "GROUP BY opponent, period", (season, pos)).fetchall()
    per_def: dict[str, list] = defaultdict(list)
    for r in rows:
        per_def[r["opponent"]].append(r["fp"] or 0.0)
    allowed = {d: sum(v) / len(v) for d, v in per_def.items()
               if len(v) >= MIN_DEF_GAMES}
    ordered = sorted(allowed, key=lambda d: allowed[d])
    return ({d: {"rank": i + 1, "allowed_pg": round(allowed[d], 1)}
             for i, d in enumerate(ordered)}, len(ordered))


def _schedule(team, season, played_weeks, ranks, def_n) -> dict:
    """Next games from the cached nflverse schedule, matchup-ranked.

    The schedule season may be AHEAD of the stats season (August: 2026
    schedule, 2025 logs) — the defense ranks stay last-season's and the
    page says whose season they are."""
    try:
        from .seasons import season_of
        import datetime
        sched_season = season_of("nfl", datetime.date.today().isoformat())
    except Exception:                                        # noqa: BLE001
        sched_season = season
    try:
        from .sources import nflverse
        sched = nflverse.load_schedules()
    except Exception:                                        # noqa: BLE001
        return {}
    future = []
    # August belongs to two seasons at once: season_of still says last
    # year (nothing new has kicked off) while the schedule file already
    # carries next year's slate. Take the first season that still has
    # unplayed games for this club.
    for cand in (sched_season, sched_season + 1):
        rows = [r for r in sched if r.get("season") == str(cand)
                and team in (r.get("home_team"), r.get("away_team"))]
        played = {int(w) for w in played_weeks} if cand == season else set()
        future = sorted((r for r in rows
                         if int(r.get("week") or 0) not in played
                         and not (r.get("home_score") or "").strip()),
                        key=lambda r: int(r.get("week") or 0))
        if future:
            sched_season = cand
            break
    if not future:
        return {}
    nxt = []
    for r in future[:4]:
        home = r.get("home_team") == team
        opp = r.get("away_team") if home else r.get("home_team")
        d = ranks.get(opp) or {}
        nxt.append({"week": int(r.get("week") or 0), "opponent": opp,
                    "home": home, "def_rank": d.get("rank"),
                    "allowed_pg": d.get("allowed_pg")})
    up = future[0] if future else None
    upcoming = None
    if up:
        home = up.get("home_team") == team
        try:
            spread = -float(up.get("spread_line"))
        except (TypeError, ValueError):
            spread = None
        try:
            total = float(up.get("total_line"))
        except (TypeError, ValueError):
            total = None
        upcoming = {"home_team": up.get("home_team"),
                    "away_team": up.get("away_team"),
                    "date": up.get("gameday", ""),
                    "kickoff": up.get("gametime", ""),
                    "spread": spread, "total": total,
                    "we_are_home": home}
    return {"season": sched_season, "def_rank_season": season,
            "def_rank_of": def_n, "next": nxt, "upcoming": upcoming}
