"""Live NFL scores from ESPN's public scoreboard API.

    https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard

Keyless and free. The parser is pure and unit-tested; the fetch wrapper caches
briefly (live data moves fast) and degrades to :class:`DataUnavailable` when the
host is blocked. ``attach_live`` overlays the current state onto a slate's games
by matching team abbreviations.
"""

from __future__ import annotations

import json

from .fetch import fetch_text, DataUnavailable, DEFAULT_AGENT
from ..models import LiveStatus

ESPN_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# ESPN abbreviations that differ from nflverse.
ESPN_ABBR = {"WSH": "WAS", "LAR": "LA"}


def _abbr(a: str) -> str:
    return ESPN_ABBR.get(a, a)


def _state(espn_state: str) -> str:
    return {"pre": "scheduled", "in": "live", "post": "final"}.get(espn_state, "scheduled")


def parse_espn_scoreboard(data: dict) -> dict[frozenset, LiveStatus]:
    """Map an ESPN scoreboard payload to {frozenset({home, away}): LiveStatus}."""
    out: dict[frozenset, LiveStatus] = {}
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors", [])
        home = away = None
        hs = as_ = None
        for c in competitors:
            ab = _abbr(c.get("team", {}).get("abbreviation", ""))
            score = c.get("score")
            score = int(score) if str(score).lstrip("-").isdigit() else None
            if c.get("homeAway") == "home":
                home, hs = ab, score
            else:
                away, as_ = ab, score
        if not home or not away:
            continue
        status = ev.get("status", {}) or comp.get("status", {})
        stype = status.get("type", {})
        state = _state(stype.get("state", "pre"))
        period = stype.get("shortDetail", "") if state != "live" else ""
        live = LiveStatus(
            state=state, home_score=hs, away_score=as_,
            period=(f"Q{status.get('period')}" if state == "live" and status.get("period") else period),
            clock=status.get("displayClock", "") if state == "live" else "",
            detail=(comp.get("situation", {}) or {}).get("downDistanceText", ""),
            start_time=ev.get("date", ""),
        )
        out[frozenset((home, away))] = live
    return out


def fetch_live() -> dict[frozenset, LiveStatus]:
    # ESPN 403s an unfamiliar User-Agent; see fetch.DEFAULT_AGENT.
    text = fetch_text(ESPN_NFL, "espn_nfl_scoreboard.json", ttl=30,
                      user_agent=DEFAULT_AGENT)
    return parse_espn_scoreboard(json.loads(text))


def _near_in_time(a: str, b: str, days: int = 1) -> bool:
    """Are these two dates within ``days`` of each other?

    NOT equality, and the reason is a real fixture: DAL @ NYG kicks at
    20:20 Eastern on 2026-09-13, which is 00:20 UTC on the 14th. ESPN
    stamps its dates UTC and nflverse stores the local gameday, so every
    Sunday-night and Monday-night game disagrees by one. Requiring an exact
    match would silently switch the live board off for exactly the games
    people watch it during.

    Unparseable either side returns True — the caller falls back to the
    team match rather than dropping a live score over a bad string.
    """
    import datetime as _dt
    try:
        d1 = _dt.date.fromisoformat((a or "")[:10])
        d2 = _dt.date.fromisoformat((b or "")[:10])
    except ValueError:
        return True
    return abs((d1 - d2).days) <= days


def attach_live(slate) -> int:
    """Overlay live state onto a slate's games. Returns games matched.

    MATCHED ON TEAMS *AND* DATE, because teams alone is not a game.

    ESPN's scoreboard takes no season-type filter here — it returns whatever
    the NFL is playing today — so during August that is PRESEASON. The key
    is `frozenset({home, away})`, which ignores both the date and which side
    is home, so a preseason meeting between two teams that also face each
    other in Week 1 would paint its score straight onto the Week 1 card:
    a finished 17-13 sitting on a fixture a month away, on a board whose
    whole claim is that its numbers are real.

    It has never had a way to be caught, either. Nothing downstream settles
    from this overlay — the journal grades off `history.db` — so the failure
    is confined to the board, where it looks exactly like a working live
    score. Adding the preseason to the site is what made the collision
    reachable, so the guard goes in with it.

    A day of tolerance rather than equality; see `_near_in_time`.
    """
    try:
        board = fetch_live()
    except DataUnavailable:
        return 0
    n = 0
    for g in slate.games:
        live = board.get(frozenset((g.home, g.away)))
        if live and _near_in_time(getattr(live, "start_time", ""),
                                  getattr(g, "date", "")):
            g.live = live
            n += 1
    return n
