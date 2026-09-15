"""Camp signals — daily depth-chart snapshots diffed across the preseason.

The pro-bettor read on preseason: the BOX SCORES are mostly noise (backups
compile stats against backups in the fourth quarter), but the DEPTH CHART
is the coaching staff's own public verdict, and it moves all through camp.
Sleeper's players feed carries every depth chart and the site already
downloads it daily for the Fantasy page — then throws yesterday's copy
away. This module keeps a dated snapshot per day and diffs the window:

* **risers** — climbed the depth chart since camp opened (WR3 → WR1);
* **fallers** — slid down it;
* **new starters** — took over a №1 job they didn't hold before, the
  single strongest Week-1 signal camp produces (rookies flagged).

That is the honest preseason edge: who WON a job, from the team's own
chart, tracked daily — not a projection invented off an August stat line.
Week-1 prop lines and late-August fantasy drafts both price off last
season's roles; the diff is where they're already wrong.

Snapshots are stored in one JSON file (kept ~90 days). Everything here is
pure over loaded snapshots; only the record/load helpers touch disk.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .offseason import FANTASY_POSITIONS, _canon_team
from .sources.fetch import CACHE_DIR

SNAPSHOT_FILE = "depth_snapshots.json"
KEEP_DAYS = 90
# Depth spots deeper than this are churn, not signal — a WR6↔WR7 swap is
# roster management. Movement only counts when it touches the top of the
# chart on at least one end.
SIGNAL_ORDER = 3


def _path(path=None) -> Path:
    return Path(path) if path else Path(CACHE_DIR) / SNAPSHOT_FILE


def depth_snapshot(blob: dict) -> dict[str, dict]:
    """One day's depth chart: {player name: {team, position, order}}.

    Only fantasy positions with a team and a numeric depth slot — a player
    off the chart entirely carries no order, and inventing one would make
    every practice-squad move look like a demotion.
    """
    out: dict[str, dict] = {}
    for p in (blob or {}).values():
        if not isinstance(p, dict):
            continue
        pos = (p.get("position") or "").upper()
        if pos not in FANTASY_POSITIONS or not p.get("active", True):
            continue
        name = (p.get("full_name")
                or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
        team = _canon_team(p.get("team"))
        order = p.get("depth_chart_order")
        if not name or not team or not isinstance(order, int):
            continue
        out[name] = {"team": team, "position": pos, "order": order,
                     "rookie": (p.get("years_exp") or 0) == 0}
    return out


def record_snapshot(blob: dict, today: str, path=None) -> dict[str, dict]:
    """Store today's snapshot (overwriting same-date reruns), prune beyond
    KEEP_DAYS, and return the full snapshot store {date: snapshot}."""
    p = _path(path)
    try:
        store = json.loads(p.read_text())
    except (OSError, ValueError):
        store = {}
    snap = depth_snapshot(blob)
    if snap:                       # an empty feed must not erase history
        store[today] = snap
    try:
        floor = (_dt.date.fromisoformat(today)
                 - _dt.timedelta(days=KEEP_DAYS)).isoformat()
        store = {d: s for d, s in store.items() if d >= floor}
    except ValueError:
        pass
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store))
    except OSError:
        pass                       # a read-only disk loses history, not the build
    return store


def camp_movement(store: dict[str, dict], min_days: int = 2) -> dict:
    """Diff the earliest stored snapshot against the latest.

    Returns {"from", "to", "risers", "fallers", "new_starters"} — or a
    not-enough-history marker until ``min_days`` distinct days exist:
    a single snapshot has nothing to diff, and pretending otherwise would
    report the entire league as "new"."""
    days = sorted(store)
    if len(days) < min_days:
        return {"tracking_since": days[0] if days else None,
                "days": len(days), "risers": [], "fallers": [],
                "new_starters": []}
    first, last = store[days[0]], store[days[-1]]
    risers, fallers, new_starters = [], [], []
    for name, now in last.items():
        was = first.get(name)
        if was is None or was["team"] != now["team"]:
            # New to the chart or new to the team — the roster-sync layer
            # already reports trades; a depth diff across teams is noise.
            continue
        delta = was["order"] - now["order"]        # positive = climbed
        if delta == 0:
            continue
        if min(was["order"], now["order"]) > SIGNAL_ORDER:
            continue
        row = {"player": name, "team": now["team"],
               "position": now["position"], "from_order": was["order"],
               "to_order": now["order"], "rookie": now.get("rookie", False)}
        if delta > 0:
            (new_starters if now["order"] == 1 and was["order"] > 1
             else risers).append(row)
        else:
            fallers.append(row)
    key = lambda r: (r["to_order"], -(r["from_order"] - r["to_order"]))  # noqa: E731
    risers.sort(key=key)
    new_starters.sort(key=lambda r: (r["position"], r["team"]))
    fallers.sort(key=lambda r: (r["from_order"], r["to_order"]))
    return {"from": days[0], "to": days[-1], "days": len(days),
            "tracking_since": days[0], "risers": risers,
            "fallers": fallers, "new_starters": new_starters}


def in_camp_window(today: str) -> bool:
    """Mid-July through the season's first full week — when depth-chart
    movement is signal. The rest of the year it's injury churn the
    injury layer already covers."""
    try:
        d = _dt.date.fromisoformat(today)
    except ValueError:
        return False
    return (d.month == 7 and d.day >= 15) or d.month == 8 or \
        (d.month == 9 and d.day <= 14)


def camp_report(blob: dict | None, today: str, path=None) -> dict | None:
    """The Fantasy page's camp section: record today, diff the window.
    None outside the camp window or without a roster feed."""
    if blob is None or not in_camp_window(today):
        return None
    store = record_snapshot(blob, today, path=path)
    out = camp_movement(store)
    out["window"] = "preseason"
    return out
