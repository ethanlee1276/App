"""What a pitcher throws, how often, and how much of it gets missed.

MLB_MODEL §6 parked the arsenal matchup behind a claim:

    | §6 Pitch arsenal matchup | 📋 | Needs pitch-mix + per-pitch-type
    | hitter data; the platoon engine below is the current best proxy |

**Half of that is already on disk and costs nothing.** `velocity.py`
loads a starter's last five playByPlay payloads to read his velocity, and
those same payloads carry the pitch TYPE and the CALL on every pitch. So
the pitcher half of the matchup — what he throws, in what proportion, and
how much swing-and-miss each pitch gets — is a second read of games the
board already fetched. No new feed, no new request, no new credit.

The hitter half is the expensive one and this module does not pretend to
have it. See `docs/PITCH_LEVEL_SCOPE.md`: a batter's whiff rate against
sliders needs his season, not tonight's opponent's five starts, and that
is either Savant's pitch-arsenal batter leaderboard (one CSV, cheap,
unverified from the sandbox) or a season of playByPlay (~1.5 GB). Naming
which is the point — "needs data" was hiding two very different costs.

WHAT THIS MEASURES, and why each piece is worth having on its own:

  MIX       share of pitches by type. A starter who has gone from 45%
            four-seam to 28% is a different pitcher from the one the
            projection was fitted on, whatever his velocity says.
  WHIFF     swinging strikes per SWING, by type. Not per pitch: a pitch
            nobody offers at is a ball, and dividing by every pitch
            measures how often he is in the zone rather than how nasty
            the pitch is.
  SHELVED   a type that has vanished from the recent starts. `velocity.py`
            already reports this for speed; a pitch dropped from the mix
            is the same fact from the other side.

NOTHING HERE PRICES ANYTHING. The claimed edge measures AUC 0.479
(`docs/THE_INFORMATION_TEST.md`), so a new input into a grade is the move
that finding rules out. This is a probe, and a dimension if it earns one.
"""

from __future__ import annotations

#: A type thrown fewer times than this in a start is noise — a single
#: show-me curveball is not part of an arsenal.
MIN_TYPE_PITCHES = 3
#: Swings needed before a whiff rate is reported at all. Two swings and
#: one miss is not a 50% whiff pitch.
MIN_SWINGS = 10

#: statsapi `details.call.code`. Only the codes that describe what the
#: BATTER did — everything else (balls, pickoffs, automatic strikes) is
#: not a swing and must not reach the denominator.
#:
#: The foul tip (T) is a swing AND a miss in the sense that matters here:
#: the batter did not square it up. It is counted as a swing and not as a
#: whiff, deliberately — a foul tip is contact, and calling it a whiff
#: would inflate every splitter in the league.
SWING_CODES = {"S", "W", "T", "F", "L", "X", "D", "E", "M", "Q", "R"}
WHIFF_CODES = {"S", "W", "M", "Q"}


def mix(rows, pitcher_id=None, min_type: int = MIN_TYPE_PITCHES) -> dict:
    """`{pitch_type: share}` for one pitcher, biggest first.

    Shares are over the types that CLEARED the floor, so they sum to 1
    and a one-off show-me pitch does not shave a point off everything
    else. `n` reports the pitches behind them.
    """
    counts: dict = {}
    for r in rows:
        if pitcher_id is not None and r.get("pitcher_id") != pitcher_id:
            continue
        t = r.get("pitch_type")
        if t:
            counts[t] = counts.get(t, 0) + 1
    kept = {t: c for t, c in counts.items() if c >= min_type}
    total = sum(kept.values())
    if not total:
        return {"n": 0, "shares": {}, "counts": counts}
    return {"n": total,
            "shares": {t: round(c / total, 4) for t, c in
                       sorted(kept.items(), key=lambda kv: -kv[1])},
            "counts": counts}


def whiff_by_type(rows, pitcher_id=None, min_swings: int = MIN_SWINGS) -> dict:
    """`{pitch_type: {whiff_rate, swings}}` — misses per SWING.

    Per swing, not per pitch. A pitch nobody offers at is a ball, and
    dividing by every pitch would measure how often he is in the zone
    rather than how hard the pitch is to hit. A type under the swing
    floor reports `None` rather than a rate off three offers.
    """
    acc: dict = {}
    for r in rows:
        if pitcher_id is not None and r.get("pitcher_id") != pitcher_id:
            continue
        t, code = r.get("pitch_type"), (r.get("called") or "").upper()
        if not t or code not in SWING_CODES:
            continue
        a = acc.setdefault(t, [0, 0])
        a[0] += 1
        if code in WHIFF_CODES:
            a[1] += 1
    return {t: {"swings": s,
                "whiff_rate": round(w / s, 4) if s >= min_swings else None,
                "whiffs": w}
            for t, (s, w) in sorted(acc.items(), key=lambda kv: -kv[1][0])}


def arsenal(rows, pitcher_id) -> dict:
    """One start's arsenal: mix and whiff rate together."""
    m = mix(rows, pitcher_id)
    return {"n": m["n"], "shares": m["shares"],
            "whiff": whiff_by_type(rows, pitcher_id)}


def history(person_id: int, season: int, limit: int = 5) -> list[dict]:
    """The last `limit` starts, each with its arsenal.

    Reuses `velocity.recent_start_pks` and the same cached playByPlay
    payloads, so on a night the board already priced this pitcher's
    velocity this costs nothing but the parse.
    """
    from .sources.pbp import fetch_playbyplay, pitches
    from .velocity import recent_start_pks
    out = []
    for s in recent_start_pks(person_id, season, limit):
        try:
            rows = pitches(fetch_playbyplay(s["game_pk"]))
        except Exception:                                    # noqa: BLE001
            continue
        a = arsenal(rows, person_id)
        if a["n"]:
            out.append({"date": s["date"], "game_pk": s["game_pk"], **a})
    return out


def mix_shift(hist, baseline_starts: int = 4) -> dict:
    """How the latest start's mix differs from the ones before it.

    THE SAME SHAPE AS THE VELOCITY TELL, and for the same reason: a
    starter who has gone from 45% four-seam to 28% is not the pitcher the
    projection was fitted on, whether or not he lost a tick.

    Returns one row per type, biggest move first, with `dropped` for a
    pitch that was in the baseline and is absent from the latest start —
    the mix-side twin of `velocity.trend_all`'s shelved pitch.
    """
    if len(hist) < 2:
        return {"n_starts": len(hist), "types": {}, "enough": False}
    # MOST-RECENT-FIRST, like `velocity.recent_start_pks` returns and like
    # `velocity.trend` reads it. The first cut of this took `hist[-1]` as
    # the latest start and the ones before it as the baseline, which is
    # the OLDEST start against the four newer ones — the comparison
    # backwards, and plausible enough to print. On Gerrit Cole it reported
    # "SL 18% -> 28%, FF 55% -> 45%" (he is leaning on the slider) when
    # the truth was the reverse: FF 52% -> 57%, SL 21% -> 17%.
    #
    # Nothing in the numbers looks wrong when this is inverted. It was
    # caught by reading the printed dates against the printed verdict.
    latest, prior = hist[0], hist[1:1 + baseline_starts]
    base: dict = {}
    for st in prior:
        for t, share in st["shares"].items():
            base.setdefault(t, []).append(share)
    types: dict = {}
    for t in set(base) | set(latest["shares"]):
        b = base.get(t) or []
        base_share = sum(b) / len(b) if b else None
        now = latest["shares"].get(t)
        types[t] = {
            "baseline": round(base_share, 4) if base_share is not None else None,
            "latest": now,
            "delta": (round((now or 0.0) - base_share, 4)
                      if base_share is not None else None),
            # A pitch he threw and has stopped throwing. Not a delta of
            # -0.45 buried in a list: its own flag, because "he shelved
            # the changeup" is a different sentence from "he throws it
            # less".
            "dropped": bool(base_share and not now),
            "new": bool(now and base_share is None),
        }
    return {"n_starts": len(hist), "enough": True,
            "types": dict(sorted(types.items(),
                                 key=lambda kv: -abs(kv[1]["delta"] or 0)))}


def pooled_whiff(hist, min_swings: int = MIN_SWINGS) -> dict:
    """Whiff rate by type across ALL the starts, not one at a time.

    WHY THE PER-START VIEW IS NOT ENOUGH, from Ethan's Gerrit Cole run:
    every one of his five starts reported "under the floor" for the
    slider, curve and change, because a start gives 6-11 swings on a
    secondary pitch and the floor is 10. Three quarters of the arsenal
    was invisible in a report about the arsenal.

    Pooled, the same five starts give 52 slider swings, 34 changeups and
    26 curves — all comfortably over. Nothing about the floor was wrong;
    it was being applied to the wrong unit.

    Per-start stays, because it is the only view that can show a pitch
    getting worse. This is the view that can show what the pitch IS.
    """
    acc: dict = {}
    for st in hist:
        for t, w in (st.get("whiff") or {}).items():
            a = acc.setdefault(t, [0, 0])
            a[0] += w.get("swings", 0)
            a[1] += w.get("whiffs", 0)
    return {t: {"swings": sw, "whiffs": wh,
                "whiff_rate": round(wh / sw, 4) if sw >= min_swings else None}
            for t, (sw, wh) in sorted(acc.items(), key=lambda kv: -kv[1][0])}
