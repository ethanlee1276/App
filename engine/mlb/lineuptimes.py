"""When each game's lineup card actually posted.

MLB_MODEL §4 calls the lineup-release move "baseball's unique tell":

    MLB lines jump when lineups post. If a number moved against your
    position right after lineups confirmed, the market just priced
    information — a star's rest day, a platoon swap, a lefty-heavy
    lineup — that your inputs may have missed.

Every piece of that sentence was already available except the clock.
`lineupwatch.py` walks the schedule and reads each game's boxscore to see
whether both battingOrders are populated — it knows exactly which games
have posted and when it looked — and then returns `(posted, total)` and
throws the rest away. So "did the price move AFTER lineups posted" had no
boundary to be measured against.

This records the boundary. One row per game: the first moment we
observed its card up.

WHAT THE TIMESTAMP HONESTLY IS. It is when we FIRST SAW the lineup, not
when the team released it. Those differ by up to one polling interval, and
the gap is only bounded when something is actually polling — a day nobody
ran `lineupwatch --watch` gets whatever the next build happened to catch.
So the record carries `seen_within_s`: the gap since the previous look at
that game, which is the width of the window the true release time sits in.
A measurement that quietly treats a six-hour-old observation as a precise
boundary would find "movement after lineups" everywhere, because almost
all of a day's movement would fall on the after side.

Nothing prices from this. It is the input a measurement needs, recorded
first so the measurement has something to run on later.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

STORE = Path("data/cache/lineup_times.json")

#: Beyond this, the observation is too coarse to call a boundary. Four
#: hours is longer than the window between a card posting and first
#: pitch, so an "after" that could be this stale is not an after.
MAX_USEFUL_GAP_S = 4 * 3600


def _load(path: Path | None = None) -> dict:
    p = Path(path) if path else STORE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict, path: Path | None = None) -> None:
    p = Path(path) if path else STORE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def note_look(date: str, game_pk, posted: bool, ts: float | None = None,
              path: Path | None = None) -> dict:
    """Record one observation of one game's lineup state.

    Called on every look, posted or not — the not-posted looks are what
    make the gap meaningful. Without them the first sighting has no
    previous observation to be measured against and its window is
    unbounded, which is indistinguishable from a stale guess.

    Returns the row for this game. Idempotent once posted: the FIRST
    sighting is the boundary, and a later look must never move it.
    """
    ts = time.time() if ts is None else ts
    data = _load(path)
    key = f"{date}:{game_pk}"
    row = data.get(key) or {"date": date, "game_pk": game_pk,
                            "posted_ts": None, "last_look_ts": None,
                            "seen_within_s": None}
    if posted and row.get("posted_ts") is None:
        prev = row.get("last_look_ts")
        row["posted_ts"] = ts
        # The width of the window the real release sits in. None when we
        # have never looked before — honest ignorance, not zero.
        row["seen_within_s"] = round(ts - prev, 1) if prev else None
    row["last_look_ts"] = ts
    data[key] = row
    _save(data, path)
    return row


def posted_at(date: str, game_pk, path: Path | None = None) -> float | None:
    """The boundary for this game, or None if we never caught it."""
    row = _load(path).get(f"{date}:{game_pk}")
    return (row or {}).get("posted_ts")


def is_usable(date: str, game_pk, path: Path | None = None) -> bool:
    """Is the boundary tight enough to measure a move against?

    A first sighting with no previous look, or one separated from it by
    hours, is a real timestamp and a useless boundary. Saying so here
    keeps the caller from having to remember.
    """
    row = _load(path).get(f"{date}:{game_pk}") or {}
    if not row.get("posted_ts"):
        return False
    gap = row.get("seen_within_s")
    return gap is not None and gap <= MAX_USEFUL_GAP_S


def coverage(path: Path | None = None) -> dict:
    """How much of the record is actually measurable, for the report."""
    data = _load(path)
    total = len(data)
    caught = sum(1 for r in data.values() if r.get("posted_ts"))
    usable = sum(1 for r in data.values()
                 if r.get("posted_ts")
                 and r.get("seen_within_s") is not None
                 and r["seen_within_s"] <= MAX_USEFUL_GAP_S)
    gaps = sorted(r["seen_within_s"] for r in data.values()
                  if r.get("seen_within_s") is not None)
    return {"games": total, "caught": caught, "usable": usable,
            "median_gap_s": gaps[len(gaps) // 2] if gaps else None}
