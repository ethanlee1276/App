"""Live MLB game state from the MLB Stats API schedule + linescore.

    https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=linescore

Keyless and free. The parser is pure and unit-tested; the fetch wrapper reuses
the cached JSON getter (blocked in some sandboxes). ``attach_live`` overlays
current state onto an MLB slate's games by team abbreviation.
"""

from __future__ import annotations

from ...models import LiveStatus
from ...sources.fetch import DataUnavailable
from .mlbstats import STATS_BASE, _get_json, TEAM_ID_ABBR


def _state(abstract: str) -> str:
    return {"Preview": "scheduled", "Live": "live", "Final": "final"}.get(abstract, "scheduled")


def parse_live(schedule_json: dict) -> dict[frozenset, LiveStatus]:
    """Map a schedule+linescore payload to {frozenset({home, away}): LiveStatus}."""
    out: dict[frozenset, LiveStatus] = {}
    for day in schedule_json.get("dates", []):
        for g in day.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {})
            away = teams.get("away", {}).get("team", {})
            home_ab = TEAM_ID_ABBR.get(home.get("id"), home.get("abbreviation", ""))
            away_ab = TEAM_ID_ABBR.get(away.get("id"), away.get("abbreviation", ""))
            if not home_ab or not away_ab:
                continue
            status = g.get("status", {})
            state = _state(status.get("abstractGameState", "Preview"))
            ls = g.get("linescore", {}) or {}
            inning = ls.get("currentInningOrdinal", "")
            half = ls.get("inningState", "")
            period = f"{half} {inning}".strip() if state == "live" else \
                     (status.get("detailedState", "") if state == "final" else "")
            outs = ls.get("outs") if state == "live" else None
            # Occupied bases from the offense block (a base key is present only
            # when a runner is on it).
            bases = None
            if state == "live":
                off = ls.get("offense", {}) or {}
                occ = [b for b, k in ((1, "first"), (2, "second"), (3, "third")) if off.get(k)]
                bases = occ
            out[frozenset((home_ab, away_ab))] = LiveStatus(
                state=state,
                home_score=teams.get("home", {}).get("score"),
                away_score=teams.get("away", {}).get("score"),
                period=period, outs=outs, bases=bases,
                start_time=g.get("gameDate", ""),
            )
    return out


def fetch_live(date: str) -> dict[frozenset, LiveStatus]:
    data = _get_json(
        f"{STATS_BASE}/schedule?sportId=1&date={date}&hydrate=linescore",
        f"mlb_live_{date}.json", ttl=30)
    return parse_live(data)


def attach_live(slate, date: str) -> int:
    try:
        board = fetch_live(date)
    except DataUnavailable:
        return 0
    n = 0
    for g in slate.games:
        live = board.get(frozenset((g.home, g.away)))
        if live:
            g.live = live
            n += 1
    return n
