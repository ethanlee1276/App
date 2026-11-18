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

THE TWO-LEG TICKETS HAVE A HOLD OF THEIR OWN (GPWIN1, 2026-11-18). A game's
two strongest picks as a two-leg ticket (engine/gameparlays.tickets_of,
source ``game_two``) are a different bet with a different record, so they are
held on theirs and by their own bar (SIZES): a league's last WINDOW graded
two-leg tickets, 40 at least, hitting under 36%, where the tickets claim 42%
or better. The three-leg hold reads three-leg tickets only, so the easier
ticket never brings the harder one back. A two-leg hold is the same row with
``"legs": 2``; `held(sport, legs=2)` asks for it.

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

#: Each size of ticket and its own bar: the journal's source, the hit rate it
#: must reach, the graded tickets before the hold says anything, and the ones
#: graded since a hold began before they can bring it back. Three legs are the
#: constants above; two legs are GPWIN1's.
SIZES = {3: {"source": SOURCE, "floor": FLOOR, "min_n": MIN_N, "release_n": RELEASE_N, "word": "three-leg"},
         2: {"source": "game_two", "floor": 0.36, "min_n": 40, "release_n": 40, "word": "two-leg"}}


def _legs(h: dict) -> int:
    """The size a saved hold is on: three legs unless it says two."""
    return 2 if int((h or {}).get("legs") or 3) == 2 else 3


def graded(conn, legs: int = 3) -> dict:
    """``{league: [(day journaled, won), ...]}``, oldest first: every graded
    ticket of that size in the journal (three legs: ``game_three``)."""
    try:
        rows = conn.execute("SELECT sport, ts, status FROM parlays WHERE source=? AND status IN ('won','lost') "
                            "ORDER BY ts, id", (SIZES[legs]["source"],)).fetchall()
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
    tickets hit under their floor, carry each hold's start, release the ones
    whose tickets since have hit it, and save. Each size on its own record
    (SIZES)."""
    today = today or _dt.date.today()
    prev = load(path)
    holds = {(h["sport"], _legs(h)): dict(h) for h in prev.get("holds") or [] if h.get("sport")}
    released = {(h["sport"], _legs(h)): dict(h) for h in prev.get("released") or [] if h.get("sport")}
    for k in STANDING:
        if (k["sport"], 3) not in holds and (k["sport"], 3) not in released:
            holds[(k["sport"], 3)] = dict(k)
    for legs, cfg in SIZES.items():
        by = graded(conn, legs)
        for sp in sorted(set(by) | {s for s, n in holds if n == legs}):
            rows = by.get(sp, [])
            h = holds.get((sp, legs))
            if h:
                if h.get("source") != "standing":
                    h["n"], h["won"] = _rate(rows[-WINDOW:])
                h["since_n"], h["since_won"] = _rate([r for r in rows if r[0] >= str(h.get("since") or "")])
                if h["since_n"] >= cfg["release_n"] and h["since_won"] / h["since_n"] >= cfg["floor"]:
                    released[(sp, legs)] = {**h, "released_on": today.isoformat()}
                    holds.pop((sp, legs))
                continue
            rel = released.get((sp, legs))
            pool = [r for r in rows if not rel or r[0] > str(rel.get("released_on") or "")]
            n, won = _rate(pool[-WINDOW:])
            if n >= cfg["min_n"] and won / n < cfg["floor"]:
                holds[(sp, legs)] = {"sport": sp, "since": today.isoformat(), "n": n, "won": won,
                                     "source": "measured", "since_n": 0, "since_won": 0,
                                     **({"legs": legs} if legs != 3 else {})}
                released.pop((sp, legs), None)
    order = lambda h: (h["sport"], _legs(h))                                   # noqa: E731
    out = {"measured_on": today.isoformat(), "floor": FLOOR, "window": WINDOW,
           "holds": sorted(holds.values(), key=order), "released": sorted(released.values(), key=order)}
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
    """The leagues on paper now, either size: the saved holds, and the
    standing hold until a saved pass has released it."""
    state = load(path)
    out = [h for h in state.get("holds") or [] if h.get("sport")]
    have = {h["sport"] for h in out if _legs(h) == 3} | {h.get("sport") for h in state.get("released") or []
                                                         if _legs(h) == 3}
    out += [dict(k) for k in STANDING if k["sport"] not in have]
    return out


def held(sport, path=None, legs: int = 3) -> dict | None:
    """The hold on a league's three-leg tickets (or, ``legs=2``, its two-leg
    ones), or None."""
    sp = str(sport or "").lower()
    return next((h for h in holds(path) if h.get("sport") == sp and _legs(h) == legs), None)


def words(h: dict) -> str:
    """The hold in a reader's words, for every game it covers."""
    n, won = int(h.get("n") or 0), int(h.get("won") or 0)
    lg = str(h.get("sport") or "").upper()
    rec = (f"have hit {won} of {n} ({won / n:.0%})" if n else f"have hit under {SIZES[_legs(h)]['floor']:.0%}")
    if h.get("source") != "standing" and n:
        rec = f"have hit {won} of their last {n} ({won / n:.0%})"
    try:
        day = _dt.date.fromisoformat(str(h.get("since") or ""))
        since = f"{day.day} {day.strftime('%B')}"
    except ValueError:
        since = "the hold began"
    cfg = SIZES[_legs(h)]
    return (f"On paper, not posted: our {cfg['word']} parlays in the {lg} {rec}, under the {cfg['floor']:.0%} "
            f"they need. Each game's are still built and graded on the record, and they come back by themselves "
            f"once {cfg['release_n']} graded since {since} hit {cfg['floor']:.0%}.")


def verdict(out: dict) -> dict:
    """The settle pass's line for the heartbeat: the leagues on paper, each
    with its record and its tickets since, and the ones back."""
    hs = (out or {}).get("holds") or []
    keep = ("sport", "since", "n", "won", "since_n", "since_won", "source", "legs")
    three = [h for h in hs if _legs(h) == 3]
    two = [h for h in hs if _legs(h) == 2]
    return {"on_paper": [h.get("sport") for h in three],
            "back": [h.get("sport") for h in (out or {}).get("released") or [] if _legs(h) == 3],
            **({"two_leg_on_paper": [h.get("sport") for h in two]} if two else {}),
            "holds": [{k: h.get(k) for k in keep if h.get(k) is not None} for h in hs]}
