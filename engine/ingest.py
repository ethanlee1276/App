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


#: Season types the regular tables accept. nflverse ships REG and POST
#: today and no preseason at all, so this filter changes nothing right
#: now — it exists because the day that stops being true is the day
#: preseason weeks 1-3 would silently merge into regular weeks 1-3 under
#: the same `period`, and nobody would see it until a September
#: projection came back wrong. Preseason has its own table; see
#: `ingest_nfl_preseason`.
REGULAR_TYPES = ("REG", "POST", "")


def _is_regular(row: dict) -> bool:
    from .sources.nflverse import _s
    return _s(row, "season_type", "game_type", default="REG").upper() in REGULAR_TYPES


def nfl_player_log_rows(stats_rows: list[dict], season: int) -> list[dict]:
    from .sources.nflverse import _s, _f, POSITION_MARKETS, MARKET_COLUMNS
    out = []
    for r in stats_rows:
        if not _is_regular(r):
            continue
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


# Fantasy usage metrics — the INPUTS (opportunity), not the outputs (points).
# Volume is predictive; efficiency is noise. Stored per player-week so shares
# and trends can be computed against team totals.
NFL_USAGE_MARKETS = {
    "targets": ("targets",),
    "carries": ("carries",),
    "receptions": ("receptions",),
    "air_yards": ("receiving_air_yards", "air_yards"),
    "fp_ppr": ("fantasy_points_ppr",),
    "pass_att": ("attempts", "passing_attempts"),
}


def nfl_usage_rows(stats_rows: list[dict], season: int) -> list[dict]:
    from .sources.nflverse import _s, _f, POSITION_MARKETS
    out = []
    for r in stats_rows:
        if not _is_regular(r):
            continue
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
        for market, cols in NFL_USAGE_MARKETS.items():
            if market == "pass_att" and pos != "QB":
                continue
            out.append({
                "sport": "nfl", "season": season, "period": f"{wk:03d}",
                "game_id": f"{team}-{wk:03d}", "player": name, "team": team,
                "opponent": opp, "position": pos, "home": 1,
                "market": market, "value": _f(r, *cols),
            })
    return out


def nfl_td_rows(stats_rows: list[dict], season: int) -> list[dict]:
    """``anytime_td`` result rows: rushing + receiving touchdowns per game.

    This is what settles the NFL long-shot board. Passing TDs are
    deliberately excluded — an anytime-scorer prop pays the player who
    SCORES the touchdown, not the one who throws it."""
    from .sources.nflverse import _s, _f, POSITION_MARKETS
    out = []
    for r in stats_rows:
        if not _is_regular(r):
            continue
        pos = _s(r, "position", "position_group").upper()
        if pos not in POSITION_MARKETS:
            continue
        wk = int(_f(r, "week", default=0))
        if wk <= 0:
            continue
        name = _s(r, "player_display_name", "player_name", "full_name")
        team = _s(r, "recent_team", "team")
        if not name:
            continue
        tds = (_f(r, "rushing_tds", default=0.0)
               + _f(r, "receiving_tds", default=0.0))
        out.append({
            "sport": "nfl", "season": season, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": name, "team": team,
            "opponent": _s(r, "opponent_team", "opponent"), "position": pos,
            "home": 1, "market": "anytime_td", "value": tds,
        })
    return out


def snap_count_rows(rows: list[dict], season: int) -> list[dict]:
    """``snap_pct`` result rows (offensive snap share, 0–1) per player-week.

    Snap share is the measured ROLE the volume stats can't see; it feeds
    the touchdown board's reasoning and the fantasy usage layer."""
    from .sources.nflverse import _s, _f
    out = []
    for r in rows:
        pos = _s(r, "position").upper()
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        wk = int(_f(r, "week", default=0))
        if wk <= 0:
            continue
        name = _s(r, "player", "player_name")
        team = _s(r, "team", "recent_team")
        if not name:
            continue
        pct = _f(r, "offense_pct", default=0.0)
        if pct > 1.0:                     # some vintages publish 0–100
            pct /= 100.0
        out.append({
            "sport": "nfl", "season": season, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": name, "team": team,
            "opponent": _s(r, "opponent", "opponent_team"), "position": pos,
            "home": 1, "market": "snap_pct", "value": round(pct, 4),
        })
    return out


def ingest_nfl_results(conn, season: int) -> dict:
    """The light, season-time results pull that keeps the NFL journal
    grading itself: weekly player stats (prop actuals + usage + touchdown
    rows) WITHOUT the ~100MB play-by-play download. Schedules — and with
    them final scores for moneyline/total settling — already refresh daily
    in maintenance."""
    from .sources.nflverse import load_weekly_stats
    result = {"player_logs": 0, "skipped": []}
    try:
        weekly = load_weekly_stats(season)
    except DataUnavailable as exc:
        result["skipped"].append(f"nfl weekly stats {season}: {exc}")
        return result
    rows = nfl_player_log_rows(weekly, season)
    rows += nfl_usage_rows(weekly, season)
    rows += nfl_td_rows(weekly, season)
    result["player_logs"] = db.upsert_player_logs(conn, rows)
    # Snap counts ride along (separate release file, so its absence never
    # blocks the stats that settle bets).
    try:
        from .sources.nflverse import load_snap_counts
        n = db.upsert_player_logs(conn, snap_count_rows(load_snap_counts(season),
                                                        season))
        result["player_logs"] += n
    except DataUnavailable as exc:
        result["skipped"].append(f"nfl snap counts {season}: {exc}")
    db.log_ingest(conn, "nfl", "weekly_results", str(season),
                  result["player_logs"])
    return result


def ingest_nfl_preseason(conn, seasons: list[int], quiet: bool = False) -> dict:
    """Exhibition box scores into `preseason_player_logs`. Prices nothing.

    Ethan, 2026-08-14: "yeah keep going" — the collection step under the
    question of whether August can ever be modelled. It cannot be answered
    today for a reason that is about data rather than taste: nflverse
    publishes no preseason player stats, so this repo has never held one
    snap of it, and there is nothing to fit on.

    THE ROWS GO IN THEIR OWN TABLE, which is the entire safety story — see
    the schema note in engine/db.py. Every consumer of `player_game_logs`
    reads it by (sport, season, period) with no season-type filter, because
    until now there was nothing to filter; a preseason row in there would
    quietly enter the roster page's "last seen", the identity map, the
    team-log charts and every form window.

    One request per game, cached six hours, finals only.
    """
    from .sources import nflpreseason as pre
    result = {"games": 0, "player_logs": 0, "finals": 0, "skipped": []}
    for season in seasons:
        try:
            games = pre.preseason_games(season)
        except DataUnavailable as exc:
            result["skipped"].append(f"nfl preseason {season}: {exc}")
            continue
        played = [g for g in games if g.get("state") == "post"]
        result["games"] += len(played)
        # THE FINALS, which are the only thing the usage scan can ever be
        # tested against. A quarterback's nine attempts are a fact about
        # the game; whether that fact moved the scoreboard is a question,
        # and it is unanswerable while the scoreboard is not on disk.
        # Scheduled rows ride along so the table also holds the fixture
        # list; `upsert_preseason_games` refuses to null a stored final.
        result["finals"] = result.get("finals", 0) + db.upsert_preseason_games(
            conn, [{"sport": "nfl", "season": season, "week": g.get("week"),
                    "game_id": g.get("game_id"), "date": g.get("date"),
                    "home": g.get("home"), "away": g.get("away"),
                    "home_score": g.get("home_score"),
                    "away_score": g.get("away_score"),
                    "completed": 1 if g.get("completed") else 0,
                    "venue": g.get("venue")} for g in games])
        for g in played:
            gid = g.get("game_id")
            if not gid:
                continue
            try:
                rows = pre.parse_boxscore(pre.fetch_boxscore(gid), g)
            except DataUnavailable as exc:
                # One unreadable game must not cost the other 47.
                result["skipped"].append(f"nfl preseason box {gid}: {exc}")
                continue
            result["player_logs"] += db.upsert_preseason_logs(conn, rows)
        if not quiet:
            print(f"  {season}: {len(played)} played game(s), "
                  f"{result['player_logs']:,} row(s) so far")
    db.log_ingest(conn, "nfl", "preseason_box",
                  f"seasons {min(seasons)}-{max(seasons)}",
                  result["player_logs"])
    return result


def ingest_nfl(conn, seasons: list[int]) -> dict:
    from .sources.nflverse import load_schedules, load_weekly_stats
    result = {"games": 0, "player_logs": 0, "skipped": []}

    # Games (reachable from the git tree even without release access).
    # The UPCOMING season rides along even though nobody asked for it:
    # nflverse publishes next season's schedule in spring and books post
    # week-1 lines all summer, so pulling it now is what lets the game
    # scripts (and the schedule's own coach stamps) go live months before
    # any stats exist. Scores are null, so nothing downstream mistakes the
    # rows for played games.
    sched_seasons = set(seasons) | {max(seasons) + 1}
    try:
        grows = nfl_game_rows(load_schedules(), sched_seasons)
        result["games"] = db.upsert_games(conn, grows)
        db.log_ingest(conn, "nfl", "games",
                      f"seasons {min(sched_seasons)}-{max(sched_seasons)}",
                      result["games"])
    except DataUnavailable as exc:
        result["skipped"].append(f"nfl games: {exc}")

    # Player logs (release-gated). Usage rows ride along on the same fetch —
    # the fantasy engine's raw material (targets, carries, air yards, PPR).
    for season in seasons:
        try:
            weekly = load_weekly_stats(season)
        except DataUnavailable:
            result["skipped"].append(f"nfl player logs {season}: release access needed")
            continue
        rows = nfl_player_log_rows(weekly, season)
        rows += nfl_usage_rows(weekly, season)
        rows += nfl_td_rows(weekly, season)
        # Snap counts ride the full ingest too — they were maintenance-only
        # at first, which left a July backfill without snap shares until
        # the in-season (Aug-Feb) job first ran.
        try:
            from .sources.nflverse import load_snap_counts
            rows += snap_count_rows(load_snap_counts(season), season)
        except DataUnavailable as exc:
            result["skipped"].append(f"nfl snap counts {season}: {exc}")
        n = db.upsert_player_logs(conn, rows)
        result["player_logs"] += n
        db.log_ingest(conn, "nfl", "player_logs", str(season), n)

    # Play-by-play for the LATEST season only (the file is ~100MB): real
    # xFP situation values, red-zone/inside-5 usage, and team PROE.
    try:
        from .sources.nflpbp import (load_pbp_rows, aggregate_pbp,
                                     xfp_player_rows, team_week_rows)
        season = max(seasons)
        agg = aggregate_pbp(load_pbp_rows(season))
        n_x = db.upsert_player_logs(conn, xfp_player_rows(agg, season))
        n_t = db.upsert_team_weeks(conn, team_week_rows(agg, season))
        result["pbp_rows"] = n_x + n_t
        db.log_ingest(conn, "nfl", "pbp", str(season), n_x + n_t)
    except DataUnavailable as exc:
        result["skipped"].append(f"nfl pbp: {exc}")
    return result


# --- MLB --------------------------------------------------------------------
def _dh_game_id(g) -> str:
    """``AWAY@HOME``, with a ``-G{n}`` suffix on doubleheader legs past the
    first — one shared key made the second leg overwrite the first."""
    gn = int(getattr(g, "game_number", 1) or 1)
    return f"{g.away}@{g.home}" + (f"-G{gn}" if gn > 1 else "")


def _game_state(g) -> str:
    """This game's state, from whichever field the builder actually filled.

    ``g.live`` is set by attach_live, which only the site build calls, so in
    the ingest it is always None. ``build_live_slate`` does know the state —
    it reads abstractGameState off the schedule — so the builder stamps it
    on the game as ``sched_state`` and this prefers that. Empty means
    genuinely unknown, and the caller decides what unknown implies.
    """
    live = getattr(g, "live", None)
    if live is not None and getattr(live, "state", ""):
        return str(live.state)
    return str(getattr(g, "sched_state", "") or "")


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
            "game_id": _dh_game_id(g), "home": g.home, "away": g.away,
            "home_score": None, "away_score": None, "spread": 0.0, "total": g.total,
            "roof": park.roof, "surface": park.surface,
            "temp": g.weather.temp_f, "wind": g.weather.wind_mph, "extra": g.park,
        })
    # Teams with a KNOWN not-final game on this date. MLB's game-log API
    # includes a player's in-progress game with partial stats, and one
    # ingested partial row is enough for the settler to grade tonight's
    # bet mid-game (the premature "lost" bug). Same-date log rows for
    # these teams are withheld until the team's day is truly final.
    #
    # This guard was dead for its entire life. It reads ``g.live``, which is
    # populated by ``attach_live`` — called ONLY by mlb_build.py, never by
    # the ingest. So ``st`` was always "", the `if st and ...` was always
    # False, and teams_in_play was always empty: every partial line from a
    # game in progress went straight into the history DB, where the settler
    # graded tonight's bets against it. An OVER already past its line grades
    # early, which merely looks wrong; an UNDER grades as a WIN in the
    # fourth inning and then the man doubles.
    #
    # Two changes. The state is now read from the schedule the builder
    # already fetched rather than from a field nobody set. And on TODAY's
    # slate the default flips: a game we cannot positively confirm as final
    # is treated as in play. Absence of evidence that a game is over is not
    # evidence that it is over. Past dates keep the old permissive rule —
    # those games are finished by definition, and being strict there would
    # withhold every row of an ordinary backfill.
    # The window is TODAY OR YESTERDAY, not today alone, because the two
    # dates being compared are not on the same clock. A 9pm Eastern first
    # pitch is already tomorrow in UTC, so on a UTC box the strict branch
    # switched off at the exact hour night games are in progress: the slate
    # said 08-01, date.today() said 08-02, and every partial line from the
    # games then being played took the permissive branch straight into the
    # history DB. One extra day of slack costs nothing — a backfill is of
    # dates well past, and the permissive branch is there for backfills.
    import datetime as _dt2
    today = _dt2.date.today()
    strict_from = (today - _dt2.timedelta(days=1)).isoformat()
    teams_in_play = set()
    for g in slate.games:
        st = str(_game_state(g)).lower()
        unsafe = (st != "final") if date >= strict_from else (st and st != "final")
        if unsafe:
            teams_in_play.update((g.home, g.away))
    prows = []
    # Doubleheader stat lines: a player has TWO same-date log entries and
    # both must survive — one shared game_id let the second overwrite the
    # first, which also blinded the settler's ambiguity guard. Entries
    # arrive chronologically (MLB's game log is oldest-first), so the
    # occurrence count IS the leg number.
    seen_leg: dict[tuple, int] = {}
    for p in slate.props:
        for gl in p.logs:
            # Key on the game's real date. ``gl.game`` is only a recency index —
            # it shifts as newer games arrive, so using it would file the same
            # real game under a new key on every ingest and duplicate history.
            # Fall back to the index only when the source gave us no date.
            period = gl.date or f"idx-{gl.game:04d}"
            if period == date and p.team in teams_in_play:
                continue
            leg = seen_leg.get((p.player, p.market, period), 0) + 1
            seen_leg[(p.player, p.market, period)] = leg
            log_season = int(gl.date[:4]) if gl.date else season
            prows.append({
                "sport": "mlb", "season": log_season, "period": period,
                "game_id": f"{p.player}-{period}"
                           + (f"-G{leg}" if leg > 1 else ""),
                "player": p.player,
                "team": p.team, "opponent": gl.opponent, "position": p.position,
                "home": 1 if gl.home else 0, "market": p.market, "value": gl.value,
            })
    return grows, prows


def mlb_starter_rows(slate, date: str) -> list[dict]:
    """Starting-pitcher rows from a slate's games. For a completed date the
    schedule's "probable pitcher" is the pitcher who actually started, which
    is what lets the game-model backtest be pitcher-aware. Handedness rides
    along — it's what the platoon splits join on."""
    season = int(date[:4])
    rows = []
    for g in slate.games:
        for team_ab, pitcher in (g.pitchers or {}).items():
            name = getattr(pitcher, "name", "") or ""
            if not name or name == "TBD":
                continue
            rows.append({
                "sport": "mlb", "season": season, "period": date,
                "game_id": _dh_game_id(g), "team": team_ab,
                "pitcher": name,
                "throws": getattr(pitcher, "throws", "") or "",
            })
    return rows


def mlb_umpire_rows(slate, date: str) -> list[dict]:
    """Home-plate umpire rows from a slate's games (completed dates always
    have officials in the boxscore). Feeds the umpire K/run profiles."""
    season = int(date[:4])
    return [{"sport": "mlb", "season": season, "period": date,
             "game_id": _dh_game_id(g), "umpire": g.plate_umpire}
            for g in slate.games if getattr(g, "plate_umpire", "")]


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
        gn = int(r.get("game_number") or 1)
        out.append({
            "sport": "mlb", "season": int(date[:4]), "period": date,
            # Leg 2+ of a doubleheader gets its own key — one shared id
            # meant the second final score erased the first.
            "game_id": f"{r['away']}@{r['home']}" + (f"-G{gn}" if gn > 1 else ""),
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
    from .mlb.sources.mlbstats import (fetch_schedule, parse_abandoned,
                                       parse_results)
    result = {"games": 0, "player_logs": 0, "abandoned": [], "skipped": []}
    try:
        schedule = fetch_schedule(start, end)
    except DataUnavailable as exc:
        result["skipped"].append(f"mlb results {start}..{end}: {exc}")
        return result
    rows = mlb_result_rows(parse_results(schedule))
    result["games"] = db.upsert_games(conn, rows)
    db.log_ingest(conn, "mlb", "results", f"{start}..{end}", result["games"])

    # A postponed game keeps its schedule slot, so the per-date slate ingest
    # stored it as a scoreless row — which the settle guard cannot tell from
    # a game still in progress. Result: every pick on either team that night
    # sits open forever. Clear the ones the API positively calls off; the
    # game comes back on its make-up date.
    for g in parse_abandoned(schedule):
        gn = int(g.get("game_number") or 1)
        gid = f"{g['away']}@{g['home']}" + (f"-G{gn}" if gn > 1 else "")
        if db.drop_games(conn, [{"sport": "mlb", "period": g["date"],
                                 "game_id": gid}]):
            result["abandoned"].append(
                f"{g['date']} {g['away']}@{g['home']}: {g['state']} — "
                f"cleared; picks on it will void")

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
        # limit=None: keep each player's FULL season log. The live default (15
        # most-recent games) is a form window — through an ingest it meant
        # every historical date re-stored the same 15 games as of today, so an
        # 82-day backfill grew the store by almost nothing.
        from .mlb.models import TOTAL_BASES, HITS, HOME_RUNS
        slate = build_live_slate(date, limit=None,
                                 hitter_markets=(TOTAL_BASES, HITS,
                                                 HOME_RUNS, "pa"))
    except DataUnavailable as exc:
        result["skipped"].append(f"mlb {date}: {exc}")
        return result
    grows, prows = mlb_rows_from_slate(slate, date)
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    result["starters"] = db.upsert_game_starters(conn, mlb_starter_rows(slate, date))
    result["umpires"] = db.upsert_game_umpires(conn, mlb_umpire_rows(slate, date))
    db.log_ingest(conn, "mlb", "slate", date, result["games"] + result["player_logs"])
    return result
