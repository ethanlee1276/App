"""Line-movement tracking: opening vs current lines and steam detection.

Every time real odds are attached to a slate, a timestamped snapshot of each
book's line is appended to ``data/cache/line_history.jsonl``. Over repeated
runs that builds a movement history the analyzer reads:

  * per book: opening line, current line, delta, and when it last moved;
  * per prop: consensus move (median across books), direction, and a **steam**
    flag — several books moving the same direction by a real amount within a
    short window, the classic footprint of sharp money.

Reverse line movement (line moving against the public) additionally needs
public betting percentages, which have no free feed — documented as future
work. The analysis functions are pure and unit-tested; recording is one
append per run.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .sources.fetch import CACHE_DIR

HISTORY_PATH = CACHE_DIR / "line_history.jsonl"


# --- recording --------------------------------------------------------------
def record_snapshots(props, ts: float | None = None,
                     path: str | Path | None = None) -> int:
    """Append one row per (prop, book) with the current line. Skips proxy
    lines — only real book numbers are worth tracking."""
    ts = ts if ts is not None else time.time()
    path = Path(path) if path else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a") as fh:
        for prop in props:
            for ln in prop.lines:
                if ln.book == "proxy":
                    continue
                fh.write(json.dumps({
                    "ts": ts, "player": prop.player, "market": prop.market,
                    "book": ln.book, "line": ln.line, "over_odds": ln.over_odds,
                }) + "\n")
                n += 1
    return n


def load_history(path: str | Path | None = None) -> list[dict]:
    path = Path(path) if path else HISTORY_PATH
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if raw:
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return rows


def closing_lines(rows: list[dict], before_ts: float | None = None
                  ) -> dict[tuple[str, str], float]:
    """Latest recorded line per ``(player, market)`` — the closing number.

    Beating the closing line is the industry's best available evidence that a
    bet was actually +EV, and unlike a true edge measurement it needs no paid
    historical odds: we simply keep snapshotting until the game starts and take
    the last one. Where several books are quoted at the same instant we take the
    median, so one outlier book can't define the close.

    ``before_ts`` restricts to snapshots at or before a cutoff (e.g. first
    pitch), so a stale post-game snapshot can't masquerade as the close.
    """
    latest: dict[tuple[str, str], float] = {}
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        try:
            ts = float(r["ts"])
            key = (r["player"], r["market"])
        except (KeyError, TypeError, ValueError):
            continue
        if before_ts is not None and ts > before_ts:
            continue
        grouped.setdefault(key, []).append(r)

    for key, items in grouped.items():
        last_ts = max(float(r["ts"]) for r in items)
        at_close = [float(r["line"]) for r in items
                    if float(r["ts"]) == last_ts and r.get("line") is not None]
        if at_close:
            latest[key] = _median(at_close)
    return latest


# --- analysis (pure) --------------------------------------------------------
@dataclass
class BookMove:
    book: str
    open: float
    current: float
    delta: float
    last_move_ts: float


@dataclass
class MoveReport:
    player: str
    market: str
    open: float          # consensus (median) opening line
    current: float       # consensus current line
    delta: float
    direction: str       # "up" | "down"
    steam: bool
    books: list[BookMove] = field(default_factory=list)


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def analyze(rows: list[dict], min_move: float = 0.5, steam_books: int = 2,
            window_s: float = 3600.0, now: float | None = None) -> list[MoveReport]:
    """Collapse the snapshot history into per-prop movement reports.

    Consecutive identical lines are deduped, so re-recording an unchanged
    board (e.g. from a cached response) never fabricates movement.
    """
    now = now if now is not None else time.time()

    # (player, market, book) -> time-ordered [(ts, line)]
    series: dict[tuple, list[tuple[float, float]]] = {}
    for r in rows:
        key = (r["player"], r["market"], r["book"])
        series.setdefault(key, []).append((float(r["ts"]), float(r["line"])))

    per_prop: dict[tuple, list[BookMove]] = {}
    for (player, market, book), pts in series.items():
        pts.sort(key=lambda p: p[0])
        dedup: list[tuple[float, float]] = []
        for ts, line in pts:
            if not dedup or dedup[-1][1] != line:
                dedup.append((ts, line))
        open_line, current = dedup[0][1], dedup[-1][1]
        per_prop.setdefault((player, market), []).append(BookMove(
            book=book, open=open_line, current=current,
            delta=current - open_line,
            last_move_ts=dedup[-1][0] if len(dedup) > 1 else 0.0,
        ))

    reports = []
    for (player, market), books in per_prop.items():
        delta = _median([b.current for b in books]) - _median([b.open for b in books])
        if abs(delta) < 1e-9 and not any(abs(b.delta) >= min_move for b in books):
            continue  # nothing moved
        direction = "up" if delta >= 0 else "down"
        sign = 1 if direction == "up" else -1
        movers = [
            b for b in books
            if sign * b.delta >= min_move and (now - b.last_move_ts) <= window_s
        ]
        reports.append(MoveReport(
            player=player, market=market,
            open=round(_median([b.open for b in books]), 1),
            current=round(_median([b.current for b in books]), 1),
            delta=round(delta, 1),
            direction=direction,
            steam=len(movers) >= steam_books,
            books=books,
        ))
    reports.sort(key=lambda r: (r.steam, abs(r.delta)), reverse=True)
    return reports


def summary_lines(reports: list[MoveReport], limit: int = 10) -> list[str]:
    out = []
    for r in reports[:limit]:
        arrow = "▲" if r.direction == "up" else "▼"
        steam = "  🔥 STEAM" if r.steam else ""
        out.append(f"  {arrow} {r.player} {r.market}: {r.open:g} → {r.current:g} "
                   f"({r.delta:+g}){steam}")
    return out
