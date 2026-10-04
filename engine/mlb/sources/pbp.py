"""Pitch-by-pitch from the free MLB Stats API.

    https://statsapi.mlb.com/api/v1/game/{gamePk}/playByPlay

Keyless, and the same host `mlbstats.py` and `statslogs.py` already use
for boxscores, schedules and people. `docs/PITCH_LEVEL_SCOPE.md` is why
this exists: MLB_MODEL §5 parks velocity trend, TTO and pitch-count
projection behind "need pitch-level feed", pointing at Baseball Savant —
and three of those four need nothing Savant has. This endpoint carries,
per pitch, the speed, spin, break, plate location and pitch type they
want, and the repo had never called it.

Measured on a real game: 656,647 bytes. About 640 KB, so the last five
starts of a night's ten probable starters is ~32 MB before caching, and
most of it is already on disk from previous nights.

WHAT A `playEvent` IS, since it is the one thing easy to get wrong: not
every event is a pitch. Pickoffs, mound visits, substitutions, stepoffs
and challenges all appear in the same list. `isPitch` separates them, and
a parser that skips the check counts a pickoff throw as a 0 mph fastball.

The parsers here are PURE and unit-tested against a fixture; the fetch
wrapper caches and degrades exactly like its neighbours. Nothing in this
module prices anything — see the last section of the scope doc for why
that is deliberate rather than unfinished.
"""

from __future__ import annotations

from .mlbstats import STATS_BASE, _get_json

#: A completed game's pitches never change, so the cache can be long. The
#: only reason it is not infinite is a game corrected after the fact.
FINAL_TTL = 7 * 24 * 3600


def fetch_playbyplay(game_pk, ttl: int = FINAL_TTL) -> dict:
    """Raw payload for one game. Cached like every other statsapi call."""
    return _get_json(f"{STATS_BASE}/game/{game_pk}/playByPlay",
                     f"mlb_pbp_{game_pk}.json", ttl=ttl)


#: How long a live game's plays may sit. The scoreboard runs on a
#: twelve-second clock; a half-minute-old at-bat is still the current
#: at-bat, and 640 KB a game is not something to re-fetch every twelve
#: seconds on a one-vCPU box.
LIVE_TTL = 30


def fetch_live_playbyplay(game_pk, ttl: int = LIVE_TTL) -> dict:
    """The same endpoint for a game IN PROGRESS, under its own cache name.

    A DIFFERENT FILE, AND THAT IS THE WHOLE POINT. `fetch_playbyplay`
    caches under `mlb_pbp_{pk}.json` for SEVEN DAYS, because "a completed
    game's pitches never change". Reading a live game through it would
    write a HALF-PLAYED payload to that name — and then the velocity,
    times-through-order and pitch-count parsers, which have no way to
    tell a partial payload from a finished one, would model tonight's
    starter off four innings for the next week.

    So the live read is a separate name that the same `mlb_pbp_` prune
    prefix still covers. The cost is one duplicate fetch per game, once,
    the first time the finished game is asked for.
    """
    return _get_json(f"{STATS_BASE}/game/{game_pk}/playByPlay",
                     f"mlb_pbp_live_{game_pk}.json", ttl=ttl)


#: Half-inning codes, so the front end never has to parse prose.
_HALF = {"top": "T", "bottom": "B"}


def recent_plays(payload: dict, limit: int = 6) -> list[dict]:
    """The last completed at-bats, newest last, as STRUCTURED rows.

    WRITTEN FROM THE FIELDS, NOT FROM THEIR SENTENCE. Every play carries
    `result.description` — MLB's own prose — and this deliberately does
    not read it. The repo already took this position once, for the same
    reason, when the injuries page grew a news section: a public fact
    (who batted, what happened, the score) is ours to state; somebody
    else's written account of it is theirs. The caller composes "Judge —
    Home Run (2 RBI)" from `event`, `batter` and `rbi`.

    A play with no `result.event` is NOT finished — it is the at-bat in
    progress, and the feed carries it in the same list. Emitting it would
    put an empty row at the top of the card every time somebody steps in.

    Newest LAST because that is the order a play-by-play reads on a page
    and the order the caller would otherwise have to reverse.
    """
    plays = []
    for p in (payload or {}).get("allPlays") or []:
        result = p.get("result") or {}
        event = (result.get("event") or "").strip()
        if not event:
            continue                   # the at-bat still being played
        about = p.get("about") or {}
        matchup = p.get("matchup") or {}
        inning = about.get("inning")
        rbi = result.get("rbi")
        plays.append({
            "inning": int(inning) if isinstance(inning, int) else None,
            "half": _HALF.get(str(about.get("halfInning") or "").lower(), ""),
            "batter": ((matchup.get("batter") or {}).get("fullName") or ""),
            "pitcher": ((matchup.get("pitcher") or {}).get("fullName") or ""),
            "event": event,
            "event_type": (result.get("eventType") or ""),
            "rbi": int(rbi) if isinstance(rbi, int) and rbi else 0,
            "scoring": bool(about.get("isScoringPlay")),
            "away_score": result.get("awayScore"),
            "home_score": result.get("homeScore"),
        })
    return plays[-limit:] if limit and limit > 0 else plays


#: The umpire's call codes, to a word. `details.call.code` is the field
#: this repo has read since the pitch parser shipped; the WORDS are the
#: public MLB vocabulary for those codes and are kept here rather than
#: read off `details.description`, which is the feed's sentence. A code
#: not in the table falls back to `details.call.description` when the
#: payload carries one, else to the code itself — never to nothing.
CALLS = {
    "B": "Ball", "*B": "Ball in dirt", "V": "Automatic ball",
    "C": "Called strike", "S": "Swinging strike", "W": "Swinging strike",
    "T": "Foul tip", "F": "Foul", "L": "Foul bunt", "O": "Foul tip out",
    "M": "Missed bunt", "Q": "Swinging pitchout", "R": "Foul pitchout",
    "P": "Pitchout", "I": "Intentional ball", "H": "Hit by pitch",
    "X": "In play, out", "D": "In play, no out", "E": "In play, runs",
    "J": "In play, out", "Z": "In play, runs",
}


def _hit(ev: dict) -> dict | None:
    """The batted-ball data on an in-play event, or None.

    `hitData` HAS NOT BEEN READ BY THIS REPO BEFORE. Its keys —
    `launchSpeed`, `launchAngle`, `totalDistance`, `trajectory`,
    `coordinates{coordX, coordY}` — are the Stats API's published names
    and every read is tolerant: a payload without them yields None and
    the page draws no arc. docs/DROPLET_CHECKS.md §2 carries the probe
    that prints the real shape off a cached game; until it has run this
    is the one part of the file built on the documentation rather than
    on a payload looked at.
    """
    hd = ev.get("hitData")
    if not isinstance(hd, dict):
        return None
    co = hd.get("coordinates") or {}
    out = {
        "launch_speed": _num(hd.get("launchSpeed")),
        "launch_angle": _num(hd.get("launchAngle")),
        "distance": _num(hd.get("totalDistance")),
        "trajectory": str(hd.get("trajectory") or ""),
        "x": _num(co.get("coordX")),
        "y": _num(co.get("coordY")),
    }
    return out if any(v not in (None, "") for v in out.values()) else None


def _when(d: dict) -> str:
    """An ISO instant off `about`/an event, or "". Read tolerantly:
    `startTime`/`endTime` are documented on both and have not been
    verified here; the page shows a time only when one arrives."""
    for k in ("endTime", "startTime"):
        v = (d or {}).get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def game_events(payload: dict) -> list[dict]:
    """Every pitch and every completed at-bat, in game order, as rows.

    THE PLAY-BY-PLAY PAGE'S FEED (Ethan's render, 2026-09-05: "Ball ·
    Juan Soto takes a ball high", "Called Strike", "Lineout to CF ·
    102.4 MPH, 379 FT"). Two kinds of row share one list so the rail
    reads in order:

      kind "pitch"  — one per pitch: the call in words (`CALLS`), the
                      pitch type's name and its speed, the batter and
                      the pitcher, the count after it where the payload
                      says, the same at-bat index the result row has.
      kind "atbat"  — the completed plate appearance, the SAME row
                      `recent_plays` builds, plus `hit` (see `_hit`) on
                      a ball put in play.

    Composed from `event`, `call.code`, `type.description`, `startSpeed`
    and the batter's name — never from `details.description` or
    `result.description`, the feed's prose. The at-bat in progress
    contributes its pitches and no result row; `current_at_bat` says
    who is up.
    """
    out: list[dict] = []
    for p in (payload or {}).get("allPlays") or []:
        about = p.get("about") or {}
        matchup = p.get("matchup") or {}
        result = p.get("result") or {}
        inning = about.get("inning")
        half = _HALF.get(str(about.get("halfInning") or "").lower(), "")
        ab = about.get("atBatIndex")
        batter = (matchup.get("batter") or {}).get("fullName") or ""
        pitcher = (matchup.get("pitcher") or {}).get("fullName") or ""
        hit = None
        for ev in p.get("playEvents") or []:
            details = ev.get("details") or {}
            is_pitch = ev.get("isPitch")
            if is_pitch is None:
                is_pitch = details.get("isPitch")
            if not is_pitch:
                continue
            call = details.get("call") or {}
            code = str(call.get("code") or "")
            pd = ev.get("pitchData") or {}
            cnt = ev.get("count") or {}
            row = {
                "kind": "pitch",
                "inning": int(inning) if isinstance(inning, int) else None,
                "half": half,
                "at_bat": ab,
                "n": ev.get("pitchNumber"),
                "call": CALLS.get(code) or str(call.get("description") or code or "Pitch"),
                "code": code,
                "pitch": str((details.get("type") or {}).get("description") or ""),
                "speed": _num(pd.get("startSpeed")),
                "batter": batter,
                "pitcher": pitcher,
                "balls": cnt.get("balls") if isinstance(cnt.get("balls"), int) else None,
                "strikes": cnt.get("strikes") if isinstance(cnt.get("strikes"), int) else None,
                "in_play": bool(details.get("isInPlay")),
                "time": _when(ev),
            }
            out.append(row)
            h = _hit(ev)
            if h:
                hit = h
        event = (result.get("event") or "").strip()
        if not event:
            continue                   # the at-bat still being played
        rbi = result.get("rbi")
        out.append({
            "kind": "atbat",
            "inning": int(inning) if isinstance(inning, int) else None,
            "half": half,
            "at_bat": ab,
            "batter": batter,
            "pitcher": pitcher,
            "event": event,
            "event_type": (result.get("eventType") or ""),
            "rbi": int(rbi) if isinstance(rbi, int) and rbi else 0,
            "scoring": bool(about.get("isScoringPlay")),
            "away_score": result.get("awayScore"),
            "home_score": result.get("homeScore"),
            "hit": hit,
            "time": _when(about),
        })
    return out


def current_at_bat(payload: dict) -> dict | None:
    """Who is up and who is throwing, from the at-bat in progress.

    The last play with no `result.event` is the one being played — the
    same rule `recent_plays` uses to skip it. Names come from `matchup`,
    the fields the row parser has always read; the count and outs come
    from the fast scoreboard's linescore on the page, which the card
    already carries, so nothing here guesses at a `count` block.
    """
    plays = (payload or {}).get("allPlays") or []
    if not plays:
        return None
    last = plays[-1]
    if ((last.get("result") or {}).get("event") or "").strip():
        return None                    # between at-bats, or the game is over
    matchup = last.get("matchup") or {}
    about = last.get("about") or {}
    pitches = [e for e in (last.get("playEvents") or [])
               if (e.get("isPitch") if e.get("isPitch") is not None
                   else (e.get("details") or {}).get("isPitch"))]
    return {
        "batter": (matchup.get("batter") or {}).get("fullName") or "",
        "batter_id": (matchup.get("batter") or {}).get("id"),
        "pitcher": (matchup.get("pitcher") or {}).get("fullName") or "",
        "pitcher_id": (matchup.get("pitcher") or {}).get("id"),
        "inning": about.get("inning") if isinstance(about.get("inning"), int) else None,
        "half": _HALF.get(str(about.get("halfInning") or "").lower(), ""),
        "pitches": len(pitches),
    }


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pitches(payload: dict) -> list[dict]:
    """Every PITCH in the game, flat, in order.

    One dict per pitch rather than the nested payload, because everything
    downstream — velocity trend, TTO, pitch counts — wants a sequence and
    none of them wants to relearn this shape.

    Tolerant by construction: statsapi omits `pitchData` on some events
    and whole sub-objects on others, and a KeyError here would take down
    a nightly build over one malformed pitch in a rain-shortened game.
    """
    out: list[dict] = []
    for play in (payload.get("allPlays") or []):
        about = play.get("about") or {}
        matchup = play.get("matchup") or {}
        pitcher = (matchup.get("pitcher") or {})
        batter = (matchup.get("batter") or {})
        for ev in (play.get("playEvents") or []):
            details = ev.get("details") or {}
            # `isPitch` lives on the event; older payloads carry it under
            # details. Both are checked because a pickoff throw with a
            # speed field is otherwise indistinguishable from a pitch.
            is_pitch = ev.get("isPitch")
            if is_pitch is None:
                is_pitch = details.get("isPitch")
            if not is_pitch:
                continue
            pd = ev.get("pitchData") or {}
            coords = pd.get("coordinates") or {}
            breaks = pd.get("breaks") or {}
            ptype = (details.get("type") or {})
            out.append({
                "pitcher_id": pitcher.get("id"),
                "pitcher": pitcher.get("fullName"),
                "batter_id": batter.get("id"),
                "batter": batter.get("fullName"),
                "inning": about.get("inning"),
                "half": about.get("halfInning"),
                "at_bat": about.get("atBatIndex"),
                "pitch_number": ev.get("pitchNumber"),
                "pitch_type": ptype.get("code"),
                "pitch_name": ptype.get("description"),
                "speed": _num(pd.get("startSpeed")),
                "end_speed": _num(pd.get("endSpeed")),
                "spin_rate": _num(breaks.get("spinRate")),
                "break_angle": _num(breaks.get("breakAngle")),
                "break_length": _num(breaks.get("breakLength")),
                "extension": _num(pd.get("extension")),
                "px": _num(coords.get("pX")),
                "pz": _num(coords.get("pZ")),
                "zone": pd.get("zone"),
                "called": (details.get("call") or {}).get("code"),
            })
    return out


def pitch_counts(rows: list[dict]) -> dict:
    """`{pitcher_id: pitches thrown}` for the game."""
    out: dict = {}
    for r in rows:
        pid = r.get("pitcher_id")
        if pid is not None:
            out[pid] = out.get(pid, 0) + 1
    return out


def velocity_by_type(rows: list[dict], pitcher_id=None) -> dict:
    """`{pitch_type: (mean speed, n)}`, optionally for one pitcher.

    BY TYPE, NOT OVERALL, and that is the whole point. A starter who
    throws more curveballs in a cold game drops his average velocity
    without losing a tick of anything — §5 calls a 1+ mph fall a red flag
    for injury, and a mix shift would fire it every time. Comparing a
    four-seam against a four-seam is the only version of the check that
    means what it says.
    """
    acc: dict = {}
    for r in rows:
        if pitcher_id is not None and r.get("pitcher_id") != pitcher_id:
            continue
        t, s = r.get("pitch_type"), r.get("speed")
        if not t or s is None:
            continue
        tot, n = acc.get(t, (0.0, 0))
        acc[t] = (tot + s, n + 1)
    return {t: (round(tot / n, 2), n) for t, (tot, n) in acc.items() if n}


def times_through_order(rows: list[dict], pitcher_id) -> dict:
    """`{batter_id: which time through the order this PA was}`, 1-based.

    Counted per pitcher over distinct plate appearances, so a batter
    faced in the 1st and again in the 4th reads 1 then 2. TTO is about
    familiarity accumulating within one matchup, so a reliever entering
    in the 7th starts every batter he faces at 1 — which is what makes it
    per-pitcher rather than per-game.
    """
    seen: dict = {}
    out: dict = {}
    last_ab = None
    for r in rows:
        if r.get("pitcher_id") != pitcher_id:
            continue
        ab = r.get("at_bat")
        if ab == last_ab:
            continue                    # same plate appearance, later pitch
        last_ab = ab
        b = r.get("batter_id")
        if b is None:
            continue
        seen[b] = seen.get(b, 0) + 1
        out[(b, ab)] = seen[b]
    return out
