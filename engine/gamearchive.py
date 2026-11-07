"""Any game's page, finished long ago or not — every game on every
team's schedule.

Ethan, 2026-10-30, with ESPN's Panthers–Packers final open on his Duo
(the game leaders, the scoring plays a quarter at a time, the box score,
the team stats): "one thing we need to add is being able to see game
history for each team. We should be able to go to each specific game and
see all this type of data that espn offers. So add these pages for every
sport for each team."

THE PAGE EXISTED; THE GAME DID NOT. The game page — the gamecast
(js/gamecast.js), the court (js/hoopscast.js), the park — draws one file
per game, `web/data/pbp/{league}_{event}.json`, which the live loops
write while a game is on (livescore_build.write_pbp, live_build.write_pbp)
and prune a day and a half after it ends. A schedule's earlier games had
nothing to open, so each row opened the opponent instead (more.js
teamGameDoor: "a final from an earlier week ... has no game page yet").

This builds the same document for any game, from the same feed by the
same builders — ESPN's summary through `livescore_build.pbp_doc` for
football, basketball and hockey, MLB's own feed through
`live_build.mlb_doc` for baseball — when a reader opens it. A final
cannot change, so its document is kept (ARCHIVE_DIR) and the next reader
costs nothing. Every line on the page is still the builders' composition
from the feed's numbers; nothing here reads a word the builders do not
(engine/sources/espnplays, "WHAT IS NEVER READ").

FINDING THE GAME. A schedule row comes from our games table, which keeps
each source's own id (nflverse's, CFBD's, "AWAY@HOME" for the daily
sports), never ESPN's. So a game is found the way the live board finds
one: the league's scoreboard for that day, each side resolved into the
board's own vocabulary (`livescores._side_key`, MLB's team ids), matched
on home and away. A day whose games are over is kept as long as a final.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
from pathlib import Path

from .sources.fetch import CACHE_DIR, DEFAULT_AGENT, fetch_text

#: The leagues ESPN's summary serves (livescores.ESPN_SCOREBOARD).
ESPN_LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl")
#: Baseball reads MLB's own feed, as its live page does.
LEAGUES = ESPN_LEAGUES + ("mlb",)

#: Finished games' documents, one gzipped file each, kept for good — a
#: final does not change. Capped (ARCHIVE_MAX), the longest unread first to
#: go. A football or basketball game's document is a few hundred kilobytes
#: of JSON and a tenth of that gzipped: the whole shelf is tens of
#: megabytes, not the half a gigabyte it would be as text. In a folder of
#: its own, which neither cache prune walks into (they read the top level).
ARCHIVE_DIR = CACHE_DIR / "gamearchive"
ARCHIVE_MAX = 4000

#: A scoreboard for a day whose games are all over: kept a month (the
#: cache prune has its own say after that). Today's and yesterday's are
#: re-read every couple of minutes, since a game on them may still be on.
PAST_DAY_TTL = 30 * 86400
OPEN_TTL = 120
#: A game's own feed, for a game not over (or not kept yet): five minutes.
FEED_TTL = 300

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_EVENT = re.compile(r"\d{1,12}")
#: A team key as the boards write it: "GB", "LAK", "Ohio State", and the
#: college fallback "espn:2390".
_TEAM = re.compile(r"[A-Za-z0-9 .&'():/-]{1,48}")


class BadRequest(ValueError):
    """A question this cannot answer as asked — an unknown league, a day
    that is not a day. The route says 400 and the page says why."""


def _et_today() -> _dt.date:
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:                                        # noqa: BLE001
        return _dt.date.today()


def _ttl_for(day: _dt.date) -> int:
    return PAST_DAY_TTL if day < _et_today() - _dt.timedelta(days=1) else OPEN_TTL


def _et_day(stamp) -> str:
    """ESPN's ISO kickoff ("2026-10-26T17:00Z") as the US Eastern date the
    schedules file games under; "" when it will not read."""
    s = str(stamp or "").strip()
    if not s:
        return ""
    try:
        when = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if when.tzinfo is None:
            return when.date().isoformat()
        from zoneinfo import ZoneInfo
        return when.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                        # noqa: BLE001
        return s[:10] if _DATE.fullmatch(s[:10]) else ""


def _side(league: str, team) -> str:
    """One club's code in the league's own spelling (engine.divisions): the
    schedules hold ESPN's ("NY" for the Liberty and the Knicks, "LA" for the
    Kings) where the scoreboard's rows hold the board's (NYL, NYK, LAK), and
    a straight comparison missed every game of those clubs."""
    from .divisions import canonical
    return canonical(league, str(team or ""))


def _game_number(game_id: str) -> int:
    """A doubleheader's leg from our own id ("NYY@BOS-G2" is the second)."""
    m = re.search(r"-G(\d+)$", str(game_id or ""))
    return int(m.group(1)) if m else 1


# ---------------------------------------------------------------- the day
def day_games(league: str, day: _dt.date) -> list[dict]:
    """The league's games on one day, each as the live board's own row —
    ``{event_id, home, away, ...}`` with the sides in the board's
    vocabulary. Raises when the feed does not answer (the caller decides
    what an unanswered day means)."""
    if league == "mlb":
        return _mlb_day(day)
    from .sources.livescores import ESPN_SCOREBOARD, SCOREBOARD_QUERY, parse_espn_rows
    query = SCOREBOARD_QUERY.get(league, "")
    url = (ESPN_SCOREBOARD[league] + (query + "&" if query else "?")
           + "dates=" + day.strftime("%Y%m%d"))
    text = fetch_text(url, f"espn_{league}_day_{day:%Y%m%d}.json",
                      ttl=_ttl_for(day), user_agent=DEFAULT_AGENT)
    return parse_espn_rows(json.loads(text), league)


def _mlb_rows(raw: dict) -> list[dict]:
    """MLB's schedule payload as rows, sides through MLB's team ids — the
    read live_build.build makes — each with its doubleheader leg and the
    status `live_build._row` takes."""
    from .mlb.sources.live import TEAM_ID_ABBR, parse_live
    board = parse_live(raw)
    out: list[dict] = []
    for block in raw.get("dates", []) or []:
        for g in block.get("games", []) or []:
            pk = g.get("gamePk")
            st = board.get(int(pk)) if pk else None
            teams = g.get("teams") or {}
            home = (teams.get("home") or {}).get("team") or {}
            away = (teams.get("away") or {}).get("team") or {}
            home_ab = TEAM_ID_ABBR.get(home.get("id"), home.get("abbreviation", ""))
            away_ab = TEAM_ID_ABBR.get(away.get("id"), away.get("abbreviation", ""))
            if not pk or not st or not home_ab or not away_ab:
                continue
            out.append({"event_id": str(pk), "game_pk": int(pk), "home": home_ab,
                        "away": away_ab, "game_number": int(g.get("gameNumber") or 1),
                        "date": str(g.get("officialDate") or block.get("date") or ""),
                        "status": st})
    return out


def _mlb_day(day: _dt.date) -> list[dict]:
    from .mlb.sources.live import STATS_BASE, _get_json
    raw = _get_json(f"{STATS_BASE}/schedule?sportId=1&date={day.isoformat()}&hydrate=linescore",
                    f"mlb_day_{day.isoformat()}.json", ttl=_ttl_for(day))
    return _mlb_rows(raw)


def _mlb_game(pk: int) -> dict | None:
    """One MLB game's row by its own id, for a page opened by link."""
    from .mlb.sources.live import STATS_BASE, _get_json
    raw = _get_json(f"{STATS_BASE}/schedule?sportId=1&gamePk={pk}&hydrate=linescore",
                    f"mlb_game_{pk}.json", ttl=FEED_TTL)
    rows = [r for r in _mlb_rows(raw) if r["game_pk"] == pk]
    return rows[0] if rows else None


def find(league: str, day: _dt.date, home: str, away: str, game_id: str = "") -> dict | None:
    """The game on ``day`` between ``home`` and ``away``, as its day's row.

    THE DAY ASKED FOR FIRST, AND ITS ANSWER IS THE ANSWER. A neighbouring
    day is read only when that day answered and the game is not on it — a
    late kick filed on the other side of midnight — and never when it did
    not answer, which would be a guess. Baseball never looks next door: a
    series plays the same two teams three days running, so the next day's
    game is a different game, not this one filed late. A neutral site may
    list the two the other way round; that is matched on the day itself.
    """
    want = _game_number(game_id)
    home, away = _side(league, home), _side(league, away)
    one_day = _dt.timedelta(days=1)
    for i, d in enumerate((day, day - one_day, day + one_day)):
        try:
            rows = day_games(league, d)
        except Exception:                                    # noqa: BLE001
            if i == 0:
                raise
            continue
        hits = [r for r in rows if _side(league, r.get("home")) == home and _side(league, r.get("away")) == away]
        if not hits and i == 0:
            hits = [r for r in rows if _side(league, r.get("home")) == away and _side(league, r.get("away")) == home]
        if hits:
            if len(hits) > 1:
                hits.sort(key=lambda r: r.get("game_number") or 1)
                return next((r for r in hits if (r.get("game_number") or 1) == want), hits[0])
            return hits[0]
        if league == "mlb":
            return None
    return None


# ---------------------------------------------------------- the document
def _keep(path: Path, doc: dict) -> None:
    """Write a final's document beside the others, atomically, and hold
    the shelf to ARCHIVE_MAX by dropping the longest unread (a read touches
    its file: event_doc)."""
    try:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(gzip.compress(json.dumps(doc).encode("utf-8"), compresslevel=6))
        os.replace(tmp, path)
        files = list(ARCHIVE_DIR.glob("*.json.gz"))
        if len(files) > ARCHIVE_MAX:
            files.sort(key=lambda p: p.stat().st_mtime)
            for old in files[:len(files) - int(ARCHIVE_MAX * 0.9)]:
                old.unlink(missing_ok=True)
    except OSError:
        pass                          # a page that cannot be kept is still served


def _espn_doc(league: str, event: str) -> dict | None:
    """The game's summary through the live page's own builder."""
    import livescore_build as lb
    from .sources import espnplays
    from .sources.livescores import parse_espn_rows
    payload = espnplays.fetch_summary(league, event, ttl=FEED_TTL)
    hdr = (payload or {}).get("header") or {}
    comps = [c for c in (hdr.get("competitions") or []) if isinstance(c, dict)]
    if not comps:
        return None
    comp = comps[0]
    # THE SUMMARY'S HEADER IS THE SCOREBOARD'S EVENT, so the live board's
    # own parser reads it: the sides in the board's vocabulary, the score,
    # the state — and nothing a second reading could get differently.
    rows = parse_espn_rows({"events": [{"id": str(hdr.get("id") or event), "date": comp.get("date", ""),
                                        "competitions": comps, "status": comp.get("status") or {}}]}, league)
    if not rows:
        return None
    g = lb._row(rows[0], league)
    sides = {str(g.get("home_id") or ""): g["home"], str(g.get("away_id") or ""): g["away"]}
    sides.pop("", None)
    doc = lb.pbp_doc(league, g, payload, sides=sides)
    doc["date"] = _et_day(comp.get("date"))
    return doc


def _mlb_doc(event: str, row: dict | None = None) -> dict | None:
    """The game's play-by-play through the baseball page's own builder."""
    import live_build as lvb
    from . import playmoments
    from .mlb.sources.pbp import fetch_live_playbyplay, fetch_live_win_probability, recent_plays
    pk = int(event)
    row = row if row and row.get("game_pk") == pk else _mlb_game(pk)
    if not row:
        return None
    g = lvb._row(pk, row["status"])
    g["home"], g["away"] = row["home"], row["away"]
    payload = fetch_live_playbyplay(pk, ttl=FEED_TTL)
    every = recent_plays(payload, 0)
    try:
        chances = playmoments.mlb_win_chances(fetch_live_win_probability(pk, ttl=FEED_TTL))
    except Exception:                                        # noqa: BLE001
        chances = {}
    try:
        playmoments.enrich(every, "mlb", chances, key=lambda r: r.get("at_bat"))
    except Exception:                                        # noqa: BLE001
        pass
    doc = lvb.mlb_doc(g, payload, every, chances=chances)
    doc["date"] = row.get("date") or ""
    return doc


def event_doc(league: str, event: str, row: dict | None = None) -> dict | None:
    """One game's page document by the feed's own id: the kept copy of a
    final, or built now (and kept, once final)."""
    path = ARCHIVE_DIR / f"{league}_{event}.json.gz"
    try:
        kept = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        if isinstance(kept, dict) and kept.get("event_id"):
            try:
                os.utime(path)                  # read: the last to be dropped
            except OSError:
                pass
            return kept
    except (OSError, ValueError, EOFError):
        pass
    doc = _mlb_doc(event, row) if league == "mlb" else _espn_doc(league, event)
    if not doc:
        return None
    doc["archive"] = True
    if (doc.get("live") or {}).get("state") == "final":
        _keep(path, doc)
    return doc


def game(league: str, event: str = "", date: str = "", home: str = "",
         away: str = "", game_id: str = "") -> dict | None:
    """The page for a game, by the feed's id or by its day and its two
    sides. None when no such game is on the feed; BadRequest when the
    question is malformed; the feed's own error when it does not answer."""
    league = str(league or "").strip().lower()
    if league not in LEAGUES:
        raise BadRequest("unknown league")
    event = str(event or "").strip()
    if event:
        if not _EVENT.fullmatch(event):
            raise BadRequest("an event is the feed's own number")
        return event_doc(league, event)
    date = str(date or "").strip()[:10]
    if not _DATE.fullmatch(date):
        raise BadRequest("a game is asked for by its day")
    home, away = str(home or "").strip(), str(away or "").strip()
    if not (_TEAM.fullmatch(home) and _TEAM.fullmatch(away)) or home == away:
        raise BadRequest("both sides are needed")
    try:
        day = _dt.date.fromisoformat(date)
    except ValueError:
        raise BadRequest("a game is asked for by its day") from None
    # THE SCHEDULE'S OWN ID WHEN IT IS THE FEED'S (college, the NBA and the
    # WNBA store ESPN's event number): the game itself, no day to search.
    # Taken only when the page it gives is these two sides; anything else
    # — a feed that does not know the number, another game — and the day
    # is searched as for every other league.
    game_id = str(game_id or "").strip()
    if league in ESPN_LEAGUES and _EVENT.fullmatch(game_id):
        try:
            doc = event_doc(league, game_id)
        except Exception:                                    # noqa: BLE001
            doc = None
        if doc and {_side(league, doc.get("home")), _side(league, doc.get("away"))} \
                == {_side(league, home), _side(league, away)}:
            return doc
    row = find(league, day, home, away, game_id)
    if not row:
        return None
    return event_doc(league, str(row["event_id"]), row=row)
