"""An ESPN fantasy league, read without a credential.

Ethan, 2026-08-15, asked to sync more than Sleeper and named ESPN.

THE ONLY VERSION OF THIS THAT SHIPS IS THE ONE THAT NEEDS NO LOGIN.

ESPN's fantasy read API answers for a league that is set **viewable by
the public** with no authentication at all. A PRIVATE league needs
`espn_s2` and `SWID` — session cookies lifted out of a logged-in browser,
which grant full account access, last for months and cannot be scoped to
one league. This project does not take credentials, and a session cookie
is a credential.

So: public leagues work here, and a private one gets a message naming the
setting to change rather than a prompt for cookies. That is a real
limitation and it is the right one — see docs/FANTASY_PLATFORMS.md.

WRITTEN AGAINST AN API THIS CONTAINER CANNOT REACH, same as
`nflpreseason.py` was, and with the same three defences rather than hope:

  * the raw payload is CACHED BEFORE it is parsed, so a wrong parse costs
    an edit and not another round of requests;
  * a shape it does not recognise RAISES instead of returning empty — an
    empty league and an unparsed one look identical on a page and mean
    opposite things;
  * anything it cannot map is REPORTED, never silently dropped. ESPN
    describes scoring as numeric `statId`s, and a mapping written from
    memory is exactly how `pass_att` shipped as a market that did not
    exist. Unknown ids come back in `unmapped` so the first real run
    tells us what to add, instead of quietly scoring the league wrong.

Standard library only, through the shared cache-first fetcher.
"""

from __future__ import annotations

import json

from .fetch import CACHE_DIR, DEFAULT_AGENT, DataUnavailable, fetch_text

#: The read host. ESPN moved fantasy reads here from `fantasy.espn.com`;
#: both have answered in the recent past, so the older one is a fallback
#: rather than a replacement.
BASE = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
        "{season}/segments/0/leagues/{league}")
FALLBACK = ("https://fantasy.espn.com/apis/v3/games/ffl/seasons/"
            "{season}/segments/0/leagues/{league}")
#: Views ESPN needs asked for by name or it returns a skeleton.
VIEWS = ("mSettings", "mTeam", "mRoster")
TTL = 600

#: ESPN's lineup slot ids. These are stable and long-documented; the
#: SCORING ids are the ones this file refuses to guess at.
SLOT_IDS = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DEF", 17: "K",
    20: "BN", 21: "IR", 23: "FLEX",
}
#: ESPN position ids for a player's actual position.
POSITION_IDS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}

#: ESPN `statId` → the scoring key `fantasy_lineup` understands.
#:
#: DELIBERATELY SHORT. Only the ids this repo can act on are here, and
#: everything else is reported as unmapped rather than assumed to be
#: zero — a scoring rule silently dropped is a lineup silently wrong.
STAT_IDS = {
    3: "pass_yd", 4: "pass_td", 20: "pass_int",
    24: "rush_yd", 25: "rush_td",
    42: "rec_yd", 43: "rec_td", 53: "rec",
}


def _url(season: int, league: str, host: str = BASE) -> str:
    views = "&".join(f"view={v}" for v in VIEWS)
    return host.format(season=int(season), league=str(league)) + "?" + views


def fetch_league(season: int, league_id: str, ttl: int = TTL) -> dict:
    """The raw league payload, cached to disk before anything reads it.

    A private league answers 401; that is turned into a message naming
    the setting to change, because "unauthorized" on its own sends the
    reader looking for a password field this app does not have.
    """
    name = f"espn_ffl_{season}_{league_id}.json"
    last = None
    for host in (BASE, FALLBACK):
        try:
            text = fetch_text(_url(season, league_id, host), name, ttl=ttl,
                              user_agent=DEFAULT_AGENT)
        except DataUnavailable as exc:
            last = exc
            if "401" in str(exc) or "403" in str(exc):
                raise DataUnavailable(
                    "ESPN refused this league without a login, which means "
                    "it is PRIVATE. This app does not take session cookies "
                    "— ask the commissioner to set the league to viewable "
                    "by the public and it reads with no credential at all."
                ) from exc
            continue
        try:
            return json.loads(text)
        except ValueError as exc:
            raise DataUnavailable(
                f"ESPN returned something that is not JSON for league "
                f"{league_id}; the raw body is cached at {CACHE_DIR / name}"
            ) from exc
    raise DataUnavailable(f"ESPN unreachable for league {league_id}: {last}")


def parse_scoring(payload: dict) -> dict:
    """``{"scoring": {key: points}, "unmapped": [{statId, points}]}``.

    ESPN gives points per `statId`. Anything not in `STAT_IDS` comes back
    in `unmapped` — the whole reason this returns two things instead of
    one. A league scoring a rule we ignored is a lineup we got wrong, and
    it should say so on the page rather than in a log nobody reads.
    """
    settings = (payload or {}).get("settings")
    if not isinstance(settings, dict):
        raise DataUnavailable(
            "ESPN payload has no `settings` — the shape has changed, or "
            "this is an error body. Nothing was parsed.")
    items = ((settings.get("scoringSettings") or {}).get("scoringItems"))
    if items is None:
        raise DataUnavailable(
            "ESPN payload has no `scoringSettings.scoringItems`. Nothing "
            "was parsed — an empty scoring map would read as a league that "
            "scores nothing.")
    scoring, unmapped = {}, []
    for it in items or []:
        sid = it.get("statId")
        pts = it.get("points")
        if pts is None:
            pts = (it.get("pointsOverrides") or {}).get("16")
        if pts is None:
            continue
        key = STAT_IDS.get(sid)
        if key:
            scoring[key] = float(pts)
        elif float(pts) != 0.0:
            unmapped.append({"statId": sid, "points": float(pts)})
    return {"scoring": scoring, "unmapped": unmapped}


def parse_slots(payload: dict) -> list[str]:
    """Roster slots in the shape `fantasy_lineup` expects.

    ESPN gives counts per slot id; this expands them into the flat,
    repeated list the optimiser reads ("QB","RB","RB","WR",...).
    """
    settings = (payload or {}).get("settings") or {}
    counts = (settings.get("rosterSettings") or {}).get("lineupSlotCounts")
    if not isinstance(counts, dict):
        raise DataUnavailable(
            "ESPN payload has no `rosterSettings.lineupSlotCounts`; the "
            "roster shape is unknown and guessing it would optimise a "
            "lineup for a league that does not exist.")
    out = []
    for sid, n in sorted(counts.items(), key=lambda kv: int(kv[0])):
        slot = SLOT_IDS.get(int(sid))
        if not slot:
            continue                       # IDP and other slots we do not model
        out.extend([slot] * int(n or 0))
    return out


def parse_rosters(payload: dict) -> dict:
    """``{team label: [{player, position}]}`` for every team in the league."""
    teams = (payload or {}).get("teams")
    if teams is None:
        raise DataUnavailable(
            "ESPN payload has no `teams` — nothing was parsed.")
    out: dict = {}
    for t in teams or []:
        label = (t.get("name")
                 or " ".join(x for x in (t.get("location"), t.get("nickname"))
                             if x).strip()
                 or f"Team {t.get('id')}")
        rows = []
        for entry in ((t.get("roster") or {}).get("entries") or []):
            p = ((entry.get("playerPoolEntry") or {}).get("player") or {})
            name = p.get("fullName") or ""
            pos = POSITION_IDS.get(p.get("defaultPositionId"))
            if name and pos:
                rows.append({"player": name, "position": pos})
        out[label] = rows
    return out


def owner_of(payload: dict, member_id: str) -> str | None:
    """Which team label belongs to a member id, or None.

    None is the honest answer for someone who is not in the league, and
    it is what stops the desk optimising a stranger's roster.
    """
    for t in (payload or {}).get("teams") or []:
        owners = t.get("owners") or []
        if member_id and str(member_id) in [str(o) for o in owners]:
            return (t.get("name")
                    or " ".join(x for x in (t.get("location"),
                                            t.get("nickname")) if x).strip()
                    or f"Team {t.get('id')}")
    return None


def league(season: int, league_id: str, ttl: int = TTL) -> dict:
    """Everything the league desk needs, in the shared adapter shape.

    Matches what the Sleeper path already produces so the desk never
    learns which platform it is talking to:
    ``{name, slots, scoring, rosters, unmapped}``.
    """
    payload = fetch_league(season, league_id, ttl=ttl)
    sc = parse_scoring(payload)
    return {
        "platform": "espn",
        "name": ((payload.get("settings") or {}).get("name")
                 or f"ESPN league {league_id}"),
        "season": int(season),
        "slots": parse_slots(payload),
        "scoring": sc["scoring"],
        "unmapped": sc["unmapped"],
        "rosters": parse_rosters(payload),
    }
