"""The NBA's switches, thrown by the box's own checks — a setting on the box still wins.

Ethan, 2026-11-04: "I don't want to have to specifically ask you for certain
tools or us grabbing certain pieces of data ... I want you to just do it."

Three of the NBA lab's changes waited on a command typed on the box
(runbook JY and JZ): the spread that follows the projection, the minutes a
fresh absence opens, and the rotation's rules. Each command printed a
verdict against a bar written before it ran, and a person then switched
the change by hand. The weekly deep refit now runs each check itself
(engine/deepfit's NBA pieces) and the verdict throws the switch:

  * ``spread``    nbalabcheck.py --part spread --save-verdict records READY
                  or NOT YET. The NBA's refit then fits its calibration on
                  the spread the verdict asks for, and only once that refit
                  has run clean does ``on`` follow it — the runbook's order,
                  the refit and then the switch.
  * ``rotation``  nbarules.py --save records whether the three rules still
                  hold on the box's own seasons; ``on`` follows at once (the
                  rules are on unless the box's seasons say otherwise).
  * ``rates``     nbarates.py --save (2026-11-04) records whether the rates
                  read past his last twenty games (engine/nba/rates) still
                  come out closer on the box's own seasons; ``on`` follows
                  at once, as the rotation's does.
  * ``starters``  nbarules.py --save (2026-11-04) records whether the
                  starting five's news (engine/nba/starters) still takes
                  error off the minutes and points it touches on the box's
                  own seasons; ``on`` follows at once, as the rotation's does.
  * the vacancy keeps its own store (engine/nba/vacancy, `nbavacancy.py
    --heldout --save`), which the board already reads only when it holds.

AN ENVIRONMENT VARIABLE STILL WINS: ``QB_NBA_SPREAD``, ``QB_NBA_ROTATION``,
``QB_NBA_RATES`` and ``QB_NBA_STARTERS`` set to anything decide outright, and the
refit never fits against them — the off-switch a person can always reach.
Unset, the box's own verdict decides; with no verdict on file, the spread is
off and the rules, the rates and the starting five's news are on, as they
were measured.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

STORE = "nba_switches.json"
#: The environment variable that overrides each switch.
ENV = {"spread": "QB_NBA_SPREAD", "rotation": "QB_NBA_ROTATION", "rates": "QB_NBA_RATES",
       "starters": "QB_NBA_STARTERS"}
#: Each switch with no verdict on file, as the board ran before the checks
#: (the rates read past the twenty, engine/nba/rates, on from the day it
#: was measured; the starting five's news, engine/nba/starters, the same).
DEFAULT = {"spread": False, "rotation": True, "rates": True, "starters": True}
#: What an environment variable says "off" with.
OFF_WORDS = ("0", "off", "false", "no")

_cache: dict = {"key": None, "data": {}}


def _path() -> str:
    from .. import modelstate
    return modelstate.path(STORE)


def load() -> dict:
    """The verdicts on file, read again only when the file changes: a board
    asks once a prop, thousands of times a build."""
    p = _path()
    try:
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _cache["key"] != key:
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        _cache.update(key=key, data=data if isinstance(data, dict) else {})
    return _cache["data"]


def _write(data: dict) -> str:
    p = _path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, p)
    return p


def env_says(name: str):
    """True / False when the box's environment sets this switch, else None."""
    v = str(os.environ.get(ENV[name], "") or "").strip().lower()
    if not v:
        return None
    return v not in OFF_WORDS


def is_on(name: str) -> bool:
    """The switch as the board reads it: the environment, else the box's
    own verdict, else the default."""
    said = env_says(name)
    if said is not None:
        return said
    entry = load().get(name) or {}
    on = entry.get("on")
    return DEFAULT[name] if on is None else bool(on)


def entry(name: str) -> dict:
    return dict(load().get(name) or {})


def _today() -> str:
    return _dt.date.today().isoformat()


def record_check(name: str, ready: bool, why: str, follow: bool = False, today: str | None = None) -> str:
    """File a check's verdict. ``follow`` throws the switch with it at once
    (the rotation's rules); without it the switch waits for whoever acts on
    the verdict (the spread: the NBA refit, `apply_target`)."""
    data = dict(load())
    e = dict(data.get(name) or {})
    e.update(verdict="ready" if ready else "not yet", why=str(why or ""), checked=today or _today())
    if follow and bool(e.get("on", DEFAULT[name])) != bool(ready):
        e.update(on=bool(ready), since=today or _today())
    elif follow and "on" not in e:
        e["on"] = bool(ready)
    data[name] = e
    return _write(data)


def target(name: str):
    """What the verdict on file asks the switch to be, or None when there is
    no verdict, or the environment decides (the refit then fits as the
    board will price, and changes nothing)."""
    if env_says(name) is not None:
        return None
    e = load().get(name) or {}
    if e.get("verdict") not in ("ready", "not yet"):
        return None
    return e["verdict"] == "ready"


def apply_target(name: str, today: str | None = None) -> str:
    """Throw the switch to what its verdict asks, once whatever had to come
    first (the NBA refit) ran clean. Returns a line for the log, or ""."""
    want = target(name)
    if want is None:
        return ""
    data = dict(load())
    e = dict(data.get(name) or {})
    was = bool(e.get("on", DEFAULT[name]))
    if was == want and "on" in e:
        return ""
    e.update(on=want, since=today or _today())
    data[name] = e
    _write(data)
    return f"NBA {name}: switched {'ON' if want else 'OFF'} by the box's own check — {e.get('why', '')}"
