"""League news from ESPN's keyless site API, tagged with the teams and players
each story is about (2026-11-17).

The site's headlines (engine/sources/news.py) are each league's RSS feeds: a
title, a source and a link, twelve a league. A game report watching its own
game (engine/reportwatch; Ethan, 2026-11-17: "make sure the game reports keep
a constant watch and update on nfl news and injuries") needs to know WHICH
game a story is about, and a title is a poor witness to that. ESPN's site API
publishes the same newsroom as JSON, one keyless endpoint per league in the
envelope this repository already reads for scores and injuries:

    /apis/site/v2/sports/{sport}/{league}/news?limit=N

and each article carries `categories`: the league, the teams and the athletes
the story concerns, by name. That is the join.

WHAT IS TAKEN, AND WHAT IS NOT: the same line news.py draws. The headline,
the link out, ESPN's name, the time it was published, and the names of the
teams and athletes ESPN tagged. The description and the story are ESPN's
expression and are not read, so nothing downstream can show them.

The parser is pure, reads by key name and drops rather than guesses: an
article with no headline or no link is not a row. Cached through the
standard fetch layer, five minutes (a newsroom is not a scoreboard, and the
watcher that reads this runs every five). Standard library only.
"""

from __future__ import annotations

import datetime as dt

from .fetch import DEFAULT_AGENT, fetch_json

ROOT = "https://site.api.espn.com/apis/site/v2/sports"

#: The leagues with a newsroom feed, by the site's sport codes (the paths are
#: espninjuries.LEAGUES' own).
LEAGUES = {
    "nfl": f"{ROOT}/football/nfl/news",
    "cfb": f"{ROOT}/football/college-football/news",
    "nba": f"{ROOT}/basketball/nba/news",
    "wnba": f"{ROOT}/basketball/wnba/news",
    "nhl": f"{ROOT}/hockey/nhl/news",
    "mlb": f"{ROOT}/baseball/mlb/news",
    "cbb": f"{ROOT}/basketball/mens-college-basketball/news",
}

#: Seconds a fetched newsroom is believed before ESPN is asked again.
TTL = 300
#: Articles asked for in one read: a day of a league's newsroom and more.
LIMIT = 100


def _epoch(stamp) -> int:
    try:
        return int(dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return 0


def parse(payload) -> list[dict]:
    """ESPN's news envelope → ``[{title, link, source, epoch, teams, athletes}]``,
    newest first. `teams` and `athletes` are the names ESPN tagged the story
    with; the description is never read (see the module docstring)."""
    out = []
    for a in ((payload or {}).get("articles") or []):
        if not isinstance(a, dict):
            continue
        title = str(a.get("headline") or "").strip()
        link = (((a.get("links") or {}).get("web") or {}).get("href") or "").strip()
        if not title or not link.startswith("http"):
            continue
        teams, athletes = [], []
        for c in a.get("categories") or []:
            if not isinstance(c, dict):
                continue
            kind = str(c.get("type") or "").lower()
            name = str(c.get("description") or "").strip()
            if not name:
                inner = c.get("team") if kind == "team" else c.get("athlete") if kind == "athlete" else None
                name = str((inner or {}).get("description") or (inner or {}).get("displayName") or "").strip()
            if name and kind == "team" and name not in teams:
                teams.append(name)
            elif name and kind == "athlete" and name not in athletes:
                athletes.append(name)
        out.append({"title": title[:300], "link": link, "source": "ESPN",
                    "epoch": _epoch(a.get("published") or a.get("lastModified")),
                    "teams": teams, "athletes": athletes})
    out.sort(key=lambda r: -r["epoch"])
    return out


def fetch(league: str) -> list[dict]:
    """One league's newsroom, parsed. KeyError for a league with no feed;
    whatever the fetch layer raises for a feed that cannot be read."""
    payload = fetch_json(f"{LEAGUES[league]}?limit={LIMIT}", f"espn_news_{league}.json",
                         ttl=TTL, user_agent=DEFAULT_AGENT)
    return parse(payload)
