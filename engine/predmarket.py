"""Prediction-market intelligence — informed-FLOW detection on Polymarket.

v1 scope, chosen deliberately from the spec:

* **Polymarket only.** The venues aren't symmetric: Polymarket wallets are
  public on-chain, which is what makes flow forensics possible at all;
  Kalshi publishes no trader identity, so its module would be a different,
  thinner product. Build the deep one first.
* **Record from day one.** Order flow cannot be backfilled — every scoring
  idea needs stored tape to validate against. Every build cycle appends the
  live trade feed and a market snapshot to our own DB before any analysis
  runs. A year of tape is the moat; the dashboard is not.
* **"Informed flow", never "insider tracker".** We score PUBLIC trade data
  for statistical anomalies that correlate with informed positioning. A
  flag is a probability, not a verdict, and the UI shows the receipts —
  which signals fired and their values.

Signals implemented now (from the spec's weight table, adapted to what our
own tape can support honestly):

* size tiers ($10K / $100K / $500K+) — the table stakes, weakest alone;
* order-book impact — position vs the market's 24h volume;
* niche market — real size into a thin market;
* fresh wallet — first appearance in OUR recorded tape within 24h of the
  trade. Bloomberg's review found 57% of top flagged wallets were created
  <24h before the trade; until the tape matures this proxy over-fires, and
  the caveat ships with the signal;
* multi-signal compounding — independent signals stacking outrank any one.

And the feature the spec calls the most valuable because everyone else is
weakest at it: **actionability**. Every flag answers "is this still
tradeable?" — entry price vs the market's price now — and is classified
Live / Chasing / Historical.

Free public endpoints, stdlib only:
  * Gamma API  (gamma-api.polymarket.com)  — market discovery + prices
  * Data API   (data-api.polymarket.com)   — the public trade tape
"""

from __future__ import annotations

import json
import time

from .sources.fetch import fetch_text, DataUnavailable

GAMMA = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

FEED_FLOOR_USD = 5_000
TIERS = ((500_000, "$500K+ position", 40),
         (100_000, "$100K+ position", 30),
         (10_000, "$10K+ position", 15),
         (5_000, "$5K+ position", 8))
IMPACT_MIN = 0.05             # ≥5% of the market's 24h volume
NICHE_VOL = 100_000           # a "thin" market in 24h dollar volume
FRESH_HOURS = 24
SNAP_BUCKET_S = 600           # one market snapshot per 10 minutes
LIVE_CENTS = 0.03             # price within 3c of entry = still tradeable
HISTORICAL_HOURS = 24


# --- fetch ------------------------------------------------------------------
def fetch_markets(limit: int = 100, ttl: int = 120) -> list[dict]:
    url = (f"{GAMMA}/markets?closed=false&active=true"
           f"&order=volume24hr&ascending=false&limit={limit}")
    return json.loads(fetch_text(url, "pm_markets.json", ttl=ttl))


def fetch_trades(limit: int = 500, ttl: int = 60) -> list[dict]:
    url = f"{DATA_API}/trades?limit={limit}&takerOnly=true"
    return json.loads(fetch_text(url, "pm_trades.json", ttl=ttl))


def fetch_big_trades(min_cash: int = 5000, limit: int = 300,
                     ttl: int = 120) -> list[dict]:
    """The tape FILTERED to large cash trades. The general feed is almost
    all retail-sized fills, so a 500-row slice can easily contain zero
    whales — this dedicated pull is how the flow feed never misses them."""
    url = (f"{DATA_API}/trades?limit={limit}&takerOnly=true"
           f"&filterType=CASH&filterAmount={min_cash}")
    return json.loads(fetch_text(url, "pm_big_trades.json", ttl=ttl))


LEADERBOARD = "https://lb-api.polymarket.com"
# Polymarket's leaderboard supports day / week / month / all-time only —
# there is no year window. All-time is the closest thing to long-term
# skill, so prefer it; fall through until a window answers.
LEADERBOARD_WINDOWS = (("all", "all time"), ("1m", "the past month"),
                       ("1w", "the past week"))


def fetch_leaderboard(window: str = "all", limit: int = 10,
                      ttl: int = 3600) -> list[dict]:
    """Polymarket's own P&L leaderboard (the one behind polymarket.com's
    leaderboard page). Public, keyless. Ranked by realized profit — skill
    by outcome, not by notional size."""
    url = f"{LEADERBOARD}/leaderboard?window={window}&rankType=pnl&limit={limit}"
    return json.loads(fetch_text(url, f"pm_leaderboard_{window}.json", ttl=ttl))


def fetch_wallet_trades(wallet: str, limit: int = 20, ttl: int = 900) -> list[dict]:
    url = f"{DATA_API}/trades?user={wallet}&limit={limit}"
    return json.loads(fetch_text(url, f"pm_wtrades_{wallet[:16]}.json", ttl=ttl))


PNL_API = "https://user-pnl-api.polymarket.com"


def fetch_pnl_series(wallet: str, interval: str = "1m", fidelity: str = "1d",
                     ttl: int = 3600) -> list[dict]:
    """A wallet's cumulative P&L curve — the same series Polymarket's own
    profile page charts. Public, keyless."""
    url = (f"{PNL_API}/user-pnl?user_address={wallet}"
           f"&interval={interval}&fidelity={fidelity}")
    return json.loads(fetch_text(url, f"pm_pnl_{wallet[:16]}.json", ttl=ttl))


def parse_pnl_series(raw) -> list[list[float]]:
    """Normalize to ``[[ts, pnl], ...]`` sorted by time; junk rows dropped."""
    out = []
    for r in raw or []:
        try:
            out.append([int(r["t"]), round(float(r["p"]), 2)])
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


# --- pure parsers -----------------------------------------------------------
def _jlist(v):
    """Gamma encodes list fields as JSON strings ('["Yes","No"]')."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []
    return v or []


def parse_markets(raw: list[dict]) -> list[dict]:
    """Normalize Gamma market rows to what the board and scorer need."""
    out = []
    for m in raw:
        outcomes = [str(o) for o in _jlist(m.get("outcomes"))]
        prices = []
        for p in _jlist(m.get("outcomePrices")):
            try:
                prices.append(float(p))
            except (TypeError, ValueError):
                prices.append(None)
        yes = None
        if outcomes and prices and len(outcomes) == len(prices):
            for o, p in zip(outcomes, prices):
                if o.lower() == "yes":
                    yes = p
                    break
            if yes is None:
                yes = prices[0]
        try:
            vol24 = float(m.get("volume24hr") or 0)
        except (TypeError, ValueError):
            vol24 = 0.0
        try:
            liq = float(m.get("liquidity") or 0)
        except (TypeError, ValueError):
            liq = 0.0
        slug = m.get("slug") or ""
        if not slug or yes is None:
            continue
        out.append({"slug": slug, "question": m.get("question") or slug,
                    "yes": round(yes, 4), "vol24": round(vol24, 2),
                    "liquidity": round(liq, 2),
                    "end_date": (m.get("endDate") or "")[:10]})
    return out


def parse_trades(raw: list[dict]) -> list[dict]:
    """Normalize Data-API tape rows. ``usd`` = shares × price."""
    out = []
    for t in raw:
        try:
            price = float(t.get("price") or 0)
            size = float(t.get("size") or 0)
            ts = int(t.get("timestamp") or 0)
        except (TypeError, ValueError):
            continue
        wallet = t.get("proxyWallet") or ""
        slug = t.get("slug") or ""
        if not wallet or not slug or ts <= 0 or price <= 0 or size <= 0:
            continue
        out.append({
            "venue": "polymarket",
            "tx": t.get("transactionHash") or f"{wallet}-{ts}",
            "ts": ts, "wallet": wallet, "slug": slug,
            "title": t.get("title") or slug,
            "outcome": t.get("outcome") or "",
            "side": (t.get("side") or "").upper(),
            "price": price, "size": size,
            "usd": round(price * size, 2),
            # The tape carries each trader's Polymarket display name — the
            # page shows people, not hex strings.
            "trader": t.get("name") or t.get("pseudonym") or "",
        })
    return out


def parse_leaderboard(raw: list[dict]) -> list[dict]:
    """Normalize leaderboard rows; field names vary, so probe defensively."""
    out = []
    for r in raw or []:
        wallet = r.get("proxyWallet") or r.get("wallet") or r.get("address") or ""
        if not wallet:
            continue
        try:
            pnl = float(r.get("amount") or r.get("pnl") or 0)
        except (TypeError, ValueError):
            pnl = 0.0
        out.append({"wallet": wallet,
                    "name": r.get("name") or r.get("userName")
                            or r.get("pseudonym") or "",
                    "pnl": round(pnl, 2)})
    return out


def build_top_traders(leaders: list[dict],
                      trades_by_wallet: dict[str, list[dict]],
                      pnl_by_wallet: dict[str, list] | None = None,
                      per_trader: int = 5) -> list[dict]:
    """The top-P&L wallets with their most recent trades attached — "what
    are the best traders doing right now", straight from public data.
    ``pnl_by_wallet`` optionally carries each wallet's one-month cumulative
    P&L curve for the row's equity sparkline."""
    out = []
    for rank, ld in enumerate(leaders, start=1):
        recent = sorted(trades_by_wallet.get(ld["wallet"], []),
                        key=lambda t: -t["ts"])[:per_trader]
        out.append({
            "rank": rank, "wallet": ld["wallet"], "name": ld["name"],
            "pnl": ld["pnl"],
            "pnl_series": (pnl_by_wallet or {}).get(ld["wallet"], []),
            "recent": [{"market": t["title"], "slug": t["slug"],
                        "outcome": t["outcome"], "side": t["side"],
                        "usd": t["usd"], "price": t["price"], "ts": t["ts"]}
                       for t in recent],
        })
    return out


# --- storage (record from day one) ------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS pm_trades (
    venue TEXT, tx TEXT, ts INTEGER, wallet TEXT, slug TEXT, title TEXT,
    outcome TEXT, side TEXT, price REAL, size REAL, usd REAL,
    PRIMARY KEY (venue, tx, wallet, outcome, ts)
);
CREATE TABLE IF NOT EXISTS pm_snaps (
    venue TEXT, ts INTEGER, slug TEXT, question TEXT, yes REAL,
    vol24 REAL, liquidity REAL, end_date TEXT,
    PRIMARY KEY (venue, ts, slug)
);
CREATE INDEX IF NOT EXISTS idx_pm_trades_wallet ON pm_trades (wallet, ts);
CREATE TABLE IF NOT EXISTS pm_wallets (
    wallet TEXT PRIMARY KEY, name TEXT
);
-- Every flag the feed ever showed, graded when its market resolves. The
-- report card this builds is the difference between a score that MEANS
-- something and a decorative number.
CREATE TABLE IF NOT EXISTS pm_flags (
    venue TEXT, tx TEXT, ts INTEGER, wallet TEXT, slug TEXT, market TEXT,
    outcome TEXT, side TEXT, price REAL, usd REAL, score INTEGER,
    status TEXT DEFAULT 'open',
    won INTEGER, roi REAL, resolved_ts INTEGER,
    PRIMARY KEY (venue, tx, wallet, outcome, ts)
);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)


def store_trades(conn, trades: list[dict]) -> int:
    ensure_tables(conn)
    n = 0
    for t in trades:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pm_trades (venue, tx, ts, wallet, slug, "
            "title, outcome, side, price, size, usd) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (t["venue"], t["tx"], t["ts"], t["wallet"], t["slug"], t["title"],
             t["outcome"], t["side"], t["price"], t["size"], t["usd"]))
        n += cur.rowcount
        if t.get("trader"):
            conn.execute("INSERT OR REPLACE INTO pm_wallets (wallet, name) "
                         "VALUES (?, ?)", (t["wallet"], t["trader"]))
    conn.commit()
    return n


def wallet_names(conn) -> dict[str, str]:
    """Display names harvested from the tape — people, not hex strings."""
    ensure_tables(conn)
    return {r["wallet"]: r["name"]
            for r in conn.execute("SELECT wallet, name FROM pm_wallets")}


def store_snapshot(conn, markets: list[dict], now: float | None = None) -> int:
    """One snapshot per market per 10-minute bucket — enough history for
    price-at-flag analysis without unbounded growth at a 60s refresh."""
    ensure_tables(conn)
    bucket = int((now if now is not None else time.time()) // SNAP_BUCKET_S) * SNAP_BUCKET_S
    n = 0
    for m in markets:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pm_snaps (venue, ts, slug, question, yes, "
            "vol24, liquidity, end_date) VALUES ('polymarket',?,?,?,?,?,?,?)",
            (bucket, m["slug"], m["question"], m["yes"], m["vol24"],
             m["liquidity"], m["end_date"]))
        n += cur.rowcount
    conn.commit()
    return n


def recent_tape(conn, hours: int = 24, now: float | None = None) -> list[dict]:
    """The last N hours of OUR recorded tape — what the flow feed scores.

    Scoring only the latest API pull (~500 trades) left the feed empty most
    cycles: $10K+ trades are a few per hour, and each pull is a thin slice.
    The recorded tape accumulates them across pulls, which is the point of
    recording in the first place."""
    ensure_tables(conn)
    cutoff = int((now if now is not None else time.time()) - hours * 3600)
    rows = conn.execute(
        "SELECT venue, tx, ts, wallet, slug, title, outcome, side, price, "
        "size, usd FROM pm_trades WHERE ts >= ? ORDER BY ts DESC", (cutoff,))
    return [dict(r) for r in rows]


def wallet_history(conn) -> dict[str, dict]:
    """{wallet: {"first_ts": int, "n": int, "usd": float}} from OUR tape."""
    ensure_tables(conn)
    out = {}
    for r in conn.execute(
            "SELECT wallet, MIN(ts) AS first_ts, COUNT(*) AS n, "
            "SUM(usd) AS usd FROM pm_trades GROUP BY wallet"):
        out[r["wallet"]] = {"first_ts": int(r["first_ts"]), "n": int(r["n"]),
                            "usd": float(r["usd"] or 0)}
    return out


# --- scoring (pure) ---------------------------------------------------------
def score_trade(trade: dict, market: dict | None, history: dict | None,
                now: float | None = None) -> dict | None:
    """Composite 0-100 informed-flow score with receipts, or ``None`` when
    the trade is below the feed floor. Never a verdict — a probability."""
    now = now if now is not None else time.time()
    usd = trade["usd"]
    if usd < FEED_FLOOR_USD:
        return None

    signals: list[dict] = []
    for floor, label, pts in TIERS:
        if usd >= floor:
            signals.append({"name": label, "value": f"${usd:,.0f}", "pts": pts})
            break

    vol24 = float((market or {}).get("vol24") or 0)
    if vol24 > 0:
        impact = usd / vol24
        if impact >= IMPACT_MIN:
            signals.append({"name": "Order-book impact",
                            "value": f"{impact:.0%} of 24h volume", "pts": 20})
        if vol24 < NICHE_VOL:
            signals.append({"name": "Niche market",
                            "value": f"${vol24:,.0f} 24h volume", "pts": 15})

    h = (history or {}).get(trade["wallet"])
    if h and 0 <= trade["ts"] - h["first_ts"] <= FRESH_HOURS * 3600 and h["n"] <= 5:
        signals.append({"name": "Fresh wallet",
                        "value": "first seen <24h before this trade "
                                 "(our tape only — matures as recording accrues)",
                        "pts": 25})

    score = sum(s["pts"] for s in signals)
    # Independent signals stacking is worth more than any one alone.
    if len(signals) >= 3:
        score *= 1.3
    elif len(signals) == 2:
        score *= 1.2
    score = min(100, round(score))

    # Actionability — the question every alert must answer.
    current = (market or {}).get("yes")
    entry = trade["price"]
    if current is not None and trade["outcome"].lower() == "no":
        current = round(1.0 - current, 4)
    age_h = (now - trade["ts"]) / 3600.0
    if age_h > HISTORICAL_HOURS:
        status = "Historical"
    elif current is None:
        status = "Live"
    else:
        moved = (current - entry) if trade["side"] != "SELL" else (entry - current)
        status = "Live" if moved < LIVE_CENTS else "Chasing"

    return {
        "wallet": trade["wallet"], "market": trade["title"],
        "slug": trade["slug"], "outcome": trade["outcome"],
        "tx": trade.get("tx", ""),
        "side": trade["side"], "usd": usd, "ts": trade["ts"],
        "entry_price": entry,
        "current_price": current,
        "score": score, "signals": signals, "status": status,
        "wallet_trades": (h or {}).get("n", 0),
    }


# --- flag validation: grade ourselves against resolutions -------------------
def store_flags(conn, feed: list[dict]) -> int:
    """Persist every flag the feed shows — a flag that isn't recorded can
    never be graded, and an ungraded flag is just decoration."""
    ensure_tables(conn)
    n = 0
    for f in feed:
        cur = conn.execute(
            "INSERT OR IGNORE INTO pm_flags (venue, tx, ts, wallet, slug, "
            "market, outcome, side, price, usd, score) "
            "VALUES ('polymarket',?,?,?,?,?,?,?,?,?,?)",
            (f.get("tx", ""), f["ts"], f["wallet"], f["slug"], f["market"],
             f["outcome"], f["side"], f["entry_price"], f["usd"], f["score"]))
        n += cur.rowcount
    conn.commit()
    return n


def fetch_market_by_slug(slug: str, ttl: int = 21600) -> list[dict]:
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9_-]+", "_", slug)[:60]
    return json.loads(fetch_text(f"{GAMMA}/markets?slug={slug}",
                                 f"pm_mkt_{safe}.json", ttl=ttl))


def market_resolution(market: dict | None) -> str | None:
    """The winning outcome name of a CLOSED market, or ``None``. Resolved
    Polymarket prices pin to ~1/0; anything ambiguous stays unresolved."""
    if not market or not market.get("closed"):
        return None
    outcomes = [str(o) for o in _jlist(market.get("outcomes"))]
    prices = []
    for p in _jlist(market.get("outcomePrices")):
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            return None
    if len(outcomes) != len(prices) or not outcomes:
        return None
    for o, p in zip(outcomes, prices):
        if p >= 0.95:
            return o
    return None


def resolve_flags(conn, max_slugs: int = 25, fetch=None) -> int:
    """Settle open flags whose markets have resolved. A BUY of the winning
    outcome at price p returns 1/p per dollar; a SELL is a bet on the other
    side at (1-p). Bounded slug fetches per run; results cache anyway."""
    ensure_tables(conn)
    fetch = fetch or fetch_market_by_slug
    slugs = [r["slug"] for r in conn.execute(
        "SELECT DISTINCT slug FROM pm_flags WHERE status='open' "
        "ORDER BY ts LIMIT ?", (max_slugs,))]
    settled = 0
    now = int(time.time())
    for slug in slugs:
        try:
            raw = fetch(slug)
        except DataUnavailable:
            continue
        winner = market_resolution(raw[0] if isinstance(raw, list) and raw else None)
        if winner is None:
            continue
        for f in conn.execute("SELECT rowid, * FROM pm_flags WHERE slug=? "
                              "AND status='open'", (slug,)).fetchall():
            if f["side"] == "SELL":
                won = f["outcome"] != winner
                stake_price = max(1e-6, 1.0 - f["price"])
            else:
                won = f["outcome"] == winner
                stake_price = max(1e-6, f["price"])
            roi = (1.0 / stake_price - 1.0) if won else -1.0
            conn.execute(
                "UPDATE pm_flags SET status='settled', won=?, roi=?, "
                "resolved_ts=? WHERE rowid=?",
                (1 if won else 0, round(roi, 4), now, f["rowid"]))
            settled += 1
    conn.commit()
    return settled


def flag_report(conn, min_wallet_flags: int = 3) -> dict:
    """The honest report card: hit rate vs the entry prices' implied rate,
    flat-stake ROI, a calibration z-score (above 0 = flagged flow beat its
    price; chance says ~0), split by score band — plus the wallets whose
    graded record looks least like luck."""
    import math
    ensure_tables(conn)
    rows = conn.execute("SELECT * FROM pm_flags WHERE status='settled'").fetchall()
    if not rows:
        return {"graded": 0}

    def implied(f) -> float:
        p = f["price"] if f["side"] != "SELL" else 1.0 - f["price"]
        return min(0.999, max(0.001, p))

    def agg(sub):
        n = len(sub)
        wins = sum(f["won"] for f in sub)
        exp = sum(implied(f) for f in sub)
        var = sum(implied(f) * (1 - implied(f)) for f in sub)
        return {"n": n, "wins": wins,
                "hit_rate": round(wins / n, 4),
                "avg_implied": round(exp / n, 4),
                "roi": round(sum(f["roi"] for f in sub) / n, 4),
                "z": round((wins - exp) / math.sqrt(var), 2) if var > 0 else 0.0}

    report = {"graded": len(rows), **agg(rows), "by_score": [], "wallets": []}
    for label, lo, hi in (("70+", 70, 101), ("40–69", 40, 70), ("<40", 0, 40)):
        sub = [f for f in rows if lo <= f["score"] < hi]
        if sub:
            report["by_score"].append({"band": label, **agg(sub)})
    by_wallet: dict[str, list] = {}
    for f in rows:
        by_wallet.setdefault(f["wallet"], []).append(f)
    skilled = [{"wallet": w, **agg(fs)} for w, fs in by_wallet.items()
               if len(fs) >= min_wallet_flags]
    skilled.sort(key=lambda s: -s["z"])
    report["wallets"] = skilled[:5]
    return report


def build_flow_feed(trades: list[dict], markets: list[dict],
                    history: dict, now: float | None = None,
                    limit: int = 40) -> list[dict]:
    by_slug = {m["slug"]: m for m in markets}
    feed = []
    for t in trades:
        scored = score_trade(t, by_slug.get(t["slug"]), history, now=now)
        if scored:
            feed.append(scored)
    feed.sort(key=lambda f: (-f["score"], -f["usd"]))
    return feed[:limit]
