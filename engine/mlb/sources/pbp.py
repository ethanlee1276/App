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
