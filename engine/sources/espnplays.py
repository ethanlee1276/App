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
the drives block is the only football source and this reads no other.

BASKETBALL WAS SEEN ON A FINISHED GAME, NOT A LIVE ONE. Four WNBA probes
ran between games (2026-09-04, 2026-09-05 three times) and showed no
`plays`; `--prefer post --date` then read the Aug 30 final, event
401857186, and printed the shape a basketball summary keeps:

    plays: [<play>, ...]                       # 392 on a finished game
    play:  id, sequenceNumber, period{number, displayValue},
           clock{displayValue}, team{id}, participants[{athlete{id}}],
           type{id, text}, scoringPlay, shootingPlay, scoreValue,
           pointsAttempted, awayScore, homeScore, coordinate{x, y},
           wallclock, text, shortDescription

No `drives`, no `scoringPlays`; `header` and `boxscore{players, teams}`
alongside. A basketball play names its team and its players BY ID ONLY,
so the row's `team` and `player` are looked up rather than read: the
team through the scoreboard's competitor ids (the same `team.id` that
`cfbdata._team_key` falls back on), the player through
`boxscore.players[].statistics[].athletes[].athlete{id, displayName}`,
which is the exact read `espnhoops.parse_summary` has built the NBA and
WNBA boards from for weeks. Whether a LIVE payload carries the same
`plays` block is the one thing a finished game cannot show; the first
in-progress probe is the confirmation, and a payload without it yields
no plays and says so.

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

WHAT IS NEVER READ. A play's `text` (and basketball's
`shortDescription`) and a drive's `description` are ESPN's written
account of the game. `espnprobe` reported them as `str(110)`, `str(64)`,
`str(9)` and `str(23)` on purpose, and this module composes every row
from the numbers beside them — down, distance, yard line, yards gained,
the type label, the score, the points a shot was worth — the same
position `engine/mlb/sources/pbp.recent_plays` takes with MLB's
`description`, and the injuries page's news section before it.

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

#: The leagues whose summary carries `drives`.
FOOTBALL = ("nfl", "cfb")

#: The leagues whose summary carries a top-level `plays` list — seen on
#: a finished WNBA game (event 401857186). NBA is the same
#: `sports/basketball` API one segment over, exactly as NFL is to CFB,
#: and is served on the same inference: confirmed by its first live game.
HOOPS = ("nba", "wnba")

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


def _athletes(payload: dict) -> dict[str, str]:
    """ESPN athlete id → display name, from the box score.

    The read `espnhoops.parse_summary` makes — `boxscore.players[]
    .statistics[].athletes[].athlete{id, displayName}` — and no other,
    because that one has produced the hoops boards for weeks and the
    rest of the block has not been looked at. A play names its
    participants by id alone, so without this the card could say "Jump
    Shot" but not who took it.
    """
    out: dict[str, str] = {}
    box = (payload or {}).get("boxscore") or {}
    for block in box.get("players") or []:
        if not isinstance(block, dict):
            continue
        for group in block.get("statistics") or []:
            for ath in (group or {}).get("athletes") or []:
                info = (ath or {}).get("athlete") or {}
                aid = str(info.get("id") or "")
                name = str(info.get("displayName") or "").strip()
                if aid and name:
                    out[aid] = name
    return out


def _sides_from_boxscore(payload: dict, league: str) -> dict[str, str]:
    """ESPN team id → the board's side key, from `boxscore.players[].team`.

    THE FALLBACK, not the source. `parse_summary` reads that dict's
    `abbreviation`; `id` beside it is the same ESPN team dict the
    scoreboard's competitor carries, and is resolved the same way, but
    the probe did not print this block and the scoreboard's ids are the
    verified route (see `hoops_plays`). A block with no ids maps nothing.
    """
    out: dict[str, str] = {}
    box = (payload or {}).get("boxscore") or {}
    for block in box.get("players") or []:
        team = (block or {}).get("team") if isinstance(block, dict) else None
        if not isinstance(team, dict):
            continue
        tid = str(team.get("id") or "")
        if tid:
            out[tid] = _side_key(team, league)
    return out


def hoops_plays(payload: dict, league: str = "wnba", limit: int = 6,
                sides: dict[str, str] | None = None) -> list[dict]:
    """The last plays of a basketball game, newest last, as STRUCTURED rows.

    ``sides`` maps ESPN's team id to the board's own side key — the
    caller has it from the scoreboard, whose competitor `team.id` is the
    field `cfbdata._team_key` already falls back on, so a play's `team`
    matches the card's `home`/`away` by the same route the score does.
    Without it the box score's team dicts are tried, and a team neither
    knows is written as `espn:{id}` rather than dropped — a play with a
    team is a fact even when the name is not to hand.

    `player` is the FIRST listed participant. The probe's one sample was
    the opening jump ball with three, and which of a shot's participants
    ESPN lists first (the shooter, on every summary this repo has
    looked at by hand) is a first-live-game check, not a promise.

    `event` is ESPN's type label ("Jump Shot", "Rebound", "Free Throw")
    — a category, not a sentence, the same thing the football row and
    the MLB row call `event`. `points` is `scoreValue`, the points the
    play put on the board (0 when it did not); `shot` is
    `shootingPlay`, so a miss can be told from a rebound.
    """
    plays = (payload or {}).get("plays")
    if not isinstance(plays, list):
        return []
    names = _athletes(payload)
    teams = dict(_sides_from_boxscore(payload, league))
    teams.update(sides or {})
    rows: list[dict] = []
    seen: set = set()
    for p in plays:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        if pid and pid in seen:
            continue
        if pid:
            seen.add(pid)
        tid = str((p.get("team") or {}).get("id") or "")
        parts = p.get("participants") or []
        first = (parts[0] or {}).get("athlete") if parts and isinstance(parts[0], dict) else None
        aid = str((first or {}).get("id") or "")
        ptype = p.get("type") or {}
        rows.append({
            "kind": "hoops",
            "id": pid,
            "period": _int((p.get("period") or {}).get("number")),
            "clock": str((p.get("clock") or {}).get("displayValue") or ""),
            "team": (teams.get(tid) or (f"espn:{tid}" if tid else "")),
            "player": names.get(aid, ""),
            "event": (ptype.get("text") or "Play"),
            "scoring": bool(p.get("scoringPlay")),
            "shot": bool(p.get("shootingPlay")),
            "points": _int(p.get("scoreValue")) or 0,
            "points_attempted": _int(p.get("pointsAttempted")) or 0,
            "away_score": _int(p.get("awayScore")),
            "home_score": _int(p.get("homeScore")),
        })
    return rows[-limit:] if limit and limit > 0 else rows
