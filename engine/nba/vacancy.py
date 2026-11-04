"""The minutes a fresh absence opens, handed to the teammates who play — once it is proven held out.

nbavacancy.py measured it on the box (2026-10-17, Ethan's paste, section
O): when a regular of 24+ minutes who played in one of his club's last
three games is not in the box score, his teammates run +1.8 minutes and
+1.1 points a game above the board's number, in both seasons stored, with
the intervals clear of zero — THE BAR set before that run, MET. The board
still gives them nothing: the minutes model has a slot for it
(`engine/nba/minutes.project_minutes(vacancy_minutes=...)`) and nothing
fills it, so a teammate's number is the same whether the star plays or
sits while the books raise his line the moment the star is ruled out.

THE RULE, the plainest one the measurement suggests: ``k`` × the absent
men's usual minutes (their last ten for the club), shared over tonight's
rotation in proportion to each man's own base minutes. One number, ``k``,
the share of the vacated minutes the rotation the board prices absorbs.

THE BAR FOR MOVING A NUMBER, written before the held-out run
(`nbavacancy.py --heldout`): each season held out in turn, ``k`` fitted on
the others (least squared error on minutes), and in EVERY held-out season
the squared error of BOTH minutes and points in fresh-absence games falls
against the empty slot. Only then does `--save` write a verdict that
holds, and only a verdict that holds fills the slot (`k_for`). Normal
games are untouched by construction: no absence, no vacancy.

Standard library only.
"""

from __future__ import annotations

import json
import os

STORE = "nba_vacancy.json"
#: The shares tried for ``k``: none of the vacated minutes to all of them.
K_GRID = tuple(round(0.05 * i, 2) for i in range(21))

#: WHO TAKES THE MINUTES (2026-11-04, measured on the lab's two seasons,
#: each held out: docs/NBA_LAB.md, "Who inherits"). Shared by base minutes,
#: a sitting regular's minutes went mostly to the stars, who were already
#: near their ceiling; on the floor they go to the men with room to play
#: more — the bench and the back of the rotation. Weighted base × (ROOM_CAP
#: − base), the minutes error in fresh-absence games fell 7.6% / 6.4% and
#: points 1.3% / 1.5% against sharing by base, in both seasons, with the
#: same cap and k (0.40) fitted on the other season both ways. A man of
#: ROOM_CAP minutes or more takes none; the most goes to a man of about half
#: of it.
ROOM_CAP = 34.0
#: The rule a verdict was fitted under rides with it (`save` callers file
#: it): a k fitted under one rule means nothing under the other, so a
#: verdict filed under another rule leaves the slot empty until the box's
#: own check refits it (`k_for`).
RULE = "room"


def weight(base, rule: str = RULE) -> float:
    """One rotation man's claim on the vacated minutes: ``room`` (the
    vacancy, since 2026-11-04) or ``base`` (the rule before it, which a
    regular's return still runs backwards — nba_build.return_for, measured
    that way)."""
    try:
        b = float(base or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if b <= 0:
        return 0.0
    return b * max(0.0, ROOM_CAP - b) if rule == "room" else b


def shares(absent_minutes: float, rotation: dict, k: float, rule: str = RULE) -> dict:
    """``{player: vacancy minutes}`` — ``k`` × the absent minutes, split by
    each rotation player's claim (`weight`). Empty when nothing is owed."""
    try:
        absent_minutes, k = float(absent_minutes or 0.0), float(k or 0.0)
    except (TypeError, ValueError):
        return {}
    claims = {p: weight(b, rule) for p, b in rotation.items()}
    tot = sum(claims.values())
    if k <= 0 or absent_minutes <= 0 or tot <= 0:
        return {}
    return {p: round(k * absent_minutes * w / tot, 2) for p, w in claims.items() if w > 0}


def _path() -> str:
    from .. import modelstate
    return modelstate.path(STORE)


def load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(sport: str, verdict: dict) -> str:
    data = load()
    data[str(sport).lower()] = verdict
    p = _path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, p)
    return p


def verdict(sport: str) -> dict:
    return load().get(str(sport).lower()) or {}


def k_for(sport: str) -> float:
    """The share the board applies: the saved ``k`` once its held-out
    verdict holds under today's sharing rule, else 0.0 (the empty slot, as
    before). A verdict filed before the rule rode with it was fitted on base
    minutes."""
    v = verdict(sport)
    if not v.get("holds") or str(v.get("rule") or "base") != RULE:
        return 0.0
    try:
        return max(0.0, min(1.0, float(v.get("k") or 0.0)))
    except (TypeError, ValueError):
        return 0.0
