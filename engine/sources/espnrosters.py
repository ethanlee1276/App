"""Every club's current roster from ESPN's keyless site API — NBA and WNBA.

Ethan, 2026-10-03: "make sure our rosters are good and our team data is
good ... I want every single sport to have the same thing." Basketball's
roster page was built from appearances (`engine.rosters.from_game_logs`):
right in March, wrong every October, when it is last season's team with
every summer signing missing. ESPN publishes each club's roster on the
same host the injury board and the standings already come from.

Two calls per club at most — the league's team list once (for ESPN's ids),
then one roster each — on a six-hour cache. A club whose roster will not
load is named in the second return value so the page can say so.

Pure parsers, read by key name: an athlete with no name is not a row.
Basketball rosters arrive as a flat list; football's are grouped
(offense/defense/special teams), and both shapes are walked.
"""
from __future__ import annotations

from .. import divisions
from .fetch import DEFAULT_AGENT, DataUnavailable, fetch_json

ROOT = "https://site.api.espn.com/apis/site/v2/sports"
PATHS = {"nba": "basketball/nba", "wnba": "basketball/wnba"}
ROSTER_TTL = 6 * 3600


def parse_teams(sport: str, payload: dict) -> dict:
    """``{our abbreviation: ESPN team id}`` from the league's team list."""
    out = {}
    for sp in (payload or {}).get("sports") or []:
        for lg in (sp or {}).get("leagues") or []:
            for t in (lg or {}).get("teams") or []:
                team = (t or {}).get("team") or {}
                ab, ident = team.get("abbreviation"), team.get("id")
                if ab and ident:
                    out[divisions.canonical(sport, ab)] = str(ident)
    return out


def _athletes(payload: dict):
    for a in (payload or {}).get("athletes") or []:
        if isinstance(a, dict) and isinstance(a.get("items"), list):
            yield from (x for x in a["items"] if isinstance(x, dict))
        elif isinstance(a, dict):
            yield a


def parse_roster(payload: dict) -> list[dict]:
    """``[{player, position, number, age, height, weight, birthplace,
    headshot, status}]`` for one club."""
    out = []
    for a in _athletes(payload):
        name = str(a.get("fullName") or a.get("displayName") or "").strip()
        if not name:
            continue
        pos = a.get("position")
        pos = (pos.get("abbreviation") or pos.get("name") or "") if isinstance(pos, dict) else (pos or "")
        shot = a.get("headshot")
        shot = shot.get("href") if isinstance(shot, dict) else shot
        born = a.get("birthPlace") if isinstance(a.get("birthPlace"), dict) else {}
        hurt = [i for i in (a.get("injuries") or []) if isinstance(i, dict)]
        out.append({
            "player": name,
            "position": str(pos).upper(),
            "number": str(a.get("jersey") or "").strip() or None,
            "age": a.get("age") if isinstance(a.get("age"), int) else None,
            "height": a.get("displayHeight") or None,
            "weight": a.get("displayWeight") or None,
            "birthplace": ", ".join(x for x in (born.get("city"), born.get("state") or born.get("country")) if x)
            or None,
            "headshot": str(shot or "") if str(shot or "").startswith("http") else "",
            "status": str(hurt[0].get("status") or "") if hurt else "",
        })
    return out


def fetch_league(sport: str, ttl: int = ROSTER_TTL, fetch=None) -> tuple[dict, list]:
    """``({our abbreviation: [people]}, [clubs that would not load])``."""
    path = PATHS.get(sport)
    if not path:
        raise DataUnavailable(f"no ESPN roster path for {sport}")
    fetch = fetch or (lambda url, name: fetch_json(url, name, ttl=ttl, user_agent=DEFAULT_AGENT))
    ids = parse_teams(sport, fetch(f"{ROOT}/{path}/teams", f"espn_{sport}_teams.json"))
    if not ids:
        raise DataUnavailable(f"ESPN listed no {sport} teams")
    out, missed = {}, []
    for ab, ident in sorted(ids.items()):
        try:
            people = parse_roster(fetch(f"{ROOT}/{path}/teams/{ident}/roster",
                                        f"espn_{sport}_roster_{ident}.json"))
        except DataUnavailable:
            missed.append(ab)
            continue
        if people:
            out[ab] = people
        else:
            missed.append(ab)
    return out, missed
