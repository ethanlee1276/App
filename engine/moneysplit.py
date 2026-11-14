"""Where the money is going on a game — read off the prediction markets' tape.

Ethan, 2026-09-28, with DraftKings' "% of bets placed" bars beside our game
page: "When we click on a game, I want it to also show the shit the
Sportsbook shows like what percent of money is on what team and on what
spread and on what Moneyline." A sportsbook's split is its own customers'
data — no free feed exists (engine/linemoves says so), and the sites that
show it scrape the books, which this site does not do. Ethan chose the free
source: the two prediction markets we already price from, Kalshi and
Polymarket, whose public trade tapes say which side every trade's TAKER
bought — the trader who crossed the spread to get on a side, which is the
exchange's version of a bet placed.

WHAT THE NUMBERS ARE, EXACTLY:

  * money %   dollars the takers paid to get on each side;
  * trades %  how many taker trades went to each side (the ticket count).

Over the most recent TRADE_PAGE trades on each market (one page, so a busy
game reads its latest flow and a quiet one its whole history), pre-game
only: a started game's tape is live betting and is left out. Kalshi's
winner is two markets ("PHI wins", "CHI wins"); a YES taker on one and a NO
taker on the other are money on the same club, so both are read. The
spread and total are read only at the BOARD'S OWN line — the same bet the
books quote (engine/crowd holds that rule) — never a neighbouring strike.

A market with too little behind it (under MIN_USD or MIN_TRADES) is left
off rather than drawn as a confident 100-0 bar.

NEVER RAISES into a build: every venue and every market is its own failure
domain, and a missing split is only a missing section.
"""

from __future__ import annotations

import datetime as _dt
import json
import time

from .sources.fetch import fetch_text, DataUnavailable

KALSHI_TRADES = "https://api.elections.kalshi.com/trade-api/v2/markets/trades?ticker={t}&limit={n}"
#: POLYMARKET'S DATA API v2 (2026-11-14). The money split read Kalshi alone
#: in every league, and the census's `why` (step QN) named the cause on the
#: first build that carried it: every Polymarket trade read answered "HTTP
#: Error 410: Gone". Polymarket retired its Data API v1 on 2 November 2026
#: (v1's /trades, /positions and /activity answer 410, "Data API v1 has been
#: retired"); v2 selects a market by `condition` rather than `market`, takes
#: `taker_only`, pages by cursor at up to a thousand rows a call, wraps its
#: rows in `data` and spells its fields in snake_case. One page, the latest
#: thousand taker fills, as before.
POLY_TRADES = "https://data-api.polymarket.com/v2/trades?condition={c}&limit={n}&taker_only=true"
TRADE_PAGE = 1000
TTL_S = 600                 # one read per market per ten minutes, cached
MAX_GAMES = 20              # the soonest games on a build; a college Saturday has sixty
DEADLINE_S = 60.0           # a slow venue never holds a build longer than this
MIN_USD = 250.0
MIN_TRADES = 10


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- the tapes, as money per side -------------------------------------------
def kalshi_flow(trades, yes_side: str, no_side: str, acc: dict | None = None) -> dict:
    """Taker money per side from Kalshi trades on one market.

    A YES taker paid the yes price per contract to be on ``yes_side``; a NO
    taker paid the no price to be on ``no_side``. Dollar fields first
    (the API's fixed-point migration: count_fp, yes_price_dollars), the
    legacy cent integers behind them — kalshi.parse_markets reads prices
    the same way."""
    acc = acc if acc is not None else {}
    for t in trades or []:
        if not isinstance(t, dict):
            continue
        n = _num(t.get("count_fp"))
        if n is None:
            n = _num(t.get("count"))
        yp = _num(t.get("yes_price_dollars"))
        if yp is None and _num(t.get("yes_price")) is not None:
            yp = _num(t.get("yes_price")) / 100.0
        np_ = _num(t.get("no_price_dollars"))
        if np_ is None and _num(t.get("no_price")) is not None:
            np_ = _num(t.get("no_price")) / 100.0
        if np_ is None and yp is not None:
            np_ = 1.0 - yp
        side = str(t.get("taker_side") or "").lower()
        if not n or n <= 0 or side not in ("yes", "no"):
            continue
        price = yp if side == "yes" else np_
        if price is None or not (0.0 < price < 1.0):
            continue
        s = acc.setdefault(yes_side if side == "yes" else no_side, {"usd": 0.0, "n": 0})
        s["usd"] += n * price
        s["n"] += 1
    return acc


def poly_flow(trades, side_of, acc: dict | None = None) -> dict:
    """Taker money per side from Polymarket trades (takerOnly). ``side_of``
    maps an outcome name to ("side", "other side") or None. A BUY of an
    outcome is money on it at the price paid; a SELL is money moving to the
    other outcome, at one minus the price."""
    acc = acc if acc is not None else {}
    for t in trades or []:
        if not isinstance(t, dict):
            continue
        got = side_of(str(t.get("outcome") or ""))
        size, price = _num(t.get("size")), _num(t.get("price"))
        verb = str(t.get("side") or "").upper()
        if not got or not size or size <= 0 or price is None or not (0.0 < price < 1.0) \
                or verb not in ("BUY", "SELL"):
            continue
        side, usd = (got[0], size * price) if verb == "BUY" else (got[1], size * (1.0 - price))
        s = acc.setdefault(side, {"usd": 0.0, "n": 0})
        s["usd"] += usd
        s["n"] += 1
    return acc


def split(acc: dict, a: str, b: str) -> dict | None:
    """``{a: money share, b: …, a_bets: trade share, b_bets: …, usd, n}``,
    or None when the market is too thin to say anything."""
    sa, sb = acc.get(a) or {"usd": 0.0, "n": 0}, acc.get(b) or {"usd": 0.0, "n": 0}
    usd, n = sa["usd"] + sb["usd"], sa["n"] + sb["n"]
    if usd < MIN_USD or n < MIN_TRADES:
        return None
    return {a: round(sa["usd"] / usd, 3), b: round(sb["usd"] / usd, 3),
            f"{a}_bets": round(sa["n"] / n, 3), f"{b}_bets": round(sb["n"] / n, 3),
            "usd": round(usd), "n": n}


# --- fetching ----------------------------------------------------------------
def fetch_kalshi_trades(ticker: str) -> list:
    body = fetch_text(KALSHI_TRADES.format(t=ticker, n=TRADE_PAGE),
                      f"kx_trades_{ticker}.json", ttl=TTL_S, timeout=20)
    got = json.loads(body)
    return got.get("trades") or [] if isinstance(got, dict) else []


#: ASKED COMPRESSED (2026-11-14), as Polymarket's events pages require for
#: a big page (step OY, `polysports.ACCEPT`); `fetch_text` unpacks a gzip
#: body. That was the first guess at why every read failed; the census's
#: `why` showed the real cause, v1's retirement (POLY_TRADES above).
POLY_HEADERS = {"Accept-Encoding": "gzip"}


def _poly_rows(got) -> list:
    """v2's rows (wrapped in ``data``), or v1's bare list, or nothing."""
    if isinstance(got, list):
        return got
    if isinstance(got, dict):
        for key in ("data", "trades"):
            if isinstance(got.get(key), list):
                return got[key]
    return []


def _poly_trade(t: dict) -> dict:
    """One v2 fill in the four names `poly_flow` reads (v1's)."""
    def first(*keys):
        return next((t.get(k) for k in keys if t.get(k) not in (None, "")), None)
    return {"side": first("side", "taker_side"), "outcome": first("outcome", "outcome_name"),
            "size": first("size", "shares"), "price": first("price")}


def fetch_poly_trades(cid: str) -> list:
    # Its own cache name: v1's last cached pages are never read as v2's.
    body = fetch_text(POLY_TRADES.format(c=cid, n=TRADE_PAGE),
                      f"pm_trades2_{cid[:40]}.json", ttl=TTL_S, timeout=20,
                      headers=POLY_HEADERS)
    return [_poly_trade(t) for t in _poly_rows(json.loads(body)) if isinstance(t, dict)]


# --- the game ----------------------------------------------------------------
def _kickoff_order(g: dict) -> str:
    return f"{str(g.get('date') or '')[:10]}T{str(g.get('kickoff') or '')}"


def attach(result: dict, sport: str, kalshi_markets=None, kalshi_line_markets=None,
           poly_rows=None, kalshi_trades=None, poly_trades=None, now: float | None = None) -> dict:
    """Hang ``money`` on every upcoming game with enough exchange flow.
    Returns a census. The trade readers are injectable (tests, replays)."""
    from . import crowd, exchangefair as _xf
    from .sources import kalshi, polysports
    kt = kalshi_trades or fetch_kalshi_trades
    pt = poly_trades or fetch_poly_trades
    games = [g for g in result.get("games") or [] if isinstance(g, dict)]
    census = {"games": 0, "ml": 0, "spread": 0, "total": 0, "errors": 0, "late": 0}
    upcoming = sorted((g for g in games if not crowd.started(g, now)), key=_kickoff_order)[:MAX_GAMES]
    if not upcoming:
        return census
    named = _xf.with_names(crowd._board_names(upcoming, result.get("teams")), sport)
    by_key = {(str(g.get("away")), str(g.get("home"))): g for g in named}
    key = lambda g: (str(g.get("away")), str(g.get("home")))  # noqa: E731

    # Which market says what, per game — matched exactly as crowd.attach does.
    kx_win: dict = {}
    for m in kalshi_markets or []:
        if kalshi.sport_of(m) not in (None, sport):
            continue
        g, _why = kalshi.match_game_verbose(m, named)
        if g is None:
            continue
        yes = kalshi.yes_team(m, g)
        if yes and m.get("ticker"):
            kx_win.setdefault(key(g), []).append((m["ticker"], yes))
    pm: dict = {}
    for r in poly_rows or []:
        if r.get("sport") not in (None, sport):
            continue
        g, _first_home = polysports.match_game(r, named)
        if g is not None and key(g) not in pm:
            pm[key(g)] = r

    start = time.monotonic()
    for g0 in upcoming:
        if time.monotonic() - start > DEADLINE_S:
            census["late"] += 1
            continue
        k = key(g0)
        g = by_key.get(k) or g0
        other = {"home": "away", "away": "home"}

        def club_of(name, g=g):
            h, a = polysports._club(name, g, "home"), polysports._club(name, g, "away")
            return ("home", "away") if h and not a else ("away", "home") if a and not h else None

        def over_under(name):
            low = name.strip().lower()
            return ("over", "under") if low == "over" else ("under", "over") if low == "under" else None

        ml: dict = {}
        sp: dict = {}
        tot: dict = {}
        venues = set()

        def read(fn, *args):
            try:
                return fn(*args)
            except (DataUnavailable, ValueError, OSError) as exc:
                census["errors"] += 1
                # WHICH VENUE REFUSED, AND HOW: the first refusal each, so a
                # count of failed reads names its cause on the board.
                venue = "Kalshi" if fn is kt else "Polymarket"
                census.setdefault("why", {}).setdefault(
                    venue, f"{type(exc).__name__}: {exc}"[:200])
                return []

        def take(venue, acc, flow):
            """Run one tape into ``acc``; name the venue if it added trades."""
            before = sum(x["n"] for x in acc.values())
            flow()
            if sum(x["n"] for x in acc.values()) > before:
                venues.add(venue)

        for ticker, yes in kx_win.get(k, []):
            take("Kalshi", ml, lambda t=ticker, y=yes: kalshi_flow(read(kt, t), y, other[y], ml))
        klines = crowd.kalshi_lines(kalshi_line_markets, g0, ids=True)
        if klines.get("kalshi_spread_ticker"):
            y = klines["kalshi_spread_yes"]
            take("Kalshi", sp, lambda: kalshi_flow(read(kt, klines["kalshi_spread_ticker"]), y, other[y], sp))
        if klines.get("kalshi_total_ticker"):
            take("Kalshi", tot, lambda: kalshi_flow(read(kt, klines["kalshi_total_ticker"]), "over", "under", tot))
        r = pm.get(k)
        if r is not None:
            if r.get("condition_id"):
                take("Polymarket", ml, lambda: poly_flow(read(pt, r["condition_id"]), club_of, ml))
            plines = crowd.crowd_lines(r, g, True, ids=True)
            if plines.get("poly_spread_cid"):
                take("Polymarket", sp, lambda: poly_flow(read(pt, plines["poly_spread_cid"]), club_of, sp))
            if plines.get("poly_total_cid"):
                take("Polymarket", tot, lambda: poly_flow(read(pt, plines["poly_total_cid"]), over_under, tot))

        out = {}
        s = split(ml, "home", "away")
        if s:
            out["ml"] = s
        s = split(sp, "home", "away")
        if s and crowd.home_spread(g0) is not None:
            out["spread"] = dict(s, line=crowd.home_spread(g0))
        s = split(tot, "over", "under")
        if s and g0.get("total") is not None:
            out["total"] = dict(s, line=float(g0["total"]))
        if not out:
            g0.pop("money", None)
            continue
        out["venues"] = sorted(venues)
        out["at"] = _dt.datetime.now().strftime("%H:%M")
        g0["money"] = out
        census["games"] += 1
        for m in ("ml", "spread", "total"):
            census[m] += m in out
    return census
