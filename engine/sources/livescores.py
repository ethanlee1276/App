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


def attach_live(slate) -> int:
    """Overlay live state onto a slate's games. Returns games matched."""
    try:
        board = fetch_live()
    except DataUnavailable:
        return 0
    n = 0
    for g in slate.games:
        live = board.get(frozenset((g.home, g.away)))
        if live:
            g.live = live
            n += 1
    return n
