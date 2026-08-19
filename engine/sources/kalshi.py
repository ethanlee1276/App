"""Kalshi market data — the second prediction-market venue, priced.

Keyless and public: Kalshi's market-data endpoints require no account, no
key, and no credentials, which is exactly the posture the competitive
recipe demands (prefer exchange public APIs over scraped odds — Swish v.
OddsJam is about scraping BOOKS, and an exchange publishing its own order
book is the clean opposite of that).

WHY THIS VENUE IS DIFFERENT FROM POLYMARKET, AND WHY THAT SHAPES THE CODE

Polymarket wallets are public on-chain, which is what makes the informed-
flow module possible — WHO is buying is the signal there. Kalshi publishes
no trader identity, so a flow module here would be a thinner product
(engine/predmarket.py records that decision). What Kalshi DOES publish is a
real two-sided order book on CFTC-regulated event contracts, in all fifty
states, increasingly on sports. That makes it useful for the thing the
recipe calls the Exchange-Native pillar: a PRICE — a fair value with no
vig to strip, because an exchange's mid IS the market's probability, where
a sportsbook's line has the book's margin baked in and has to be de-vigged
on an assumption.

So this module is a pricing source, not a flow tracker: fetch wrappers that
degrade to DataUnavailable, pure parsers unit-tested offline, and a
snapshot store — order books cannot be backfilled, and a year of tape is
the moat here exactly as it is for Polymarket.
"""

from __future__ import annotations

import datetime as _dt
import json
import re

from .fetch import fetch_text, DataUnavailable                # noqa: F401

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"

#: Sports series prefixes seen on Kalshi's board. Used to FILTER a market
#: dump to sports, never to assert what exists — the series list is theirs
#: to grow, so anything unmatched still parses and simply isn't tagged.
SPORT_HINTS = {
    "mlb": ("MLB", "BASEBALL"),
    "nfl": ("NFL", "FOOTBALL"),
    "nba": ("NBA", "BASKETBALL"),
    "wnba": ("WNBA",),
    "cfb": ("NCAAF", "CFB"),
    "ufc": ("UFC", "MMA"),
}

#: Candidate game-winner series per sport, fetched DIRECTLY. Found on
#: Ethan's first live --desk run (2026-08-11): the general /markets page
#: returns an arbitrary 200 of the exchange's thousands of listings —
#: politics and econ long before any ballgame — so the desk saw zero
#: sports markets from a perfectly healthy feed. Series are the fix, the
#: same shape the weather desk already uses for KXHIGH*. Names are
#: candidates on purpose: a series that doesn't exist fetches nothing
#: and costs nothing, and every fetch is reported in the build output so
#: the next --desk run says which names were real.
SPORT_SERIES = {
    "mlb": ("KXMLBGAME", "MLBGAME"),
    "nfl": ("KXNFLGAME", "NFLGAME"),
    "nba": ("KXNBAGAME", "KXNBA"),
    "wnba": ("KXWNBAGAME", "KXWNBA"),
    "cfb": ("KXNCAAFGAME",),
}


def fetch_sports_markets(parse) -> tuple[list[dict], dict]:
    """Game markets straight from the sports series, plus a per-series
    report. ``parse`` is parse_markets, injected so tests stay offline.

    Returns (markets, {series: count | "error"}). A missing series is
    simply absent from the exchange's catalog under that name — recorded
    as 0 so the report distinguishes "wrong name" from "feed down"."""
    out, report = [], {}
    for sport, candidates in SPORT_SERIES.items():
        for series in candidates:
            try:
                events = fetch_events(series)
            except Exception:                     # noqa: BLE001
                report[series] = "error"
                continue
            markets = []
            for ev in events or []:
                markets.extend(ev.get("markets") or [])
            parsed = parse(markets)
            report[series] = len(parsed)
            out.extend(parsed)
            if parsed:
                break        # this sport's real series found; skip aliases
    return out, report


def fetch_markets(limit: int = 200, status: str = "open",
                  ttl: int = 300) -> list[dict]:
    """One page of open markets, busiest first where the API allows."""
    url = f"{KALSHI}/markets?limit={limit}&status={status}"
    raw = json.loads(fetch_text(url, "kalshi_markets.json", ttl=ttl))
    return raw.get("markets", []) or []


def fetch_events(series_ticker: str, limit: int = 100,
                 ttl: int = 300) -> list[dict]:
    url = (f"{KALSHI}/events?series_ticker={series_ticker}"
           f"&status=open&limit={limit}&with_nested_markets=true")
    raw = json.loads(fetch_text(url, f"kalshi_events_{series_ticker}.json",
                                ttl=ttl))
    return raw.get("events", []) or []


def _num(v) -> float | None:
    """Kalshi serialises decimals as strings ("0.4300"); floats and ints
    pass through; anything else is None, never a throw."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_markets(raw: list[dict]) -> list[dict]:
    """Normalize Kalshi market objects to the fields the site prices with.

    Pure, so it unit-tests offline. FOUND BY THE LIVE AUTOPSY on Ethan's
    machine (2026-08-11): the API migrated its price fields. Prices now
    arrive as DOLLAR decimals — yes_bid_dollars / yes_ask_dollars /
    last_price_dollars, 0.00-1.00 on a $1 contract — and volumes as
    *_fp strings; the old cent-integer fields come back as None, which
    made the parser reject every real market on the exchange. Dollars
    are read first; the legacy cent fields remain as a fallback so old
    fixtures and any stored snapshot still parse.

    The mid of a real two-sided book is the honest fair value, and when
    one side is missing the last trade stands in — reported as such,
    because a fair value with no book behind it is a weaker claim and
    the page says so.
    """
    out = []
    for m in raw or []:
        yes_bid = _num(m.get("yes_bid_dollars"))
        yes_ask = _num(m.get("yes_ask_dollars"))
        last = _num(m.get("last_price_dollars"))
        if yes_bid is None and yes_ask is None and last is None:
            # Legacy cent integers, scaled to the same 0-1 space.
            cb, ca, cl = (_num(m.get("yes_bid")), _num(m.get("yes_ask")),
                          _num(m.get("last_price")))
            yes_bid = cb / 100.0 if cb is not None else None
            yes_ask = ca / 100.0 if ca is not None else None
            last = cl / 100.0 if cl is not None else None
        if yes_bid and yes_ask:
            mid = (yes_bid + yes_ask) / 2.0
            basis = "book"
            spread = round((yes_ask - yes_bid) * 100.0, 2)
        elif last:
            mid = last
            basis = "last_trade"
            spread = None
        else:
            continue                     # nothing priced — nothing to say
        vol = _num(m.get("volume_24h_fp"))
        if vol is None:
            vol = _num(m.get("volume_24h")) or 0.0
        oi = _num(m.get("open_interest_fp"))
        if oi is None:
            oi = _num(m.get("open_interest")) or 0.0
        out.append({
            "ticker": m.get("ticker", ""),
            "event_ticker": m.get("event_ticker", ""),
            "title": m.get("title", ""),
            "subtitle": m.get("subtitle") or m.get("yes_sub_title") or "",
            "prob": round(mid, 4),
            "price_basis": basis,
            "spread_cents": spread,
            "volume_24h": vol,
            "open_interest": oi,
            "close_time": m.get("close_time", ""),
            "category": (m.get("category") or "").strip(),
        })
    out.sort(key=lambda r: -r["volume_24h"])
    return out


def sport_of(row: dict) -> str | None:
    """Which of our leagues a Kalshi market belongs to, if any."""
    hay = " ".join((row.get("ticker", ""), row.get("event_ticker", ""),
                    row.get("title", ""), row.get("category", ""))).upper()
    for sport, hints in SPORT_HINTS.items():
        if any(h in hay for h in hints):
            return sport
    return None


#: Words that survive team-name normalisation but carry no identity.
_STOP = {"THE", "AT", "VS", "WIN", "WINS", "WINNER", "BEAT", "GAME", "TO"}


def _name_tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^A-Z0-9]+", (text or "").upper())
            if len(t) >= 3 and t not in _STOP}


def match_game(row: dict, games: list[dict]) -> dict | None:
    """Match one Kalshi market to one of tonight's games, by team name.

    ``games`` rows carry home/away abbreviations plus full names. Both
    teams must appear in the market's text — one name alone matches every
    future series and half the league's markets. No fuzzy scoring: a match
    this cheap is either obvious or it is wrong, and wrong here means
    hanging an edge claim on somebody else's game.
    """
    hay = _name_tokens(f"{row.get('title', '')} {row.get('subtitle', '')} "
                       f"{row.get('event_ticker', '')}")
    for g in games:
        home_hit = (_name_tokens(g.get("home_name", "")) & hay
                    or g.get("home", "").upper() in hay)
        away_hit = (_name_tokens(g.get("away_name", "")) & hay
                    or g.get("away", "").upper() in hay)
        if home_hit and away_hit:
            return g
    return None


# --- the tape ---------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS kalshi_snapshots (
    bucket_ts INTEGER, ticker TEXT, prob REAL, spread_cents REAL,
    volume_24h REAL, open_interest REAL, title TEXT,
    PRIMARY KEY (bucket_ts, ticker)
);
"""

SNAP_BUCKET_S = 600


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)


def price_series(conn, ticker: str, hours: int = 24,
                 now: float | None = None) -> list[dict]:
    """OUR recorded price tape for one market, oldest first.

    The snapshots have been written on every refresh since the Kalshi
    adapter shipped; nothing read them back until the board grew a chart.
    Each point is a 10-minute bucket that was actually observed — there is
    no interpolation and no backfill, because an order book cannot be
    backfilled and a smooth line through gaps we never saw would be a
    picture of a market that did not exist.

    A gap in the middle is therefore real information: the machine was
    down, or the market was not on the board that cycle. The caller draws
    the points it is given.
    """
    import time as _time
    ensure_tables(conn)
    since = (now if now is not None else _time.time()) - hours * 3600
    rows = conn.execute(
        "SELECT bucket_ts, prob, spread_cents, volume_24h, open_interest "
        "FROM kalshi_snapshots WHERE ticker=? AND bucket_ts>=? "
        "ORDER BY bucket_ts", (ticker, since)).fetchall()
    return [{"ts": int(r[0]), "prob": r[1], "spread_cents": r[2],
             "vol": r[3], "oi": r[4]} for r in rows]


def store_snapshot(conn, rows: list[dict], now: float | None = None) -> int:
    """Append one 10-minute bucket of prices. Order books cannot be
    backfilled — every pricing idea needs stored tape to validate against,
    and the day Kalshi matters is the day a year of this already exists."""
    import time as _time
    ensure_tables(conn)
    bucket = int((now or _time.time()) // SNAP_BUCKET_S) * SNAP_BUCKET_S
    n = 0
    for r in rows:
        if not r.get("ticker"):
            continue
        conn.execute(
            "INSERT OR IGNORE INTO kalshi_snapshots (bucket_ts, ticker, prob,"
            " spread_cents, volume_24h, open_interest, title) "
            "VALUES (?,?,?,?,?,?,?)",
            (bucket, r["ticker"], r["prob"], r.get("spread_cents"),
             r.get("volume_24h", 0), r.get("open_interest", 0),
             r.get("title", "")))
        n += conn.total_changes and 1
    conn.commit()
    return n


def yes_team(row: dict, g: dict) -> str | None:
    """Which side of the matched game this market's YES pays on.

    A Kalshi game market is "Will TEAM win?", and TEAM can be either the
    home or the away club. Comparing P(home) to every YES price (the
    board's original math) had the sign backwards whenever YES was the
    away team, which is half the league.

    Four deciders, most reliable first, each documented by a real market
    shape:

    1. The TICKER's last segment — Kalshi's game tickers end in the YES
       team's own code ("KXMLBGAME-26AUG03-NYYBOS-NYY" pays on NYY).
       The exchange's naming beats any reading of prose.
    2. The SUBTITLE, when it names exactly one club (yes_sub_title is
       that club on many series).
    3. The TITLE, when it names exactly one club ("Will the Yankees
       win?").
    4. First mention, when the title names BOTH ("Yankees beat the Red
       Sox" — English puts the team the market is about first).

    A market none of these decide goes unmodeled rather than modeled on
    a coin flip.
    """
    tail = (row.get("ticker", "") or "").rsplit("-", 1)[-1].upper()
    if tail and tail == g.get("home", "").upper():
        return "home"
    if tail and tail == g.get("away", "").upper():
        return "away"
    h_tok = _name_tokens(g.get("home_name", ""))
    a_tok = _name_tokens(g.get("away_name", ""))
    for field in ("subtitle", "title"):
        own = _name_tokens(row.get(field, "") or "")
        if not own:
            continue
        home = bool(h_tok & own or g.get("home", "").upper() in own)
        away = bool(a_tok & own or g.get("away", "").upper() in own)
        if home != away:
            return "home" if home else "away"
    title = (row.get("title", "") or "").upper()
    h_pos = min((title.find(t) for t in h_tok if t in title), default=-1)
    a_pos = min((title.find(t) for t in a_tok if t in title), default=-1)
    if h_pos >= 0 and a_pos >= 0 and h_pos != a_pos:
        return "home" if h_pos < a_pos else "away"
    return None


#: The recommendation gate, all three bars documented:
#:   edge   — 6 probability points, the futures board's own honest unit;
#:            below it the number is inside model noise.
#:   volume — a "price" nobody trades is a stale quote, not a market.
#:   book   — a real two-sided book only. A last-trade print can be hours
#:            old; recommending against it claims an edge over a price
#:            that no longer exists.
KALSHI_MIN_EDGE_PTS = 6.0
KALSHI_MIN_VOLUME = 250.0
KALSHI_MAX_SPREAD_CENTS = 6.0


def board(markets: list[dict], games_by_sport: dict | None = None,
          model_probs: dict | None = None, top: int = 25) -> dict:
    """The cross-market board: Kalshi's probability beside ours.

    ``games_by_sport``: {sport: [game rows]} for tonight, used to pin a
    market to a real game. ``model_probs``: {(sport, "AWY@HOM"): p_home}
    from our own game engines. The board never invents a leg it lacks —
    a row missing our number still shows Kalshi's, labelled, because a
    price with no comparison is still information and pretending otherwise
    would just hide the venue.

    Rows that clear the gate carry ``rec``/``rec_side`` — the desk's
    actual recommendations, journaled as a flat-stake PAPER book until
    the bucket earns real stakes the same way the loose book would.
    """
    rows = []
    for m in markets:
        sport = sport_of(m)
        if not sport:
            continue
        row = dict(m, sport=sport, matchup=None, model_p=None,
                   edge_pts=None, yes_side=None, rec=False, rec_side=None)
        g = None
        if games_by_sport and games_by_sport.get(sport):
            g = match_game(m, games_by_sport[sport])
        if g is not None:
            key = f"{g.get('away', '')}@{g.get('home', '')}"
            row["matchup"] = key
            p_home = (model_probs or {}).get((sport, key))
            side = yes_team(m, g)
            if p_home is not None and side is not None:
                p_yes = float(p_home) if side == "home" else 1 - float(p_home)
                row["yes_side"] = side
                row["model_p"] = round(p_yes, 4)
                # Positive: our model likes YES more than the exchange
                # charges for it. Stated in points of probability, the same
                # honest unit the futures board uses.
                row["edge_pts"] = round((p_yes - m["prob"]) * 100, 1)
                liquid = (m.get("price_basis") == "book"
                          and float(m.get("volume_24h") or 0) >= KALSHI_MIN_VOLUME
                          and (m.get("spread_cents") or 99) <= KALSHI_MAX_SPREAD_CENTS)
                if liquid and abs(row["edge_pts"]) >= KALSHI_MIN_EDGE_PTS:
                    row["rec"] = True
                    row["rec_side"] = "YES" if row["edge_pts"] > 0 else "NO"
        rows.append(row)
    rows.sort(key=lambda r: (not r["rec"], r["edge_pts"] is None,
                             -(abs(r["edge_pts"]) if r["edge_pts"] is not None
                               else r["volume_24h"])))
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "venue": "kalshi",
        "rows": rows[:top],
        "sports_seen": sorted({r["sport"] for r in rows}),
        "n_markets": len(rows),
        "n_matched": sum(1 for r in rows if r["matchup"]),
        "n_modeled": sum(1 for r in rows if r["model_p"] is not None),
        "n_rec": sum(1 for r in rows if r["rec"]),
    }


def fetch_markets_by_tickers(tickers: list[str], ttl: int = 120) -> list[dict]:
    """The settlement pull: specific markets by ticker, results included."""
    if not tickers:
        return []
    url = f"{KALSHI}/markets?tickers={','.join(tickers[:40])}"
    raw = json.loads(fetch_text(url, "kalshi_settle.json", ttl=ttl))
    return raw.get("markets", []) or []
