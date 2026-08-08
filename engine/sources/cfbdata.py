"""College football from ESPN's public scoreboard API.

    https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard

Keyless, free, and — unusually for this project — it carries almost the
whole model in one payload. :mod:`engine.cfb.model` decides everything from
*how hard the market is looking at this game*, and the four inputs that
question needs are all here: each team's conference, its curated ranking,
the kickoff time, and the day of the week.

Three things in here are load-bearing and easy to get wrong:

**The weekday must be Eastern, not UTC.** A Saturday 8pm ET kickoff is
Sunday 00:00 UTC, and a Wednesday MACtion game is Thursday in UTC. Read
naively, every marquee night game would be stamped a weeknight and handed
the low-attention haircut — the model would claim a soft number on the
most-watched window of the week. So the conversion runs US DST rules and
is tested against exactly those two cases.

**An unknown conference is not a soft conference.** ESPN identifies a
team's league by a numeric ``conferenceId``. The built-in table below is
overridden by the live groups feed when it is reachable, and when a name
can't be resolved the game goes out with an empty conference — which
``attention_tier`` deliberately reads as *standard*, never as "nobody is
watching this."

**134 teams don't belong in a checked-in file.** Colours, nicknames and
abbreviations come off the teams feed at build time and ride in the
payload, so the board renders real identities without a hand-maintained
list going stale every time a school rebrands or the FBS expands.

Pure parsers, unit-tested without network; the fetch wrappers cache and
degrade to :class:`DataUnavailable` like every other source here.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import unicodedata

from .fetch import DEFAULT_AGENT, fetch_json, DataUnavailable

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
SCOREBOARD = BASE + "/scoreboard"
TEAMS = BASE + "/teams"
GROUPS = BASE + "/groups"

FBS_GROUP = "80"          # ESPN's group id for Division I-A (FBS)
UNRANKED = 99             # what curatedRank.current says when nobody ranks you

# ESPN conference group ids. This is a FALLBACK: fetch_conferences() replaces
# it from the live feed whenever that is reachable, because conferences in
# this sport move around constantly. Anything not resolved here comes out
# empty, and empty means "unknown", not "soft" — see attention_tier().
CONFERENCE_IDS = {
    "1": "ACC", "4": "Big 12", "5": "Big Ten", "8": "SEC", "9": "Pac-12",
    "12": "Conference USA", "15": "MAC", "17": "Mountain West",
    "18": "FBS Independents", "20": "American", "37": "Sun Belt",
    "151": "FCS",
}

# The power conferences, spelled the way engine.cfb.model expects them.
CONFERENCE_ALIASES = {
    "atlantic coast conference": "ACC",
    "southeastern conference": "SEC",
    "big ten conference": "Big Ten",
    "big 12 conference": "Big 12",
    "pac-12 conference": "Pac-12",
    "american athletic conference": "American",
    "mid-american conference": "MAC",
    "mountain west conference": "Mountain West",
    "sun belt conference": "Sun Belt",
    "conference usa": "Conference USA",
}


# --- time: the Eastern weekday is what "weeknight game" means ---------------
def _dst_bounds(year: int) -> tuple[_dt.date, _dt.date]:
    """US daylight time: second Sunday in March → first Sunday in November."""
    march = _dt.date(year, 3, 1)
    first_sun = march + _dt.timedelta(days=(6 - march.weekday()) % 7)
    nov = _dt.date(year, 11, 1)
    return first_sun + _dt.timedelta(days=7), nov + _dt.timedelta(days=(6 - nov.weekday()) % 7)


def to_eastern(iso_utc: str) -> _dt.datetime | None:
    """A UTC ISO stamp as naive US Eastern wall-clock time."""
    s = (iso_utc or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        t = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    start, end = _dst_bounds(t.year)
    offset = -4 if start <= t.date() < end else -5
    return t + _dt.timedelta(hours=offset)


def weekday_et(iso_utc: str) -> str:
    """'Saturday', 'Wednesday', … in the time zone the sport is played in."""
    t = to_eastern(iso_utc)
    return t.strftime("%A") if t else ""


# --- names ------------------------------------------------------------------
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def name_key(name: str) -> str:
    """Loose key for joining team names across feeds.

    The ampersand COLLAPSES rather than expanding to "and": 'Texas A&M' and
    'Texas A M' have to produce the same key, and no feed in this pipeline
    actually spells it out — expanding would have made the two spellings
    disagree and silently dropped a paid-for line.
    """
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " ").replace("-", " ").replace(".", " ")
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_team(name: str, lookup: dict[str, str]) -> str:
    """Best abbreviation for a team name from another feed, or ''.

    Books quote "Miami (OH) RedHawks"; ESPN's short name is "Miami (OH)".
    Trying the full string first and then peeling nicknames off the end
    joins those without a hand-written alias table — and returning '' when
    nothing matches is what keeps an unmatched school visible as a counted
    miss instead of a game that quietly never got priced.
    """
    key = name_key(name)
    if not key:
        return ""
    words = key.split()
    for cut in range(0, min(2, len(words) - 1) + 1):
        hit = lookup.get(" ".join(words[:len(words) - cut]))
        if hit:
            return hit
    return ""


def conference_name(raw: str) -> str:
    """Normalise a conference to the spelling the model's power set uses."""
    r = (raw or "").strip()
    return CONFERENCE_ALIASES.get(r.lower(), r)


# --- parsers (pure) ---------------------------------------------------------
def parse_conferences(payload: dict) -> dict[str, str]:
    """``{group_id: conference name}`` from ESPN's groups feed.

    Two shapes are in the wild for this endpoint, so both are read rather
    than betting the whole conference layer on one of them.
    """
    out: dict[str, str] = {}
    rows = payload.get("groups") or payload.get("children") or []
    for g in rows:
        gid = str(g.get("groupId") or g.get("id") or "").strip()
        name = (g.get("shortName") or g.get("name") or g.get("abbreviation") or "").strip()
        if gid and name:
            out[gid] = conference_name(name)
    return out


def conference_ids(live: dict[str, str] | None = None) -> dict[str, str]:
    """Every conference group id we can name, live feed layered on top.

    The built-in table is the floor and the live feed is the improvement,
    never the other way round — ``fetch_conferences`` answers ``{}`` when
    the groups endpoint is unreachable, and a caller that used that answer
    alone would decide this sport has no conferences at all.

    It exists as a function because it had two callers with two behaviours:
    ``parse_scoreboard`` merged correctly and `assets.py --audit` did not,
    so the audit read every school as unaffiliated and fell back to checking
    ESPN's whole 756-row college database.
    """
    return {**CONFERENCE_IDS, **(live or {})}


def parse_teams(payload: dict) -> dict[str, dict]:
    """``{abbr: {name, nick, primary, alt, id}}`` from ESPN's teams feed.

    This is the identity the board draws with. It ships in the slate JSON
    rather than a checked-in file — 134 teams is exactly the kind of list
    that rots quietly.
    """
    out: dict[str, dict] = {}
    try:
        rows = payload["sports"][0]["leagues"][0]["teams"]
    except (KeyError, IndexError, TypeError):
        rows = payload.get("teams") or []
    for row in rows:
        t = row.get("team", row) or {}
        abbr = (t.get("abbreviation") or "").strip()
        if not abbr:
            continue
        color = (t.get("color") or "").strip().lstrip("#")
        alt = (t.get("alternateColor") or "").strip().lstrip("#")
        # Which conference ESPN files the school under, when it says. The
        # feed ignores our ``groups=80`` and answers with its whole college
        # database — measured, 756 schools, most of them NAIA and D-II that
        # no D-I scoreboard will ever show. Anything that needs to separate
        # the schools we can render from the ones we cannot has to have
        # something to separate them BY, and this is the only marker the
        # payload offers. Empty when absent, which callers must treat as
        # "unknown", never as "not D-I".
        groups = t.get("groups") or {}
        out[abbr] = {
            "id": str(t.get("id") or ""),
            "name": t.get("displayName") or t.get("location") or abbr,
            "nick": t.get("shortDisplayName") or t.get("location") or abbr,
            "primary": f"#{color}" if color else "",
            "alt": f"#{alt}" if alt else "",
            "conf": str(t.get("conferenceId") or groups.get("id") or ""),
        }
    return out


def team_lookup(teams: dict[str, dict]) -> dict[str, str]:
    """``{loose name key: abbr}`` for joining odds-feed team names.

    Every spelling a book might use — full name, school, nickname — points
    at the same abbreviation.
    """
    out: dict[str, str] = {}
    for abbr, t in teams.items():
        for variant in (t.get("name"), t.get("nick"), abbr):
            k = name_key(variant or "")
            if k:
                out.setdefault(k, abbr)
    return out


def _rank(competitor: dict) -> int | None:
    cur = (competitor.get("curatedRank") or {}).get("current")
    try:
        cur = int(cur)
    except (TypeError, ValueError):
        return None
    return cur if 1 <= cur < UNRANKED else None


def _score(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_scoreboard(payload: dict,
                     conferences: dict[str, str] | None = None) -> list[dict]:
    """An ESPN scoreboard payload → the game dicts the CFB model reads.

    Everything ``attention_tier`` needs is set here; everything the two
    refusals need (§2.3 quarterback, §2.4 December participation) is
    deliberately NOT — those come from a source that actually knows, and
    until then they stay false so the play is held rather than guessed.
    """
    confs = conference_ids(conferences)
    games: list[dict] = []
    for ev in payload.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        home = away = None
        for c in comp.get("competitors", []) or []:
            team = c.get("team") or {}
            side = {
                "abbr": (team.get("abbreviation") or "").strip(),
                "name": team.get("displayName") or "",
                "conference": conference_name(
                    confs.get(str(team.get("conferenceId") or ""), "")),
                "rank": _rank(c),
                "score": _score(c.get("score")),
            }
            if c.get("homeAway") == "home":
                home = side
            else:
                away = side
        if not home or not away or not home["abbr"] or not away["abbr"]:
            continue

        status = (comp.get("status") or ev.get("status") or {})
        stype = status.get("type") or {}
        state = {"pre": "scheduled", "in": "live",
                 "post": "final"}.get(stype.get("state", "pre"), "scheduled")
        kickoff = ev.get("date") or comp.get("date") or ""
        venue = comp.get("venue") or {}
        games.append({
            "game_id": str(ev.get("id") or comp.get("id") or ""),
            "home": home["abbr"], "away": away["abbr"],
            "home_name": home["name"], "away_name": away["name"],
            "home_conference": home["conference"],
            "away_conference": away["conference"],
            "home_rank": home["rank"], "away_rank": away["rank"],
            "home_score": home["score"], "away_score": away["score"],
            "kickoff": kickoff,
            "date": (to_eastern(kickoff).date().isoformat()
                     if to_eastern(kickoff) else ""),
            "weekday": weekday_et(kickoff),
            "neutral_site": bool(comp.get("neutralSite")),
            "conference_game": bool(comp.get("conferenceCompetition")),
            "week": (ev.get("week") or {}).get("number"),
            "season": (ev.get("season") or {}).get("year"),
            "season_type": (ev.get("season") or {}).get("type"),
            "state": state,
            "completed": bool(stype.get("completed")),
            "detail": stype.get("shortDetail", ""),
            "venue": venue.get("fullName", ""),
            "indoor": bool(venue.get("indoor")),
            "label": ev.get("shortName") or f"{away['abbr']} @ {home['abbr']}",
            # §2 — nothing here confirms a quarterback or a bowl roster.
            "qb_confirmed": False,
            "participation_verified": False,
            "weather_checked": False,
        })
    return games


def game_rows(games: list[dict]) -> list[dict]:
    """Finished games as rows for ``db.upsert_games``.

    Only completed games: a scoreless row for a game in progress is what
    the settle guard reads as "still playing", and writing partial scores
    would grade bets against a half-played result.
    """
    rows = []
    for g in games:
        if not g.get("completed") or g.get("home_score") is None:
            continue
        rows.append({
            "sport": "cfb", "season": g.get("season") or 0,
            "period": g.get("date") or "", "game_id": g["game_id"],
            "home": g["home"], "away": g["away"],
            "home_score": g["home_score"], "away_score": g["away_score"],
            "extra": json.dumps({"week": g.get("week"),
                                 "neutral": g.get("neutral_site"),
                                 "conference_game": g.get("conference_game")}),
        })
    return rows


# --- fetch wrappers ---------------------------------------------------------
def fetch_scoreboard(date: str, ttl: int = 300) -> dict:
    """One day's board. ``date`` is ISO (YYYY-MM-DD).

    ``limit`` matters: ESPN defaults to a couple of dozen events and a
    September Saturday has 60+, so the default would silently drop half the
    slate — including exactly the unwatched games this model is built for.
    """
    day = date.replace("-", "")
    url = f"{SCOREBOARD}?dates={day}&groups={FBS_GROUP}&limit=900"
    return fetch_json(url, f"espn_cfb_{day}.json", ttl=ttl,
                      user_agent=DEFAULT_AGENT)


def fetch_teams(ttl: int = 7 * 24 * 3600) -> dict:
    url = f"{TEAMS}?limit=900&groups={FBS_GROUP}"
    return fetch_json(url, "espn_cfb_teams.json", ttl=ttl,
                      user_agent=DEFAULT_AGENT)


def fetch_conferences(ttl: int = 7 * 24 * 3600) -> dict[str, str]:
    """Live conference names, or ``{}`` when the groups feed won't answer.

    It does NOT fall back to the built-in ids, whatever this docstring used
    to claim. ``conference_ids()`` layers those underneath, and a caller
    that skips it reads an unreachable feed as "this sport has no
    conferences" — which is what sent `--audit cfb` through all 756 schools.
    """
    try:
        payload = fetch_json(f"{GROUPS}?groups={FBS_GROUP}",
                             "espn_cfb_groups.json", ttl=ttl,
                             user_agent=DEFAULT_AGENT)
    except DataUnavailable:
        return {}
    return parse_conferences(payload)


def load_games(date: str, ttl: int = 300) -> list[dict]:
    """A day's FBS slate, conference names resolved as far as they can be."""
    confs = fetch_conferences()
    return parse_scoreboard(fetch_scoreboard(date, ttl=ttl), confs)


def load_range(start: str, end: str, ttl: int = 24 * 3600,
               conferences: dict[str, str] | None = None) -> list[dict]:
    """Every game across a date range, one keyless request per day.

    Days that can't be fetched are skipped rather than aborting the range —
    a rating built from 90% of the season beats no rating at all, and the
    fitted-vs-prior label downstream says which one is in force.
    """
    try:
        d0 = _dt.date.fromisoformat(start)
        d1 = _dt.date.fromisoformat(end)
    except ValueError:
        return []
    out: list[dict] = []
    day = d0
    while day <= d1:
        try:
            out += parse_scoreboard(fetch_scoreboard(day.isoformat(), ttl=ttl),
                                    conferences)
        except (DataUnavailable, ValueError):
            pass
        day += _dt.timedelta(days=1)
    return out


def load_results(start: str, end: str, ttl: int = 24 * 3600) -> list[dict]:
    """Completed games across a date range, for the ratings history."""
    return [g for g in load_range(start, end, ttl=ttl) if g["completed"]]
