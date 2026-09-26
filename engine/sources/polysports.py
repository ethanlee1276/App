"""Polymarket's sports game markets: the second crowd price on a game.

Ethan, 2026-09-26: "we should also look into where we can use pollymarket
and kalshi odds for money lines and other bets since crowd betting is
more accurate when it comes to what's right and wrong."

KALSHI WAS ALREADY PRICED (`sources/kalshi`, `engine/exchangefair`);
POLYMARKET WAS NOT. `engine/predmarket` reads Polymarket for its trade
tape (the informed-flow feed), never for a game's winner, so a venue
that lists every NFL, MLB, NBA, WNBA and major college game had no say
on any of them. This module is the missing half: fetch a league's open
game events, keep each game's moneyline market, and pin it to one of
tonight's games.

THE SHAPE, AS GAMMA SHIPS IT. A game is an EVENT (slug like
``nfl-buf-mia-2026-09-28``) holding several MARKETS — the moneyline, the
spreads, the totals. The moneyline's ``outcomes`` are the two clubs'
names ("Bills", "Dolphins") and ``outcomePrices`` the matching prices;
``sportsMarketType`` names the kind where Gamma sends it. Everything here
reads defensively: a field Gamma renames costs the rows, never the build,
and `fetch_sports` reports per tag how many events came back so the next
box run says which tags are real (the same way `kalshi.fetch_sports_
markets` reports its series).

NOTHING HERE PRICES A BET. It hangs a number on a game, with the book's
quality beside it; `engine/crowd` decides what to show and
`engine/crowdfit` measures whether it is worth anything.
"""

from __future__ import annotations

import json
import re

from .fetch import fetch_text, DataUnavailable                # noqa: F401

GAMMA = "https://gamma-api.polymarket.com"

#: Candidate tag slugs per league, tried in order until one returns
#: events. Names are candidates on purpose — a tag that does not exist
#: returns nothing and costs one request, and the report says which ones
#: were real.
SPORT_TAGS = {
    "nfl": ("nfl",),
    "cfb": ("cfb", "ncaaf", "college-football"),
    "mlb": ("mlb",),
    "nba": ("nba",),
    "wnba": ("wnba",),
}

#: A short timeout: this runs inside a board build that the launcher
#: kills at 180 seconds, and a crowd price is garnish on that board.
TIMEOUT_S = 12

#: Market words that mean "not the moneyline".
NOT_ML = re.compile(r"\b(spread|o/u|over|under|total|points|handicap|draw|1st|first|half|quarter|inning|"
                    r"props?|mvp|yards|touchdowns?|runs?)\b", re.I)


def _jlist(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            got = json.loads(v)
            return got if isinstance(got, list) else []
        except ValueError:
            return []
    return []


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_events(tag: str, limit: int = 200, ttl: int = 300) -> list[dict]:
    url = (f"{GAMMA}/events?tag_slug={tag}&closed=false&active=true"
           f"&limit={limit}&order=startDate&ascending=true")
    raw = json.loads(fetch_text(url, f"poly_events_{tag}.json", ttl=ttl, timeout=TIMEOUT_S))
    return raw if isinstance(raw, list) else (raw.get("events") or raw.get("data") or [])


def is_moneyline(m: dict) -> bool:
    """A two-club winner market, not a spread, total or prop."""
    kind = str(m.get("sportsMarketType") or "").lower()
    if kind:
        return kind in ("moneyline", "winner", "game")
    outs = [str(o) for o in _jlist(m.get("outcomes"))]
    if len(outs) != 2 or {o.lower() for o in outs} & {"yes", "no", "draw", "tie"}:
        return False
    return not NOT_ML.search(str(m.get("question") or ""))


def parse_events(events: list[dict]) -> list[dict]:
    """One row per game moneyline: both clubs as the venue names them,
    the first club's price, and the book's quality."""
    out = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        for m in ev.get("markets") or []:
            if not isinstance(m, dict) or m.get("closed") is True or not is_moneyline(m):
                continue
            outs = [str(o) for o in _jlist(m.get("outcomes"))]
            prices = [_num(p) for p in _jlist(m.get("outcomePrices"))]
            if len(outs) != 2 or len(prices) != 2 or prices[0] is None:
                continue
            bid, ask = _num(m.get("bestBid")), _num(m.get("bestAsk"))
            if bid and ask and 0 < bid < ask < 1:
                p0, basis = (bid + ask) / 2.0, "book"
                spread = round((ask - bid) * 100.0, 2)
            else:
                p0, basis = prices[0], "last_trade"
                sp = _num(m.get("spread"))
                spread = round(sp * 100.0, 2) if sp is not None else None
            if not (0.0 < p0 < 1.0):
                continue
            out.append({
                "slug": str(m.get("slug") or ""),
                "event_slug": str(ev.get("slug") or ""),
                "question": str(m.get("question") or ev.get("title") or ""),
                "teams": outs,
                "prob": round(p0, 4),                       # P(teams[0] wins)
                "price_basis": basis,
                "spread_cents": spread,
                "volume_24h": _num(m.get("volume24hr")) or 0.0,
                "liquidity": _num(m.get("liquidity")) or 0.0,
                "start": str(m.get("gameStartTime") or ev.get("startDate") or ev.get("endDate") or "")[:19],
            })
    return out


def fetch_sports(sports=None) -> tuple[list[dict], dict]:
    """``(rows, report)`` for every league asked: the game moneylines, and
    per tag how many events came back (or "error")."""
    rows, report = [], {}
    for sport in (sports or SPORT_TAGS):
        for tag in SPORT_TAGS.get(sport, ()):
            try:
                events = fetch_events(tag)
            except Exception:                                  # noqa: BLE001
                report[tag] = "error"
                break                     # the venue is down; aliases will not help
            parsed = [dict(r, sport=sport) for r in parse_events(events)]
            report[tag] = len(parsed)
            rows.extend(parsed)
            if parsed:
                break
    return rows, report


def _tokens(text: str) -> set[str]:
    from .kalshi import _name_tokens
    return _name_tokens(text)


def _club(outcome: str, g: dict, side: str) -> bool:
    """Does the venue's name for a club belong to this side of the game?
    Every word of the venue's name must be in ours ("Ohio State" is not
    "Ohio"), or it is the club's code."""
    own = _tokens(outcome)
    if not own:
        return False
    code = str(g.get(side) or "").strip().upper()
    if outcome.strip().upper() == code:
        return True
    return own <= _tokens(str(g.get(f"{side}_name") or ""))


def match_game(row: dict, games: list[dict]) -> tuple[dict | None, bool | None]:
    """``(game, first_is_home)`` or ``(None, None)``: the one game both
    clubs belong to, on the same day give or take one (a late start is
    tomorrow in UTC). Two games matching is refused, not guessed at."""
    a, b = (row.get("teams") or ["", ""])[:2]
    day = str(row.get("start") or "")[:10]
    hits = []
    for g in games or []:
        gd = str(g.get("date") or "")[:10]
        if day and gd and abs(_days(day) - _days(gd)) > 1:
            continue
        if _club(a, g, "home") and _club(b, g, "away"):
            hits.append((g, True))
        elif _club(a, g, "away") and _club(b, g, "home"):
            hits.append((g, False))
    return hits[0] if len(hits) == 1 else (None, None)


def _days(iso: str) -> int:
    import datetime as _dt
    try:
        return _dt.date.fromisoformat(iso[:10]).toordinal()
    except ValueError:
        return 0


def p_home(row: dict, first_is_home: bool) -> float:
    p = float(row["prob"])
    return round(p if first_is_home else 1.0 - p, 4)
