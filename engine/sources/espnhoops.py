"""NBA and WNBA from ESPN's public API — including the history.

The original WNBA source pointed at ``cdn.wnba.com`` on the theory that the
league runs the same stack as the NBA and would therefore publish the same
JSON at the same paths. That was a guess made without a way to verify it,
and on Ethan's machine it returned something that wasn't JSON for every
date in the season.

This module is the answer that does not require a guess. ESPN's site API
already feeds NFL live scores and the entire college football board in
this repo, in exactly this shape, against endpoints that demonstrably
work:

    /apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD
    /apis/site/v2/sports/basketball/wnba/summary?event={id}

The scoreboard gives the day's games and finals; the summary gives the box
score. Both are keyless.

**The box-score parse reads by column NAME, never by position.** ESPN
returns a ``names`` array alongside each athlete's ``stats`` array, and
the order of those columns is not a promise anyone made us. Indexing by
position would work until the day a column moved, and the failure would
be silent — minutes quietly read as rebounds, and a board full of
confident nonsense. Mapping by name costs nothing and cannot drift.
"""

from __future__ import annotations

from .fetch import DEFAULT_AGENT, fetch_json, DataUnavailable

ROOT = "https://site.api.espn.com/apis/site/v2/sports"

# The only thing that differs between the two basketball leagues is the
# path. Keeping them in one module rather than two is the point: a second
# copy of a box-score parser drifts, and the first symptom would be one
# league quietly missing a stat the other has.
LEAGUES = {
    "nba": f"{ROOT}/basketball/nba",
    "wnba": f"{ROOT}/basketball/wnba",
}

BASE = LEAGUES["wnba"]
SCOREBOARD = BASE + "/scoreboard"
SUMMARY = BASE + "/summary"


def _base(league: str) -> str:
    return LEAGUES.get(league, BASE)

# ESPN's box-score column names → our market keys. Anything not listed is
# ignored rather than guessed at.
STAT_MAP = {"MIN": "min", "PTS": "pts", "REB": "reb", "AST": "ast",
            "3PT": "fg3m"}


def _season_of(date: str, league: str) -> int:
    """The season a date belongs to, labelled by the year it STARTED.

    Lives in ``engine.seasons`` now — the ingest that writes the label and
    the queries that read it must never disagree about which year a March
    game belongs to.
    """
    from ..seasons import season_of
    return season_of(league, date)


def _num(raw) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def parse_scoreboard(payload: dict) -> list[dict]:
    """One day's games: ids, teams, finals."""
    out: list[dict] = []
    for ev in payload.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        home = away = None
        for c in comp.get("competitors", []) or []:
            # The display name rides along with the abbreviation. The odds
            # feed names teams in full ("Los Angeles Sparks") and this feed
            # names them by ESPN's own short code, so something has to hold
            # both halves of that join — and a hand-written table of the
            # league's abbreviations is the thing that rots every time a
            # team is added or renamed.
            t = c.get("team") or {}
            side = {"abbr": (t.get("abbreviation") or "").strip(),
                    "name": (t.get("displayName") or t.get("name") or "").strip(),
                    "score": _num(c.get("score"))}
            if c.get("homeAway") == "home":
                home = side
            else:
                away = side
        if not home or not away or not home["abbr"] or not away["abbr"]:
            continue
        status = (comp.get("status") or ev.get("status") or {})
        stype = status.get("type") or {}
        completed = bool(stype.get("completed"))
        # IN PROGRESS WAS NOT REPRESENTED AT ALL. This read `completed`
        # and nothing else, so the only two states a hoops game could
        # ever have here were "finished" and "not finished" — a game
        # actually being played was indistinguishable from one that had
        # not tipped. `cfbdata.parse_scoreboard` has carried the three
        # states since it was written; this one never did, and that is
        # why a WNBA board could not show a live game no matter how
        # fresh the fetch was (reported 2026-08-30, 8:56 PM, two games
        # from 3:00 and 5:00 still reading "lines post closer to
        # tip-off").
        state = {"pre": "scheduled", "in": "live",
                 "post": "final"}.get(stype.get("state", "pre"), "scheduled")
        out.append({
            "game_id": str(ev.get("id") or ""),
            "home": home["abbr"], "away": away["abbr"],
            "home_name": home["name"], "away_name": away["name"],
            # UNCHANGED, and deliberately: settlement reads these and a
            # third-quarter score written here would grade a bet against
            # a game still being played.
            "home_score": home["score"] if completed else None,
            "away_score": away["score"] if completed else None,
            # The running score, carried separately for the same reason.
            "live_home_score": home["score"],
            "live_away_score": away["score"],
            "state": state,
            "period": status.get("period"),
            "clock": stype.get("shortDetail") or status.get("displayClock") or "",
            "completed": completed,
            "kickoff": ev.get("date", ""),
        })
    return out


def parse_summary(payload: dict) -> list[dict]:
    """A game summary → per-player stat rows.

    Columns are matched by NAME. ESPN gives a ``names``/``keys`` array per
    team block and an aligned ``stats`` array per athlete; reading by
    position would silently mis-assign every stat the day a column moves.
    """
    rows: list[dict] = []
    box = payload.get("boxscore") or {}
    for team_block in box.get("players", []) or []:
        team = ((team_block.get("team") or {}).get("abbreviation") or "").strip()
        for group in team_block.get("statistics", []) or []:
            names = [str(n).upper() for n in (group.get("names") or [])]
            if not names:
                continue
            for ath in group.get("athletes", []) or []:
                info = ath.get("athlete") or {}
                player = (info.get("displayName") or "").strip()
                if not player:
                    continue
                stats = ath.get("stats") or []
                vals: dict = {}
                for i, col in enumerate(names):
                    if col not in STAT_MAP or i >= len(stats):
                        continue
                    raw = stats[i]
                    if col == "MIN":
                        vals["min"] = _num(raw) or 0.0
                    elif col == "3PT":
                        # "5-11" → makes. Attempts are the denominator and
                        # are not a market we price.
                        made = str(raw).split("-")[0]
                        vals["fg3m"] = _num(made) or 0.0
                    else:
                        v = _num(raw)
                        if v is not None:
                            vals[STAT_MAP[col]] = v
                if not vals:
                    continue
                # Identity, which this parser used to read and throw away.
                # `info` already holds the athlete id and, on most
                # payloads, the photo URL — so a face for the NBA and WNBA
                # boards costs one dict lookup rather than a second feed.
                #
                # The URL is TAKEN, not reconstructed from the id. Building
                # `.../headshots/{league}/players/full/{id}.png` by hand is
                # the same class of guess that produced `limit=400` and the
                # User-Agent 403; a href the feed handed us cannot be wrong
                # about its own shape. The id is kept anyway, because it is
                # the only stable handle if a payload ever omits the href.
                shot = (info.get("headshot") or {})
                rows.append({
                    "player": player, "team": team,
                    "position": "S" if ath.get("starter") else "B",
                    "stats": vals,
                    "espn_id": str(info.get("id") or ""),
                    "headshot": (shot.get("href") if isinstance(shot, dict)
                                 else str(shot or "")) or "",
                })
    return rows


#: A day that has not finished yet. The scoreboard carries the STATE of
#: every game — scheduled, in progress, final — and the score with it, so
#: on today's date it is a live feed and must be read like one. Five
#: minutes is what `cfbdata.fetch_scoreboard` uses for the same payload.
LIVE_TTL = 300


def _is_settled(date: str) -> bool:
    """Is this date over, so its scoreboard can never change again?

    The slate day rolls at 5 AM, not midnight (see `launch._slate_date`):
    a game that tips at 10 PM Pacific is still last night's, and treating
    it as settled at 00:01 would freeze it mid-fourth-quarter.
    """
    import datetime as _d
    try:
        asked = _d.date.fromisoformat(date)
    except ValueError:
        return False
    today = (_d.datetime.now() - _d.timedelta(hours=5)).date()
    return asked < today


def fetch_scoreboard(date: str, ttl: int | None = None,
                     league: str = "wnba") -> dict:
    """One day's board. ``ttl`` defaults to the day's own lifetime.

    SIX HOURS WAS THE DEFAULT AND IT FROZE THE LIVE BOARD. Reported
    2026-08-30 at 8:56 PM: two WNBA games that had tipped at 3:00 and
    5:00 still reading "lines post closer to tip-off", hours after they
    finished. The board itself was six minutes old — it was the
    SCOREBOARD UNDER it that was six hours old, so every game's state
    was a snapshot from before either had started.

    The old default's reasoning was sound and applied to the wrong days:
    "a finished day never changes, so history caches effectively forever
    and a re-run of a six-season backfill costs nothing." True of a
    finished day. Today is not one, and the same constant served both.

    So the lifetime now follows whether the day can still change. A
    backfill over past seasons keeps its month-long cache and costs
    nothing; today is read every five minutes like the live feed it is.
    """
    day = date.replace("-", "")
    if ttl is None:
        ttl = 30 * 24 * 3600 if _is_settled(date) else LIVE_TTL
    return fetch_json(f"{_base(league)}/scoreboard?dates={day}&limit=60",
                      f"espn_{league}_{day}.json", ttl=ttl,
                      user_agent=DEFAULT_AGENT)


def fetch_summary(game_id: str, ttl: int = 30 * 24 * 3600,
                  league: str = "wnba") -> dict:
    return fetch_json(f"{_base(league)}/summary?event={game_id}",
                      f"espn_{league}_box_{game_id}.json", ttl=ttl,
                      user_agent=DEFAULT_AGENT)


def load_day(date: str, ttl: int | None = None,
             league: str = "wnba") -> list[dict]:
    """``ttl=None`` lets the date decide — see `fetch_scoreboard`."""
    return parse_scoreboard(fetch_scoreboard(date, ttl=ttl, league=league))


def ingest_day(conn, date: str, league: str = "wnba",
               scores_only: bool = False) -> dict:
    """Store one date's finals and player logs.

    ``scores_only`` skips the per-game box scores. That is the difference
    between a six-season backfill taking an afternoon and taking a week,
    and final scores alone already unlock team ratings, the margin/total
    variance fits and settlement — everything except prop backtests.
    """
    from .. import db

    result: dict = {"games": 0, "player_logs": 0, "assets": 0, "skipped": []}
    arows: list[dict] = []
    try:
        games = load_day(date, league=league)
    except DataUnavailable as exc:
        result["skipped"].append(f"{league} scoreboard {date}: {exc}")
        return result

    grows, prows = [], []
    for g in games:
        grows.append({
            "sport": league, "season": _season_of(date, league), "period": date,
            "game_id": g["game_id"], "home": g["home"], "away": g["away"],
            "home_score": g["home_score"], "away_score": g["away_score"],
            "spread": 0.0, "total": None, "roof": "indoor",
            "surface": "hardwood", "temp": None, "wind": None, "extra": None,
        })
        if not g["completed"] or scores_only:
            continue                       # nothing to log from an unplayed game
        try:
            summary = fetch_summary(g["game_id"], league=league)
        except DataUnavailable as exc:
            result["skipped"].append(f"{league} box {g['game_id']}: {exc}")
            continue
        opp = {g["home"]: g["away"], g["away"]: g["home"]}
        for row in parse_summary(summary):
            # Identity once per player per game, not once per market — the
            # same person appears in this loop for points, rebounds and
            # assists, and an id does not vary between them.
            if row.get("espn_id") or row.get("headshot"):
                arows.append({"sport": league, "player": row["player"],
                              "espn_id": row.get("espn_id", ""),
                              "headshot": row.get("headshot", ""),
                              "seen": date})
            for market, value in row["stats"].items():
                prows.append({
                    "sport": league, "season": _season_of(date, league),
                    "period": date,
                    "game_id": g["game_id"], "player": row["player"],
                    "team": row["team"], "opponent": opp.get(row["team"], ""),
                    "position": row["position"],
                    "home": 1 if row["team"] == g["home"] else 0,
                    "market": market, "value": value,
                })
    result["games"] = db.upsert_games(conn, grows)
    result["player_logs"] = db.upsert_player_logs(conn, prows)
    result["assets"] = db.upsert_player_assets(conn, arows)
    return result


# --- drop-in shims for the shared basketball build ---------------------------
# nba_build calls ``parse_schedule_day(fetch_schedule(), date)``, a shape
# that assumes a single season-wide schedule file. ESPN is per-day, so
# ``fetch_schedule`` has nothing to hand over and the day fetch happens
# inside ``parse_schedule_day``. The odd-looking signature is deliberate:
# it keeps ONE call site in nba_build for both leagues, and a second code
# path for the WNBA board is exactly how the two would drift apart.
def fetch_schedule(ttl: int = 21600) -> dict:
    return {}


def parse_schedule_day(_schedule: dict, date: str,
                       league: str = "wnba") -> list[dict]:
    """One day's games in the shape the shared build expects."""
    try:
        games = load_day(date, league=league)
    except DataUnavailable:
        return []
    # THE STATE TRAVELS. This mapping listed six fields and dropped the
    # rest, so even once `parse_scoreboard` knew a game was live the
    # board never heard about it — the reason has to reach the page, not
    # merely exist upstream of it.
    return [{"game_id": g["game_id"], "home": g["home"], "away": g["away"],
             "home_name": g.get("home_name", ""),
             "away_name": g.get("away_name", ""),
             "kickoff": g.get("kickoff", ""),
             "home_score": g["home_score"], "away_score": g["away_score"],
             "live_home_score": g.get("live_home_score"),
             "live_away_score": g.get("live_away_score"),
             "state": g.get("state", "scheduled"),
             "period": g.get("period"), "clock": g.get("clock", ""),
             "completed": g.get("completed", False)}
            for g in games]
