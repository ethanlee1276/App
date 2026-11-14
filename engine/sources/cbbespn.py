"""Men's college basketball from ESPN — a league binding over :mod:`espnhoops`.

Ethan, 2026-11-13: "we need to add college basketball ... look at all the
tools and resources and data points we use for NBA, and obviously put that
towards college basketball." The NBA and the WNBA already read one parser
and one day ingest under two league slugs; college is the third slug on the
same module, so a box score is read the same way in all three and a fix to
one is a fix to all of them.

What differs is in `espnhoops`, written down there once:

  * the scoreboard asks for Division I (``groups=50``) and a page that holds
    a Saturday (`SCOREBOARD_QUERY`);
  * regulation is two halves (`REG_PERIODS`);
  * a school's code is ESPN's only where it is unique — Division I — and a
    small school a Division I team hosts in November is ``espn:{id}``
    (`team_key`).

The league's season runs November to April (`engine.seasons`), labelled by
the year it starts, like the NBA's.
"""

from __future__ import annotations

from .espnhoops import (          # noqa: F401
    LEAGUES, ROOT, STAT_MAP, parse_summary,
)
from . import espnhoops as _h

LEAGUE = "cbb"


def parse_scoreboard(payload: dict) -> list[dict]:
    return _h.parse_scoreboard(payload, league=LEAGUE)


def fetch_scoreboard(date: str, ttl: int | None = None) -> dict:
    """``ttl=None`` lets the date decide (`espnhoops.fetch_scoreboard`)."""
    return _h.fetch_scoreboard(date, ttl=ttl, league=LEAGUE)


def fetch_summary(game_id: str, ttl: int = 30 * 24 * 3600) -> dict:
    return _h.fetch_summary(game_id, ttl=ttl, league=LEAGUE)


def load_day(date: str, ttl: int | None = None) -> list[dict]:
    return _h.load_day(date, ttl=ttl, league=LEAGUE)


def ingest_day(conn, date: str, scores_only: bool = False) -> dict:
    return _h.ingest_day(conn, date, league=LEAGUE, scores_only=scores_only)


def fetch_schedule(ttl: int = 21600) -> dict:
    return _h.fetch_schedule(ttl=ttl)


def parse_schedule_day(_schedule: dict, date: str) -> list[dict]:
    return _h.parse_schedule_day(_schedule, date, league=LEAGUE)


def teams_from_games(games: list[dict]) -> dict:
    """``{code: {name, nick, loc, short, abbr, primary, secondary, logo,
    conf, id, rank}}`` for the teams in ``games`` (the board's table, the shape
    `web/js/teams_*.js` carries for the pro leagues). College's 365 schools
    are not a file in the repo: like college football's, they ride in the
    board, built from the scoreboard that named them."""
    out: dict = {}
    for g in games or []:
        for side in ("home", "away"):
            code = g.get(side)
            if not code:
                continue
            info = dict(g.get(f"{side}_info") or {})
            row = {
                "name": info.get("name") or g.get(f"{side}_name") or code,
                "nick": info.get("nick") or "",
                "loc": info.get("loc") or "",
                "short": info.get("short") or "",
                "abbr": info.get("abbr") or (code if not str(code).startswith("espn:") else ""),
                "primary": info.get("primary") or "",
                "secondary": info.get("secondary") or "",
                "logo": info.get("logo") or "",
                "conf": g.get(f"{side}_conf") or "",
                "id": str(g.get(f"{side}_id") or ""),
            }
            rank = g.get(f"{side}_rank")
            if rank:
                row["rank"] = rank
            out[code] = row
    return out


#: What `probe` asks ESPN, each a URL this league's code reads. Written
#: because the sandbox this was built in cannot reach ESPN (403 at its
#: proxy); one run on the box replaces every guess below with a fact.
PROBE_PATHS = (
    ("Division I scoreboard", "scoreboard?dates={day}&groups=50&limit=500"),
    ("Injuries", "injuries"),
    ("Rankings", "rankings"),
    ("News", "news?limit=5"),
)


def probe(date: str = "", fetch=None) -> list[dict]:
    """What every college basketball endpoint we read ACTUALLY returns.

    ``date`` defaults to last Saturday (a full slate). The scoreboard row
    says how many games came back — ESPN cut college football's answer at
    25 whatever ``limit`` said (`cfbdata.SCOREBOARD_CUT_AT`), and a
    Saturday of college basketball is 140-odd games, so 25 here would be
    the same cut — and the first game's summary and both its teams'
    rosters are asked for too, so the box score, the play list, the
    headshots and the roster path are all seen. ``fetch(url) -> (status,
    text)`` for tests."""
    import datetime as _d
    import json as _json
    import urllib.request

    if not date:
        today = _d.date.today()
        date = (today - _d.timedelta(days=(today.weekday() - 5) % 7 or 7)).isoformat()
    day = date.replace("-", "")
    base = LEAGUES[LEAGUE]

    def _get(url):
        if fetch is not None:
            return fetch(url)
        req = urllib.request.Request(url)          # no User-Agent: ESPN 403s a custom one
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")

    out: list[dict] = []
    first: dict = {}

    def _row(label, url, read=None):
        row = {"label": label, "url": url}
        try:
            status, text = _get(url)
            row["status"], row["bytes"] = status, len(text)
            try:
                data = _json.loads(text)
            except ValueError:
                row["json"] = False
                row["head"] = text.strip()[:70].replace("\n", " ")
                out.append(row)
                return None
            row["json"] = True
            row["top_keys"] = sorted(data)[:6] if isinstance(data, dict) else "list"
            if read:
                row["read"] = read(data)
            out.append(row)
            return data
        except Exception as exc:                               # noqa: BLE001
            row["status"], row["error"] = "error", str(exc)[:90]
            out.append(row)
            return None

    for label, path in PROBE_PATHS:
        def _read(data, label=label):
            if label.startswith("Division I"):
                games = parse_scoreboard(data)
                if games:
                    first.update(games[0])
                return (f"{len(data.get('events') or [])} events, {len(games)} parsed; "
                        f"{sum(1 for g in games if g.get('home_rank') or g.get('away_rank'))} "
                        f"with a ranked team")
            if label == "Injuries":
                teams = data.get("injuries") or []
                return f"{len(teams)} team block(s)"
            if label == "Rankings":
                polls = data.get("rankings") or []
                return ", ".join(str(p.get("name") or p.get("type") or "?") for p in polls[:3])
            return ""
        _row(label, f"{base}/{path.format(day=day)}", _read)

    if first.get("game_id"):
        def _sread(data):
            box = data.get("boxscore") or {}
            players = sum(len(b.get("statistics") or []) for b in box.get("players") or [])
            rows = parse_summary(data)
            shots = sum(1 for r in rows if r.get("headshot"))
            return (f"{len(data.get('plays') or [])} plays, {len(rows)} player rows "
                    f"({shots} with a headshot), {players} stat block(s)")
        _row(f"Summary of {first.get('away')} @ {first.get('home')}",
             f"{base}/summary?event={first['game_id']}", _sread)
        for side in ("home", "away"):
            tid = first.get(f"{side}_id")
            if not tid:
                continue

            def _rread(data):
                from .espnrosters import parse_roster
                people = parse_roster(data)
                return (f"{len(people)} players, "
                        f"{sum(1 for p in people if p.get('headshot'))} with a headshot")
            _row(f"Roster of {first.get(side)} (team {tid})", f"{base}/teams/{tid}/roster", _rread)
    from .leaguestandings import ESPN_SEASON_SHIFT, parse_espn
    from ..seasons import season_of
    yr = season_of(LEAGUE, date) + ESPN_SEASON_SHIFT.get(LEAGUE, 0)

    def _stread(data):
        rows = parse_espn(data, groups=True)
        return (f"{len(rows)} teams in "
                f"{len({r.get('group') for r in rows if r.get('group')})} conference table(s)")
    _row("Standings (regular season)",
         f"https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/"
         f"standings?season={yr}&seasontype=2", _stread)
    return out
