"""The inventions, one file per board: what each build hands the pick page.

Ethan, 2026-10-16: "add everything now. 1-13 and dont stop till
everything is done." Thirteen ideas from the brainstorm he asked for —
ideas no betting app he could name was using. Each lives in its own
module with its own measurement; this is only the carrier.

ONE PRIVATE FILE PER BOARD. A build calls `build` with the slate it just
priced and writes `ideas_<sport>.json` beside the full boards
(`gate.FULL_DIR`, outside the web root, so Caddy has no route to it).
`server.py` serves a slice of it — one pick's, or one game's — at
/api/ideas, behind the membership, exactly as the books' minute-by-minute
lines are served. Nothing here is on a public path.

ONE SECTION, ONE FAILURE. Every invention is a section, built inside its
own try: a section that raises is recorded as an error string under its
own name and the other sections ship. A new idea cannot cost the board,
and a broken one says so instead of vanishing.

NOTHING HERE MOVES A NUMBER. Every section is a reading, shown as one.
An invention reaches a price only through its own measurement and its
own bar: once its saved verdict holds, engine/ideagate applies it where
it belongs (Ethan, 2026-10-17: "make sure we are wrapping all the features
into the most likely bets and edge bets where it makes sense").

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The latest build's data per sport, in this process — what engine/ideagate
#: reads while the same build makes its Most Likely board and Edge picks.
LAST: dict = {}

#: The sections, in the order the pick page draws them. Each entry:
#: name -> module. The module's `ideas_section(props, games, board, sport)`
#: returns JSON-able data; its `pick_view` and `game_view` slice that data
#: for one pick or one game; an optional `journal(sport, data)` keeps what
#: its measurement needs, and runs only from a build (`attach`), never from
#: `build`, so a test that builds the file writes nothing anywhere.
#: Imported lazily, so one module's import error is that section's error
#: and nobody else's.
SECTIONS = {
    "menu": "bookmenu",
    "curve": "altcurve",
    "recipe": "bookrecipe",
    "copies": "bookclusters",
    "practice": "practice",
    "attention": "attention",
    "kicks": "kickphysics",
    "rookie": "rookies",
    "sim": "playsim",
    "role": "rolechange",
    "range": "conformal",
    "autopsy": "autopsy",
}

_CACHE: dict = {}

#: The most a board build spends on the readings, all sections together.
#: Past it the rest are skipped for this build (named in the file's errors)
#: and the board is written on time: the NFL build ran out its 600 seconds
#: every cycle on 2026-10-17, and the readings are the part that can wait.
BUDGET_SECONDS = 60.0


def _section_fns(name: str):
    import importlib
    m = importlib.import_module(f"engine.{SECTIONS[name]}")
    return (getattr(m, "ideas_section", None), getattr(m, "pick_view", None),
            getattr(m, "game_view", None), getattr(m, "journal", None))


def build(sport: str, props=None, games=None, board=None, only=None,
          budget: float = BUDGET_SECONDS, clock=time.monotonic) -> dict:
    """Every section for one board, each timed (``timings``), inside one
    budget. Never raises."""
    out: dict = {"sport": sport, "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                 "sections": {}, "errors": {}, "timings": {}}
    t0 = clock()
    for name in SECTIONS:
        if only and name not in only:
            continue
        if clock() - t0 > budget:
            out["errors"][name] = f"skipped: the readings' {budget:.0f}-second budget was spent"
            continue
        t = clock()
        try:
            fn = _section_fns(name)[0]
            if fn is None:
                continue
            data = fn(props or [], games or [], board or {}, sport)
            if data is not None:
                out["sections"][name] = data
        except Exception as exc:                            # noqa: BLE001
            out["errors"][name] = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            out["timings"][name] = round(clock() - t, 2)
    return out


def directory() -> Path:
    from .gate import FULL_DIR
    return Path(FULL_DIR)


def path_for(sport: str, where=None) -> Path:
    return Path(where or directory()) / f"ideas_{str(sport).lower()[:8]}.json"


def write(sport: str, data: dict, where=None) -> Path:
    """Atomically, so the server never reads half a file."""
    p = path_for(sport, where)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), default=str))
    os.replace(tmp, p)
    return p


def read(sport: str, where=None) -> dict:
    """The last file a build wrote, cached on its modification time."""
    p = path_for(sport, where)
    try:
        st = p.stat()
    except OSError:
        return {}
    hit = _CACHE.get(str(p))
    if hit and hit[0] == st.st_mtime_ns:
        return hit[1]
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    _CACHE[str(p)] = (st.st_mtime_ns, data)
    return data


def pick_slice(data: dict, player: str, market: str, side: str = "", line=None) -> dict:
    """Each section's reading for one pick (only sections with one)."""
    out: dict = {"sport": data.get("sport"), "built_at": data.get("built_at"), "player": player,
                 "market": market, "sections": {}}
    for name, sec in (data.get("sections") or {}).items():
        if name not in SECTIONS:
            continue
        try:
            fn = _section_fns(name)[1]
            v = fn(sec, player, market, side, line) if fn else None
        except Exception:                                   # noqa: BLE001
            v = None
        if v:
            out["sections"][name] = v
    return out


def game_slice(data: dict, home: str, away: str) -> dict:
    out: dict = {"sport": data.get("sport"), "built_at": data.get("built_at"), "home": home,
                 "away": away, "sections": {}}
    for name, sec in (data.get("sections") or {}).items():
        if name not in SECTIONS:
            continue
        try:
            fn = _section_fns(name)[2]
            v = fn(sec, home, away) if fn else None
        except Exception:                                   # noqa: BLE001
            v = None
        if v:
            out["sections"][name] = v
    return out


def attach(sport: str, props, games, board, out=None, quiet: bool = False) -> dict:
    """What a build calls: build every section and write the file beside
    the build's own full board (`out` is the board's public path, as
    `gate.publish` takes it). Never raises; prints one line, and the error
    names if any.

    THE JOURNALS RUN ONLY FOR THE REAL BOARD. A build pointed at a scratch
    tree (every test that runs one) writes its file there and keeps nothing
    in the history database, which no test may touch."""
    try:
        from . import gate
        where = gate._full_dir_for(out) if out else directory()
        live = Path(where).resolve() == Path(directory()).resolve()
        data = build(sport, props, games, board)
        LAST[sport] = data
        for name, sec in (list(data["sections"].items()) if live else []):
            try:
                fn = _section_fns(name)[3]
                if fn is not None:
                    fn(sport, sec)
            except Exception as exc:                        # noqa: BLE001
                data["errors"][f"{name}.journal"] = f"{type(exc).__name__}: {exc}"[:300]
        write(sport, data, where)
        if not quiet:
            errs = data.get("errors") or {}
            tm = data.get("timings") or {}
            slow = sorted(tm.items(), key=lambda kv: -kv[1])[:3]
            print(f"  Ideas: {len(data['sections'])} section(s) written for {sport.upper()} in "
                  f"{sum(tm.values()):.0f}s (slowest: {', '.join(f'{k} {v:.0f}s' for k, v in slow)})"
                  + (f" — failed: {', '.join(f'{k} ({v})' for k, v in errs.items())}" if errs else ""))
        return data
    except Exception as exc:                                # noqa: BLE001
        if not quiet:
            print(f"  ⚠️  ideas file skipped: {exc}")
        return {}
