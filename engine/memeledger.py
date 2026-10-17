"""Did the coins we put on the board actually go up?

Ethan, 2026-08-19: "track which meme coins we recommend and if they
actually gain value or lose value after we recommend them … make it real
and accurate."

Rocket Radar has been publishing a ranked board with no memory. This
gives it one, on the same terms the sports side has had since the
beginning: **the call is recorded at the price we saw, before the outcome
is known, and it is never deleted.** A record that only remembers its
winners is not a record.

FOUR DECISIONS DO THE WORK HERE, and each of them is the difference
between a number that means something and a number that flatters.

1. A CALL IS ONE COIN, ONE CHANNEL, ONE DAY. A coin sits on the board for
   hours and the loop rebuilds every few minutes, so the naive thing —
   one row per appearance — would file the same idea three hundred times
   and let a single lucky coin outvote a hundred bad ones. `UNIQUE (mint,
   channel, day)` makes the unit the IDEA, not the impression.

2. THE PATH, NOT JUST THE ENDPOINT. A coin that went 5x and round-tripped
   to zero and a coin that never moved both close at 0%, and they are not
   the same event. Every call carries its peak and its trough since the
   call, so the record can say "the median call peaked +34% and closed
   -12%" — which is the actual shape of this market and is invisible in
   a table of closing returns.

3. A COIN THAT VANISHES IS AN OUTCOME, NOT A GAP. Mints leave the feed
   because liquidity died. Dropping them would quietly delete the losses
   and leave a board of survivors — the single easiest way to build a
   fake track record in this asset class. A call whose coin stops
   appearing is marked `gone` and keeps its last mark.

4. THE HEADLINE IS THE MEDIAN. One 50x makes any mean meaningless, and a
   mean is what a promoter would quote. Median return, hit rate, and the
   worst case get equal billing.

This module is a LEDGER. It records, it grades, it reports. It does not
score, rank or recommend — that is engine/memecoins.py — and nothing here
ever writes back into what the board shows.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path("data/memeledger.db")

#: When we look back. Meme coins resolve in minutes, so the early marks
#: are close together; 7d is there for the rare coin that survives a week
#: and would otherwise leave the record saying nothing about it.
HORIZONS = (("1h", 3600), ("6h", 6 * 3600),
            ("24h", 24 * 3600), ("7d", 7 * 24 * 3600))

#: A call stops being marked once its last horizon has matured and a
#: grace period has passed. Nothing is deleted; it simply stops costing
#: work on every build.
SETTLE_AFTER_S = 8 * 24 * 3600

#: THE PATH SUMMARY AND THE HORIZON TABLE MUST DESCRIBE THE SAME CALLS.
#: The horizon rows only contain calls old enough to have matured; the
#: path was summarising every call including ones filed four minutes ago,
#: whose peak-since-call is necessarily near zero. Side by side that read
#: as a contradiction — "median call peaked +3%" printed directly above a
#: 24h median in the thousands — when it was two different populations.
#: A call has to have had at least the first horizon to appear in either.
PATH_MIN_AGE_S = HORIZONS[0][1]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meme_calls (
  id        INTEGER PRIMARY KEY,
  ts        REAL NOT NULL,
  day       TEXT NOT NULL,
  mint      TEXT NOT NULL,
  symbol    TEXT,
  name      TEXT,
  channel   TEXT NOT NULL,
  rank      INTEGER,
  price     REAL NOT NULL,
  mc        REAL,
  liq       REAL,
  momentum  INTEGER,
  risk      INTEGER,
  UNIQUE (mint, channel, day)
);
CREATE TABLE IF NOT EXISTS meme_marks (
  call_id   INTEGER NOT NULL,
  horizon   TEXT NOT NULL,
  ts        REAL NOT NULL,
  price     REAL NOT NULL,
  pct       REAL NOT NULL,
  UNIQUE (call_id, horizon)
);
CREATE TABLE IF NOT EXISTS meme_path (
  call_id    INTEGER PRIMARY KEY,
  last_ts    REAL,
  last_price REAL,
  peak       REAL,
  peak_ts    REAL,
  trough     REAL,
  trough_ts  REAL,
  seen       INTEGER DEFAULT 0,
  gone_ts    REAL
);
CREATE INDEX IF NOT EXISTS meme_calls_ts ON meme_calls (ts);
"""


def connect(path=None) -> sqlite3.Connection:
    path = Path(path if path is not None else DEFAULT_DB)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    # The busiest writer on the box: memes_build rewrites this every 20
    # seconds while the Record page reads it. WAL + a busy timeout, from
    # engine/db.tune() — see the note there.
    from .db import tune as _db_tune
    _db_tune(conn)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _day(ts: float) -> str:
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def _price(row: dict):
    try:
        p = float(row.get("price_usd") or 0)
    except (TypeError, ValueError):
        return None
    return p if p > 0 else None


# --- recording ---------------------------------------------------------------
def log_calls(conn, board: dict, now: float | None = None) -> int:
    """File today's board as calls. Returns how many were NEW.

    Both channels are recorded. The exit channel is a call too — "this one
    is falling apart" is a claim that can be right or wrong, and a desk
    that only grades its buys is grading half its opinions.

    A coin with no usable price is skipped rather than filed at zero: a
    call we cannot mark later is not a call, and a zero would divide into
    every return that followed it.
    """
    now = time.time() if now is None else now
    day = _day(now)
    by_mint = {c.get("mint"): c for c in (board.get("coins") or [])}
    n = 0
    for channel in ("rocket", "exit"):
        mints = board.get("rocket" if channel == "rocket" else "exits") or []
        for rank, mint in enumerate(mints, 1):
            row = by_mint.get(mint)
            price = _price(row or {})
            if not row or price is None:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO meme_calls (ts, day, mint, symbol, "
                "name, channel, rank, price, mc, liq, momentum, risk) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (now, day, mint, row.get("symbol", ""), row.get("name", ""),
                 channel, rank, price, row.get("market_cap"),
                 row.get("liquidity"), row.get("momentum"), row.get("risk")))
            if cur.rowcount:
                conn.execute(
                    "INSERT OR IGNORE INTO meme_path (call_id, last_ts, "
                    "last_price, peak, peak_ts, trough, trough_ts, seen) "
                    "VALUES (?,?,?,?,?,?,?,0)",
                    (cur.lastrowid, now, price, price, now, price, now))
                n += 1
    conn.commit()
    return n


def _open_calls(conn, now: float):
    return conn.execute(
        "SELECT c.*, p.peak, p.trough, p.gone_ts FROM meme_calls c "
        "JOIN meme_path p ON p.call_id = c.id "
        "WHERE c.ts > ? ORDER BY c.ts", (now - SETTLE_AFTER_S,)).fetchall()


def mark(conn, board: dict, now: float | None = None) -> dict:
    """Update every open call against the prices on this build.

    Two things happen per call. The PATH is updated — last price, and the
    peak and trough since the call, which is what lets the record describe
    the shape of a move rather than only its end. And any HORIZON that has
    matured since the last build is stamped once, permanently.

    A call whose mint is not in this build is marked `gone` and left
    alone. That is not a missing data point; for a memecoin it is usually
    the answer.
    """
    now = time.time() if now is None else now
    by_mint = {c.get("mint"): c for c in (board.get("coins") or [])}
    out = {"marked": 0, "stamped": 0, "gone": 0}
    for c in _open_calls(conn, now):
        row = by_mint.get(c["mint"])
        price = _price(row or {})
        if price is None:
            if c["gone_ts"] is None:
                conn.execute("UPDATE meme_path SET gone_ts=? WHERE call_id=?",
                             (now, c["id"]))
                out["gone"] += 1
            continue
        peak = max(c["peak"] or price, price)
        trough = min(c["trough"] or price, price)
        conn.execute(
            "UPDATE meme_path SET last_ts=?, last_price=?, peak=?, "
            "peak_ts=CASE WHEN ?>peak THEN ? ELSE peak_ts END, trough=?, "
            "trough_ts=CASE WHEN ?<trough THEN ? ELSE trough_ts END, "
            "seen=seen+1, gone_ts=NULL WHERE call_id=?",
            (now, price, peak, price, now, trough, price, now, c["id"]))
        out["marked"] += 1
        age = now - c["ts"]
        for name, secs in HORIZONS:
            if age < secs:
                break
            cur = conn.execute(
                "INSERT OR IGNORE INTO meme_marks (call_id, horizon, ts, "
                "price, pct) VALUES (?,?,?,?,?)",
                (c["id"], name, now, price, (price / c["price"]) - 1.0))
            out["stamped"] += cur.rowcount
    conn.commit()
    return out


# --- reporting ---------------------------------------------------------------
def _median(xs: list[float]):
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


#: RETURN BUCKETS, log-ish on purpose. A meme call's outcome spans -100%
#: to +1000% and a linear histogram spends seven of its eight bars on the
#: interval between "lost everything" and "lost most of it", which is the
#: one stretch nobody needs resolution in. These edges put the detail
#: where the decisions are: did it double, did it rug, did it do nothing.
#: Lower bound inclusive, upper exclusive; the last bucket is open.
DIST_EDGES = (-0.80, -0.50, -0.20, 0.0, 0.50, 2.00, 10.0)
DIST_LABELS = ("≤ -80%", "-80 to -50%", "-50 to -20%", "-20 to 0%",
               "0 to +50%", "+50 to +200%", "+200 to +1000%", "> +1000%")


def distribution(values) -> list[dict]:
    """How the calls actually landed, as counts — not a mean, not a range.

    Ethan, 2026-08-20: "of our last 40 calls, the median peaked +31% and
    ended -83%; here's the distribution." The medians are the headline and
    the shape is the finding: a book whose median is -83% because
    everything lost a bit is a different product from one whose median is
    -83% because four calls in forty went up ten times and the rest went
    to zero. Only the histogram tells those apart.
    """
    out = [{"label": lab, "n": 0} for lab in DIST_LABELS]
    for v in values:
        if v is None:
            continue
        i = 0
        while i < len(DIST_EDGES) and v >= DIST_EDGES[i]:
            i += 1
        out[i]["n"] += 1
    return out


def _summarise(rows: list[sqlite3.Row]) -> dict:
    """One channel at one horizon. Median leads; the mean is not shown.

    A mean return over memecoins is a number about the single luckiest
    row. Median, hit rate and the worst case describe what actually
    happened to a reader who took the calls.
    """
    pcts = [r["pct"] for r in rows]
    return {
        "n": len(pcts),
        "median": _median(pcts),
        "hit_rate": (sum(1 for p in pcts if p > 0) / len(pcts)) if pcts else None,
        "best": max(pcts) if pcts else None,
        "worst": min(pcts) if pcts else None,
        "down_80": sum(1 for p in pcts if p <= -0.8),
    }


def report(conn, now: float | None = None) -> dict:
    """The record, per channel per horizon, plus the path summary."""
    now = time.time() if now is None else now
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "horizons": [h for h, _ in HORIZONS], "channels": {}}
    total = conn.execute("SELECT COUNT(*) FROM meme_calls").fetchone()[0]
    out["calls_total"] = total
    for channel in ("rocket", "exit"):
        ch: dict = {"marks": {}}
        ch["calls"] = conn.execute(
            "SELECT COUNT(*) FROM meme_calls WHERE channel=?",
            (channel,)).fetchone()[0]
        for name, _ in HORIZONS:
            rows = conn.execute(
                "SELECT m.pct FROM meme_marks m JOIN meme_calls c "
                "ON c.id=m.call_id WHERE c.channel=? AND m.horizon=?",
                (channel, name)).fetchall()
            ch["marks"][name] = _summarise(rows)
        # The shape of the move, over EVERY call — including the ones
        # whose coin vanished before we could mark it even once.
        #
        # The first version filtered on `p.seen > 0`, and that one clause
        # was survivorship bias in the module written to prevent it: a
        # coin that disappeared an hour after the call left no mark, so it
        # left the summary, so "gone" read 0 while a third of the calls
        # had gone to nothing. The coins that vanish fastest are the worst
        # ones, and they are the first thing an honest record must keep.
        path = conn.execute(
            "SELECT (p.peak / c.price) - 1.0 AS up, "
            "       (p.trough / c.price) - 1.0 AS down, "
            "       (p.last_price / c.price) - 1.0 AS last, "
            "       p.seen AS seen, p.gone_ts IS NOT NULL AS gone "
            "FROM meme_path p JOIN meme_calls c ON c.id=p.call_id "
            "WHERE c.channel=? AND c.ts <= ?",
            (channel, now - PATH_MIN_AGE_S)).fetchall()
        # The medians describe the calls we could actually follow. The
        # `gone` count sits beside them rather than being folded in as
        # -100%: a dead pool is unsellable, which is not quite the same
        # claim as worthless, and quietly imputing a number is how a
        # record starts arguing for itself.
        seen = [r for r in path if r["seen"] > 0]
        ch["path"] = {
            "n": len(path),
            "followed": len(seen),
            "median_peak": _median([r["up"] for r in seen]),
            "median_trough": _median([r["down"] for r in seen]),
            "median_last": _median([r["last"] for r in seen]),
            "gone": sum(1 for r in path if r["gone"]),
            "never_marked": sum(1 for r in path if r["seen"] == 0),
            # The shape behind the medians. Two of them, because the whole
            # point of keeping the path is that a call's best moment and
            # its last moment are different facts.
            "dist_peak": distribution([r["up"] for r in seen]),
            "dist_last": distribution([r["last"] for r in seen]),
        }
        out["channels"][channel] = ch
    return out


def recent(conn, limit: int = 40, now: float | None = None) -> list[dict]:
    """The last calls, each with what happened to it. The receipts."""
    now = time.time() if now is None else now
    rows = conn.execute(
        "SELECT c.*, p.last_price, p.peak, p.trough, p.gone_ts, p.seen "
        "FROM meme_calls c JOIN meme_path p ON p.call_id=c.id "
        "ORDER BY c.ts DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        marks = {m["horizon"]: m["pct"] for m in conn.execute(
            "SELECT horizon, pct FROM meme_marks WHERE call_id=?", (r["id"],))}
        base = r["price"] or 0
        out.append({
            "ts": r["ts"], "mint": r["mint"], "symbol": r["symbol"],
            "name": r["name"], "channel": r["channel"], "rank": r["rank"],
            "price": r["price"], "momentum": r["momentum"], "risk": r["risk"],
            "marks": marks,
            "peak": (r["peak"] / base - 1.0) if base and r["peak"] else None,
            "trough": (r["trough"] / base - 1.0) if base and r["trough"] else None,
            "last": (r["last_price"] / base - 1.0) if base and r["last_price"] else None,
            "gone": r["gone_ts"] is not None,
            "seen": r["seen"],
        })
    return out


def export_json(conn, path, now: float | None = None) -> str:
    doc = report(conn, now)
    doc["recent"] = recent(conn, 40, now)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1)
    tmp.replace(p)
    return str(p)
