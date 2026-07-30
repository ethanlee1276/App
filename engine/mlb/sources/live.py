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


# Detailed states that the API reports under abstractGameState "Live" but where
# no pitch has been thrown yet — treat these as not-yet-started, not live.
_PREGAME_DETAIL = {"warmup", "pre-game", "pregame", "delayed start", "scheduled"}


def _state(abstract: str, detailed: str = "") -> str:
    base = {"Preview": "scheduled", "Live": "live", "Final": "final"}.get(abstract, "scheduled")
    if base == "live" and (detailed or "").strip().lower() in _PREGAME_DETAIL:
        return "scheduled"
    return base


def parse_live(schedule_json: dict) -> dict:
    """Map a schedule+linescore payload to a live board with THREE key
    shapes per game:

    * ``gamePk`` (int) — exact, the join attach_live prefers;
    * ``(frozenset({home, away}), gameNumber)`` — doubleheader-safe;
    * ``frozenset({home, away})`` — kept for single games only. On a
      doubleheader day the same pair plays twice, and this bare key once
      held whichever leg parsed LAST — both slate cards then wore one
      game's inning and score. An ambiguous key is now dropped entirely.
    """
    out: dict = {}
    pairs_seen: set = set()
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
            state = _state(status.get("abstractGameState", "Preview"),
                           status.get("detailedState", ""))
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
            st = LiveStatus(
                state=state,
                home_score=teams.get("home", {}).get("score"),
                away_score=teams.get("away", {}).get("score"),
                period=period, outs=outs, bases=bases,
                start_time=g.get("gameDate", ""),
            )
            pair = frozenset((home_ab, away_ab))
            out[(pair, int(g.get("gameNumber") or 1))] = st
            pk = g.get("gamePk")
            if pk:
                out[int(pk)] = st
            dh = (g.get("doubleHeader") or "N") != "N"
            if dh or pair in pairs_seen:
                out.pop(pair, None)      # two legs — the bare key lies
            else:
                out[pair] = st
            pairs_seen.add(pair)
    return out


def fetch_live(date: str) -> dict:
    data = _get_json(
        f"{STATS_BASE}/schedule?sportId=1&date={date}&hydrate=linescore",
        f"mlb_live_{date}.json", ttl=30)
    return parse_live(data)


def attach_live(slate, date: str) -> int:
    """Overlay live state onto the slate's games — by gamePk first (exact),
    then pair+leg number, then the bare pair (single games only)."""
    try:
        board = fetch_live(date)
    except DataUnavailable:
        return 0
    n = 0
    for g in slate.games:
        pair = frozenset((g.home, g.away))
        live = (board.get(int(getattr(g, "game_pk", 0) or 0))
                or board.get((pair, getattr(g, "game_number", 0) or 1))
                or board.get(pair))
        if live:
            g.live = live
            n += 1
    return n
