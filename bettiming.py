#!/usr/bin/env python3
"""When should a pick be bet: as soon as it posts, or nearer kickoff?

    cd /srv/qellys && sudo -u qellys python3 bettiming.py
    sudo -u qellys python3 bettiming.py --sport nfl
    sudo -u qellys python3 bettiming.py --since 2026-09-01

Ethan, 2026-10-04: "do all of it" — first of the list: every Most Likely
pick journals the price we posted it at and, once settled, the closing
price for the same side. If the price usually gets WORSE before kickoff,
the site should say "bet it now" and push picks early; if it usually gets
BETTER, the honest advice is to wait. This reads the answer out of the
journal. Read-only; it writes nothing.

WHAT A ROW IS. One book (the published ones, each on its own) and one
sport, split by how long before the game day the pick was first posted
(same day, the day before, two or more days before — the journal stamps
when it posted, in UTC, and the game's calendar day; kickoff times are not
journaled, so this is days, not hours). For each:

  moved our way   how often the closing price was shorter than ours (the
                  market came to us — we beat it by betting early)
  moved against   how often it drifted longer (waiting would have paid)
  avg CLV         the average move in implied-probability points, positive
                  = toward us (engine/ledger._bet_price_clv)
  ROI posted      flat 1-unit ROI at the price we posted
  ROI at close    flat 1-unit ROI had the same picks been taken at the close

THE VERDICT, WRITTEN BEFORE ANY RUN. Per sport and book, on rows with a
close: "bet when posted" if avg CLV ≥ +VERDICT_PTS and its standard error
puts it at least two from zero on MIN_N picks or more; "waiting pays" for
the mirror; otherwise "no difference yet". It moves nothing on the site;
a verdict that holds is a change to how the alerts and the cards word it,
made by hand.

THE CLOSE, CORRECTED 2026-10-04 (after the first run on the box). The
journal's `closing_odds` is ONE book's last quote — whichever the harvest
wrote last (engine/db.closing_odds_by_date says so) — while the price we
post is the BEST on the screen. Best-of-six against an arbitrary one reads
as the price "moving toward us" when nothing moved at all. So the verdict
is now read off the SAME BOOK's close (the book we posted at, from the
harvested odds history, pre-game rows only, same line and side), with the
best close across every book beside it as the strict version. The
journal-close numbers still print, marked as the biased reading.

A second table repeats the loss audit's sharpest finding on this data:
picks whose price moved AGAINST them by MOVE_PTS or more, their hit rate
against their claim. A large gap there is news the market had and we did
not, which says "post later, after news", not "bet earlier".
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

BOOKS = {"likely_live": "Most Likely, staked", "likely": "Most Likely, paper",
         "board": "The one board", "main": "Edge picks"}
VERDICT_PTS = 0.5
MIN_N = 100
MOVE_PTS = 0.02
ET_OFFSET_H = -4          # the journal stamps UTC; game days are Eastern
COLS = ("sport", "category", "ts", "game_day", "odds", "closing_odds", "status", "hit_prob",
        "player", "market", "side", "line", "book", "date", "lead_min")


def implied(o) -> float | None:
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (100.0 - o)


def profit(odds, status: str) -> float | None:
    """Flat one-unit result at an American price."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if status == "push":
        return 0.0
    if status == "lost":
        return -1.0
    if status != "won" or not o:
        return None
    return o / 100.0 if o > 0 else 100.0 / -o


def days_ahead(ts: str, game_day: str) -> int | None:
    """Whole days between when the pick posted (Eastern) and its game day."""
    try:
        posted = _dt.datetime.fromisoformat(str(ts)[:19]) + _dt.timedelta(hours=ET_OFFSET_H)
        game = _dt.date.fromisoformat(str(game_day)[:10])
    except (TypeError, ValueError):
        return None
    return (game - posted.date()).days


def bucket(d: int | None) -> str:
    if d is None:
        return "unknown"
    return "same day" if d <= 0 else "day before" if d == 1 else "2+ days"


def _bookkey(b) -> str:
    return re.sub(r"[^a-z0-9]", "", str(b or "").lower())


class BookCloses:
    """Closing quotes per book from the harvested odds history, read once
    per (sport, market), for the same-book and best-book CLV."""

    def __init__(self, hist):
        self.hist = hist
        self._cache: dict = {}

    def quotes(self, b: dict) -> list:
        if not b.get("player") or not b.get("market"):
            return []
        from engine import db, ledger
        from engine.sources.oddsapi import normalize_name
        ck = (b["sport"], b["market"])
        if ck not in self._cache:
            try:
                self._cache[ck] = db.closing_odds_all_books(self.hist, *ck)
            except sqlite3.Error:
                self._cache[ck] = {}
        try:
            dates = ledger.close_dates(self.hist, b)
        except Exception:                                   # noqa: BLE001
            dates = [str(b.get("game_day") or b.get("date") or "")[:10]]
        got = ledger.close_at(self._cache[ck], normalize_name(b["player"] or ""), dates) or []
        out = []
        for q in got:
            if ledger._pregame_close(q, b) is None:
                continue
            price = ledger._close_odds_from(q, b["line"], b["side"])
            if price is not None:
                out.append((_bookkey(q.get("book")), price))
        return out

    def same_and_best(self, b: dict):
        qs = self.quotes(b)
        if not qs:
            return None, None
        mine = _bookkey(b.get("book"))
        same = next((p for k, p in qs if k and k == mine), None)
        best = min((p for _k, p in qs), key=lambda p: implied(p))   # longest price = least implied
        return same, best


def rows(conn, sport: str | None = None, since: str | None = None, closes: BookCloses | None = None) -> list[dict]:
    have = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    sel = ", ".join(c if c in have else f"NULL AS {c}" for c in COLS)
    q = (f"SELECT {sel} FROM bets "
         "WHERE status IN ('won','lost','push') AND category IN (%s)" % ",".join("?" * len(BOOKS)))
    args: list = list(BOOKS)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    if since:
        q += " AND COALESCE(game_day, substr(ts,1,10)) >= ?"
        args.append(since)
    conn.row_factory = sqlite3.Row
    out = []
    for r in conn.execute(q, args):
        took, close = implied(r["odds"]), implied(r["closing_odds"])
        same = best = None
        if closes is not None:
            same, best = closes.same_and_best({**dict(r), "category": r["category"]})
        out.append({"sport": r["sport"], "book": r["category"], "when": bucket(days_ahead(r["ts"], r["game_day"])),
                    "status": r["status"], "claim": r["hit_prob"], "odds": r["odds"], "close": r["closing_odds"],
                    "clv_journal": None if took is None or close is None else close - took,
                    "clv": None if took is None or same is None else implied(same) - took,
                    "clv_best": None if took is None or best is None else implied(best) - took,
                    "pnl": profit(r["odds"], r["status"]),
                    "pnl_close": profit(same, r["status"]) if same else None})
    return out


def summarize(rs: list[dict]) -> dict:
    with_close = [r for r in rs if r["clv"] is not None]
    clvs = [r["clv"] for r in with_close]
    n = len(clvs)
    jn = [r["clv_journal"] for r in rs if r.get("clv_journal") is not None]
    bs = [r["clv_best"] for r in rs if r.get("clv_best") is not None]
    mean = sum(clvs) / n if n else None
    se = (math.sqrt(sum((c - mean) ** 2 for c in clvs) / (n - 1)) / math.sqrt(n)) if n > 1 else None
    posted = [r["pnl"] for r in with_close if r["pnl"] is not None]
    closed = [r["pnl_close"] for r in with_close if r["pnl_close"] is not None]
    return {"n": len(rs), "with_close": n,
            "our_way": sum(1 for c in clvs if c > 0) / n if n else None,
            "against": sum(1 for c in clvs if c < 0) / n if n else None,
            "avg_clv": mean, "se": se,
            "roi_posted": sum(posted) / len(posted) if posted else None,
            "roi_close": sum(closed) / len(closed) if closed else None,
            "journal_n": len(jn), "journal_clv": sum(jn) / len(jn) if jn else None,
            "best_n": len(bs), "best_clv": sum(bs) / len(bs) if bs else None}


def verdict(s: dict) -> str:
    m, se, n = s["avg_clv"], s["se"], s["with_close"]
    if m is None or se is None or n < MIN_N:
        return f"not enough same-book closes yet ({n} of {MIN_N})"
    pts = m * 100
    if pts >= VERDICT_PTS and m >= 2 * se:
        return f"BET WHEN POSTED — the price moves toward us {pts:+.1f} pts on average"
    if pts <= -VERDICT_PTS and -m >= 2 * se:
        return f"WAITING PAYS — the price drifts away {pts:+.1f} pts on average"
    return f"no difference yet ({pts:+.1f} pts, ±{2 * se * 100:.1f})"


def moved_against(rs: list[dict]) -> dict:
    """Hit rate vs claim for picks the market moved against by MOVE_PTS+."""
    bad = [r for r in rs if r["clv"] is not None and r["clv"] <= -MOVE_PTS
           and r["status"] in ("won", "lost") and r["claim"] is not None]
    rest = [r for r in rs if r["clv"] is not None and r["clv"] > -MOVE_PTS
            and r["status"] in ("won", "lost") and r["claim"] is not None]

    def rate(xs):
        if not xs:
            return None, None
        return (sum(1 for r in xs if r["status"] == "won") / len(xs),
                sum(float(r["claim"]) for r in xs) / len(xs))
    return {"against": (len(bad), *rate(bad)), "rest": (len(rest), *rate(rest))}


def pct(v) -> str:
    return "—" if v is None else f"{v:.0%}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bettiming.py")
    ap.add_argument("--sport")
    ap.add_argument("--since")
    ap.add_argument("--db", default=str(ROOT / "data" / "ledger.db"))
    ap.add_argument("--hist", default=str(ROOT / "data" / "history.db"), help="the odds history (same-book closes)")
    a = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    try:
        hist = sqlite3.connect(f"file:{a.hist}?mode=ro", uri=True)
        hist.row_factory = sqlite3.Row
        hist.execute("SELECT 1 FROM odds_history LIMIT 1")
        closes = BookCloses(hist)
    except sqlite3.Error as exc:
        print(f"(no odds history at {a.hist}: {exc}; same-book closes unavailable)")
        closes = None
    rs = rows(conn, a.sport, a.since, closes)
    by = defaultdict(list)
    for r in rs:
        by[(r["sport"], r["book"])].append(r)
    print("WHEN TO BET — posted price vs the SAME BOOK's closing price, settled picks\n")
    for (sport, book), group in sorted(by.items()):
        s = summarize(group)
        if not s["with_close"] and not s["journal_n"]:
            continue
        print(f"{sport.upper()} · {BOOKS.get(book, book)} — {s['with_close']} of {s['n']} with a same-book close")
        print(f"  verdict: {verdict(s)}")
        pts = lambda v: "—" if v is None else f"{v * 100:+.1f}"
        print(f"  best close across books: {pts(s['best_clv'])} pts on {s['best_n']}   "
              f"(journal close, one arbitrary book — biased: {pts(s['journal_clv'])} pts on {s['journal_n']})")
        for when in ("2+ days", "day before", "same day", "unknown"):
            sub = [r for r in group if r["when"] == when]
            t = summarize(sub)
            if not t["with_close"]:
                continue
            clv = "—" if t["avg_clv"] is None else f"{t['avg_clv'] * 100:+.1f}"
            print(f"    {when:10}  n {t['with_close']:4}  our way {pct(t['our_way'])}  against {pct(t['against'])}  "
                  f"avg CLV {clv} pts  ROI posted {pct(t['roi_posted'])}  at close {pct(t['roi_close'])}")
        ma = moved_against(group)
        (nb, hb, cb), (nr, hr, cr) = ma["against"], ma["rest"]
        if nb:
            print(f"  moved against us {MOVE_PTS * 100:.0f}+ pts: {nb} picks hit {pct(hb)} (claimed {pct(cb)}); "
                  f"the rest {nr} hit {pct(hr)} (claimed {pct(cr)})")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
