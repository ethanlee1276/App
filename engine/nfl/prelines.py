"""The market's number on a preseason game — shown, recorded, not priced.

Ethan, 2026-08-14: "i wanna show props for the pre season. i wanna show
either money lines or over unders or whatever i dont car."

WHAT THIS IS AND, MORE IMPORTANTLY, WHAT IT IS NOT.

It is the posted line beside the starter scan: what the book thinks, next
to what the coaching staffs have historically done. That pairing is the
whole value — "SF has played its starters 22 attempts a game in past
Augusts, and the market has them -3" is two facts a reader can put
together themselves.

It is NOT our opinion. There is no model number here, no edge, no stake
and no recommendation, because `engine/nfl/prefit` has not been able to
establish that starter usage predicts a preseason result by enough to bet
— and until it can, a number of ours beside the book's would be an
invitation to act on nothing.

THE COST, WHICH IS WHY THIS IS AFFORDABLE AT ALL. The Odds API bills per
market per region for the WHOLE board, not per game. Three markets is
three credits for all sixteen fixtures in a preseason week, cached six
hours, live for the five weeks a year the preseason exists. Call that 12
credits on a heavy day and under 500 for the entire preseason. The pacer
is still consulted first — this is a nice-to-have and must never be the
reason a real slate went unpriced.

RECORDING IS THE POINT, NOT A SIDE EFFECT. `prefit.prices_allowed` is
hard False for a stated reason: proving the effect exists is not proving
the BOOK MISSED IT, and that second question needs preseason closing
lines nobody here has ever stored. Every pull appends to
`preseason_lines.jsonl`. In a few Augusts that file is the sample that
makes the question answerable; today it is the reason the answer is
honestly "not yet".

Standard library only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..sources.fetch import CACHE_DIR

#: One credit each, for the whole board.
PRE_MARKETS = ("h2h", "spreads", "totals")
#: What a pull costs. Named so the number in the docstring cannot drift
#: away from the number actually spent.
CREDITS_PER_PULL = len(PRE_MARKETS)
#: Preseason lines move, but not on the timescale a live chart needs.
#: Six hours is four pulls a day at most.
PRE_TTL = 6 * 3600
#: This slate's slice of the daily allowance. Small on purpose.
PRE_BUDGET_SHARE = 0.05
#: How far a fixture's kickoff may be from an event's commence time and
#: still be the same game. Books and ESPN agree to the minute in practice;
#: this is loose enough to survive a timezone bug and tight enough that two
#: different meetings of the same pair could not collide.
MATCH_WINDOW_S = 36 * 3600

HISTORY_PATH = CACHE_DIR / "preseason_lines.jsonl"


# --- the pull ---------------------------------------------------------------
def fetch(api_key: str | None = None, cache_only: bool = False,
          ttl: int = PRE_TTL):
    """The NFL board's full-game markets. Raises nothing — returns []."""
    from ..sources import oddsapi
    try:
        events, _quota = oddsapi.fetch_sport_odds(
            "nfl", api_key=api_key, markets=list(PRE_MARKETS),
            ttl=ttl, cache_only=cache_only, cache_tag="pre")
        return events or []
    except Exception:                                         # noqa: BLE001
        return []


def snapshot(events, ts: float | None = None) -> list[dict]:
    """Board payload → one row per game, de-vigged. Reuses the live reader.

    `livelines.snapshot_rows` already does exactly this arithmetic — one
    book's two sides de-vigged, the median across books, spread and total
    riding along — and it does it with the pairing rule that matters: both
    sides from the SAME book. Rewriting it here would be a second place
    for that rule to be got wrong.

    ``live_only`` is off: a preseason fixture is interesting BEFORE it
    kicks off, which is the opposite of the live chart's need.
    """
    from ..livelines import snapshot_rows
    from ..sources.oddsapi import TEAM_ABBR
    rows = snapshot_rows(events, TEAM_ABBR, "nfl", ts=ts, live_only=False)
    for ev in events or []:
        home = TEAM_ABBR.get(ev.get("home_team", ""))
        away = TEAM_ABBR.get(ev.get("away_team", ""))
        for r in rows:
            if r["home"] == home and r["away"] == away:
                r["commence"] = ev.get("commence_time", "")
    return rows


def record(rows: list[dict], path: str | Path | None = None) -> int:
    """Append a pull to the preseason line history. One JSON object a line."""
    if not rows:
        return 0
    f = Path(path or HISTORY_PATH)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return len(rows)


def load(path: str | Path | None = None) -> list[dict]:
    """Every recorded preseason line, oldest first. Bad lines are skipped."""
    f = Path(path or HISTORY_PATH)
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# --- matching a price to a fixture ------------------------------------------
def _epoch(iso: str):
    if not iso:
        return None
    try:
        import datetime as dt
        return dt.datetime.fromisoformat(
            str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def match(rows: list[dict], game: dict) -> dict | None:
    """The line row for one preseason fixture, or None.

    Matched on the TEAM PAIR first and the kickoff second. Two teams
    meeting twice in one preseason would be extraordinary, but "would be
    extraordinary" is how a chart ends up showing another game's number,
    so the kickoff has to agree as well when both times are readable.
    """
    home, away = game.get("home"), game.get("away")
    if not home or not away:
        return None
    want = _epoch(game.get("kickoff") or "")
    best, best_key = None, None
    for r in rows:
        if r.get("home") != home or r.get("away") != away:
            continue
        got = _epoch(r.get("commence") or "")
        if want is None or got is None:
            gap = float("inf")            # unreadable: still a candidate
        else:
            gap = abs(got - want)
            if gap > MATCH_WINDOW_S:
                continue
        # Closest kickoff wins; among equally close readings the NEWEST
        # does, because the history is append-only and a later row for the
        # same fixture is a later reading of the same market.
        key = (gap, -float(r.get("ts") or 0))
        if best_key is None or key < best_key:
            best, best_key = r, key
    return best


def attach(board: dict, rows: list[dict] | None = None,
           path: str | Path | None = None) -> int:
    """Hang each fixture's ``market`` block on the board payload.

    Runs whether or not a pull was paid for — the newest recorded row for
    a fixture is already on disk. Returns how many fixtures got one.
    """
    rows = rows if rows is not None else load(path)
    if not rows:
        return 0
    # Newest wins: the history is append-only, so a later row for the same
    # game is a later reading of the same market.
    rows = sorted(rows, key=lambda r: r.get("ts") or 0)
    n = 0
    for w in (board or {}).get("weeks", []) or []:
        for g in w.get("games", []) or []:
            r = match(rows, g)
            if not r:
                continue
            g["market"] = {
                "p_home": r.get("p_home"), "books": r.get("books"),
                "home_odds": r.get("home_odds"), "away_odds": r.get("away_odds"),
                "spread": r.get("spread"), "total": r.get("total"),
                "taken_at": r.get("ts"),
            }
            n += 1
    return n


# --- the whole errand -------------------------------------------------------
def affordable(board: dict, now: float | None = None) -> tuple[bool, str]:
    """Should we spend three credits on preseason lines right now?

    Two gates, and the cheap one is first. There is no point asking the
    pacer about a slate that has already finished playing — the preseason
    board is live about five weeks a year and silent for the other
    forty-seven.
    """
    import datetime as dt
    now = time.time() if now is None else now
    today = dt.date.fromtimestamp(now).isoformat()
    upcoming = [g for w in (board or {}).get("weeks", []) or []
                for g in w.get("games", []) or []
                if (g.get("date") or "") >= today]
    if not upcoming:
        return False, "no unplayed preseason fixture — nothing to price"
    from .. import oddsbudget
    ok, why = oddsbudget.should_refresh(
        CREDITS_PER_PULL, now=now, sport="nflpre", share=PRE_BUDGET_SHARE,
        kickoffs=[g.get("kickoff") for g in upcoming if g.get("kickoff")])
    return ok, why


def refresh(board: dict, api_key: str | None = None, now: float | None = None,
            path: str | Path | None = None,
            force: bool = False) -> tuple[int, str]:
    """Pull, record and attach. ``(fixtures priced, note)``.

    A refused pull is not a failure: the cached rows are still attached, so
    the board shows the last number it saw rather than nothing.
    """
    now = time.time() if now is None else now
    ok, why = (True, "forced") if force else affordable(board, now)
    spent = 0
    if ok:
        events = fetch(api_key=api_key)
        rows = snapshot(events, ts=now)
        if rows:
            record(rows, path)
            spent = CREDITS_PER_PULL
            from .. import oddsbudget
            oddsbudget.log_spend("board", "nflpre", CREDITS_PER_PULL,
                                 f"{len(rows)} preseason line(s)")
            oddsbudget.mark_refreshed(now, sport="nflpre")
    n = attach(board, path=path)
    note = (f"{n} fixture(s) carry a market line"
            + (f" ({spent} credit(s) spent)" if spent else f" — {why}"))
    return n, note
