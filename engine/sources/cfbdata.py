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
    # 151 WAS "FCS" AND IT IS THE AMERICAN. Derived, not recalled, by
    # `assets.py --conf-table`: two independent Saturdays — 2025-11-01 and
    # 2025-11-29 — both resolve 151 to the American Athletic Conference,
    # unanimously, off a join that matched 50 of 50 teams on each slate.
    # Every other id checked on those runs came back matching, so the method
    # is not simply disagreeing with everything.
    #
    # Which id real FCS teams carry is still unknown, and deliberately not
    # guessed. Unknown is handled correctly already: an unresolved conference
    # comes out empty, and `attention_tier` reads empty as STANDARD, never as
    # "nobody is watching" — see the header note above.
    "151": "American",
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
    # CFBD's spellings, measured 2026-08-08 against a real slate. It drops
    # the trailing "Conference", so the aliases above miss it and the same
    # league arrives under two names depending on which feed answered. That
    # showed up as `15 MAC -> RENAMED -> Mid-American`, which is not
    # realignment, it is two spellings of the same thing.
    "mid-american": "MAC",
    "american athletic": "American",
    "mountain west": "Mountain West",
    "sun belt": "Sun Belt",
    "big ten": "Big Ten",
    "big 12": "Big 12",
    "cusa": "Conference USA",
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
#: What one page of the groups feed holds. Measured: every division came
#: back with exactly 25 teams, four divisions, 100 total — a page size, not
#: a roster. A map this size describes nothing and must not be used to
#: filter anything, because the schools it omits are omitted by pagination
#: rather than by fact.
GROUP_PAGE = 25


def parse_group_divisions(payload: dict) -> dict[str, str]:
    """``{espn team id: NCAA division}`` from ESPN's groups feed.

    DIVISION, NOT CONFERENCE, and the distinction cost a shipped mistake.
    Measured 2026-08-08 from Ethan's machine, the tree is::

        {status, groups: [ {name, abbreviation, children: [
            {name, abbreviation, teams: [ {id, name, ... } ]} ]} ]}

    and the four ``children`` are **FBS, FCS, NCAA Division II, NCAA
    Division III**. There are no conference nodes in it at any depth. An
    earlier version of this function assumed the level below the top held
    conferences and wired its answer into ``parse_scoreboard``, which would
    have labelled Alabama's conference "FBS" — dropping every power-five
    school out of ``attention_tier``'s power set and pricing the SEC as
    though nobody was watching. That wiring is gone.

    Two further facts about the group nodes, both load-bearing:

    * **they carry no id.** Only teams do. So ``{group_id: name}`` — what
      this module has asked this endpoint for since it was written — was
      never buildable from it, which is why ``fetch_conferences`` reports
      nothing while the feed is perfectly healthy.
    * **the team lists are paginated at 25.** So this map is not a complete
      enumeration of anything and cannot be used as a membership test.

    It is kept because division membership is the honest thing this feed
    does carry, and because a complete version of it would be the D-I filter
    ``assets.py --audit cfb`` still needs. Callers must check the size
    against ``GROUP_PAGE`` before trusting it as a list.
    """
    out: dict[str, str] = {}

    def walk(node, label: str = "", depth: int = 0):
        if depth > 6 or not isinstance(node, dict):
            return
        name = conference_name((node.get("shortName") or node.get("name")
                                or node.get("abbreviation") or "").strip())
        if depth == 0:
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
                     conferences: dict[str, str] | None = None) -> list[dict]:
    """An ESPN scoreboard payload → the game dicts the CFB model reads.

    Everything ``attention_tier`` needs is set here; everything the two
    refusals need (§2.3 quarterback, §2.4 December participation) is
    deliberately NOT — those come from a source that actually knows, and
    until then they stay false so the play is held rather than guessed.

    CONFERENCE COMES FROM ``conferenceId`` AND NOTHING ELSE. A previous
    version preferred a {team id: conference} map off the groups feed, on
    the assumption that the level below the top of that tree held
    conferences. Measured 2026-08-08, it holds NCAA DIVISIONS — the map came
    back naming every school's conference "FBS" or "NCAA Division II". That
    is not a conference, it would have dropped every power-five school out
    of ``attention_tier``'s power set, and the board would have gone on
    pricing as though nobody was watching the SEC.
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


ROSTER = BASE + "/teams/{team_id}/roster"


def parse_team_roster(payload: dict) -> dict:
    """``{normalised name: position}`` for one team, this season.

    THE WEEK-ONE HALF OF THE TRANSFER PROBLEM. Usage is filed under the
    school a player produced for, so a summer transfer is invisible to a
    board that looks him up under the two teams in front of it. From week
    two his own box scores place him; in week one nobody has played, and
    this is the only published source that says where he is now.

    Keyed on the ESPN team id, which is what `games` already stores — so
    the join is exact rather than a school-name match.

    Athletes arrive grouped ("offense", "defense", "specialTeam") with
    the real position on each item. The group label is kept as a fallback
    because a payload that changes shape should cost a coarser position,
    not an empty roster.
    """
    from .oddsapi import normalize_name
    out: dict = {}
    for group in (payload or {}).get("athletes") or []:
        if not isinstance(group, dict):
            continue
        fallback = str(group.get("position") or "").upper()
        for a in group.get("items") or []:
            if not isinstance(a, dict):
                continue
            name = (a.get("fullName") or a.get("displayName") or
                    " ".join(x for x in (a.get("firstName"),
                                         a.get("lastName")) if x))
            if not str(name).strip():
                continue
            pos = a.get("position")
            if isinstance(pos, dict):
                pos = pos.get("abbreviation") or pos.get("name") or ""
            out[normalize_name(str(name))] = str(pos or fallback).upper()
    return out


def fetch_team_roster(team_id: str, ttl: int = 24 * 3600) -> dict:
    """One team's current roster. A day's cache: rosters move slowly and
    a Saturday slate would otherwise re-ask for the same twenty teams."""
    ident = str(team_id).split(":")[-1]
    return fetch_json(ROSTER.format(team_id=ident),
                      f"espn_cfb_roster_{ident}.json", ttl=ttl,
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
    # Measured: every division came back with exactly GROUP_PAGE teams, so
    # the lists are paginated. `fetch_teams` already sends limit=900 against
    # this same API and gets 756 rows back, which is reason to think the
    # parameter is honoured here even though `groups` is not.
    ("limit=900", f"{GROUPS}?limit=900", "espn_cfb_groups_lim.json"),
]


#: The groups endpoint does not carry conference names, and asking it four
#: times per cache miss to be told so again is waste on every CFB build.
#:
#: MEASURED, three runs, 2026-08-08. All four URL shapes answer 200 with the
#: same payload: NCAA divisions, no id on any group node, team lists cut at
#: GROUP_PAGE. ``limit=900`` — the parameter that gets 756 rows out of this
#: same API's teams endpoint — does not lift the pagination either.
#:
#: So the build path stops asking. ``probe=True`` still goes to the wire, so
#: `assets.py --conferences` can re-check in one command if ESPN ever
#: changes it. This is a measurement, not a permanent verdict; it is just
#: not one worth re-taking on a schedule.
GROUPS_CARRY_CONFERENCES = False


def fetch_conferences(ttl: int = 7 * 24 * 3600,
                      report: list | None = None,
                      probe: bool = False) -> dict[str, str]:
    """Live conference names, or ``{}`` — which, measured, is always.

    It does NOT fall back to the built-in ids. ``conference_ids()`` layers
    those underneath, and a caller that skips it reads an empty answer as
    "this sport has no conferences" — which is what sent `--audit cfb`
    through all 756 schools.

    Without ``probe`` this makes no request at all. See
    ``GROUPS_CARRY_CONFERENCES``: the endpoint has been measured three times
    and does not carry what this asks for, so the four-request ladder was
    buying nothing on every build.
    """
    if not (probe or GROUPS_CARRY_CONFERENCES):
        if report is not None:
            report.append(("not asked", 0, "measured: this feed has no "
                           "conference names — --conferences to re-check"))
        return {}
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


def fetch_group_divisions(ttl: int = 7 * 24 * 3600,
                          report: list | None = None) -> dict[str, str]:
    """``{espn team id: NCAA division}`` off the groups feed.

    Diagnostic and audit use only — nothing in pricing reads this. See
    ``parse_group_divisions`` for why: the feed carries divisions, not
    conferences, and paginates its team lists at ``GROUP_PAGE``. Unlike
    ``fetch_conferences`` this still goes to the wire, because divisions ARE
    what it carries and a complete page would be usable; it is only ever
    called from the audit and the diagnostic, not from a build.
    """
    for label, url, cache in GROUP_CANDIDATES:
        try:
            payload = fetch_json(url, cache, ttl=ttl, user_agent=DEFAULT_AGENT)
        except DataUnavailable as exc:
            if report is not None:
                report.append((label, 0, f"unreachable: {exc}"))
            continue
        teams = parse_group_divisions(payload)
        if report is not None:
            note = "answered, no teams in it"
            if teams:
                note = ("ok" if len(teams) > GROUP_PAGE * 8
                        else f"TRUNCATED — a page is {GROUP_PAGE} per division")
            report.append((label, len(teams), note))
        if teams:
            return teams
    return {}


def load_games(date: str, ttl: int = 300) -> list[dict]:
    """A day's FBS slate, conference names resolved as far as they can be."""
    return parse_scoreboard(fetch_scoreboard(date, ttl=ttl),
                            fetch_conferences())


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


# ---------------------------------------------------------------------------
# Player box scores — the layer the sidebar said could not exist.
#
# HIDDEN_WHY carried "no free player-level feed covers 134 programs" for
# the Players, Trending and Rosters tabs, and the claim was stale the day
# it was written: the SAME keyless API this module already reads has a
# summary endpoint with the full box score, one request per game, exactly
# the shape espnhoops has ingested for the NBA and WNBA since August.
# (Ethan, 2026-08-24: "can we now work on CFB not having any of this
# info.")
#
# Football's box differs from basketball's in two ways this parser has to
# respect. Groups are POSITIONAL (passing / rushing / receiving), so the
# same column name means different markets in different groups — "YDS" is
# pass_yds in one block and rush_yds in the next — which is why the map
# below is keyed (group, column) and never column alone. And one player
# spans groups (a quarterback who scrambles appears in passing AND
# rushing), so rows merge by player before they are emitted.

SUMMARY = BASE + "/summary"

#: (group name, column label) → our market id. Labels are matched by
#: NAME within their group; reading by position would silently mis-assign
#: every stat the day ESPN moves a column. Vocabulary matches the NFL's
#: (engine/models.py MARKET_LABELS) so one player search speaks one
#: language across both footballs.
BOX_MARKETS = {
    ("passing", "YDS"): "pass_yds",
    ("rushing", "CAR"): "carries",
    ("rushing", "YDS"): "rush_yds",
    ("receiving", "REC"): "receptions",
    ("receiving", "YDS"): "rec_yds",
    ("receiving", "TGTS"): "targets",     # present on some college feeds
    # Touchdown columns (2026-08-25): the anytime-TD long-shot board
    # journals its picks, and a journaled bet needs a result row to
    # settle against — these two sum into `anytime_td` in parse_summary.
    ("rushing", "TD"): "rush_td",
    ("receiving", "TD"): "rec_td",
}

#: When the athlete record carries no position of its own, the group he
#: appeared in first is the honest guess: group order is passing,
#: rushing, receiving, so quarterbacks resolve QB and backs RB. A tight
#: end falls to WR — a known, bounded mislabel, corrected automatically
#: whenever the feed does carry the real position.
GROUP_POS = {"passing": "QB", "rushing": "RB", "receiving": "WR"}


def parse_summary(payload: dict) -> list[dict]:
    """A game summary → per-player rows: {player, team, position, stats,
    espn_id, headshot}. Same contract as espnhoops.parse_summary."""
    merged: dict[tuple, dict] = {}
    box = payload.get("boxscore") or {}
    for team_block in box.get("players", []) or []:
        team = ((team_block.get("team") or {}).get("abbreviation") or "").strip()
        for group in team_block.get("statistics", []) or []:
            gname = str(group.get("name") or "").strip().lower()
            labels = [str(x).upper() for x in
                      (group.get("labels") or group.get("names") or [])]
            if not labels:
                continue
            for ath in group.get("athletes", []) or []:
                info = ath.get("athlete") or {}
                player = (info.get("displayName") or "").strip()
                if not player:
                    continue
                stats = ath.get("stats") or []
                vals: dict = {}
                for i, col in enumerate(labels):
                    mk = BOX_MARKETS.get((gname, col))
                    if mk is None or i >= len(stats):
                        continue
                    v = _score(stats[i])
                    if v is not None:
                        vals[mk] = v
                if not vals:
                    continue
                pos = ((info.get("position") or {}).get("abbreviation")
                       if isinstance(info.get("position"), dict) else "") or ""
                shot = info.get("headshot") or {}
                row = merged.setdefault((team, player), {
                    "player": player, "team": team,
                    "position": pos.upper() or GROUP_POS.get(gname, ""),
                    "stats": {},
                    "espn_id": str(info.get("id") or ""),
                    "headshot": (shot.get("href") if isinstance(shot, dict)
                                 else str(shot or "")) or "",
                })
                if pos:
                    row["position"] = pos.upper()
                row["stats"].update(vals)
    # `anytime_td` is DERIVED here, where both halves of a player's day
    # are finally in one row — a back who ran one in and caught another
    # appears in two groups, and summing at column-parse time would see
    # only one of them. The ledger settles the long-shot board against
    # this market by name (SETTLEABLE_LONGSHOTS), so a player with either
    # TD column present gets the row, zeros included: "played and did not
    # score" is the result most anytime-TD bets settle against.
    out = list(merged.values())
    for row in out:
        s = row["stats"]
        if "rush_td" in s or "rec_td" in s:
            s["anytime_td"] = float(s.get("rush_td") or 0) \
                + float(s.get("rec_td") or 0)
    return out


def fetch_summary(game_id: str, ttl: int = 30 * 24 * 3600) -> dict:
    """One game's box score. A month's cache: a final box never changes."""
    return fetch_json(f"{SUMMARY}?event={game_id}",
                      f"cfb_summary_{game_id}.json", ttl=ttl,
                      user_agent=DEFAULT_AGENT)


def ingest_player_logs(conn, start: str, end: str,
                       quiet: bool = False) -> dict:
    """Box scores for every completed CFB game already in the games table.

    WALKS OUR OWN ROWS, NOT THE SCOREBOARD AGAIN: `ingest.py cfb` has
    already stored each game with ESPN's own event id as game_id, so the
    summaries are one request per game with no second discovery pass.

    Failure shape mirrors espnhoops.ingest_day — a refused summary is a
    skipped game and a note, never a dead run, because ESPN is known to
    refuse this endpoint from some cloud IPs while serving the scoreboard
    happily to the same box.
    """
    from .. import db
    from ..seasons import season_of

    result: dict = {"games": 0, "player_logs": 0, "skipped": []}
    rows = conn.execute(
        "SELECT game_id, period, home, away FROM games "
        "WHERE sport='cfb' AND period >= ? AND period <= ? "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY period",
        (start, end)).fetchall()
    prows, arows = [], []
    for g in rows:
        try:
            summary = fetch_summary(str(g["game_id"]))
        except DataUnavailable as exc:
            result["skipped"].append(f"cfb box {g['game_id']}: {exc}")
            continue
        result["games"] += 1
        opp = {g["home"]: g["away"], g["away"]: g["home"]}
        for row in parse_summary(summary):
            if row.get("espn_id") or row.get("headshot"):
                arows.append({"sport": "cfb", "player": row["player"],
                              "espn_id": row.get("espn_id", ""),
                              "headshot": row.get("headshot", ""),
                              "seen": g["period"]})
            for market, value in row["stats"].items():
                prows.append({
                    "sport": "cfb", "season": season_of("cfb", g["period"]),
                    "period": g["period"], "game_id": str(g["game_id"]),
                    "player": row["player"], "team": row["team"],
                    "opponent": opp.get(row["team"], ""),
                    "position": row["position"],
                    "home": 1 if row["team"] == g["home"] else 0,
                    "market": market, "value": value,
                })
    result["player_logs"] = db.upsert_player_logs(conn, prows) if prows else 0
    if arows:
        db.upsert_player_assets(conn, arows)
    if not quiet and result["skipped"]:
        for note in result["skipped"][:3]:
            print(f"    skipped: {note}")
    return result
