"""Who was on the ice with whom: the league's shift charts.

Ethan, 2026-10-03: "do all of them" — line combinations among them. A box
score says how long a skater played; it cannot say who he played with. The
league's stats host (``/stats/rest/en/shiftcharts``, keyless, one call a
game) lists every shift — player, period, start and end — and two skaters
whose shifts overlap most are linemates. engine/nhl/lines.py turns the
overlaps into forward lines and defence pairs.

A ROW HERE is one shift as absolute seconds from the opening faceoff
(period offsets of 1,200; overtime counted on). Goal and penalty events the
chart also carries (a non-shift ``typeCode``) are not shifts and are
dropped, as is any row with no player or a clock that will not read.

Pure parser, read by key name. This sandbox cannot reach the host;
`ingest.py nhl --probe` shows the box what comes back.
"""
from __future__ import annotations

from .fetch import fetch_json

STATS_API = "https://api.nhle.com/stats/rest/en"
#: The chart's code for a shift (goals and penalties carry others).
SHIFT_CODE = 517
PERIOD_S = 1200


def fetch_shifts(game_id, ttl: int = 30 * 86400) -> dict:
    return fetch_json(f"{STATS_API}/shiftcharts?cayenneExp=gameId={game_id}",
                      f"nhl_shifts_{game_id}.json", ttl=ttl)


def _clock(text) -> int | None:
    try:
        m, s = str(text).split(":")
        return int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def parse_shifts(payload: dict) -> dict:
    """{team: {player: [(start_s, end_s), ...]}} for one game."""
    out: dict = {}
    for r in (payload or {}).get("data") or []:
        if not isinstance(r, dict):
            continue
        code = r.get("typeCode")
        if code not in (None, SHIFT_CODE) and str(code) != str(SHIFT_CODE):
            continue
        name = f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip()
        team = str(r.get("teamAbbrev") or "")
        start, end = _clock(r.get("startTime")), _clock(r.get("endTime"))
        try:
            per = int(r.get("period") or 0)
        except (TypeError, ValueError):
            per = 0
        if not (name and team and per and start is not None and end is not None) or end <= start:
            continue
        base = (per - 1) * PERIOD_S
        out.setdefault(team, {}).setdefault(name, []).append((base + start, base + end))
    return out
