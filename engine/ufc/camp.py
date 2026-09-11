"""Fight-week and camp information, measured instead of read about.

§7 calls camp intelligence MMA's signature edge, and the honest position
here has always been that no structured feed of camp footage or training
reports exists. That is still true. What was wrong was concluding that
therefore *nothing* about a fighter's camp is knowable — because three
things are, and we already fetch all of them:

* **Layoff.** Days since his last fight. Ring rust after a long absence is
  one of the few camp effects with real evidence behind it, and a very
  short turnaround is the opposite problem: no full camp to have.
* **Activity.** Fights per year across the tracked window. A fighter on a
  regular cycle is a fighter whose preparation is routine; one fight in
  three years is a different animal wearing the same record.
* **Gym.** Where ESPN names an association we store it — and because we
  store it on every draft, a CHANGE becomes visible by diffing our own
  history, exactly the way NFL trades are found here without a news feed.
  A camp change is the single most-cited qualitative camp signal in the
  sport, and it turns out to be measurable after all, just not instantly:
  it needs two drafts to see.

None of this is camp footage. It does not pretend to be. It is the part of
"how is this guy's camp" that can be observed without a source that does
not exist — and it means the fight-week component of the grade is a real
measurement for most fighters instead of a hole waiting on Friday.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

# Days. Under SHORT there was no full camp; over LONG the rust is real.
# The middle band is an ordinary preparation cycle and scores full marks.
SHORT_TURNAROUND = 45
IDEAL_MIN, IDEAL_MAX = 90, 400
LONG_LAYOFF = 550                    # ~18 months, the dossier's own bar
DEAD_LAYOFF = 900                    # 2½ years — a different fighter

# Fights per year across the tracked window.
HEALTHY_RATE = 2.0

GYM_FILE = Path("data") / "ufc_gyms.json"


def _days(a: str | None, b: str | None) -> int | None:
    try:
        return (_dt.date.fromisoformat(str(b)) - _dt.date.fromisoformat(str(a))).days
    except (TypeError, ValueError):
        return None


def layoff_score(days: int | None) -> tuple[float | None, str]:
    """0-1 for how well-timed this fight is in a fighter's calendar."""
    if days is None:
        return None, "no dated fight history"
    if days < SHORT_TURNAROUND:
        return 0.35, (f"{days}-day turnaround — too short for a full camp")
    if days < IDEAL_MIN:
        return 0.70, f"{days} days since his last fight — a quick turnaround"
    if days <= IDEAL_MAX:
        return 1.0, f"{days} days since his last fight — a normal camp cycle"
    if days <= LONG_LAYOFF:
        return 0.70, f"{days // 30}-month layoff — longer than a usual cycle"
    if days <= DEAD_LAYOFF:
        return 0.40, f"{days // 30}-month layoff — ring rust is a live risk"
    return 0.20, (f"{days // 30}-month layoff — that is long enough that the "
                  f"measured tape may describe a fighter who no longer exists")


def activity_score(fights: int, span_days: int | None) -> tuple[float | None, str]:
    if not fights or not span_days or span_days <= 0:
        return None, "not enough dated fights to measure a cycle"
    per_year = fights / (span_days / 365.25)
    if per_year >= HEALTHY_RATE:
        return 1.0, f"{per_year:.1f} fights a year — an active, routine cycle"
    if per_year >= 1.0:
        return 0.75, f"{per_year:.1f} fights a year — a slow but regular cycle"
    return 0.45, (f"{per_year:.1f} fights a year — long gaps between camps")


# --- gym affiliation, and changes found by diffing our own drafts -----------
def load_gyms(path: Path | str | None = None) -> dict:
    p = Path(path) if path else GYM_FILE
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record_gym(name: str, gym: str, today: str | None = None,
               path: Path | str | None = None) -> dict:
    """Store a fighter's current gym. Returns what changed, if anything.

    History is kept, not overwritten — a gym move is only visible because
    we remember where he was. Same trick as the NFL transactions panel:
    no news feed, no curation, and it covers every fighter rather than the
    ones somebody thought to mention.
    """
    p = Path(path) if path else GYM_FILE
    store = load_gyms(p)
    day = today or _dt.date.today().isoformat()
    rec = store.get(name) or {"history": []}
    hist = rec.get("history") or []
    changed_from = ""
    if gym and (not hist or hist[-1]["gym"] != gym):
        changed_from = hist[-1]["gym"] if hist else ""
        hist.append({"gym": gym, "seen": day})
    rec["history"] = hist
    rec["gym"] = gym or (hist[-1]["gym"] if hist else "")
    store[name] = rec
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2, sort_keys=True))
    return {"gym": rec["gym"], "changed_from": changed_from,
            "changed": bool(changed_from)}


def gym_state(name: str, store: dict, within_days: int = 400,
              today: str | None = None) -> dict:
    """What we know about this fighter's camp, and whether it just moved."""
    rec = store.get(name) or {}
    hist = rec.get("history") or []
    if not hist:
        return {"gym": "", "changed": False, "why": ""}
    day = today or _dt.date.today().isoformat()
    last = hist[-1]
    recent = (len(hist) > 1
              and (_days(last.get("seen"), day) or 10_000) <= within_days)
    return {
        "gym": last.get("gym", ""),
        "changed": bool(recent),
        "why": (f"changed camps to {last.get('gym')} "
                f"(was {hist[-2].get('gym')}, first seen {last.get('seen')})"
                if recent else f"trains at {last.get('gym')}"),
    }


def profile(dossier: dict, gyms: dict | None = None,
            today: str | None = None) -> dict:
    """Everything measurable about one fighter's camp going into this fight."""
    day = today or _dt.date.today().isoformat()
    last_fight = dossier.get("last_fight")
    first_fight = dossier.get("first_fight")
    n = int(dossier.get("fights", 0) or 0)

    lay, lay_why = layoff_score(_days(last_fight, day))
    act, act_why = activity_score(n, _days(first_fight, last_fight))
    gs = gym_state(dossier.get("name", ""), gyms or {}, today=day)

    parts = [p for p in (lay, act) if p is not None]
    score = round(sum(parts) / len(parts), 3) if parts else None
    # Averaging alone is non-monotonic in the layoff, and the failure is
    # not subtle: a man three years out who used to fight four times a
    # year outscored one 26 months out who never did. A severe layoff is
    # not something an old activity rate rescues — it caps the component,
    # because the question is what shape he is in NOW.
    if lay is not None and score is not None and lay <= 0.40:
        score = min(score, lay)
    why = [w for w in (lay_why, act_why) if w]
    if gs["why"]:
        why.append(gs["why"])
    # A camp change is INFORMATION, not automatically a negative — new
    # coaches fix things as often as they break them. It is scored as a
    # small uncertainty rather than a verdict, and it is always named so
    # the reason is visible rather than buried in a number.
    if gs["changed"] and score is not None:
        score = round(max(0.0, score - 0.15), 3)
    return {"score": score, "why": why, "gym": gs["gym"],
            "gym_changed": gs["changed"], "layoff_days": _days(last_fight, day),
            "fights_tracked": n}
