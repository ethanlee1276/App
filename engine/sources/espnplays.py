"""Live football drives from ESPN's game summary.

    https://site.api.espn.com/apis/site/v2/sports/football/{league}/summary?event={id}

WRITTEN AGAINST A PAYLOAD THAT WAS LOOKED AT FIRST. `espnprobe.py` ran on
the droplet on 2026-09-05 during a live college game (event 401856664,
state "in") and printed the structure — key names, types, lengths, the
values of numbers and booleans, never a play's text. This module reads
exactly the keys it reported and nothing it did not:

    drives: {current: <drive>, previous: [<drive>, ...]}
    drive:  id, team{abbreviation, displayName, id, ...}, offensivePlays,
            yards, start{period{number}, yardLine, text},
            timeElapsed{displayValue}, plays[...], description
    play:   id, sequenceNumber, period{number}, clock{displayValue},
            start{down, distance, yardLine, yardsToEndzone, team},
            end{...}, statYardage, type{text, abbreviation, id},
            scoringPlay, isTurnover, isPenalty, awayScore, homeScore,
            text, wallclock, modified

Top-level `plays` and `scoringPlays` were ABSENT on that live game, so
the drives block is the only source and this reads no other.

TWO THINGS THE PROBE SHOWED THAT DECIDE THE CODE BELOW. First,
`drives.current` and the single entry in `drives.previous` were
byte-for-byte the same shape and size — the same drive — so `previous`
evidently carries every drive so far INCLUDING the one in progress, and
concatenating the two would print the current drive twice. Plays are
de-duplicated by their own `id`, which is correct under either reading.
Second, a drive's `team` dict carries the same fields the scoreboard's
competitor `team` does, so `livescores._side_key` resolves it into the
board's own vocabulary and a play's team label matches the card's
`home`/`away` by construction rather than by luck.

WHAT IS NEVER READ. A play's `text` and a drive's `description` are
ESPN's written account of the game. `espnprobe` reported them as
`str(110)` and `str(23)` on purpose, and this module composes every row
from the numbers beside them — down, distance, yard line, yards gained,
the type label, the score — the same position `engine/mlb/sources/pbp.
recent_plays` takes with MLB's `description`, and the injuries page's
news section before it.

NFL IS INFERRED, NOT YET SEEN. The NFL probe ran pre-game and showed no
drives (correct for a game that has not kicked off). It is the same
`sports/football` API one segment over, so this module serves both — and
the first live NFL game is the confirmation. A payload with no `drives`
yields no plays and says so, rather than an empty strip that reads as
"nothing has happened yet".
"""

from __future__ import annotations

import json

from .fetch import DEFAULT_AGENT, fetch_text
from .livescores import ESPN_SCOREBOARD, _side_key

#: One segment different from the scoreboard, per league.
ESPN_SUMMARY = {lg: url[:-len("scoreboard")] + "summary"
                for lg, url in ESPN_SCOREBOARD.items()}

#: The leagues whose summary carries `drives`. Basketball has not been
#: probed live yet (both pre-game payloads showed no `plays` block), so
#: it is deliberately not here until it has.
FOOTBALL = ("nfl", "cfb")

#: A drive moves a few times a minute; the scoreboard loop runs every
#: twelve seconds. Thirty seconds is one refetch per two or three polls.
LIVE_TTL = 30


def fetch_summary(league: str, event_id: str, ttl: int = LIVE_TTL) -> dict:
    """One game's summary, cached under its own live name.

    `espn_{league}_live_{event}.json` — the `espn_nfl_` / `espn_cfb_`
    prune prefixes already cover it, so a season of live games does not
    accumulate. NO User-Agent header: `fetch.DEFAULT_AGENT` is the
    sentinel for "send none", which is what every ESPN endpoint here
    accepts and what a custom string gets a 403 for.
    """
    url = f"{ESPN_SUMMARY[league]}?event={event_id}"
    text = fetch_text(url, f"espn_{league}_live_{event_id}.json", ttl=ttl,
                      user_agent=DEFAULT_AGENT)
    return json.loads(text)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _drives(payload: dict) -> list[dict]:
    """Every drive so far, in order, the one in progress last."""
    block = (payload or {}).get("drives") or {}
    if not isinstance(block, dict):
        return []
    out = list(block.get("previous") or [])
    cur = block.get("current")
    if isinstance(cur, dict):
        out.append(cur)
    return [d for d in out if isinstance(d, dict)]


def football_plays(payload: dict, league: str = "cfb",
                   limit: int = 6) -> list[dict]:
    """The last completed plays, newest last, as STRUCTURED rows.

    A row is composed from the fields the probe reported and never from
    `text`. `team` is the DRIVE's team resolved through `_side_key`, so
    it is the same string the card's `home`/`away` carry. `event` is
    ESPN's type label ("Rush", "Pass Reception", "Punt") — a category,
    not a sentence — and is what the MLB row calls its `event` too, so
    one renderer filter serves both.

    De-duplicated by play `id`: `drives.previous` was observed to include
    the drive in progress, and without this the current drive prints
    twice. Newest LAST because that is how a play-by-play reads.
    """
    rows: list[dict] = []
    seen: set = set()
    for drive in _drives(payload):
        team = _side_key(drive.get("team") or {}, league)
        for p in drive.get("plays") or []:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "")
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            start = p.get("start") or {}
            ptype = p.get("type") or {}
            rows.append({
                "kind": "football",
                "id": pid,
                "period": _int((p.get("period") or {}).get("number")),
                "clock": str((p.get("clock") or {}).get("displayValue") or ""),
                "team": team,
                "event": (ptype.get("text") or ptype.get("abbreviation")
                          or "Play"),
                "down": _int(start.get("down")) or None,
                "distance": _int(start.get("distance")),
                "yard_line": _int(start.get("yardLine")),
                "yards": _int(p.get("statYardage")) or 0,
                "scoring": bool(p.get("scoringPlay")),
                "turnover": bool(p.get("isTurnover")),
                "penalty": bool(p.get("isPenalty")),
                "away_score": _int(p.get("awayScore")),
                "home_score": _int(p.get("homeScore")),
            })
    return rows[-limit:] if limit and limit > 0 else rows


def current_drive(payload: dict, league: str = "cfb") -> dict | None:
    """The drive in progress as numbers: team, plays, yards, time.

    Composed from `offensivePlays`, `yards` and `timeElapsed` rather than
    from `description`, which is ESPN's sentence saying the same thing.
    None when the payload has no current drive — between drives, at the
    half, or on a payload with no drives block at all.
    """
    block = (payload or {}).get("drives") or {}
    cur = block.get("current") if isinstance(block, dict) else None
    if not isinstance(cur, dict):
        return None
    return {
        "team": _side_key(cur.get("team") or {}, league),
        "plays": _int(cur.get("offensivePlays")) or 0,
        "yards": _int(cur.get("yards")) or 0,
        "elapsed": str((cur.get("timeElapsed") or {}).get("displayValue")
                       or ""),
        "start_yard_line": _int((cur.get("start") or {}).get("yardLine")),
        "period": _int(((cur.get("start") or {}).get("period") or {})
                       .get("number")),
    }
