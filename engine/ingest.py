"""Ingestion pipeline — pull from the source adapters into the history DB.

NFL games (schedules) come from the nflverse git tree and ingest anywhere;
NFL player logs come from the release-gated weekly stats; MLB comes from the
MLB Stats API. Each stage degrades to a reported skip when its host is blocked,
so a partial ingest (e.g. 5 years of games without player logs) still succeeds.
The row-building parsers are pure and unit-tested.
"""

from __future__ import annotations

from . import db
from .sources.fetch import DataUnavailable


# --- NFL --------------------------------------------------------------------
def nfl_game_rows(schedule_rows: list[dict], seasons: set[int]) -> list[dict]:
    from .sources.nflverse import _s, _f
    out = []
    for r in schedule_rows:
        try:
            season = int(_s(r, "season", default="0"))
        except ValueError:
            continue
        if season not in seasons:
            continue
        wk = _s(r, "week", default="")
        if not wk:
            continue
        home, away = _s(r, "home_team"), _s(r, "away_team")
        out.append({
            "sport": "nfl", "season": season, "period": f"{int(float(wk)):03d}",
            "game_id": f"{away}@{home}", "home": home, "away": away,
            "home_score": _f(r, "home_score", default=None),
            "away_score": _f(r, "away_score", default=None),
            "spread": -_f(r, "spread_line", default=0.0),
            "total": _f(r, "total_line", default=None),
            "roof": _s(r, "roof"), "surface": _s(r, "surface", default="grass"),
            "temp": _f(r, "temp", default=None), "wind": _f(r, "wind", default=None),
            "extra": None,
        })
    return out


def nfl_player_log_rows(stats_rows: list[dict], season: int) -> list[dict]:
    from .sources.nflverse import _s, _f, POSITION_MARKETS, MARKET_COLUMNS
    out = []
    for r in stats_rows:
        pos = _s(r, "position", "position_group").upper()
        if pos not in POSITION_MARKETS:
            continue
        wk = int(_f(r, "week", default=0))
        if wk <= 0:
            continue
        name = _s(r, "player_display_name", "player_name", "full_name")
        team = _s(r, "recent_team", "team")
        opp = _s(r, "opponent_team", "opponent")
        if not name:
            continue
        for market, _role in POSITION_MARKETS[pos]:
            out.append({
                "sport": "nfl", "season": season, "period": f"{wk:03d}",
                "game_id": f"{team}-{wk:03d}", "player": name, "team": team,
                "opponent": opp, "position": pos, "home": 1,
                "market": market, "value": _f(r, *MARKET_COLUMNS[market]),
            })
    return out


def ingest_nfl(conn, seasons: list[int]) -> dict:
    from .sources.nflverse import load_schedules, load_weekly_stats
    result = {"games": 0, "player_logs": 0, "skipped": []}

    # Games (reachable from the git tree even without release access).
    try:
        grows = nfl_game_rows(load_schedules(), set(seasons))
        result["games"] = db.upsert_games(conn, grows)
        db.log_ingest(conn, "nfl", "games", f"seasons {min(seasons)}-{max(seasons)}", result["games"])
    except DataUnavailable as exc:
        result["skipped"].append(f"nfl games: {exc}")

    # Player logs (release-gated).
    for season in seasons:
        try:
            rows = nfl_player_log_rows(load_weekly_stats(season), season)
        except DataUnavailable:
            result["skipped"].append(f"nfl player logs {season}: release access needed")
            continue
        n = db.upsert_player_logs(conn, rows)
        result["player_logs"] += n
        db.log_ingest(conn, "nfl", "player_logs", str(season), n)
    return result


# --- MLB --------------------------------------------------------------------
def mlb_rows_from_slate(slate, date: str) -> tuple[list[dict], list[dict]]:
    """Game + player-log rows from a live MLB slate. Player logs use the game
    index within the season as the sortable period."""
    from .mlb.parks import get_park
    season = int(date[:4])
    grows = []
    for g in slate.games:
        park = get_park(g.park)
        grows.append({
            "sport": "mlb", "season": season, "period": date,
            "game_id": f"{g.away}@{g.home}", "home": g.home, "away": g.away,
            "home_score": None, "away_score": None, "spread": 0.0, "total": g.total,
            "roof": park.roof, "surface": park.surface,
            "temp": g.weather.temp_f, "wind": g.weather.wind_mph, "extra": g.park,
        })
    prows = []
    for p in slate.props:
        for gl in p.logs:
            # Key on the game's real date. ``gl.game`` is only a recency index —
            # it shifts as newer games arrive, so using it would file the same
            # real game under a new key on every ingest and duplicate history.
            # Fall back to the index only when the source gave us no date.
            period = gl.date or f"idx-{gl.game:04d}"
            log_season = int(gl.date[:4]) if gl.date else season
            prows.append({
                "sport": "mlb", "season": log_season, "period": period,
                "game_id": f"{p.player}-{period}", "player": p.player,
                "team": p.team, "opponent": gl.opponent, "position": p.position,
                "home": 1 if gl.home else 0, "market": p.market, "value": gl.value,
            })
    return grows, prows


def mlb_result_rows(results: list[dict]) -> list[dict]:
    """Game rows (with real final scores) from parsed MLB results."""
    from .mlb.parks import get_park
    from .mlb.sources.mlbstats import VENUE_PARK
    out = []
    for r in results:
        venue = (r.get("venue") or "").lower()
        park_key = next((k for frag, k in VENUE_PARK.items() if frag in venue), "generic")
        park = get_park(park_key)
        date = r["date"]
        out.append({
            "sport": "mlb", "season": int(date[:4]), "period": date,
            "game_id": f"{r['away']}@{r['home']}",
            "home": r["home"], "away": r["away"],
            "home_score": r["home_score"], "away_score": r["away_score"],
            "spread": 0.0, "total": None,
            "roof": park.roof, "surface": park.surface,
            "temp": None, "wind": None, "extra": park_key,
        })
    return out


def ingest_mlb_results(conn, start: str, end: str,
                       with_logs: bool = True, progress=None) -> dict:
    """Ingest completed MLB games over a date range.

    Two layers, because the backtest needs both:

    * **final scores** — one cheap ranged request, and what the team-strength
      model learns from;
    * **player game logs** — the per-game outcomes a prop backtest replays.
      These come from the per-date slate builder, so they cost a few requests
      per day; ``with_logs=False`` skips them when only ratings are wanted.

    Without the log layer a harvested set of odds has nothing to be replayed
    against, which is exactly the dead end of "N book lines, 0 entries found".
    """
    import datetime as _dt
    from .mlb.sources.mlbstats import fetch_results
    result = {"games": 0, "player_logs": 0, "skipped": []}
    try:
        rows = mlb_result_rows(fetch_results(start, end))
    except DataUnavailable as exc:
        result["skipped"].append(f"mlb results {start}..{end}: {exc}")
        return result
    result["games"] = db.upsert_games(conn, rows)
    db.log_ingest(conn, "mlb", "results", f"{start}..{end}", result["games"])

    if not with_logs:
        return result

    day = _dt.date.fromisoformat(start)
    last = _dt.date.fromisoformat(end)
    while day <= last:
        iso = day.isoformat()
        sub = ingest_mlb_date(conn, iso)
        result["player_logs"] += sub["player_logs"]
        result["skipped"] += sub["skipped"]
        if progress:
            progress(iso, sub["player_logs"])
        day += _dt.timedelta(days=1)
    return result


def ingest_mlb_date(conn, date: str) -> dict:
    from .mlb.sources.statslogs import build_live_slate
    result = {"games": 0, "player_logs": 0, "skipped": []}
    try:
        slate = build_live_slate(date)
    except DataUnavailable as exc:
        result["skipped"].append(f"mlb {date}: {exc}")
        return result
    grows, prows = mlb_rows_from_slate(slate, date)
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    db.log_ingest(conn, "mlb", "slate", date, result["games"] + result["player_logs"])
    return result
