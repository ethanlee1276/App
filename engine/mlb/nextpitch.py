"""The next pitch, by the pitcher's own mix in this count.

Ethan, 2026-10-15, from the brainstorm he asked to have built: MLB
"next-pitch odds" on the live pitch tracker. What it is, said plainly: for
the man on the mound, every pitch we have stored from him this season and
last (engine/mlb/charts' `mlb_pitches`), grouped by the count it was thrown
in, against batters on the side this one stands on, and each kind's share
of them. Not a model: a count of what he has done, which the page says. It
moves no number on any board.

THE COUNT BEFORE THE PITCH. The feed's count on a pitch is the count
after it (a first-pitch strike reads 0-1), so the count a pitch was thrown
in is the one after the pitch before it in the same at-bat, and 0-0 for
the first.

TOO FEW IN A COUNT. A count he has thrown in fewer than MIN_N times
against this side falls back, in order, to: that count against every
batter; the count's family against this side (ahead, even or behind);
that family against every batter; then his whole mix. Each count says
which it used and how many pitches stand behind it.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

#: Pitches a count needs before its own mix is shown.
MIN_N = 30
#: Kinds shown per count, most thrown first; the rest are "Other".
TOP = 5
#: How long one pitcher's table is kept in a running live build.
TTL_S = 6 * 3600

NAMES = {"FF": "Four-seam", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper", "SV": "Slurve",
         "CU": "Curveball", "KC": "Knuckle curve", "CS": "Slow curve", "CH": "Changeup", "FS": "Splitter",
         "FO": "Forkball", "SC": "Screwball", "KN": "Knuckleball", "EP": "Eephus", "FA": "Fastball"}
COUNTS = [f"{b}-{s}" for b in range(4) for s in range(3)]


def family(key: str) -> str:
    b, s = (int(x) for x in key.split("-"))
    return "ahead" if s > b else "behind" if b > s else "even"


def counts_before(rows: list[dict]) -> list[tuple[str, str, str]]:
    """[(count before, pitch type, bat side)] — ``rows`` ordered by game,
    at-bat and pitch number. A pitch whose earlier count the feed did not
    give is skipped, never guessed."""
    out, key, prev = [], None, (0, 0)
    for r in rows:
        ab = (r.get("game_pk"), r.get("at_bat"))
        if ab != key:
            key, prev = ab, (0, 0)
        t = r.get("pitch_type") or ""
        if prev is not None and t and prev[0] <= 3 and prev[1] <= 2:
            out.append((f"{prev[0]}-{prev[1]}", t, r.get("bat_side") or ""))
        b, s = r.get("balls"), r.get("strikes")
        prev = (b, s) if isinstance(b, int) and isinstance(s, int) else None
    return out


def _mix(items: list[str]) -> list[list]:
    tot: dict = {}
    for t in items:
        tot[t] = tot.get(t, 0) + 1
    n = len(items)
    ranked = sorted(tot.items(), key=lambda kv: -kv[1])
    out = [[t, NAMES.get(t, t), round(c / n, 3)] for t, c in ranked[:TOP]]
    rest = sum(c for _t, c in ranked[TOP:])
    if rest:
        out.append(["", "Other", round(rest / n, 3)])
    return out


def table(seen: list[tuple[str, str, str]], side: str = "") -> dict:
    """{count: {"n", "basis", "mix": [[code, name, share], ...]}} for every
    count, with the fallbacks above."""
    mine = [x for x in seen if side and x[2] == side]
    out = {}
    for key in COUNTS:
        fam = family(key)
        tries = [("count", [t for c, t, _s in mine if c == key]),
                 ("count_all", [t for c, t, _s in seen if c == key]),
                 ("family", [t for c, t, _s in mine if family(c) == fam]),
                 ("family_all", [t for c, t, _s in seen if family(c) == fam]),
                 ("all", [t for _c, t, _s in mine] or [t for _c, t, _s in seen])]
        if not side:
            tries = [x for x in tries if x[0] in ("count_all", "family_all", "all")]
        basis, items = next(((b, i) for b, i in tries if len(i) >= MIN_N), tries[-1])
        if items:
            out[key] = {"n": len(items), "basis": basis, "fam": fam, "mix": _mix(items)}
    return out


def pitcher_rows(conn, pitcher_id: int) -> list[dict]:
    """His pitches, this season and the one before (his newest stored season)."""
    top = conn.execute("SELECT MAX(season) FROM mlb_pitches WHERE pitcher_id=?", (pitcher_id,)).fetchone()
    if not top or top[0] is None:
        return []
    cur = conn.execute("SELECT game_pk, at_bat, n, pitch_type, bat_side, balls, strikes FROM mlb_pitches "
                       "WHERE pitcher_id=? AND season IN (?, ?) ORDER BY game_pk, at_bat, n",
                       (pitcher_id, int(top[0]), int(top[0]) - 1))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


_CACHE: dict = {}


def for_current(current: dict | None, db_path: str | Path | None = None, conn=None) -> dict | None:
    """The live file's ``next_pitch``: the table for the pitcher on the
    mound against the batter's side, or None when there is nobody up, no
    database or nothing stored for him. The database opens read-only:
    a live build never creates or migrates it."""
    if not current or not current.get("pitcher_id"):
        return None
    pid, side = int(current["pitcher_id"]), str(current.get("bat_side") or "")
    hit = _CACHE.get((pid, side))
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    own = conn is None
    if own:
        from engine import db
        path = Path(db_path or db.DEFAULT_DB)
        if not path.exists():
            return None
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        seen = counts_before(pitcher_rows(conn, pid))
    except sqlite3.Error:
        seen = []
    finally:
        if own:
            conn.close()
    out = {"pitcher_id": pid, "side": side, "n": len(seen), "counts": table(seen, side)} if seen else None
    _CACHE[(pid, side)] = (time.time(), out)
    return out
