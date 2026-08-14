"""The in-play line, tracked over the game — one credit a pull.

Ethan, 2026-08-14, with a sportsbook's live chart on screen: "when games
are live, can we track the live line like this. Like we pull the updated
line every so often and show this chart with the live games. Only if it
doesn't cost us an arm and a leg to pull those lines all the time."

THE COST, WHICH IS THE WHOLE QUESTION.

The Odds API bills per MARKET per REGION, not per request. That single
fact splits live tracking into an unaffordable version and a cheap one,
and which one you get depends entirely on which endpoint you call:

  * the EVENT endpoint (`/events/{id}/odds`) is what prices our board.
    It is the only place player props live, and we ask it for ~8 markets,
    so it bills ``CREDITS_PER_EVENT = 8`` PER GAME. Polling a 15-game
    slate every five minutes for six hours is 15 × 8 × 72 = 8,640
    credits. The free plan is 500 a month. That is the arm and the leg.

  * the BOARD endpoint (`/sports/{key}/odds`) returns every game at once
    and bills per market REGARDLESS OF GAME COUNT. One market, one
    region, one credit — for the whole slate, three games or thirty.

So this module asks for exactly one market, ``h2h``, from the board
endpoint. A pull costs 1 credit. At a 30-minute cadence across a six-hour
window that is ~12 credits a night, inside the free plan's ~16/day; at 15
minutes it is ~24, which needs a paid plan. The cadence is therefore a
constant here rather than a hard-coded five minutes, and the pacer that
guards pre-game pricing is consulted before any of it — a live chart is a
nice-to-have and must never be the reason tonight's board went unpriced.

WHAT GETS CHARTED, AND WHY IT IS NOT THE PRICE.

The raw American number is unchartable. It has a hole in the middle: a
team drifting from a small favourite to a small dog goes -101 → +101, a
two-point jump on the page for a hair of movement in the real world, and
it never takes a value between. Plotting that draws a cliff where nothing
happened.

Implied probability is the same information without the hole, so each
book's two-sided quote is de-vigged

    p_home = imp(home) / (imp(home) + imp(away))

and the MEDIAN across books is the point. De-vigging needs both sides
from the SAME book — pairing the best home price at one book with the
best away price at another manufactures a probability pair summing under
1, which is not a market's opinion, it is an arbitrage that exists only
in our arithmetic. Books quoting one side are skipped, not completed.

This measures the market, not us. It is not our model's win probability
and nothing here is projected, smoothed or extrapolated: every point is a
price that was really posted, at a time it was really posted.

Standard library only. Parsing is pure; recording is one append per pull.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .sources.fetch import CACHE_DIR

HISTORY_PATH = CACHE_DIR / "live_lines.jsonl"

#: The one market we ask for. Every extra name on this list is another
#: credit on every pull, forever — see the module docstring.
LIVE_MARKETS = ("h2h",)

#: Minimum seconds between live-line pulls. 30 minutes ≈ 12 credits over a
#: six-hour night, which the free plan's ~16/day can carry. Raising the
#: cadence is a plan decision, not a code one, so it lives here in the open.
LIVE_GAP_S = 30 * 60

#: A chart needs a shape, not a dot. Below this many points there is
#: nothing to draw and the caller shows the current price instead.
MIN_POINTS = 3


def _implied(odds) -> float | None:
    """American odds → implied probability, vig included."""
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None                     # not a legal American price
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def devig_pair(home_odds, away_odds) -> float | None:
    """One book's two-sided moneyline → the home team's fair probability.

    Returns None unless BOTH sides are real prices. The vig is whatever
    makes the two implied probabilities sum above 1; dividing by that sum
    removes it under the standard proportional assumption.
    """
    ph, pa = _implied(home_odds), _implied(away_odds)
    if ph is None or pa is None:
        return None
    total = ph + pa
    if total <= 0:
        return None
    return ph / total


def event_probability(by_book: dict, home: str, away: str) -> dict | None:
    """Consensus de-vigged home win probability from ``{book: {team: odds}}``.

    ``{"p_home", "books", "home_odds", "away_odds"}`` or None when no book
    quotes both sides. ``home_odds``/``away_odds`` are the best available
    price per side — those are for DISPLAY, where "the number you could
    get" is the honest thing to show; they are deliberately not what the
    probability is computed from.
    """
    probs, best_h, best_a = [], None, None
    for prices in (by_book or {}).values():
        h, a = prices.get(home), prices.get(away)
        p = devig_pair(h, a)
        if p is not None:
            probs.append(p)
        # Best price per side = the biggest American number, which is
        # monotone in payout across the sign boundary.
        if h is not None and (best_h is None or int(h) > best_h):
            best_h = int(h)
        if a is not None and (best_a is None or int(a) > best_a):
            best_a = int(a)
    if not probs:
        return None
    return {"p_home": _median(probs), "books": len(probs),
            "home_odds": best_h, "away_odds": best_a}


def snapshot_rows(events, teams: dict, sport: str, ts: float | None = None,
                  live_only: bool = True, now: float | None = None) -> list[dict]:
    """Board payload → one snapshot row per game we can name.

    ``teams`` maps the feed's full team names to our abbreviations; an
    event whose names we cannot resolve is DROPPED rather than stored
    under a guessed key, because a chart is a time series and one
    mis-keyed point silently belongs to another game's line.

    ``live_only`` keeps games whose start time has passed — the whole
    point is the in-play line. Pre-game movement is already recorded by
    `linemoves.record_snapshots` and does not need paying for twice.
    """
    from .sources.oddsapi import parse_event_h2h_by_book
    ts = time.time() if ts is None else ts
    now = ts if now is None else now
    out: list[dict] = []
    for ev in (events or []):
        home = teams.get(ev.get("home_team", ""))
        away = teams.get(ev.get("away_team", ""))
        if not home or not away:
            continue
        if live_only:
            start = _start_epoch(ev.get("commence_time"))
            if start is None or start > now:
                continue
        team_map = {ev.get("home_team", ""): home, ev.get("away_team", ""): away}
        agg = event_probability(parse_event_h2h_by_book(ev, team_map), home, away)
        if agg is None:
            continue
        out.append({"ts": round(float(ts), 3), "sport": sport,
                    "event_id": ev.get("id", ""), "home": home, "away": away,
                    "p_home": round(agg["p_home"], 5), "books": agg["books"],
                    "home_odds": agg["home_odds"], "away_odds": agg["away_odds"]})
    return out


def _start_epoch(commence) -> float | None:
    """ISO start → epoch seconds, or None when it is not an instant.

    Same rule as `linemoves.start_epoch`: a naive stamp is a clock, not a
    moment, and guessing a zone onto it would decide which games count as
    live. A game we cannot time is left out rather than charted wrongly.
    """
    if not commence:
        return None
    import datetime as _dt
    try:
        d = _dt.datetime.fromisoformat(str(commence).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return None if d.tzinfo is None else d.timestamp()


def record(rows: list[dict], path: str | Path | None = None) -> int:
    """Append snapshots. Returns how many were written."""
    if not rows:
        return 0
    p = Path(path or HISTORY_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return len(rows)


def load(path: str | Path | None = None) -> list[dict]:
    """Every snapshot on disk, oldest first. A corrupt line is skipped
    rather than fatal — this file is written by an append that can be
    interrupted, and one truncated row must not blank the chart."""
    p = Path(path or HISTORY_PATH)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and "ts" in row:
            out.append(row)
    out.sort(key=lambda r: r.get("ts", 0))
    return out


def series(rows: list[dict], home: str, away: str, sport: str | None = None,
           since: float | None = None) -> list[dict]:
    """One game's track, oldest first: ``[{"ts", "p_home", ...}, …]``.

    ``since`` cuts off earlier nights. The same two teams meet many times
    a season and the file is append-only across all of them, so without a
    cut a chart of tonight's line would open with last month's.
    """
    out = [r for r in rows
           if r.get("home") == home and r.get("away") == away
           and (sport is None or r.get("sport") == sport)
           and (since is None or float(r.get("ts", 0)) >= since)]
    out.sort(key=lambda r: r.get("ts", 0))
    # Consecutive identical prices are the same fact reported twice: the
    # book had not moved between pulls. Collapsing them keeps the chart
    # honest about WHEN it moved instead of drawing a staircase whose
    # step width is our polling interval.
    kept: list[dict] = []
    for r in out:
        if kept and kept[-1].get("p_home") == r.get("p_home"):
            continue
        kept.append(r)
    return kept


def track_for(rows: list[dict], home: str, away: str, sport: str | None = None,
              since: float | None = None) -> dict | None:
    """The chart-ready block for one game, or None when there is not
    enough to draw.

    ``values`` is NEWEST FIRST, which is the order every chart in
    `visuals.js` takes; ``labels`` is built alongside it so a point and
    its clock time can never drift apart.
    """
    pts = series(rows, home, away, sport, since)
    if len(pts) < MIN_POINTS:
        return None
    newest = list(reversed(pts))
    return {
        "home": home, "away": away,
        "values": [round(p["p_home"] * 100.0, 1) for p in newest],
        "labels": [_clock(p["ts"]) for p in newest],
        "opened": round(pts[0]["p_home"] * 100.0, 1),
        "now": round(pts[-1]["p_home"] * 100.0, 1),
        "home_odds": pts[-1].get("home_odds"),
        "away_odds": pts[-1].get("away_odds"),
        "points": len(pts),
    }


def _clock(ts) -> str:
    try:
        return time.strftime("%-I:%M %p", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return ""


def affordable(last_ts: float, now: float | None = None,
               gap: float = LIVE_GAP_S) -> bool:
    """Has enough time passed since the last live pull?

    Deliberately only the CADENCE. Whether there is budget at all is
    `oddsbudget`'s answer and is asked separately by the caller, so that a
    live chart can never be the thing that spends the credit tonight's
    board needed.
    """
    return (time.time() if now is None else now) - float(last_ts or 0) >= gap


def last_pull_ts(path: str | Path | None = None) -> float:
    """When the last live pull happened, from the history itself.

    No separate stamp file: a stamp that can disagree with the data it
    describes is a second source of truth, and the one thing we need to
    know — "did we already pay for a snapshot recently" — is written into
    every row we recorded.
    """
    rows = load(path)
    return float(rows[-1]["ts"]) if rows else 0.0


def pull_and_record(sport: str, teams: dict, api_key: str | None = None,
                    now: float | None = None, path: str | Path | None = None,
                    force: bool = False) -> tuple[int, str]:
    """One board pull of the live market, recorded. ``(rows, note)``.

    Costs `credits_per_pull()` — one credit — for the whole slate. Returns
    ``(0, reason)`` without spending when the cadence says it is too soon
    or the feed has nothing live.

    Callers must have ALREADY established that the budget can spare it;
    this deliberately does not ask, so that a live chart can never outbid
    the pre-game pull that prices tonight's board.
    """
    now = time.time() if now is None else now
    if not force and not affordable(last_pull_ts(path), now):
        return 0, "too soon since the last live pull"
    from .sources import oddsapi
    try:
        events, _quota = oddsapi.fetch_sport_odds(
            sport, api_key=api_key, markets=list(LIVE_MARKETS), ttl=0,
            cache_tag="live")
    except Exception as exc:                                  # noqa: BLE001
        return 0, f"live odds unavailable: {exc}"
    rows = snapshot_rows(events, teams, sport, ts=now, now=now)
    if not rows:
        return 0, "no live game had a two-sided price"
    record(rows, path)
    return len(rows), (f"{len(rows)} live line(s) recorded for "
                       f"{credits_per_pull()} credit")


def attach(games: list[dict], sport: str, since: float | None = None,
           path: str | Path | None = None) -> int:
    """Hang each live game's ``line_track`` on its payload dict.

    Runs on every build whether or not a pull was paid for — the history
    is already on disk, so the chart costs nothing to show. Returns how
    many games got one.
    """
    rows = load(path)
    if not rows:
        return 0
    n = 0
    for g in games or []:
        if (g.get("live") or {}).get("state") != "live":
            continue
        t = track_for(rows, g.get("home", ""), g.get("away", ""), sport, since)
        if t:
            g["line_track"] = t
            n += 1
    return n


def credits_per_pull(markets=LIVE_MARKETS) -> int:
    """What one pull costs: one credit per market, whatever the slate size.

    Exists so the number is asserted rather than believed. The board
    endpoint bills per market per region and we ask for one region.
    """
    return max(1, len(tuple(markets)))
