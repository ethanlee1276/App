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
    """The settle date a daily market is about, read off close_time."""
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
            liquid = (m.get("price_basis") == "book"
                      and float(m.get("volume_24h") or 0) >= WX_MIN_VOLUME
                      and (m.get("spread_cents") or 99) <= WX_MAX_SPREAD_CENTS)
            rec = liquid and abs(edge_pts) >= WX_MIN_EDGE_PTS
            rows.append({
                "ticker": m["ticker"], "series": series,
                "city": meta["city"], "date": date, "lead_days": lead,
                "title": m.get("title", ""), "subtitle": m.get("subtitle", ""),
                "bracket": list(bracket), "forecast_f": round(mu, 1),
                "sigma_f": sigma, "model_p": round(p, 4),
                "prob": m["prob"], "price_basis": m.get("price_basis"),
                "volume_24h": m.get("volume_24h"),
                "spread_cents": m.get("spread_cents"),
                "edge_pts": edge_pts, "rec": rec,
                "rec_side": ("YES" if edge_pts > 0 else "NO") if rec else None,
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
