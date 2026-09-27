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
    """A two-club winner market, not a spread, total, prop or future.

    TWO NAMED CLUBS, ALWAYS — never Yes/No. The box, 2026-09-26: the
    `nfl` tag's first 134 "moneylines" were season futures ("Yes"/"No",
    dated July), because they carry a winner-type `sportsMarketType` and
    the first cut trusted that field on its own. A game's winner market
    names both clubs as its outcomes; nothing else does."""
    outs = [str(o) for o in _jlist(m.get("outcomes"))]
    if len(outs) != 2 or {o.strip().lower() for o in outs} & {"yes", "no", "draw", "tie", "over", "under"}:
        return False
    kind = str(m.get("sportsMarketType") or "").lower()
    if kind and kind not in ("moneyline", "winner", "game"):
        return False
    return not NOT_ML.search(str(m.get("question") or ""))


#: A GAME event's slug: league, two club codes, the date
#: ("nfl-buf-mia-2026-09-28"). Futures and awards live under the same tags
#: with prose slugs, and are skipped before any market is read.
GAME_SLUG = re.compile(r"^[a-z]+-[a-z0-9]+-[a-z0-9]+-\d{4}-\d{2}-\d{2}")


def is_game_event(ev: dict) -> bool:
    return bool(GAME_SLUG.match(str(ev.get("slug") or "").lower()))


def parse_events(events: list[dict]) -> list[dict]:
    """One row per game moneyline: both clubs as the venue names them,
    the first club's price, and the book's quality."""
    out = []
    for ev in events or []:
        if not isinstance(ev, dict) or not is_game_event(ev):
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
                "lines": parse_lines(ev),
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


# --- the spreads and totals on the same game event -------------------------
#: THE OTHER TWO BETS ON A GAME (Ethan, 2026-09-26: "use pollymarket and
#: kalshi odds for money lines and other bets"). A game event carries its
#: spread and total markets beside the moneyline. Read with the same care:
#: a market is a spread or a total only when both its kind AND its line can
#: be read without guessing, and anything else is skipped, never coerced.
#:
#:   spread  "Spread: Chiefs (-3.5)", outcomes the two clubs — the named
#:           club gives (or gets) the points in the brackets;
#:   total   "Chiefs vs. Bills: O/U 47.5", outcomes Over / Under.
#:
#: Gamma's own `line` field is used first where it sends one; the question
#: is the fallback. `sportsMarketType` narrows the kind where present.
_SPREAD_Q = re.compile(r"spread\W+(.+?)\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*\)", re.I)
_TOTAL_Q = re.compile(r"(?:o/u|over/under|total(?: points)?)\s*:?\s*(\d+(?:\.\d+)?)", re.I)


def _side_price(m: dict, idx: int):
    """``(p, basis, spread_cents)`` for outcome ``idx`` of a two-outcome
    market: the book's mid where it is two-sided (Gamma's bid/ask are the
    FIRST outcome's), else the last trade."""
    prices = [_num(x) for x in _jlist(m.get("outcomePrices"))]
    bid, ask = _num(m.get("bestBid")), _num(m.get("bestAsk"))
    if bid and ask and 0 < bid < ask < 1:
        mid = (bid + ask) / 2.0
        return (mid if idx == 0 else 1.0 - mid), "book", round((ask - bid) * 100.0, 2)
    if len(prices) == 2 and prices[idx] is not None:
        sp = _num(m.get("spread"))
        return prices[idx], "last_trade", (round(sp * 100.0, 2) if sp is not None else None)
    return None, "", None


def parse_line(m: dict) -> dict | None:
    """One spread or total market as a row, or None when it is neither or
    cannot be read cleanly."""
    if not isinstance(m, dict) or m.get("closed") is True:
        return None
    outs = [str(o).strip() for o in _jlist(m.get("outcomes"))]
    if len(outs) != 2:
        return None
    q = str(m.get("question") or "")
    kind = str(m.get("sportsMarketType") or "").lower()
    low = {o.lower() for o in outs}
    row = None
    if low == {"over", "under"} and kind in ("", "totals", "total", "over_under"):
        line = _num(m.get("line"))
        hit = _TOTAL_Q.search(q)
        if line is None and hit:
            line = _num(hit.group(1))
        if line is None or line <= 0:
            return None
        idx = [o.lower() for o in outs].index("over")
        p, basis, spread = _side_price(m, idx)
        row = {"kind": "total", "line": line, "p": p}               # P(over)
    elif not (low & {"yes", "no", "over", "under", "draw", "tie"}) and (
            kind in ("spreads", "spread") or (not kind and "spread" in q.lower())):
        hit = _SPREAD_Q.search(q)
        if not hit:
            return None
        team, line = hit.group(1).strip(), _num(hit.group(2))
        names = [o.lower() for o in outs]
        if line is None or team.lower() not in names:
            return None
        idx = names.index(team.lower())
        p, basis, spread = _side_price(m, idx)
        row = {"kind": "spread", "team": outs[idx], "line": line, "p": p}   # P(team covers)
    if not row or row["p"] is None or not (0.0 < row["p"] < 1.0):
        return None
    row.update({"p": round(row["p"], 4), "price_basis": basis, "spread_cents": spread,
                "volume_24h": _num(m.get("volume24hr")) or 0.0,
                "liquidity": _num(m.get("liquidity")) or 0.0})
    return row


def parse_lines(ev: dict) -> list[dict]:
    return [r for r in (parse_line(m) for m in (ev.get("markets") or [])) if r]


#: Polymarket's own league names on its /sports list, per league of ours.
SPORT_KEYS = {"nfl": ("nfl",), "cfb": ("cfb", "ncaaf"), "mlb": ("mlb",),
              "nba": ("nba",), "wnba": ("wnba",)}


def fetch_series_ids(ttl: int = 86400) -> dict:
    """``{our league: [series id, …]}`` off Polymarket's /sports list,
    which names each league's GAME series. {} when the list is not there."""
    raw = json.loads(fetch_text(f"{GAMMA}/sports", "poly_sports.json", ttl=ttl, timeout=TIMEOUT_S))
    out: dict = {}
    for row in raw if isinstance(raw, list) else []:
        name = str((row or {}).get("sport") or "").strip().lower()
        ids = [x.strip() for x in str((row or {}).get("series") or "").split(",") if x.strip()]
        for ours, keys in SPORT_KEYS.items():
            if name in keys and ids:
                out.setdefault(ours, []).extend(ids)
    return out


def fetch_series_events(series_id: str, limit: int = 200, ttl: int = 300) -> list[dict]:
    url = f"{GAMMA}/events?series_id={series_id}&closed=false&active=true&limit={limit}"
    raw = json.loads(fetch_text(url, f"poly_series_{series_id}.json", ttl=ttl, timeout=TIMEOUT_S))
    return raw if isinstance(raw, list) else (raw.get("events") or raw.get("data") or [])


def fetch_sports(sports=None) -> tuple[list[dict], dict]:
    """``(rows, report)`` for every league asked: the game moneylines, and
    per source how many came back (or "error").

    THE LEAGUE'S GAME SERIES FIRST, the tag second. A tag holds every
    market about the league — futures, awards, the draft — and returns
    them oldest first, so a week's games can sit past the page. The
    series off /sports is the games alone. Either way only game events
    and two-club markets are kept (`is_game_event`, `is_moneyline`)."""
    rows, report = [], {}
    try:
        series = fetch_series_ids()
    except Exception:                                          # noqa: BLE001
        series = {}
        report["sports"] = "error"
    for sport in (sports or SPORT_TAGS):
        got = []
        for sid in series.get(sport, []):
            try:
                parsed = [dict(r, sport=sport) for r in parse_events(fetch_series_events(sid))]
            except Exception:                                  # noqa: BLE001
                report[f"series:{sid}"] = "error"
                continue
            report[f"series:{sid}"] = len(parsed)
            got.extend(parsed)
        if not got:
            for tag in SPORT_TAGS.get(sport, ()):
                try:
                    events = fetch_events(tag)
                except Exception:                              # noqa: BLE001
                    report[tag] = "error"
                    break                 # the venue is down; aliases will not help
                parsed = [dict(r, sport=sport) for r in parse_events(events)]
                report[tag] = len(parsed)
                got.extend(parsed)
                if parsed:
                    break
        seen = set()
        for r in got:
            if r["slug"] not in seen:
                seen.add(r["slug"])
                rows.append(r)
    return rows, report


def _tokens(text: str) -> set[str]:
    """A name's words, apostrophes closed up first: the venue writes
    "Hawai'i" and a split on the apostrophe leaves HAWAI, which is in no
    name of ours (the box, 2026-09-26)."""
    from .kalshi import _name_tokens
    return _name_tokens(str(text or "").replace("'", "").replace("\u2019", ""))


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
