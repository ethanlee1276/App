"""Is tonight's "probable starter" actually an opener?

MLB_MODEL §5: "Openers/bullpen games — probable-pitcher wire catches
scratches on refresh; explicit opener flag 📋".

The flag matters because every pitcher-market number assumes a starter's
workload. An opener throws the first inning and hands the ball over: an
outs projection of 16.5 for him is not optimistic, it is a category
error, and a strikeout line priced off his season K-rate is priced off
innings he will not pitch. The books know who tonight's opener is; a
model that does not is selling them the over.

DETECTION IS FROM HIS OWN RECENT STARTS, not from a role feed — none
exists, and none is needed. A pitcher whose recent starts last an inning
or two IS an opener in every sense the projection cares about, whatever
his roster designation says. The same cached game log `velocity.py`
already reads carries `inningsPitched` per start, so this costs nothing.

EVIDENCE ONLY. The flag lands as a card warning on pitcher-market props
and nothing gates on it: refusing to price opener games is a pricing
change, and `docs/THE_INFORMATION_TEST.md` is why that waits for a human.
"""

from __future__ import annotations

#: Median outs at or under this, across his recent starts, reads as an
#: opener. Six outs is two innings — a real starter having a bad month
#: still averages twelve-plus; an opener lives at three to six.
OPENER_MAX_OUTS = 6
#: Starts needed before the flag can fire at all. One short outing is a
#: blowup or an injury exit, not a role.
MIN_STARTS = 2
#: How many recent starts to look at.
RECENT_STARTS = 5


def _outs(innings) -> int | None:
    """statsapi `inningsPitched` ("5.2" = 5 and two thirds) → outs.

    The fraction digit IS a count of outs, not a decimal — "5.2" is 17
    outs, not 15.6. Parsing it as a float would make every partial inning
    slightly wrong in a way that never looks wrong.
    """
    s = str(innings or "").strip()
    if not s:
        return None
    try:
        whole, _, frac = s.partition(".")
        return int(whole or 0) * 3 + (int(frac[:1]) if frac else 0)
    except (TypeError, ValueError):
        return None


def recent_start_outs(person_id: int, season: int,
                      limit: int = RECENT_STARTS) -> list[int]:
    """Outs recorded in his last `limit` STARTS, most recent first.

    Relief appearances are excluded by `gamesStarted`, same rule as
    `velocity.recent_start_pks` and for the same reason: the question is
    what happens when he is handed the first inning.
    """
    from .sources.statslogs import fetch_game_log
    payload = fetch_game_log(person_id, "pitching", season)
    outs = []
    for split in ((payload.get("stats") or [{}])[0].get("splits") or []):
        stat = split.get("stat") or {}
        try:
            started = int(stat.get("gamesStarted") or 0)
        except (TypeError, ValueError):
            started = 0
        if not started:
            continue
        o = _outs(stat.get("inningsPitched"))
        if o is not None:
            outs.append(o)
    outs.reverse()                      # gameLog is oldest-first
    return outs[:limit]


def _median(xs: list[int]) -> float:
    ys = sorted(xs)
    n = len(ys)
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2.0


def looks_like_opener(outs: list[int]) -> bool | None:
    """True/False from a list of recent start lengths, None when unknown.

    MEDIAN, not mean: a real starter with one injury exit (18, 19, 2, 17)
    must not flag, and an opener who was once left in (3, 4, 15, 3) must.
    None below `MIN_STARTS` — one short outing is a blowup, not a role —
    and None is not False: an unknown role must not read as "confirmed
    starter" anywhere downstream.
    """
    if len(outs) < MIN_STARTS:
        return None
    return _median(outs) <= OPENER_MAX_OUTS


#: (person_id, season) → verdict. Same shape as velocity's memo, same
#: reason: one slate asks about the same starter once per market.
_MEMO: dict = {}


def opener_flag(person_id: int, season: int) -> bool | None:
    key = (person_id, season)
    if key in _MEMO:
        return _MEMO[key]
    try:
        verdict = looks_like_opener(recent_start_outs(person_id, season))
    except Exception:                                       # noqa: BLE001
        verdict = None                  # a feed hiccup is not a role
    _MEMO[key] = verdict
    return verdict
