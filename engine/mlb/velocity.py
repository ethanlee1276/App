"""Velocity, start over start — MLB_MODEL §5's injury tell.

    **Velocity, start over start.** A drop of 1+ mph is a red flag — check
    injury and mechanics reporting before trusting any projection of him.
    Why: velocity decline is often the first public symptom of a hidden
    injury.

`docs/PITCH_LEVEL_SCOPE.md` established this needs no new provider: the
free statsapi playByPlay carries every pitch's speed, and `sources/pbp.py`
parses it. This module turns a pitcher's last few starts into one number
and a verdict.

FOUR THINGS THAT DECIDE WHETHER THE NUMBER MEANS ANYTHING:

**Compared within a pitch type.** A starter who threw more breaking balls
in a cold game loses average velocity without losing a tick of anything.
Only a four-seam against a four-seam says what §5's rule says. `pbp` does
this split; this module never undoes it.

**Compared against HIS baseline, not the league's.** 92 is alarming for
Cole and ordinary for a soft-tossing lefty. The baseline is the mean of
his own prior starts.

**A start needs enough of that pitch to average.** Six four-seams in a
rain-shortened outing is not a reading, and treating it as one produces a
red flag from noise. `MIN_PITCHES` is the floor and starts below it are
dropped rather than downweighted — a thin start is absence of evidence.

**One start is noisy.** A single outing's mean fastball velocity moves
±0.3–0.5 mph on nothing at all, so the flag sits at a full mph and the
baseline averages several starts to steady it. Even then this is a
POINTER at injury reporting, which is what §5 asks it to be — not a
verdict on its own.

Nothing here prices anything. See §6 of the scope doc.
"""

from __future__ import annotations

#: A start must carry at least this many of a pitch type before its mean
#: is trusted. Below it the outing is dropped, not downweighted.
MIN_PITCHES = 10

#: §5's threshold, in mph. Negative because a DROP is the red flag.
DROP_FLAG_MPH = -1.0

#: How many prior starts make the baseline. Enough to average out one
#: cold night; short enough to still be "recent form" rather than season.
BASELINE_STARTS = 4


def start_velocity(rows: list[dict], pitcher_id, min_pitches: int = MIN_PITCHES
                   ) -> dict:
    """`{pitch_type: mean mph}` for one pitcher in one game.

    Only types thrown at least `min_pitches` times survive.
    """
    from .sources.pbp import velocity_by_type
    return {t: mph for t, (mph, n) in
            velocity_by_type(rows, pitcher_id=pitcher_id).items()
            if n >= min_pitches}


def primary_pitch(history: list[dict]) -> str | None:
    """The pitch type to judge him on: the one present in the most starts.

    NOT the fastest, and not simply the most thrown in the latest game. A
    pitcher who shelves his slider for one outing would otherwise be
    compared on a pitch with no baseline, and a reliever's rare four-seam
    would outrank the sinker he actually lives on. Presence across starts
    is what makes a comparison possible at all.
    """
    counts: dict = {}
    for h in history:
        for t in (h.get("by_type") or {}):
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        return None
    # Ties break toward the pitch thrown most in the most recent start,
    # so a genuine 50/50 arsenal still resolves deterministically.
    latest = (history[0].get("by_type") or {}) if history else {}
    return max(counts, key=lambda t: (counts[t], t in latest, t))


def trend(history: list[dict], pitch_type: str | None = None,
          baseline_starts: int = BASELINE_STARTS) -> dict | None:
    """Compare the newest start against the mean of the prior ones.

    `history` is most-recent-first, each entry
    ``{"date", "game_pk", "by_type": {type: mph}}``.

    Returns None when there is nothing to compare — no baseline start
    carrying that pitch type, or no latest reading of it. None is the
    honest answer and it is common early in a season; a zero would read
    as "no change" and quietly claim a measurement nobody made.
    """
    if len(history) < 2:
        return None
    t = pitch_type or primary_pitch(history)
    if not t:
        return None
    latest = (history[0].get("by_type") or {}).get(t)
    if latest is None:
        return None
    prior = [h["by_type"][t] for h in history[1:1 + baseline_starts]
             if t in (h.get("by_type") or {})]
    if not prior:
        return None
    base = sum(prior) / len(prior)
    delta = latest - base
    return {
        "pitch_type": t,
        "latest": round(latest, 2),
        "baseline": round(base, 2),
        "delta": round(delta, 2),
        "baseline_starts": len(prior),
        "flag": delta <= DROP_FLAG_MPH,
        "date": history[0].get("date"),
        # Stated so a caller cannot mistake this for a diagnosis. §5 wants
        # it used to go READ something, not to move a number.
        "reading": (
            f"down {abs(delta):.1f} mph on his {t} against his last "
            f"{len(prior)} start(s) — §5 calls this a red flag: check "
            f"injury and mechanics reporting before trusting a projection"
            if delta <= DROP_FLAG_MPH else
            f"{t} within {abs(delta):.1f} mph of his last {len(prior)} "
            f"start(s)"),
    }


# --- the network half, kept apart from the arithmetic above -----------------
def recent_start_pks(person_id: int, season: int, limit: int = 5) -> list[dict]:
    """`[{"date", "game_pk"}]` most-recent-first for a pitcher's STARTS.

    Relievers are excluded by `gamesStarted`, because §5's rule is about a
    starter's arm between outings. A reliever's one-inning velocity swings
    with the leverage he was used in and would flag constantly.
    """
    from .sources.statslogs import fetch_game_log
    payload = fetch_game_log(person_id, "pitching", season)
    out = []
    for split in ((payload.get("stats") or [{}])[0].get("splits") or []):
        stat = split.get("stat") or {}
        try:
            started = int(stat.get("gamesStarted") or 0)
        except (TypeError, ValueError):
            started = 0
        if not started:
            continue
        pk = (split.get("game") or {}).get("gamePk")
        if pk:
            out.append({"date": split.get("date"), "game_pk": pk})
    out.reverse()                      # gameLog is oldest-first
    return out[:limit]


def velocity_history(person_id: int, season: int, limit: int = 5,
                     min_pitches: int = MIN_PITCHES) -> list[dict]:
    """The last `limit` starts, each with its per-pitch-type mean velocity.

    Each game is one cached playByPlay fetch. A start whose payload will
    not load is SKIPPED rather than recorded empty — an empty reading
    would enter the baseline as a gap and quietly widen it.
    """
    from .sources.pbp import fetch_playbyplay, pitches
    out = []
    for s in recent_start_pks(person_id, season, limit):
        try:
            rows = pitches(fetch_playbyplay(s["game_pk"]))
        except Exception:                                   # noqa: BLE001
            continue
        by_type = start_velocity(rows, person_id, min_pitches)
        if by_type:
            out.append({"date": s["date"], "game_pk": s["game_pk"],
                        "by_type": by_type})
    return out
