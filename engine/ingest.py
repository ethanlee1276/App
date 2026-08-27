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
            # THE PRICES, WHICH WERE BEING THROWN AWAY. nflverse ships the
            # closing spread odds, total odds and moneylines for every
            # game in the same row as the numbers we already keep — free,
            # already downloaded, and discarded here since this function
            # was written. `game_backtest.py nfl` reported "0 games with a
            # stored close" across four ingested seasons and told the
            # reader to spend odds-API credits harvesting what was on
            # disk.
            #
            # In `extra` rather than in new columns: the games table is
            # shared by six sports and none of the others has these, so a
            # column apiece would be four nulls on every MLB row forever.
            # Read back by engine/gamebacktest.schedule_closes.
            "extra": _prices_json(r),
        })
    return out


def _prices_json(r: dict) -> str | None:
    """The row's closing prices, compact, or None when it carries none.

    Stored as the BOOK would print them and in the same convention
    `odds_history` uses, so the backtest can read either source without
    knowing which it got: the spread is the HOME team's number (already
    how `spread` is stored above), and the pair order is (home, away)
    for a spread and (over, under) for a total.
    """
    import json as _json
    from .sources.nflverse import _f
    out = {}
    ml_h = _f(r, "home_moneyline", default=None)
    ml_a = _f(r, "away_moneyline", default=None)
    if ml_h is not None and ml_a is not None:
        out["ml"] = [int(ml_h), int(ml_a)]
    sp_h = _f(r, "home_spread_odds", default=None)
    sp_a = _f(r, "away_spread_odds", default=None)
    if sp_h is not None and sp_a is not None:
        out["spread_odds"] = [int(sp_h), int(sp_a)]
    ov = _f(r, "over_odds", default=None)
    un = _f(r, "under_odds", default=None)
    if ov is not None and un is not None:
        out["total_odds"] = [int(ov), int(un)]
    return _json.dumps(out, separators=(",", ":")) if out else None


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
    # THE SCORING COMPONENTS, added 2026-08-15 for the lineup optimiser.
    #
    # `fp_ppr` is nflverse's own PPR total and is exactly right for a PPR
    # league — but almost nobody plays default PPR. Half-PPR, TE premium
    # and six-point passing touchdowns all change which eleven men you
    # should start, and none of them can be computed from a points total.
    # They can be computed from the parts.
    #
    # Yardage was already stored, but only for the ONE position each
    # market was a prop for: `rec_yds` for wide receivers and `rush_yds`
    # for running backs (POSITION_MARKETS). That leaves a pass-catching
    # back and every tight end with no receiving yards at all, which is
    # exactly who a half-PPR setting moves. Storing them here covers all
    # four positions on the same fetch.
    "rec_yds": ("receiving_yards",),
    "rush_yds": ("rushing_yards",),
    "pass_td": ("passing_tds",),
    "pass_int": ("interceptions", "passing_interceptions"),
    # AND THE TWO TOUCHDOWN COMPONENTS, added 2026-08-15 with the Yahoo
    # adapter. Every adapter already produces `rush_td` and `rec_td` keys
    # — Sleeper by that name, ESPN as stat ids 25 and 43, Yahoo as
    # "Rushing Touchdowns" — and until now nothing consumed them: a
    # league scoring a rushing touchdown at 4 was scored at PPR's 6
    # without a word. Storing the parts is what lets that be adjusted for,
    # and lets it be REPORTED when it cannot be.
    "rush_td": ("rushing_tds",),
    "rec_td": ("receiving_tds",),
}
#: Markets that only exist for a quarterback. Writing a zero for everyone
#: else would make "he threw no touchdowns" and "he is a wide receiver"
#: the same row.
NFL_QB_ONLY = {"pass_att", "pass_td", "pass_int"}


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
            if market in NFL_QB_ONLY and pos != "QB":
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


def ingest_cfb_history(conn, seasons: list[int], id_to_abbr: dict | None = None,
                       quiet: bool = False) -> dict:
    """Past FBS results, so college football's constants can be MEASURED.

    `engine.cfb.ratings` fits the scoring baseline, the home-field edge
    and the margin/total spread from finished games and falls back to a
    prior below `MIN_GAMES`. On 2026-08-27 this database held ONE
    completed CFB game, so every college board on the site was running
    on the prior — which puts the whole sport on probation: journaled
    and graded, never staked.

    The blocker was the feed, not the model. ESPN's scoreboard answers
    "what is on today" one day at a time and is refused outright by a
    standard egress policy; `engine.sources.cfbfastr` reads whole
    finished seasons off the same raw.githubusercontent.com path the NFL
    schedules already come down. Four seasons are 3,132 FBS-vs-FBS games.

    ``id_to_abbr`` maps ESPN team ids to the abbreviations the board
    uses — pass `{meta["id"]: abbr}` built from `cfbdata.parse_teams`
    when a build has the teams feed. Left as None it reads the map a
    previous build persisted. With neither, rows are keyed ``espn:<id>``,
    which measures every constant identically (they depend on each team
    having ONE key, not on what it is called) while staying visibly
    distinct from a real abbreviation — and `remap_cfb_team_keys`
    rewrites them the first time a build does have the feed.
    """
    from .sources import cfbfastr
    if id_to_abbr is None:
        # A build that HAD the teams feed wrote the map down
        # (engine.cfbteams.remember_ids). Reading it here is what keeps a
        # later backfill from re-introducing ``espn:`` keys the board
        # cannot join, on a box that has already learned the real ones.
        from . import cfbteams
        id_to_abbr = cfbteams.load_ids() or None
    result = {"games": 0, "seasons": [], "skipped": []}
    for season in seasons:
        try:
            out = cfbfastr.fetch_season(int(season), id_to_abbr=id_to_abbr)
        except DataUnavailable as exc:
            result["skipped"].append(f"cfb schedules {season}: {exc}")
            continue
        n = db.upsert_games(conn, out["games"])
        result["games"] += n
        result["seasons"].append({"season": int(season), "games": n,
                                  "skipped": out["skipped"]})
        db.log_ingest(conn, "cfb", "results", str(season), n)
        if not quiet:
            print(f"  cfb {season}: {n} FBS games")
    return result


def cfb_games_for(conn, season: int) -> dict:
    """``{game_id: {period, home, away, home_name, away_name}}``.

    The join `engine.sources.cfbstats` resolves school names through. It
    reads the schedule rows we already ingested, so player rows can only
    ever land on a team that was playing in that game, and only for the
    games the schedule kept — FBS vs FBS with a final score.
    """
    import json as _json
    out: dict = {}
    for r in conn.execute(
            "SELECT game_id, period, home, away, home_score, away_score, extra "
            "FROM games WHERE sport='cfb' AND season=?", (int(season),)):
        try:
            extra = _json.loads(r["extra"] or "{}")
        except (ValueError, TypeError):
            extra = {}
        out[str(r["game_id"])] = {
            "period": r["period"], "home": r["home"], "away": r["away"],
            "home_name": extra.get("home_name", ""),
            "away_name": extra.get("away_name", ""),
            # The final score, which is what `cfbstats.week_modes` audits
            # the feed's touchdowns against — a week that delivers a
            # fifth of its own points as touchdowns has lost them, and
            # 2025 lost eight weeks that way. Per side as well as
            # combined: a team credited with more touchdowns than ITS
            # OWN score allows is a tighter bound than one measured
            # against both teams' points together.
            "points": (r["home_score"] or 0) + (r["away_score"] or 0),
            "home_points": r["home_score"] or 0,
            "away_points": r["away_score"] or 0,
        }
    return out


def ingest_cfb_player_history(conn, seasons: list[int],
                              quiet: bool = False) -> dict:
    """Past college PLAYER production, so the TD board has somebody to price.

    The companion to `ingest_cfb_history`, and the more urgent half.
    Results let `engine.cfb.ratings` measure a scoring baseline; player
    rows are what `engine.cfb.tds` needs to name a scorer at all. Its
    rule is that a quoted player with no ingested usage gets no pick, and
    on 2026-08-27 this database held TEN CFB player rows — so the college
    touchdown board would have shipped empty.

    Rows land ONLY for games already in the schedule, keyed exactly as
    that schedule keyed them. Backfill the results first; a player-log
    pass on an empty schedule writes nothing and says so.
    """
    from .sources import cfbstats
    result = {"rows": 0, "assets": 0, "seasons": [], "skipped": []}
    for season in seasons:
        games = cfb_games_for(conn, int(season))
        if not games:
            result["skipped"].append(
                f"cfb players {season}: no ingested games to join to — "
                f"run the results backfill for {season} first")
            continue
        try:
            roster = cfbstats.fetch_rosters(int(season))
        except DataUnavailable as exc:
            # A position and a headshot are decoration; the usage rows
            # are the point. Losing the roster costs a label, not a row.
            roster = {}
            result["skipped"].append(f"cfb rosters {season}: {exc}")
        try:
            out = cfbstats.fetch_season(int(season), games, roster=roster)
        except DataUnavailable as exc:
            result["skipped"].append(f"cfb players {season}: {exc}")
            continue
        n = db.upsert_player_logs(conn, out["rows"]) if out["rows"] else 0
        if out["assets"]:
            result["assets"] += db.upsert_player_assets(conn, out["assets"])
        result["rows"] += n
        result["seasons"].append({"season": int(season), "rows": n,
                                  "games": out["games"],
                                  "players": out["players"],
                                  "skipped": out["skipped"]})
        db.log_ingest(conn, "cfb", "player_logs", str(season), n)
        if not quiet:
            print(f"  cfb {season}: {n} player rows across {out['games']} "
                  f"games ({out['players']} player-games)")
        # A DROPPED WEEK IS A FINDING, NOT HOUSEKEEPING. The 2025 file is
        # missing its scoring plays from week 10 on, and a coverage audit
        # that refused them quietly would look exactly like a coverage
        # audit that never ran.
        for note in out["skipped"]:
            if note.startswith("week "):
                result["skipped"].append(f"cfb {season} {note}")
                if not quiet:
                    print(f"    dropped: {note}")
    return result


#: The prefix `engine.sources.cfbfastr` keys a team under when it had no
#: abbreviation to use. Deliberately a form no real abbreviation can
#: collide with — which is what makes rewriting it safe.
ESPN_KEY_PREFIX = "espn:"


def remap_cfb_team_keys(conn, id_to_abbr: dict | None = None) -> dict:
    """Rewrite backfilled ``espn:<id>`` team keys to real abbreviations.

    FOUR SEASONS OF HISTORY THE BOARD COULD NOT SEE. The CFB backfill
    runs from wherever the nightly runs, and where ESPN's teams feed is
    refused it keys every team ``espn:61`` rather than guess. The live
    board keys the same school ``UGA``. Nothing joins: `engine.cfb.tds`
    looks up a quoted player's usage under the board's key, finds
    nothing, and prices nobody — with 268,240 measured player rows in
    the table.

    So the first build that DOES have the teams feed repairs it. The map
    is ``{ESPN team id: abbreviation}``; without one this reads the map
    `engine.cfbteams` persisted from an earlier build. Returns
    ``{"games": n, "player_logs": n, "teams": n, "unmapped": [...]}`` —
    the unmapped ids are the ones still keyed ``espn:``, which is a
    finding (a school the teams feed did not carry) rather than a
    failure.

    Team is not part of either table's primary key, so this can never
    collide two rows into one.
    """
    from . import cfbteams
    mapping = {str(k): str(v) for k, v in
               (id_to_abbr or cfbteams.load_ids() or {}).items() if k and v}
    out = {"games": 0, "player_logs": 0, "teams": 0, "unmapped": []}
    if not mapping:
        return out
    present = set()
    for table, columns in (("games", ("home", "away")),
                           ("player_game_logs", ("team", "opponent"))):
        for column in columns:
            for (value,) in conn.execute(
                    f"SELECT DISTINCT {column} FROM {table} WHERE sport='cfb' "
                    f"AND {column} LIKE ?", (ESPN_KEY_PREFIX + "%",)):
                present.add(str(value))
    if not present:
        return out
    for key in sorted(present):
        abbr = mapping.get(key[len(ESPN_KEY_PREFIX):])
        if not abbr:
            out["unmapped"].append(key)
            continue
        out["teams"] += 1
        for table, columns in (("games", ("home", "away")),
                               ("player_game_logs", ("team", "opponent"))):
            for column in columns:
                cur = conn.execute(
                    f"UPDATE {table} SET {column}=? "
                    f"WHERE sport='cfb' AND {column}=?", (abbr, key))
                out["games" if table == "games" else "player_logs"] += \
                    cur.rowcount or 0
    conn.commit()
    return out


def ingest_cfb_lines(conn, seasons: list[int] | None = None,
                     quiet: bool = False) -> dict:
    """Closing spreads and totals for college football's ingested games.

    THE COLUMN THE BACKFILL LEFT NULL ON PURPOSE, filled at last.
    `engine.sources.cfbfastr` stores scores and no lines, and said so:
    writing a 0.0 would have read as a pick'em on three thousand games.
    The cost was that nothing college the site prices had ever been
    compared with the number a bettor could have taken —
    `engine.gamecal` held CFB's market haircut at the flat guess, and
    `engine.cfbtdfit` had no implied total to grade the touchdown model's
    game-script term against.

    `engine.sources.cfblines` reads them off the same mirror the
    schedules come from. Only games already in the table are touched,
    and only their ``spread`` and ``total`` columns — a game with a
    close for one market and not the other keeps the NULL on the other.
    """
    import json as _json
    from .sources import cfblines
    result = {"spread": 0, "total": 0, "games": 0, "skipped": []}
    where = "WHERE sport='cfb'"
    args: list = []
    if seasons:
        where += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = [int(s) for s in seasons]
    games = {}
    for r in conn.execute(
            f"SELECT game_id, season, period, extra FROM games {where}", args):
        try:
            extra = _json.loads(r["extra"] or "{}")
        except (ValueError, TypeError):
            extra = {}
        games[str(r["game_id"])] = {
            "home_name": extra.get("home_name", ""),
            "away_name": extra.get("away_name", ""),
            "season": r["season"], "period": r["period"],
        }
    if not games:
        result["skipped"].append(
            "cfb lines: no ingested games to attach closes to — run the "
            "results backfill first")
        return result
    try:
        out = cfblines.fetch_lines(games, seasons)
    except DataUnavailable as exc:
        result["skipped"].append(f"cfb lines: {exc}")
        return result
    for game_id, quote in out["lines"].items():
        game = games.get(game_id)
        if not game:
            continue
        for column in ("spread", "total"):
            if column not in quote:
                continue
            conn.execute(
                f"UPDATE games SET {column}=? WHERE sport='cfb' AND "
                f"season=? AND period=? AND game_id=?",
                (quote[column], game["season"], game["period"], game_id))
            result[column] += 1
        result["games"] += 1
    conn.commit()
    db.log_ingest(conn, "cfb", "closing_lines", str(seasons or "all"),
                  result["games"])
    if not quiet:
        print(f"  cfb closes: {result['spread']:,} spread(s) and "
              f"{result['total']:,} total(s) across {result['games']:,} games")
    return result
