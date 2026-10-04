"""Weigh-in results, and the rule they were supposed to enforce.

Every card the model prints already carries this line:

    kill_if: "missed weight, late replacement, or visible cut damage at
              weigh-ins → automatic void"

That was a promise with nothing behind it. The rule was written down and
nothing checked it, so a fighter could miss weight by three pounds on
Friday morning and the bet would still show as a pick on Saturday.

This module makes it real. A missed weight becomes a red flag, and red
flags already hard-gate a bet in ``approval_gate`` — so no model change is
needed, only the fact.

**Why the results are entered by hand.** There is no free structured feed
of weigh-in results; they arrive as a broadcast and a press release.
Rather than scrape a news page and pretend the parse is reliable, the
result is typed in the same way fighter dossiers are — this engine already
refuses to bet a fighter it has no dossier for, and this is the same
bargain. What the code does provide is the arithmetic (limits, the
non-title allowance) and, more importantly, the refusal to quietly forget:
a bout whose weigh-in has not been recorded says so on the page instead of
looking identical to one that made weight.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

# Championship limits in pounds. Non-title bouts get a one-pound
# allowance, which is why "155.5 at lightweight" is fine on a Fight Night
# and a miss on a title fight — the same number, two different answers.
LIMITS = {
    "strawweight": 115.0,
    "flyweight": 125.0,
    "bantamweight": 135.0,
    "featherweight": 145.0,
    "lightweight": 155.0,
    "welterweight": 170.0,
    "middleweight": 185.0,
    "light heavyweight": 205.0,
    "heavyweight": 265.0,
}
NON_TITLE_ALLOWANCE = 1.0

STORE_FILE = Path("data") / "ufc_weighins.json"


def limit_for(division: str, title_fight: bool = False) -> float | None:
    """The number this fighter has to make, or None for a division we
    don't recognise (catchweight bouts have no standard limit)."""
    base = LIMITS.get((division or "").strip().lower())
    if base is None:
        return None
    if base == LIMITS["heavyweight"]:
        return base                      # no allowance above heavyweight
    return base + (0.0 if title_fight else NON_TITLE_ALLOWANCE)


def evaluate(weight: float, division: str, title_fight: bool = False) -> dict:
    """One fighter's scale result against the limit he had to make."""
    limit = limit_for(division, title_fight)
    if limit is None:
        return {"state": "unknown_division", "weight": weight,
                "limit": None, "over": None, "division": division}
    over = round(weight - limit, 2)
    return {"state": "missed" if over > 0 else "made", "weight": weight,
            "limit": limit, "over": max(0.0, over), "division": division,
            "title_fight": bool(title_fight)}


# --- store ------------------------------------------------------------------
def _key(name: str) -> str:
    from ..sources.oddsapi import normalize_name
    return normalize_name(name)


def load_store(path: Path | str | None = None) -> dict:
    p = Path(path) if path else STORE_FILE
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(name: str, weight: float, division: str,
           title_fight: bool = False, path: Path | str | None = None,
           today: str | None = None) -> dict:
    """Store one weigh-in result. Returns the evaluation."""
    p = Path(path) if path else STORE_FILE
    store = load_store(p)
    res = evaluate(float(weight), division, title_fight)
    store[_key(name)] = {
        **res, "name": name,
        "recorded_at": today or _dt.date.today().isoformat(),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2, sort_keys=True))
    return res


def state_for(name: str, store: dict) -> dict:
    """What we know about this fighter's weigh-in.

    "unrecorded" is a first-class answer, not an absence: a bout nobody has
    entered a result for must not look like one that made weight."""
    rec = store.get(_key(name))
    if not rec:
        return {"state": "unrecorded", "name": name}
    return dict(rec)


def stale(rec: dict, today: str | None = None, max_age_days: int = 10) -> bool:
    """True when a stored result is old enough to belong to a past card.

    Weigh-ins are per-event; last month's number must not silently clear
    this month's fight."""
    when = (rec or {}).get("recorded_at")
    if not when:
        return True
    try:
        age = (_dt.date.fromisoformat(today or _dt.date.today().isoformat())
               - _dt.date.fromisoformat(when)).days
    except ValueError:
        return True
    return age > max_age_days or age < 0


def red_flags(name: str, store: dict, today: str | None = None) -> list[str]:
    """Red flags this fighter's weigh-in earns him.

    Only a MISS produces one. An unrecorded weigh-in is surfaced on the
    page but does not gate the bet: weigh-ins land the morning before the
    card, and refusing to price anything until then would leave the board
    empty for most of fight week — which is not honesty, just silence.
    """
    rec = store.get(_key(name))
    if not rec or stale(rec, today):
        return []
    if rec.get("state") == "missed":
        over = rec.get("over") or 0
        return [f"missed weight by {over:g} lb "
                f"({rec.get('weight')} vs {rec.get('limit')})"]
    return []


def annotate_fight(fight: dict, store: dict, today: str | None = None) -> dict:
    """Attach weigh-in state to a fight, and the red flags it earns.

    Mutates the dossier dicts' ``red_flags`` on purpose: that list is what
    ``approval_gate`` already refuses to bet through, so a missed weight
    gates the fight without the model knowing this module exists.
    """
    out = {}
    for side in ("a", "b"):
        d = fight.get(side)
        name = ((fight.get("prices") or {}).get(f"fighter_{side}")
                or (d or {}).get("name") or "")
        if not name:
            continue
        st = state_for(name, store)
        if st.get("state") != "unrecorded" and stale(st, today):
            st = {"state": "unrecorded", "name": name, "was_stale": True}
        out[side] = st
        if isinstance(d, dict):
            flags = red_flags(name, store, today)
            if flags:
                d["red_flags"] = list(d.get("red_flags") or []) + flags
    fight["weigh_in"] = out
    return fight


def card_summary(fights: list[dict]) -> dict:
    """Counts for the page: how much of this card has actually weighed in."""
    made = missed = unrecorded = 0
    for f in fights:
        for st in (f.get("weigh_in") or {}).values():
            s = st.get("state")
            if s == "missed":
                missed += 1
            elif s == "made":
                made += 1
            else:
                unrecorded += 1
    return {"made": made, "missed": missed, "unrecorded": unrecorded,
            "complete": unrecorded == 0 and (made or missed) > 0}
