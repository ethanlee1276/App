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
def parse_group_teams(payload: dict) -> dict[str, str]:
    """``{espn team id: conference name}`` from ESPN's groups feed.

    THIS IS WHAT THE ENDPOINT ACTUALLY RETURNS, measured 2026-08-08 from
    Ethan's machine after two wrong guesses about it. The shape is::

        {status, groups: [ {name, abbreviation, children: [
            {name, abbreviation, teams: [ {id, name, abbreviation, ...} ]}
        ]} ]}

    The load-bearing detail is that **the group nodes carry no id**. Only
    teams do. So ``{group_id: name}`` — the map this module has asked this
    endpoint for since it was written — was never buildable from it, and no
    amount of unwrapping or deeper walking was going to produce one. That is
    why the feed "answered with nothing" twice while being perfectly healthy.

    Keyed by team instead, the same payload is strictly more useful: it says
    which conference each school is in AND, by omission, which schools are
    not in one. ESPN's teams endpoint returns its entire college database —
    756 rows, most of them NAIA and D-II — and this is the list of the ones
    that play in a conference we can name.

    The label is taken from the FIRST named level below the top and never
    overwritten deeper. The top level is the division of college football —
    "NCAA Division I-A" — which is not a conference; the level under it is.
    Some conferences then split into divisions that also carry teams, and
    naming a school's conference "East Division" would be worse than useless
    to ``attention_tier``, which reads this to decide how hard the market is
    looking at a game.
    """
    out: dict[str, str] = {}

    def walk(node, label: str = "", depth: int = 0):
        if depth > 6 or not isinstance(node, dict):
            return
        name = conference_name((node.get("shortName") or node.get("name")
                                or node.get("abbreviation") or "").strip())
        if depth == 0:
            # FBS/FCS itself, unless it holds teams directly — independents
            # can hang off the top with no conference node in between.
            here = name if node.get("teams") else ""
        else:
            here = label or name
        for t in (node.get("teams") or []):
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id") or "").strip()
            if tid and here:
                out[tid] = here
        for key in ("children", "groups", "conferences"):
            for kid in (node.get(key) or []):
                walk(kid, here, depth + 1)

    body = payload
    try:                            # the sports[0].leagues[0] envelope
        league = payload["sports"][0]["leagues"][0]
        if isinstance(league, dict):
            body = {**league, **{k: v for k, v in payload.items()
                                 if k != "sports"}}
    except (KeyError, IndexError, TypeError):
        pass
    for key in ("groups", "children", "conferences"):
        for row in (body.get(key) or []):
            walk(row)
    return out


def parse_conferences(payload: dict) -> dict[str, str]:
    """``{group_id: conference name}`` from ESPN's groups feed.

    Several shapes are in the wild for this endpoint, so the whole tree is
    walked rather than betting the conference layer on one of them.

    THE NESTING IS THE POINT. Asking for ``groups=80`` can answer with the
    FBS group itself and the conferences hanging off its ``children``. Read
    one level deep, that payload yields exactly one entry — ``{"80": "FBS"}``
    — and every real conference is missed while the fetch reports success.
    That failure looks identical from the outside to the feed being down,
    which is why this walks down instead of guessing which level to read.
    """
    out: dict[str, str] = {}

    # THE ENVELOPE. This API wraps its collections in
    # sports[0].leagues[0].<thing> — `parse_teams` has unwrapped exactly that
    # since it was written, and this function never did. Measured on Ethan's
    # machine 2026-08-08: all three URL shapes REACHED the host and returned
    # valid JSON, and all three parsed to nothing. A feed that answers and
    # yields zero conferences is not a feed that is down; it is a reader
    # looking at the wrong level.
    try:
        league = payload["sports"][0]["leagues"][0]
        if isinstance(league, dict):
            payload = {**league, **{k: v for k, v in payload.items()
                                    if k != "sports"}}
    except (KeyError, IndexError, TypeError):
        pass                       # already unwrapped, or a different shape

    def walk(node, depth=0):
        if depth > 4 or not isinstance(node, dict):
            return                              # cycles are not a thing here,
        gid = str(node.get("groupId") or node.get("id") or "").strip()
        name = (node.get("shortName") or node.get("name")
                or node.get("abbreviation") or "").strip()
        if gid and name:
            out[gid] = conference_name(name)
        for key in ("children", "groups", "conferences"):
            for kid in (node.get(key) or []):
                walk(kid, depth + 1)

    for key in ("groups", "children", "conferences"):
        for row in (payload.get(key) or []):
            walk(row)
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
        # No conference marker is read here. One was added on the guess that
        # this payload carries `conferenceId`, so that `--audit cfb` could
        # tell a Big Ten school from a JUCO; measured, it does not, and the
        # groups feed enumerates conference membership by team id anyway.
        # See `parse_group_teams`. A field nothing reads, on a guess the
        # measurement contradicted, in a map that ships 756 rows to the
        # browser, is not worth keeping for the day it might be true.
        out[abbr] = {
            "id": str(t.get("id") or ""),
            "name": t.get("displayName") or t.get("location") or abbr,
            "nick": t.get("shortDisplayName") or t.get("location") or abbr,
            "primary": f"#{color}" if color else "",
            "alt": f"#{alt}" if alt else "",
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
                     conferences: dict[str, str] | None = None,
                     team_conf: dict[str, str] | None = None) -> list[dict]:
    """An ESPN scoreboard payload → the game dicts the CFB model reads.

    Everything ``attention_tier`` needs is set here; everything the two
    refusals need (§2.3 quarterback, §2.4 December participation) is
    deliberately NOT — those come from a source that actually knows, and
    until then they stay false so the play is held rather than guessed.

    ``team_conf`` is ``{team id: conference}`` from ``fetch_group_teams`` and
    it wins where it has an answer. It is the only one of the two sources
    that is live: the ``conferenceId`` route resolves through a twelve-row
    table checked into this file, which the header above says goes stale
    every time a school moves — and schools move constantly. Absent, nothing
    changes and the built-in table answers as before.
    """
    confs = conference_ids(conferences)
    by_team = team_conf or {}
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
                    by_team.get(str(team.get("id") or ""))
                    or confs.get(str(team.get("conferenceId") or ""), "")),
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


#: The shapes worth asking for, in the order worth asking. The first entry
#: is what this module has always sent; the rest exist because on Ethan's
#: machine, 2026-08-08, that one produced nothing while the teams feed on
#: the same host answered fine. Dropping the parameter is not a random
#: second guess — ``fetch_teams`` sends the identical ``groups=80`` and the
#: feed demonstrably ignores it there, which is a reason to doubt it means
#: anything on this endpoint either.
GROUP_CANDIDATES = [
    ("groups=80", f"{GROUPS}?groups={FBS_GROUP}", "espn_cfb_groups.json"),
    ("group=80", f"{GROUPS}?group={FBS_GROUP}", "espn_cfb_groups_g.json"),
    ("no filter", GROUPS, "espn_cfb_groups_all.json"),
]


def fetch_conferences(ttl: int = 7 * 24 * 3600,
                      report: list | None = None) -> dict[str, str]:
    """Live conference names, or ``{}`` when nothing usable comes back.

    It does NOT fall back to the built-in ids. ``conference_ids()`` layers
    those underneath, and a caller that skips it reads an unreachable feed
    as "this sport has no conferences" — which is what sent `--audit cfb`
    through all 756 schools.

    WHY A LADDER RATHER THAN ONE URL. The single shape this used to send
    stopped producing conferences, and from the outside "the host refused"
    and "the payload parsed to nothing" looked the same. Both are now tried
    against alternatives and the first that yields a real map wins, so a
    changed parameter costs one extra request instead of a whole silent
    model input. ``report`` collects ``(label, count, note)`` per candidate
    for the diagnostic, which is how we find out WHICH one answered rather
    than only that something did.
    """
    for label, url, cache in GROUP_CANDIDATES:
        try:
            payload = fetch_json(url, cache, ttl=ttl, user_agent=DEFAULT_AGENT)
        except DataUnavailable as exc:
            if report is not None:
                report.append((label, 0, f"unreachable: {exc}"))
            continue
        confs = parse_conferences(payload)
        # One entry is the parent group answering for itself — the "80: FBS"
        # case — not a conference list. Keep looking.
        usable = len(confs) > 1
        if report is not None:
            report.append((label, len(confs),
                           "ok" if usable else f"parsed {sorted(confs.items())}"))
        if usable:
            return confs
    return {}


def fetch_group_teams(ttl: int = 7 * 24 * 3600,
                      report: list | None = None) -> dict[str, str]:
    """``{espn team id: conference}`` off the same groups feed.

    The map this endpoint can actually produce. ``fetch_conferences`` asks it
    for ``{group_id: name}``, which — measured — it does not carry, because
    its group nodes have no id. Rather than delete that function and its
    callers, this sits beside it: same candidate ladder, different question,
    and the one that comes back with an answer.
    """
    for label, url, cache in GROUP_CANDIDATES:
        try:
            payload = fetch_json(url, cache, ttl=ttl, user_agent=DEFAULT_AGENT)
        except DataUnavailable as exc:
            if report is not None:
                report.append((label, 0, f"unreachable: {exc}"))
            continue
        teams = parse_group_teams(payload)
        if report is not None:
            report.append((label, len(teams),
                           "ok" if teams else "answered, no teams in it"))
        if teams:
            return teams
    return {}


def load_games(date: str, ttl: int = 300) -> list[dict]:
    """A day's FBS slate, conference names resolved as far as they can be."""
    return parse_scoreboard(fetch_scoreboard(date, ttl=ttl),
                            fetch_conferences(), fetch_group_teams())


def load_range(start: str, end: str, ttl: int = 24 * 3600,
               conferences: dict[str, str] | None = None,
               team_conf: dict[str, str] | None = None) -> list[dict]:
    """Every game across a date range, one keyless request per day.

    Days that can't be fetched are skipped rather than aborting the range —
    a rating built from 90% of the season beats no rating at all, and the
    fitted-vs-prior label downstream says which one is in force.

    The conference maps are fetched ONCE here, not per day. Both are cached
    for a week, but a season backfill is ~180 days and doing the lookup
    inside the loop would ask the cache 180 times for an answer that cannot
    have changed.
    """
    if team_conf is None:
        try:
            team_conf = fetch_group_teams(ttl=ttl)
        except DataUnavailable:
            team_conf = {}
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
                                    conferences, team_conf)
        except (DataUnavailable, ValueError):
            pass
        day += _dt.timedelta(days=1)
    return out


def load_results(start: str, end: str, ttl: int = 24 * 3600) -> list[dict]:
    """Completed games across a date range, for the ratings history."""
    return [g for g in load_range(start, end, ttl=ttl) if g["completed"]]
