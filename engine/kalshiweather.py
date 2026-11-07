"""The weather desk: NWS forecasts priced against Kalshi's temperature markets.

Ethan, 2026-08-11: "maybe we can have an ai scan ... real world data and
politics and weather and shit like that to recommend the best pollymarket
bets." The honest version of that idea starts where a VERIFIABLE public
number exists that the market must eventually agree with. Daily-high
markets are that case exactly:

  * Kalshi settles each city's market against one named airport/station
    reading (the same one the National Weather Service forecasts);
  * the NWS point forecast for that station is free, keyless and
    published hours before the market closes;
  * the market resolves the SAME DAY, so the desk's record grades fast —
    a hundred settlements accumulate in weeks, not election cycles.

What this module does NOT do is scan news for politics calls. A political
market has no public forecast to price against — an LLM's vibe about a
headline is not a probability, and a bucket that cannot be graded quickly
cannot earn stakes. Politics stays with the flow detector (smart-wallet
flags, already validated on its own report card).

The probability math is deliberately plain: the NWS daily high is the
mean of a normal distribution whose width is the forecast's own
verification error at that lead time. NWS/MOS verification puts same-day
high-temperature MAE around 1.5-2°F and day-ahead near 2.5-3°F; the
sigmas below sit at the conservative end of those ranges, and every
(forecast, settle) pair is logged so the sigmas can be FIT from our own
history once it exists — the same "prior now, evidence later" contract
as every other dial in this repo.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re

from .sources.fetch import fetch_json
from .sources.kalshi import fetch_events

#: Kalshi's daily-high series and the station each one settles against.
#: Series tickers drift as Kalshi reorganises; unknown tickers simply
#: fetch nothing, so adding a city is one line and a stale one is inert.
CITIES = {
    "KXHIGHNY":   {"city": "New York",      "lat": 40.7789, "lon": -73.9692},
    "KXHIGHCHI":  {"city": "Chicago",       "lat": 41.7842, "lon": -87.7553},
    "KXHIGHMIA":  {"city": "Miami",         "lat": 25.7906, "lon": -80.3164},
    "KXHIGHAUS":  {"city": "Austin",        "lat": 30.3208, "lon": -97.7605},
    "KXHIGHDEN":  {"city": "Denver",        "lat": 39.8467, "lon": -104.6558},
    "KXHIGHLAX":  {"city": "Los Angeles",   "lat": 33.9382, "lon": -118.3866},
    "KXHIGHPHIL": {"city": "Philadelphia",  "lat": 39.8683, "lon": -75.2311},
}

#: Forecast error (°F, one standard deviation) by days of lead time.
#: Conservative NWS/MOS verification priors — refined from our own logged
#: (forecast, settle) pairs once enough accumulate.
SIGMA_BY_LEAD = {0: 2.0, 1: 3.0, 2: 3.8}
MAX_LEAD_DAYS = 2

#: The same three-bar gate shape as the sports desk, with a higher edge
#: bar: 8 points, because a 2°F sigma is our claim about the WORLD, not a
#: fitted model, and the bar should absorb that claim being a little wrong.
WX_MIN_EDGE_PTS = 8.0
WX_MIN_VOLUME = 100.0
WX_MAX_SPREAD_CENTS = 8.0

#: PAUSED (2026-11-03, Ethan: yes to hiding the weather picks). The desk's
#: graded record said its claims were not its odds: NO calls claimed about
#: 86% and won about 52% over 3,173 settled paper bets, and the ones claimed
#: in the 60s won 2%, against a whole prediction desk at -24% on paper.
#: While this is set, the board still prices every bracket and logs the
#: forecast (kalshi_wx_log, what `audit` reads), but recommends nothing, so
#: nothing is journaled, and pm_build publishes no weather rows: the page
#: says the desk is paused instead. Empty it to un-pause, and only after
#: `python3 -m engine.kalshiweather --audit` and a fresh measure say the
#: claims hold.
PAUSED = ("The weather desk is paused while its forecasts are fixed: its "
          "calls claimed far more than they won.")


def parse_bracket(text: str) -> tuple[float | None, float | None] | None:
    """(low, high) °F bounds a market's YES pays inside, from its label.

    Kalshi labels the brackets three ways — "83° or above", "72° or
    below", "78° to 79°" — and settles on whole degrees, so an inclusive
    "78 to 79" means the real-line interval [77.5, 79.5). Open ends
    return None on that side. Anything unparseable returns None overall:
    a bracket we cannot read is a bet we cannot price.
    """
    t = (text or "").replace("°", "").strip().lower()
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:f\b)?\s*or\s*(above|higher)", t)
    if m:
        return (float(m.group(1)) - 0.5, None)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:f\b)?\s*or\s*(below|lower)", t)
    if m:
        return (None, float(m.group(1)) + 0.5)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:f\b)?\s*(?:to|-|–)\s*(-?\d+(?:\.\d+)?)", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if hi < lo:
            return None
        return (lo - 0.5, hi + 0.5)
    return None


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def bracket_prob(lo: float | None, hi: float | None,
                 mu: float, sigma: float) -> float:
    """P(high temp lands in [lo, hi)) under Normal(mu, sigma)."""
    if sigma <= 0:
        return 0.0
    upper = _phi((hi - mu) / sigma) if hi is not None else 1.0
    lower = _phi((lo - mu) / sigma) if lo is not None else 0.0
    return max(0.0, min(1.0, upper - lower))


def nws_high(lat: float, lon: float, date: str, ttl: int = 1800) -> float | None:
    """The NWS forecast daily high (°F) for one station and date.

    Two hops, as the API requires: /points resolves the gridpoint, whose
    forecast lists half-day periods; the DAYTIME period of the target
    date carries the high. Missing data returns None — the desk prices
    nothing rather than pricing on a guess.
    """
    try:
        pt = fetch_json(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
                        f"nws_pt_{lat:.2f}_{lon:.2f}.json", ttl=6 * 3600)
        url = ((pt.get("properties") or {}).get("forecast") or "")
        if not url:
            return None
        fc = fetch_json(url, f"nws_fc_{lat:.2f}_{lon:.2f}.json", ttl=ttl)
        for period in ((fc.get("properties") or {}).get("periods") or []):
            if not period.get("isDaytime"):
                continue
            if str(period.get("startTime", ""))[:10] == date:
                t = period.get("temperature")
                if period.get("temperatureUnit") == "C" and t is not None:
                    t = t * 9 / 5 + 32
                return float(t) if t is not None else None
    except Exception:                                     # noqa: BLE001
        return None
    return None


def _market_date(m: dict) -> str | None:
    """The day a daily market is about: its ticker's own date first.

    THE TICKER, NOT THE CLOSE (2026-11-03). This read `close_time[:10]`,
    which is UTC. A market on one evening's high can close after midnight
    UTC, so its date may read a day late, and then it is priced against the
    NEXT day's forecast: a confident number about the wrong day, the shape
    of the desk's record when it was paused. The ticker says which day the
    contract is about (KXHIGHNY-26NOV03-...), and ledger.predmarket_event_date
    already reads it for the journal; the close time is the fallback for a
    ticker that carries no date."""
    from .ledger import predmarket_event_date
    day = predmarket_event_date(m.get("ticker"))
    if day:
        return day
    ct = m.get("close_time") or ""
    return ct[:10] if len(ct) >= 10 else None


def weather_board(markets_by_series: dict, highs: dict,
                  today: str | None = None) -> list[dict]:
    """Price every readable bracket against the forecast. Pure — tested
    offline with fixture markets and fixed forecast numbers.

    ``markets_by_series``: {series_ticker: [parsed market rows]} (the
    kalshi source's parse_markets shape). ``highs``: {(series, date): °F}.
    """
    today = today or _dt.date.today().isoformat()
    rows = []
    for series, markets in (markets_by_series or {}).items():
        meta = CITIES.get(series)
        if not meta:
            continue
        for m in markets:
            date = _market_date(m)
            if not date:
                continue
            lead = (_dt.date.fromisoformat(date)
                    - _dt.date.fromisoformat(today)).days
            if lead < 0 or lead > MAX_LEAD_DAYS:
                continue
            mu = highs.get((series, date))
            bracket = parse_bracket(m.get("subtitle") or m.get("title") or "")
            if mu is None or bracket is None:
                continue
            sigma = SIGMA_BY_LEAD.get(lead, SIGMA_BY_LEAD[MAX_LEAD_DAYS])
            p = bracket_prob(bracket[0], bracket[1], mu, sigma)
            edge_pts = round((p - m["prob"]) * 100, 1)
            # Net of Kalshi's fee (audit 2026-09-30, B7-1), on the side
            # the gap points to; the gross gap stays on the row.
            from .exchangefees import fee_bps as _fee_bps, net_edge_pts as _net
            side_p = m["prob"] if edge_pts > 0 else 1 - m["prob"]
            side_fair = p if edge_pts > 0 else 1 - p
            fee = _fee_bps("kalshi", side_p)
            net = round(_net(side_fair, side_p, "kalshi"), 2)
            liquid = (m.get("price_basis") == "book"
                      and float(m.get("volume_24h") or 0) >= WX_MIN_VOLUME
                      and (m.get("spread_cents") or 99) <= WX_MAX_SPREAD_CENTS)
            # `would_rec` is the gate on the net number; while PAUSED it
            # is recorded in the shadow log (log_shadow) and graded there,
            # but it is not a recommendation.
            would_rec = liquid and net >= WX_MIN_EDGE_PTS
            rec = would_rec and not PAUSED
            rows.append({
                "ticker": m["ticker"], "series": series,
                "city": meta["city"], "date": date, "lead_days": lead,
                "title": m.get("title", ""), "subtitle": m.get("subtitle", ""),
                "bracket": list(bracket), "forecast_f": round(mu, 1),
                "sigma_f": sigma, "model_p": round(p, 4),
                "prob": m["prob"], "price_basis": m.get("price_basis"),
                "volume_24h": m.get("volume_24h"),
                "spread_cents": m.get("spread_cents"),
                "edge_pts": edge_pts, "net_edge_pts": net, "fee_bps": fee,
                "rec": rec,
                "rec_side": ("YES" if edge_pts > 0 else "NO") if rec else None,
                "would_rec": would_rec,
                "would_side": ("YES" if edge_pts > 0 else "NO") if would_rec else None,
            })
    rows.sort(key=lambda r: (not r["rec"], -abs(r["edge_pts"])))
    return rows


def fetch_weather_markets(parse) -> dict:
    """{series: [parsed markets]} for every configured city.

    ``parse`` is engine.sources.kalshi.parse_markets, injected so tests
    never touch the wire. Cities whose series fetch fails are skipped —
    one city's outage must not cost the rest of the desk.
    """
    out = {}
    for series in CITIES:
        try:
            events = fetch_events(series)
        except Exception:                                 # noqa: BLE001
            continue
        markets = []
        for ev in events or []:
            markets.extend(ev.get("markets") or [])
        parsed = parse(markets)
        if parsed:
            out[series] = parsed
    return out


def log_forecasts(conn, rows: list[dict]) -> int:
    """Persist (forecast, market, price) so the sigmas can be fit from
    our own verification history later. Idempotent per ticker per day."""
    conn.execute("""CREATE TABLE IF NOT EXISTS kalshi_wx_log (
        date TEXT, ticker TEXT, series TEXT, forecast_f REAL, sigma_f REAL,
        lead_days INTEGER, model_p REAL, market_p REAL, settle_f REAL,
        PRIMARY KEY (date, ticker))""")
    n = 0
    for r in rows:
        cur = conn.execute(
            "INSERT OR IGNORE INTO kalshi_wx_log "
            "(date, ticker, series, forecast_f, sigma_f, lead_days, "
            "model_p, market_p) VALUES (?,?,?,?,?,?,?,?)",
            (r["date"], r["ticker"], r["series"], r["forecast_f"],
             r["sigma_f"], r["lead_days"], r["model_p"], r["prob"]))
        n += cur.rowcount
    conn.commit()
    return n


# --- the shadow record, while PAUSED (2026-11-03) ------------------------------
#: A shadow pick whose day is this far past and still has no result is not
#: asked about again (the journal's own PREDMARKET_LOST_DAYS).
SHADOW_ASK_DAYS = 14


def _shadow_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS kalshi_wx_shadow (
        ticker TEXT PRIMARY KEY, date TEXT, made TEXT, side TEXT,
        claimed REAL, price REAL, lead_days INTEGER, result TEXT)""")


def log_shadow(conn, rows: list[dict], made: str | None = None) -> int:
    """What the paused desk WOULD have recommended, so un-pausing has a
    measure of its own.

    Kept in the history db, out of the ledger, so none of it reaches the
    Record page or a member: the pause hides the picks, and this is the
    only place they are still graded. One row per ticker, the first time
    it clears the gate, which is the journal's own rule; `claimed` and
    `price` are the side's, as `log_predmarket` keeps them."""
    _shadow_table(conn)
    made = made or _dt.date.today().isoformat()
    n = 0
    for r in rows:
        side = r.get("would_side")
        if not r.get("would_rec") or side not in ("YES", "NO"):
            continue
        p, q = float(r["model_p"]), float(r["prob"])
        cur = conn.execute(
            "INSERT OR IGNORE INTO kalshi_wx_shadow "
            "(ticker, date, made, side, claimed, price, lead_days) "
            "VALUES (?,?,?,?,?,?,?)",
            (r["ticker"], r["date"], made, side,
             round(p if side == "YES" else 1 - p, 4),
             round(q if side == "YES" else 1 - q, 4), r.get("lead_days")))
        n += cur.rowcount
    conn.commit()
    return n


def shadow_open(conn, today: str | None = None) -> list[str]:
    """Shadow picks past their day with no result yet: the tickers pm_build
    adds to the journal's own settlement pull (one pull, and one cache
    name, for both)."""
    import sqlite3
    today = today or _dt.date.today().isoformat()
    oldest = (_dt.date.fromisoformat(today)
              - _dt.timedelta(days=SHADOW_ASK_DAYS)).isoformat()
    try:
        return [t for (t,) in conn.execute(
            "SELECT ticker FROM kalshi_wx_shadow WHERE result IS NULL "
            "AND date < ? AND date >= ? ORDER BY date, ticker",
            (today, oldest))]
    except sqlite3.Error:
        return []


def settle_shadow(conn, results: dict) -> int:
    """Grade shadow picks from {ticker: "yes" | "no"}: the same results
    dict the journal is graded from."""
    import sqlite3
    n = 0
    try:
        for t, res in (results or {}).items():
            if res in ("yes", "no"):
                n += conn.execute(
                    "UPDATE kalshi_wx_shadow SET result=? "
                    "WHERE ticker=? AND result IS NULL", (res, t)).rowcount
    except sqlite3.Error:
        return 0
    conn.commit()
    return n


def _shadow_report(hconn) -> dict:
    import sqlite3
    try:
        rows = hconn.execute(
            "SELECT side, claimed, result, lead_days FROM kalshi_wx_shadow "
            "WHERE result IN ('yes','no')").fetchall()
        waiting = hconn.execute(
            "SELECT COUNT(*) FROM kalshi_wx_shadow WHERE result IS NULL").fetchone()[0]
    except sqlite3.Error:
        return {"graded": {"n": 0}, "by_lead": {}, "waiting": 0}
    graded = [(c, (s or "").lower() == r) for s, c, r, _l in rows]
    by_lead: dict = {}
    for (s, c, r, lead) in rows:
        by_lead.setdefault(str(lead), []).append((c, (s or "").lower() == r))
    return {"graded": _grade(graded), "waiting": waiting,
            "by_lead": {k: _grade(v) for k, v in sorted(by_lead.items())}}


def _grade(rows) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    won = sum(1 for _p, w in rows if w)
    claimed = [p for p, _w in rows if p is not None]
    return {"n": n, "won": won, "lost": n - won, "won_pct": round(won / n, 4),
            "claimed_pct": round(sum(claimed) / len(claimed), 4) if claimed else None}


# --- the audit (2026-11-03) ----------------------------------------------------
def _date_class(ticker: str, priced: str | None) -> str:
    """How the day the desk priced compares with the day the ticker is about."""
    from .ledger import predmarket_event_date
    about = predmarket_event_date(ticker)
    if not priced:
        return "no forecast logged"
    if not about:
        return "ticker carries no date"
    if priced == about:
        return "same day"
    return "desk a day late" if priced > about else "desk a day early"


def audit(hconn, lconn) -> dict:
    """Why the paused desk lost, from its own log and journal. Read-only.

    Every forecast the desk logged, by how the day it priced compares with
    the day the ticker says the contract is about; then every settled
    weather paper bet, grouped by that and by how many days ahead the bet
    was made: won-lost, the chance claimed, the chance won. A desk pricing
    the wrong day reads as "desk a day late" losing at its claims; a desk
    pricing the right day too sharply reads as "same day" losing anyway,
    worst on the bets made the day of the high.
    """
    import sqlite3
    from collections import Counter
    from .ledger import predmarket_event_date
    priced: dict = {}
    try:
        for d, t in hconn.execute("SELECT date, ticker FROM kalshi_wx_log ORDER BY date"):
            priced.setdefault(t, d)
    except sqlite3.Error:
        pass
    logged = Counter(_date_class(t, d) for t, d in priced.items())
    samples = [{"ticker": t, "priced": d, "about": predmarket_event_date(t)}
               for t, d in priced.items() if _date_class(t, d) not in ("same day",)][:3]
    by_class: dict = {}
    by_lead: dict = {}
    for t, status, p, made in lconn.execute(
            "SELECT player, status, hit_prob, date FROM bets WHERE sport='weather' "
            "AND category='predmarket' AND status IN ('won','lost')"):
        row = (float(p) if p is not None else None, status == "won")
        by_class.setdefault(_date_class(t, priced.get(t)), []).append(row)
        about = predmarket_event_date(t)
        try:
            lead = (_dt.date.fromisoformat(about) - _dt.date.fromisoformat(str(made)[:10])).days
        except (TypeError, ValueError):
            lead = None
        by_lead.setdefault("?" if lead is None else str(lead), []).append(row)
    return {"logged": dict(logged), "samples": samples,
            "bets": {k: _grade(v) for k, v in sorted(by_class.items())},
            "by_lead": {k: _grade(v) for k, v in sorted(by_lead.items())},
            "shadow": _shadow_report(hconn)}


def _audit_lines(rep: dict) -> list[str]:
    def line(k, g):
        if not g.get("n"):
            return f"    {k:22} none"
        c = g.get("claimed_pct")
        return (f"    {k:22} {g['won']}-{g['lost']}  won {g['won_pct']:.0%}"
                + (f", claimed {c:.0%}" if c is not None else ""))
    out = [f"weather desk audit — {sum(rep['logged'].values()):,} forecasts logged",
           "  the day the desk priced, against the day the ticker is about:"]
    out += [f"    {k:22} {n:,}" for k, n in sorted(rep["logged"].items())]
    out.append("  settled paper bets, by that:")
    out += [line(k, g) for k, g in rep["bets"].items()] or ["    none"]
    out.append("  settled paper bets, by days ahead of the high:")
    out += [line(f"{k} day(s) ahead", g) for k, g in rep["by_lead"].items()] or ["    none"]
    for s in rep["samples"]:
        out.append(f"  e.g. {s['ticker']}: priced for {s['priced']}, the ticker is about {s['about']}")
    sh = rep.get("shadow") or {"graded": {"n": 0}, "by_lead": {}, "waiting": 0}
    out.append(f"  while paused, the picks it would have made (graded; "
               f"{sh['waiting']:,} waiting on a result):")
    out.append(line("all", sh["graded"]))
    out += [line(f"{k} day(s) ahead", g) for k, g in sh["by_lead"].items()]
    return out


if __name__ == "__main__":                       # pragma: no cover
    import sqlite3
    import sys
    if "--audit" in sys.argv:
        from . import db as _db, ledger as _ledger
        h = sqlite3.connect(f"file:{_db.DEFAULT_DB}?mode=ro", uri=True)
        lg = sqlite3.connect(f"file:{_ledger.DEFAULT_DB}?mode=ro", uri=True)
        for _l in _audit_lines(audit(h, lg)):
            print(_l)
    else:
        print("usage: python3 -m engine.kalshiweather --audit   (read-only)")
