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


def start_epoch(kickoff) -> float | None:
    """A game's start as a UNIX timestamp, or None when it cannot be known.

    Same rule as ``losspatterns.minutes_until``, for the same reason: a
    full ISO stamp with a Z or offset is usable, a bare local clock like
    "13:00" is not. Guessing a timezone onto a bare clock would silently
    decide which snapshots count as pre-game, and a wrong guess there is
    worse than no cut at all.
    """
    if not kickoff:
        return None
    import datetime as _dt
    try:
        start = _dt.datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None:
        return None                 # a naive stamp is a clock, not an instant
    return start.timestamp()


# --- recording --------------------------------------------------------------
def record_snapshots(props, ts: float | None = None,
                     path: str | Path | None = None,
                     slate=None) -> int:
    """Append one row per (prop, book) with the current line. Skips proxy
    lines — only real book numbers are worth tracking.

    ``slate`` (when given) stamps each row with its game's start time, so
    the close-picker can tell a pre-game price from an in-play one. The
    odds adapter's own docstring is why this matters: *"during a live
    game the event-odds endpoint returns current (in-play) prices"* — on
    a staggered slate a late pull re-prices the games already underway,
    and without a start stamp the last of those snapshots became the
    "close" for a game that had been running for two hours.
    """
    ts = ts if ts is not None else time.time()
    path = Path(path) if path else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a") as fh:
        for prop in props:
            start = None
            if slate is not None:
                try:
                    start = start_epoch(getattr(slate.game_for(prop),
                                                "kickoff", None))
                except Exception:                  # noqa: BLE001
                    start = None       # a slate that cannot locate its own
                                       # game must not cost the snapshot
            for ln in prop.lines:
                if ln.book == "proxy":
                    continue
                row = {
                    "ts": ts, "player": prop.player, "market": prop.market,
                    "book": ln.book, "line": ln.line, "over_odds": ln.over_odds,
                }
                if start is not None:
                    row["start_ts"] = start
                fh.write(json.dumps(row) + "\n")
                n += 1
    return n


def _pregame_only(items: list[dict]) -> list[dict]:
    """Drop snapshots taken at or after the game started.

    The start comes from the rows themselves, so one game has one start
    even when only some of its snapshots carry the stamp (rows recorded
    before this stamp existed carry none). No stamp anywhere = no cut:
    legacy history keeps reading exactly as it always has rather than
    being retroactively reinterpreted.
    """
    starts = [float(r["start_ts"]) for r in items
              if r.get("start_ts") is not None]
    if not starts:
        return items
    start = min(starts)
    pre = [r for r in items if float(r.get("ts", 0)) < start]
    # Every bet was placed on a pre-game price, so a key with nothing
    # pre-game is a slate we only ever saw in play — it has no close to
    # report, and inventing one from a live number is the bug being fixed.
    return pre


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


def closing_lines_by_date(rows: list[dict]) -> dict:
    """``{(normalized player, market, YYYY-MM-DD): closing line}`` — the last
    snapshot of each local day, medianed across the books quoted at that
    final instant.

    This is the free CLV source for the journal: each day's last recorded
    snapshot is the nearest thing to that night's close, and it accrues on
    every paid pull with no extra spend. (On fixed-line markets like 0.5 HR
    the line never moves, so CLV there reads 0 — honest, if unexciting.)"""
    import datetime as _dt
    from .sources.oddsapi import normalize_name

    grouped: dict[tuple, list[dict]] = {}
    for r in rows:
        try:
            ts = float(r["ts"])
            date = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            key = (normalize_name(r["player"]), r["market"], date)
            float(r["line"])                       # reject unusable rows early
            grouped.setdefault(key, []).append(r)
        except (KeyError, TypeError, ValueError):
            continue
    out: dict = {}
    for key, items in grouped.items():
        # A price quoted after first pitch is not a closing line — see
        # _pregame_only. Without this cut the last in-play re-price of a
        # staggered slate became the "close", and every CLV computed off
        # it was fiction dressed as evidence.
        items = _pregame_only(items)
        if not items:
            continue
        last = max(float(r["ts"]) for r in items)
        out[key] = _median([float(r["line"]) for r in items
                            if float(r["ts"]) == last])
    return out


def closing_odds_by_date(rows: list[dict]) -> dict:
    """``{(normalized player, market, YYYY-MM-DD): {"over": px, "under": px}}``

    BOTH SIDES, and that is the fix rather than a nicety. This returned
    the OVER price alone, and `ledger._settle_all` looked it up with a key
    carrying no side — so every UNDER bet in the journal recorded the
    OVER's closing price as its own.

    HOW IT SHOWED, 2026-08-09, on 55 bets with a close: mean CLV +3.58%
    at t = +2.0, which reads as edge — while the internal check ran
    backwards. Win rate when we "beat the close" was 41.2%; when we did
    not, 61.9%. Beating the close is supposed to PREDICT winning. Half the
    book was being scored against the opposite side of its own market, so
    for those bets the measurement was inverted by construction.

    The snapshots have carried `under_odds` since the table was created
    (db.py). Nothing read it.

    Same close-picking discipline as before: pre-game snapshots only, last
    instant of the day, median across the books quoted at it. A side with
    no usable price comes back None rather than absent, so a caller can
    tell "no quote" from "no snapshot".
    """
    import datetime as _dt
    from .sources.oddsapi import normalize_name

    grouped: dict[tuple, list[dict]] = {}
    for r in rows:
        try:
            ts = float(r["ts"])
            # A row is usable if EITHER side is quoted. Requiring the over
            # was what made the under invisible.
            if r.get("over_odds") in (None, "") and \
                    r.get("under_odds") in (None, ""):
                continue
            date = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            grouped.setdefault(
                (normalize_name(r["player"]), r["market"], date), []).append(r)
        except (KeyError, TypeError, ValueError):
            continue
    out: dict = {}
    for key, items in grouped.items():
        items = _pregame_only(items)
        if not items:
            continue
        last = max(float(r["ts"]) for r in items)
        at_close = [r for r in items if float(r["ts"]) == last]

        def _side(col):
            vals = []
            for r in at_close:
                v = r.get(col)
                if v in (None, ""):
                    continue
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
            return _median(vals) if vals else None

        out[key] = {"over": _side("over_odds"), "under": _side("under_odds")}
    return out


def todays_rows(rows: list[dict], now: float | None = None) -> list[dict]:
    """Only snapshots taken since local midnight.

    Movement is meaningful within ONE day's board. MLB plays every day, so
    without this cut yesterday's price on the same player/market chains onto
    today's and fabricates "movement" between two different games."""
    import datetime as _dt
    now = now if now is not None else time.time()
    midnight = _dt.datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    return [r for r in rows if float(r.get("ts", 0)) >= midnight]


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
        items = _pregame_only(items)
        if not items:
            continue
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
    open_odds: int | None = None       # over-side price at open
    current_odds: int | None = None
    prob_delta: float = 0.0            # implied-prob shift of the over side


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
    prob_delta: float = 0.0            # consensus implied-prob shift (over)
    open_odds: int | None = None       # consensus over price at open
    current_odds: int | None = None


def _implied(odds) -> float | None:
    """American odds → implied probability (vig included)."""
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def analyze(rows: list[dict], min_move: float = 0.5, steam_books: int = 2,
            window_s: float = 3600.0, now: float | None = None,
            min_prob_move: float = 0.02) -> list[MoveReport]:
    """Collapse the snapshot history into per-prop movement reports.

    Movement lives in two places: the LINE (yardage props re-price by moving
    the number) and the PRICE (many MLB props sit on a fixed 0.5 / 1.5 line
    and re-price through the juice — the line never moves, the odds do).
    Both are tracked; ``min_prob_move`` is the implied-probability shift on
    the over side that counts as a real price move.

    Consecutive identical snapshots are deduped, so re-recording an unchanged
    board (e.g. from a cached response) never fabricates movement.
    """
    now = now if now is not None else time.time()

    # (player, market, book) -> time-ordered [(ts, line, over_odds)]
    series: dict[tuple, list[tuple]] = {}
    for r in rows:
        key = (r["player"], r["market"], r["book"])
        series.setdefault(key, []).append(
            (float(r["ts"]), float(r["line"]), r.get("over_odds")))

    per_prop: dict[tuple, list[BookMove]] = {}
    for (player, market, book), pts in series.items():
        pts.sort(key=lambda p: p[0])
        dedup: list[tuple] = []
        for ts, line, odds in pts:
            if not dedup or dedup[-1][1] != line or dedup[-1][2] != odds:
                dedup.append((ts, line, odds))
        open_line, current = dedup[0][1], dedup[-1][1]
        p0, p1 = _implied(dedup[0][2]), _implied(dedup[-1][2])
        per_prop.setdefault((player, market), []).append(BookMove(
            book=book, open=open_line, current=current,
            delta=current - open_line,
            last_move_ts=dedup[-1][0] if len(dedup) > 1 else 0.0,
            open_odds=dedup[0][2], current_odds=dedup[-1][2],
            prob_delta=(p1 - p0) if p0 is not None and p1 is not None else 0.0,
        ))

    reports = []
    for (player, market), books in per_prop.items():
        delta = _median([b.current for b in books]) - _median([b.open for b in books])
        prob_delta = _median([b.prob_delta for b in books])
        if (abs(delta) < 1e-9 and abs(prob_delta) < min_prob_move
                and not any(abs(b.delta) >= min_move for b in books)):
            continue  # nothing moved
        # Direction: the line move wins when there is one; otherwise the
        # price move (over shortening = "up", drifting = "down").
        direction = ("up" if delta >= 0 else "down") if abs(delta) >= 1e-9 \
            else ("up" if prob_delta >= 0 else "down")
        sign = 1 if direction == "up" else -1
        movers = [
            b for b in books
            if (sign * b.delta >= min_move or sign * b.prob_delta >= min_prob_move)
            and (now - b.last_move_ts) <= window_s
        ]
        odds_open = [b.open_odds for b in books if b.open_odds is not None]
        odds_cur = [b.current_odds for b in books if b.current_odds is not None]
        reports.append(MoveReport(
            player=player, market=market,
            open=round(_median([b.open for b in books]), 1),
            current=round(_median([b.current for b in books]), 1),
            delta=round(delta, 1),
            direction=direction,
            steam=len(movers) >= steam_books,
            books=books,
            prob_delta=round(prob_delta, 4),
            open_odds=int(_median([float(o) for o in odds_open])) if odds_open else None,
            current_odds=int(_median([float(o) for o in odds_cur])) if odds_cur else None,
        ))
    reports.sort(key=lambda r: (r.steam, abs(r.delta), abs(r.prob_delta)),
                 reverse=True)
    return reports


def _fmt_odds(o) -> str:
    return f"{int(o):+d}" if o is not None else "?"


def _describe(r: MoveReport) -> str:
    """Human-readable "what moved": the line when it moved, else the price."""
    if abs(r.delta) >= 1e-9:
        return f"line {r.open:g} → {r.current:g}"
    return f"Over price {_fmt_odds(r.open_odds)} → {_fmt_odds(r.current_odds)}"


def summary_lines(reports: list[MoveReport], limit: int = 10) -> list[str]:
    out = []
    for r in reports[:limit]:
        arrow = "▲" if r.direction == "up" else "▼"
        steam = "  🔥 STEAM" if r.steam else ""
        out.append(f"  {arrow} {r.player} {r.market}: {_describe(r)}{steam}")
    return out


# --- the signal: movement vs OUR pick ---------------------------------------
def annotate_recommendations(recs: list[dict], reports: list[MoveReport]) -> int:
    """Stamp each recommendation with how the market has moved relative to
    the side WE like since our first recorded snapshot.

    "up" always means toward the Over (line raised, or the over price
    shortening), so a move agrees with an OVER pick and fights an UNDER pick.
    Agreement becomes a reason ("the market is moving our way" — the same
    direction sharp money shows up as); disagreement becomes a warning, which
    is the honest thing to show when books are actively re-pricing away from
    our number. NOT informational: this calls quality.apply_movement, which
    moves the quality score (±4, or ±7 on steam), can raise the letter, and
    REJECTS the pick outright if the drop puts it under 70. It never raises
    the stake. Said plainly because the reverse was written here for a while,
    and a reader who believes movement is inert will not go looking for it
    when a pick he expected disappears off the board.

    Returns how many recommendations got a movement stamp.
    """
    from .sources.oddsapi import normalize_name

    idx = {(normalize_name(r.player), r.market): r for r in reports}
    n = 0
    for rec in recs:
        if rec.get("has_market") is False:
            continue
        side = rec.get("side")
        if side not in ("OVER", "UNDER"):
            continue
        rep = idx.get((normalize_name(rec.get("player", "")),
                       rec.get("market", "")))
        if not rep:
            continue
        with_us = (rep.direction == "up") == (side == "OVER")
        last_move = max((b.last_move_ts for b in rep.books), default=0.0)
        rec["line_move"] = {
            "open": rep.open, "current": rep.current, "delta": rep.delta,
            "open_odds": rep.open_odds, "current_odds": rep.current_odds,
            "prob_delta": rep.prob_delta, "direction": rep.direction,
            "steam": rep.steam, "verdict": "with" if with_us else "against",
            # Age of the newest book move, so an alert can be classified
            # Live / Chase / Stale instead of showing a move already missed.
            "moved_ago_min": round((time.time() - last_move) / 60.0)
                             if last_move else None,
        }
        what = _describe(rep)
        steam_txt = " (steam — several books moved together)" if rep.steam else ""
        if with_us:
            rec.setdefault("reasons", []).append(
                f"Market moving toward the {side.title()} — {what} since "
                f"our first snapshot{steam_txt}")
        else:
            rec.setdefault("warnings", []).append(
                f"Market moving against the {side.title()} — {what} since "
                f"our first snapshot{steam_txt}")
        # §4/§10: movement is 15% of the unified quality grade. With-steam
        # raises the score; sharp movement against drops it — below 70 the
        # pick is rejected (fresh sharp money beats a stale model input).
        from .quality import apply_movement
        apply_movement(rec, with_us, rep.steam)
        n += 1
    return n
