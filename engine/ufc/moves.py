"""Where each fight's line opened, and where it is now.

Read from the snapshots the UFC build has written on every paid pull since
2026-08-10 (`linemoves.record_fight_snapshots`): one row per book per
fighter, his price and his opponent's, in the shared line history.

docs/UFC_MODEL.md, "The two upgrades worth money": MMA lines "move further
from open to close than almost any market, and a late sharp move on a
prelim nobody is watching is one of the highest-signal events in the
sport." The store that answers it has been filling for two months, and
nothing read it — `linemoves.opening_odds` was written for it and has no
caller. Ethan, 2026-10-13: "ik CFB and mlb and nba and ufc is missing
stuff."

EVIDENCE ONLY. The card says where the line opened, where it is, and which
way that is for the pick; the grade's movement component stays None
(`engine/ufc/model.py`) until a measurement on settled fights says a move
carries something the closing price does not (`stakecheck.py --clv --sport
ufc` reads the close today).

THIS BOUT ONLY. A fighter's history holds every card he has been priced on,
so a row counts toward tonight's line only if it was taken before this
bout's start and within `WINDOW_DAYS` of it, and — where the row carries
its bout's start — that start is this one. His fight in August is not
where October's line opened.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

#: How long before the bout a snapshot can be about it. The build prices a
#: card inside an eight-day window; a fighter's previous bout is months back.
WINDOW_DAYS = 14

#: A snapshot naming its bout's start counts only within this of tonight's.
SAME_BOUT_S = 36 * 3600


def _epoch(stamp) -> float | None:
    try:
        return datetime.datetime.fromisoformat(
            str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def read(names, path=None) -> list[dict]:
    """The stored moneyline snapshots naming any of ``names`` (normalized
    match), read a line at a time — the history holds every sport, and
    only a fight row is parsed."""
    from ..linemoves import HISTORY_PATH
    from ..sources.oddsapi import normalize_name
    want = {normalize_name(n) for n in names if n}
    path = Path(path) if path else HISTORY_PATH
    if not want or not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            if '"moneyline"' not in raw:
                continue
            try:
                r = json.loads(raw)
            except ValueError:
                continue
            if r.get("market") == "moneyline" and normalize_name(str(r.get("player") or "")) in want:
                out.append(r)
    return out


def bout_rows(rows: list[dict], commence) -> list[dict]:
    """The rows that are about the bout starting at ``commence``."""
    start = _epoch(commence)
    if start is None:
        return []
    keep = []
    for r in rows:
        try:
            ts = float(r["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (start - WINDOW_DAYS * 86400 <= ts < start):
            continue
        own = r.get("start_ts")
        if own is not None and abs(float(own) - start) > SAME_BOUT_S:
            continue
        keep.append(r)
    return keep


def _implied(odds) -> float:
    o = float(odds)
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _median_at(snaps: list[dict]) -> int | None:
    odds = sorted(int(s["over_odds"]) for s in snaps if s.get("over_odds") is not None)
    return odds[len(odds) // 2] if odds else None


def fighter_move(rows: list[dict], fighter: str) -> dict | None:
    """``{"open", "now", "open_ts", "now_ts", "books_open", "books_now",
    "pulls", "pts"}`` for one fighter — the median price across the books at
    the first and at the latest pull, and the move in implied probability
    points (positive: the market likes him more now). None with no rows."""
    from ..sources.oddsapi import normalize_name
    me = normalize_name(fighter)
    by_ts: dict = {}
    for r in rows:
        if normalize_name(str(r.get("player") or "")) == me:
            by_ts.setdefault(float(r["ts"]), []).append(r)
    if not by_ts:
        return None
    first, last = min(by_ts), max(by_ts)
    o, n = _median_at(by_ts[first]), _median_at(by_ts[last])
    if o is None or n is None:
        return None
    return {"open": o, "now": n, "open_ts": first, "now_ts": last,
            "books_open": len(by_ts[first]), "books_now": len(by_ts[last]),
            "pulls": len(by_ts),
            "pts": round((_implied(n) - _implied(o)) * 100.0, 1)}


def bout_move(rows: list[dict], a: str, b: str, commence) -> dict | None:
    """``{"a": move, "b": move}`` for one bout, or None before two pulls —
    one price is a line, not a move."""
    mine = bout_rows(rows, commence)
    ma, mb = fighter_move(mine, a), fighter_move(mine, b)
    if not ma and not mb:
        return None
    if max((ma or {}).get("pulls", 0), (mb or {}).get("pulls", 0)) < 2:
        return None
    return {"a": dict(ma or {}, name=a), "b": dict(mb or {}, name=b)}


def note(move: dict | None, pick: str = "") -> str:
    """The card's sentence: where the line opened, where it is, and which way
    that is for ``pick`` when there is one."""
    if not move:
        return ""
    from ..sources.oddsapi import normalize_name

    def leg(m):
        return f"{m['name']} {m['open']:+d} → {m['now']:+d}"
    legs = [move[k] for k in ("a", "b") if move.get(k) and "open" in move[k]]
    if not legs:
        return ""
    text = "Line opened " + " · ".join(leg(m) for m in legs)
    mine = next((m for m in legs if pick and normalize_name(m["name"]) == normalize_name(pick)), None)
    if mine is not None:
        pts = mine["pts"]
        if abs(pts) < 1.0:
            text += f". Barely moved for {mine['name']} ({pts:+.1f} points)"
        else:
            text += (f". The market has moved {abs(pts):.1f} points "
                     f"{'toward' if pts > 0 else 'against'} {mine['name']}")
    return text + f" ({max(m['pulls'] for m in legs)} pulls). Shown, not priced."


def attach(out: dict, fights: list[dict], path=None) -> int:
    """Put each bout's move on its pick and pass rows (``line_move``, and the
    card's sentence as ``line_note``), keyed as the build keys the weigh-ins:
    ``"<fighter_a> vs <fighter_b>"``. Returns how many bouts had a move."""
    pairs = [((f.get("prices") or {}).get("fighter_a") or "",
              (f.get("prices") or {}).get("fighter_b") or "", f.get("commence"))
             for f in fights or []]
    hist = read({n for a, b, _c in pairs for n in (a, b) if n}, path)
    by = {f"{a} vs {b}": bout_move(hist, a, b, c) for a, b, c in pairs}
    for row in list(out.get("picks") or []) + list(out.get("pass_list") or []):
        mv = by.get(row.get("fight"))
        if mv:
            row["line_move"] = mv
            row["line_note"] = note(mv, row.get("pick", ""))
    return sum(1 for v in by.values() if v)
