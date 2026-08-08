"""Live NFL scores from ESPN's public scoreboard API.

    https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard

Keyless and free. The parser is pure and unit-tested; the fetch wrapper caches
briefly (live data moves fast) and degrades to :class:`DataUnavailable` when the
host is blocked. ``attach_live`` overlays the current state onto a slate's games
by matching team abbreviations.
"""

from __future__ import annotations

import json
import re

from .fetch import fetch_text, DataUnavailable, DEFAULT_AGENT
from ..models import LiveStatus

ESPN_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# ESPN abbreviations that differ from nflverse.
ESPN_ABBR = {"WSH": "WAS", "LAR": "LA"}


def _abbr(a: str) -> str:
    return ESPN_ABBR.get(a, a)


def _state(espn_state: str) -> str:
    return {"pre": "scheduled", "in": "live", "post": "final"}.get(espn_state, "scheduled")


# "at DEN 45", "DEN 45", "MID 50", "at BUF 3". The side is a 2-4 letter
# abbreviation and the yard is 1-50; anything else is not a spot.
_SPOT_RE = re.compile(r"\b([A-Z]{2,4})\s+(\d{1,2})\s*$")


def spot_to_yard_line(text: str, home: str, away: str):
    """Absolute field position from a spot string, or None.

    0 is the HOME team's goal line and 100 is the away end zone; see the
    convention on :class:`LiveStatus`.

    WHY THE TEXT AND NOT A NUMBER. ESPN's situation block does carry a
    numeric `yardLine`, but its zero point is not documented and differs
    between the endpoints — read wrong it puts the ball on the opposite
    forty, which on a drawing is not a rounding error, it is the other
    team driving. The prose spot names the side explicitly, and the side
    is the only thing that was ever ambiguous. When the abbreviation is
    neither team's (ESPN writes "MID 50" at midfield, and college feeds
    use school codes we do not map) the yard still resolves if it is 50,
    and otherwise this returns None and nothing is drawn.
    """
    m = _SPOT_RE.search((text or "").strip())
    if not m:
        return None
    side, yard = _abbr(m.group(1)), int(m.group(2))
    if not 0 <= yard <= 50:
        return None
    if side == home:
        return float(yard)
    if side == away:
        return float(100 - yard)
    return 50.0 if yard == 50 else None


def parse_espn_scoreboard(data: dict) -> dict[frozenset, LiveStatus]:
    """Map an ESPN scoreboard payload to {frozenset({home, away}): LiveStatus}."""
    out: dict[frozenset, LiveStatus] = {}
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors", [])
        home = away = None
        hs = as_ = None
        by_id: dict[str, str] = {}
        for c in competitors:
            ab = _abbr(c.get("team", {}).get("abbreviation", ""))
            tid = str(c.get("team", {}).get("id", ""))
            if tid:
                by_id[tid] = ab
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
        sit = comp.get("situation", {}) or {}
        # Where the ball is, and who has it. Both are drawn on the card art
        # and both fail open: a spot that will not parse leaves `yard_line`
        # None and the field is drawn exactly as it was before this
        # existed. `possessionText` is the spot on its own ("DEN 45");
        # `downDistanceText` carries it on the tail of the down ("2nd & 7
        # at DEN 45"), and the same regex reads either.
        yard = None
        if state == "live":
            yard = (spot_to_yard_line(sit.get("possessionText", ""), home, away)
                    if sit.get("possessionText") else None)
            if yard is None:
                yard = spot_to_yard_line(sit.get("downDistanceText", ""), home, away)
        live = LiveStatus(
            state=state, home_score=hs, away_score=as_,
            period=(f"Q{status.get('period')}" if state == "live" and status.get("period") else period),
            clock=status.get("displayClock", "") if state == "live" else "",
            detail=sit.get("downDistanceText", ""),
            start_time=ev.get("date", ""),
            yard_line=yard,
            possession=(by_id.get(str(sit.get("possession", "")), "")
                        if state == "live" else ""),
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
