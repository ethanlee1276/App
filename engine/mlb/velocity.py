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


def start_counts(rows: list[dict], pitcher_id,
                 min_pitches: int = MIN_PITCHES) -> dict:
    """`{pitch_type: how many he threw}` for one pitcher in one game.

    Kept alongside the means because "which pitch is his" is a question
    about VOLUME, and `start_velocity` throws the count away. Without it
    the primary pitch had to be guessed from presence alone, and that is
    how Gerrit Cole — 42 four-seams in the game this was probed on — got
    judged on his slider.
    """
    from .sources.pbp import velocity_by_type
    return {t: n for t, (_mph, n) in
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
    starts: dict = {}
    thrown: dict = {}
    for h in history:
        for t in (h.get("by_type") or {}):
            starts[t] = starts.get(t, 0) + 1
        for t, n in (h.get("counts") or {}).items():
            thrown[t] = thrown.get(t, 0) + n
    if not starts:
        return None
    # VOLUME FIRST, presence second. The first version ranked on presence
    # alone and broke ties alphabetically — so a pitcher whose four-seam
    # and slider both appear in all five starts got judged on the slider,
    # because "SL" sorts above "FF". That is not a tiebreak, it is a coin
    # flip wearing a rule, and it picked wrong on the first real pitcher
    # it saw.
    #
    # `counts` may be absent on a history built before this existed, in
    # which case thrown is empty and presence still decides — with the
    # alphabetical fallback made explicit rather than accidental.
    return max(starts, key=lambda t: (thrown.get(t, 0), starts[t], t))


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


def trend_all(history: list[dict], baseline_starts: int = BASELINE_STARTS
              ) -> list[dict]:
    """Every pitch type that has a baseline, worst drop first.

    WHY NOT JUST THE PRIMARY. Probed on Gerrit Cole, whose four-seam was
    flat across five starts while his changeup went 87.64, 86.48, 86.26,
    85.09 — and then vanished from the latest outing entirely. A single
    primary-pitch verdict reported "SL within 0.8 mph" and hid a 2.5 mph
    slide on another pitch, which is the exact shape §5 is asking us to
    notice.

    A pitch DISAPPEARING is reported too, as `dropped`. Shelving a pitch
    is itself a signal — it is what a pitcher does when one is not
    working or hurts — and returning nothing for it would let the most
    informative case be the silent one.

    MORE TYPES MEANS MORE CHANCES TO CROSS THE LINE BY NOISE: four
    pitches watched at a 1 mph threshold is four rolls, not one. So this
    returns a list to read rather than a single verdict to act on, and
    the caller is told how many were examined.
    """
    types: set = set()
    for h in history:
        types.update((h.get("by_type") or {}).keys())
    out = []
    for t in sorted(types):
        r = trend(history, pitch_type=t, baseline_starts=baseline_starts)
        if r:
            out.append(r)
            continue
        # No reading in the latest start, but a baseline exists: he had
        # this pitch and stopped throwing it (or threw it under the floor).
        prior = [h["by_type"][t] for h in history[1:1 + baseline_starts]
                 if t in (h.get("by_type") or {})]
        if prior and t not in (history[0].get("by_type") or {}):
            out.append({
                "pitch_type": t, "latest": None,
                "baseline": round(sum(prior) / len(prior), 2),
                "delta": None, "baseline_starts": len(prior),
                "flag": False, "dropped": True,
                "date": history[0].get("date"),
                "reading": (f"{t} not thrown in the latest start (or under "
                            f"the {MIN_PITCHES}-pitch floor) after "
                            f"{len(prior)} start(s) averaging "
                            f"{sum(prior) / len(prior):.1f}"),
            })
    out.sort(key=lambda r: (r["delta"] if r["delta"] is not None else 99))
    return out


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
                        "by_type": by_type,
                        "counts": start_counts(rows, person_id, min_pitches)})
    return out


#: One slate asks about the same starter once per market — strikeouts and
#: outs at least, sometimes more. Each miss is five cached playByPlay
#: fetches, so without a memo a fifteen-game board multiplies that by
#: however many pitcher props it prices. Keyed on (person_id, season);
#: process-lifetime, because a build is one process and a start does not
#: change mid-run.
_MEMO: dict = {}


def delta_for(person_id, season: int) -> float | None:
    """The mph change on his primary pitch, or None if unmeasurable.

    The one function the pricing path calls. Returns a NUMBER and never
    raises: a pitcher whose game logs will not load, who has no baseline,
    or who is a reliever comes back None — and None must stay None
    through to the journal, because `losspatterns.velo_band` treats it as
    unmeasured rather than as steady.
    """
    key = (person_id, season)
    if key in _MEMO:
        return _MEMO[key]
    out = None
    try:
        hist = velocity_history(int(person_id), int(season))
        t = trend(hist)
        if t:
            out = t["delta"]
    except Exception:                                       # noqa: BLE001
        out = None          # never let a pitcher lookup break a board
    _MEMO[key] = out
    return out
