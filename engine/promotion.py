"""A met bar has to actually lift the gate.

Three modules on this site publish a promotion bar and none of them can
reach it:

  * `engine.parlayledger` computes all four of §13's conditions — a
    hundred graded tickets, positive flat-stake ROI, aggregate leg CLV
    at or above zero, z of at least two — and `launch.py` prints them
    PASS by PASS. In the same dict it returns ``"probation": True``, a
    literal. Every condition can hold and nothing happens.
  * `engine.hoops.LeagueTuning.calibrated` is a literal too, so the
    coverage page's "grades accumulate automatically; the bar lifts
    itself" was never true: the bar is a `False` in source that only a
    human editing the file can flip.
  * `engine.cfb.ratings` was the one that DID lift itself, on evidence —
    which is why it is the shape this copies.

That is the same disease found twice already this week: a rule announced
in prose and enforced nowhere. It is worse here than in the stake gate,
because it runs the other way — the stake gate did something it said it
would not, and this refuses to do something it said it would. A model
that has earned its promotion and cannot receive it is a learning loop
with the last link missing.

WHAT THIS DELIBERATELY IS NOT: an automatic flip. Every other fitter
here adopts on its own because the worst case is a slightly wrong
price. The worst case here is money at risk that was not at risk
before, on a threshold nobody looked at. So promotion is RECORDED
rather than derived: the bar decides whether promotion is *available*,
and promoting is an explicit act that writes down when it happened and
on what evidence. Demotion is the same in reverse and needs no bar at
all — withdrawing risk should never be harder than taking it.

The gate then reads the record, not a literal, so a promotion survives a
deploy and a demotion takes effect the moment it is written.

Standard library only.
"""

from __future__ import annotations

import json
import os
import time

from . import feedstate as _feedstate

STATE_PATH = _feedstate.path("promotion.json")

_cache: dict = {}


def _read() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


def bar_met(conditions: dict) -> bool:
    """True when EVERY condition holds.

    ``conditions`` is ``{name: bool}`` — the shape
    `parlayledger.report()["promotion"]` already reports and
    `launch.py` already prints. An empty set is not a met bar: a
    promotion with no conditions behind it is the thing this module
    exists to stop.
    """
    if not conditions:
        return False
    return all(bool(v) for v in conditions.values())


def failing(conditions: dict) -> list[str]:
    """Which conditions do not hold — a bar should say WHICH test failed."""
    return sorted(k for k, v in (conditions or {}).items() if not v)


def promoted(key: str) -> bool:
    """Has ``key`` been promoted? Never raises — this is on the gate path.

    A half-written state file costs the promotion, not the board, and
    the safe direction is unambiguous: unreadable means NOT promoted,
    so a corrupt file withholds risk rather than taking it.
    """
    if key in _cache:
        return _cache[key]
    entry = _read().get(key)
    ok = False
    if isinstance(entry, dict):
        try:
            ok = bool(entry["promoted"])
        except (KeyError, TypeError, ValueError):
            ok = False
    _cache[key] = ok
    return ok


def record(key: str) -> dict | None:
    """The full stored entry for ``key``, or None."""
    entry = _read().get(key)
    return entry if isinstance(entry, dict) else None


def promote(key: str, evidence: dict | None = None,
            conditions: dict | None = None, force: bool = False) -> dict:
    """Promote ``key``, refusing unless the bar is met.

    ``force`` exists for the case the bar cannot describe — a league
    whose numbers were fitted elsewhere and reviewed by hand — and it is
    recorded as forced, because a promotion nobody can audit is the same
    as one nobody measured.
    """
    if conditions is not None and not bar_met(conditions) and not force:
        raise ValueError(
            f"{key} has not met its bar: "
            f"{', '.join(failing(conditions))} still failing. Pass "
            f"force=True only for a promotion decided some other way, and "
            f"it will be recorded as forced.")
    state = _read()
    state[key] = {"promoted": True, "at": time.time(),
                  "forced": bool(force and conditions is not None
                                 and not bar_met(conditions)),
                  "conditions": dict(conditions or {}),
                  "evidence": dict(evidence or {})}
    _write(state)
    _cache.clear()
    return state[key]


def demote(key: str, why: str = "") -> dict:
    """Withdraw a promotion. No bar, on purpose — see the module docstring."""
    state = _read()
    state[key] = {"promoted": False, "at": time.time(), "why": why,
                  "was": (state.get(key) or {}).get("at")}
    _write(state)
    _cache.clear()
    return state[key]


def status(key: str, conditions: dict | None = None) -> dict:
    """Everything a reader needs: promoted, available, and what is failing."""
    entry = record(key) or {}
    met = bar_met(conditions) if conditions is not None else None
    return {"key": key,
            "promoted": promoted(key),
            "bar_met": met,
            "awaiting": bool(met and not promoted(key)),
            "failing": failing(conditions) if conditions is not None else [],
            "at": entry.get("at"),
            "forced": bool(entry.get("forced"))}


def note(key: str, conditions: dict | None = None) -> str:
    """One line for a board or a health check."""
    st = status(key, conditions)
    if st["promoted"]:
        return f"{key}: promoted — staking on its own graded record"
    if st["awaiting"]:
        return (f"{key}: every promotion condition holds and it has not "
                f"been promoted — this is a decision waiting on a person, "
                f"not a model still collecting")
    if st["failing"]:
        return f"{key}: on probation — still failing {', '.join(st['failing'])}"
    return f"{key}: on probation"


#: How to recompute a key's bar from the record, so the CLI can refuse
#: on live evidence rather than on whatever a caller passes it. A key
#: absent from here can still be promoted, but only deliberately and
#: with no conditions recorded — see `promote`.
def conditions_for(key: str) -> dict | None:
    """This key's promotion conditions, measured now, or None.

    Never raises: a box with no journal cannot answer the question, and
    "I could not measure it" must not read as "the bar is met".
    """
    try:
        if key == "parlays":
            from .parlayledger import report
            from .ledger import connect
            pr = report(connect())["promotion"]
            return {
                "tickets": pr["tickets_have"] >= pr["tickets_required"],
                "roi_positive": pr["roi_positive"],
                "clv_non_negative": pr["clv_non_negative"],
                "z_clears": pr["z_clears"],
            }
    except Exception:                                     # noqa: BLE001
        return None
    return None


if __name__ == "__main__":                       # pragma: no cover
    import sys
    argv = sys.argv[1:]
    if argv and argv[0] == "promote" and len(argv) > 1:
        key = argv[1]
        conds = conditions_for(key)
        if conds is None and "--force" not in argv:
            print(f"Cannot measure {key}'s bar on this machine. Promote it "
                  f"deliberately with --force and it is recorded as forced.")
            raise SystemExit(1)
        try:
            entry = promote(key, conditions=conds,
                            force="--force" in argv)
        except ValueError as exc:
            print(str(exc))
            raise SystemExit(1)
        print(f"{key} promoted"
              + ("  (FORCED — recorded as such)" if entry["forced"] else "")
              + f"\n  {note(key, conds)}")
        raise SystemExit(0)
    if not argv:
        state = _read()
        if not state:
            print("Nothing has been promoted or demoted.")
        for key, entry in sorted(state.items()):
            when = (time.strftime("%Y-%m-%d", time.localtime(entry["at"]))
                    if entry.get("at") else "?")
            word = "promoted" if entry.get("promoted") else "demoted"
            print(f"  {key:12} {word} {when}"
                  + ("  (forced)" if entry.get("forced") else ""))
    elif argv[0] == "demote" and len(argv) > 1:
        demote(argv[1], " ".join(argv[2:]))
        print(f"{argv[1]} demoted.")
    else:
        print(__doc__.strip().splitlines()[0])
