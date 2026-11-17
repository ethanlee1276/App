"""A league's three-leg parlays go on paper while they hit under 25%: built,
journaled and graded every slate, never posted (2026-11-17).

Ethan, asked on 2026-11-17 whether the NFL's three-leg parlays (30 of 175
hit, 17%) should keep posting or be tracked without posting while they hit
under 25%: "ok". The rule is automatic and every league's, as the Most Likely
board's paper holds are (engine/paperhold; Ethan, 2026-11-15: "that should be
automated and not asking me").

THE HOLD. A league's three-leg tickets (engine/gameparlays, source
``game_three`` in the parlay journal, engine/parlayledger) go on paper when
its last WINDOW graded tickets, MIN_N of them at least, hit under FLOOR. The
NFL's starts as a standing hold from 2026-11-17, the record it was asked on.

ON PAPER. engine/gameparlays.build still builds every game's tickets and
moves them from ``threes`` to ``paper_threes``: the journal writes and grades
them as before, so the record keeps learning on them, and no page shows them
as picks; each game says why in their place (``words``).

THE RELEASE. The tickets graded since the hold began, RELEASE_N of them at
least, hitting FLOOR or better, bring the league back by itself. A league
that came back is held again only on tickets graded after its release.

Measured on the nightly settle pass (engine/maintenance, beside the Most
Likely holds) and saved to the model state; the builds read the saved file.
Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from . import modelstate as _modelstate

DEFAULT_PATH = Path(_modelstate.path("parlayhold.json"))

#: The parlay journal's name for each game's three-leg tickets (gameparlays.SOURCES).
SOURCE = "game_three"
#: The hit rate a league's three-leg tickets must reach to be posted.
FLOOR = 0.25
#: The graded tickets the hold reads, newest last…
WINDOW = 100
#: …and how many of them before it says anything.
MIN_N = 50
#: The tickets graded since a hold began, before they can bring it back.
RELEASE_N = 50

#: The hold the question was asked on: the NFL's record on 17 November.
STANDING = ({"sport": "nfl", "since": "2026-11-17", "n": 175, "won": 30, "source": "standing"},)


def graded(conn) -> dict:
    """``{league: [(day journaled, won), ...]}``, oldest first: every graded
    three-leg ticket in the journal."""
    try:
        rows = conn.execute("SELECT sport, ts, status FROM parlays WHERE source=? AND status IN ('won','lost') "
                            "ORDER BY ts, id", (SOURCE,)).fetchall()
    except Exception:                                        # noqa: BLE001 (no journal yet)
        return {}
    out: dict = {}
    for sport, ts, status in rows:
        sp = str(sport or "").lower()
        if sp:
            out.setdefault(sp, []).append((str(ts or "")[:10], status == "won"))
    return out


def _rate(rows: list) -> tuple[int, int]:
    return len(rows), sum(1 for _, w in rows if w)


def refresh(conn, path=None, today: _dt.date | None = None) -> dict:
    """The settle pass's step: hold the leagues whose last WINDOW graded
    tickets hit under FLOOR, carry each hold's start, release the ones whose
    tickets since have hit FLOOR, and save."""
    today = today or _dt.date.today()
    prev = load(path)
    by = graded(conn)
    holds = {h["sport"]: dict(h) for h in prev.get("holds") or [] if h.get("sport")}
    released = {h["sport"]: dict(h) for h in prev.get("released") or [] if h.get("sport")}
    for k in STANDING:
        if k["sport"] not in holds and k["sport"] not in released:
            holds[k["sport"]] = dict(k)
    for sp in sorted(set(by) | set(holds)):
        rows = by.get(sp, [])
        h = holds.get(sp)
        if h:
            if h.get("source") != "standing":
                h["n"], h["won"] = _rate(rows[-WINDOW:])
            h["since_n"], h["since_won"] = _rate([r for r in rows if r[0] >= str(h.get("since") or "")])
            if h["since_n"] >= RELEASE_N and h["since_won"] / h["since_n"] >= FLOOR:
                released[sp] = {**h, "released_on": today.isoformat()}
                holds.pop(sp)
            continue
        rel = released.get(sp)
        pool = [r for r in rows if not rel or r[0] > str(rel.get("released_on") or "")]
        n, won = _rate(pool[-WINDOW:])
        if n >= MIN_N and won / n < FLOOR:
            holds[sp] = {"sport": sp, "since": today.isoformat(), "n": n, "won": won, "source": "measured",
                         "since_n": 0, "since_won": 0}
            released.pop(sp, None)
    out = {"measured_on": today.isoformat(), "floor": FLOOR, "window": WINDOW,
           "holds": sorted(holds.values(), key=lambda h: h["sport"]),
           "released": sorted(released.values(), key=lambda h: h["sport"])}
    save(out, path)
    return out


_cache: dict = {}


def load(path=None) -> dict:
    p = Path(DEFAULT_PATH if path is None else path)
    try:
        m = p.stat().st_mtime
    except OSError:
        return {}
    key = (str(p), m)
    if key not in _cache:
        try:
            raw = json.loads(p.read_text())
        except (OSError, ValueError):
            raw = {}
        _cache.clear()
        _cache[key] = raw if isinstance(raw, dict) else {}
    return _cache[key]


def save(out: dict, path=None) -> Path:
    p = Path(DEFAULT_PATH if path is None else path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, sort_keys=True))
    tmp.replace(p)
    return p


def holds(path=None) -> list:
    """The leagues on paper now: the saved holds, and the standing hold until
    a saved pass has released it."""
    state = load(path)
    out = [h for h in state.get("holds") or [] if h.get("sport")]
    have = {h["sport"] for h in out} | {h.get("sport") for h in state.get("released") or []}
    out += [dict(k) for k in STANDING if k["sport"] not in have]
    return out


def held(sport, path=None) -> dict | None:
    """The hold on a league's three-leg tickets, or None."""
    sp = str(sport or "").lower()
    return next((h for h in holds(path) if h.get("sport") == sp), None)


def words(h: dict) -> str:
    """The hold in a reader's words, for every game it covers."""
    n, won = int(h.get("n") or 0), int(h.get("won") or 0)
    lg = str(h.get("sport") or "").upper()
    rec = (f"have hit {won} of {n} ({won / n:.0%})" if n else "have hit under 25%")
    if h.get("source") != "standing" and n:
        rec = f"have hit {won} of their last {n} ({won / n:.0%})"
    try:
        day = _dt.date.fromisoformat(str(h.get("since") or ""))
        since = f"{day.day} {day.strftime('%B')}"
    except ValueError:
        since = "the hold began"
    return (f"On paper, not posted: our three-leg parlays in the {lg} {rec}, under the {FLOOR:.0%} they need. "
            f"Each game's are still built and graded on the record, and they come back by themselves once "
            f"{RELEASE_N} graded since {since} hit {FLOOR:.0%}.")


def verdict(out: dict) -> dict:
    """The settle pass's line for the heartbeat: the leagues on paper, each
    with its record and its tickets since, and the ones back."""
    hs = (out or {}).get("holds") or []
    keep = ("sport", "since", "n", "won", "since_n", "since_won", "source")
    return {"on_paper": [h.get("sport") for h in hs],
            "back": [h.get("sport") for h in (out or {}).get("released") or []],
            "holds": [{k: h.get(k) for k in keep if h.get(k) is not None} for h in hs]}
