#!/usr/bin/env python3
"""EXP-003b — on our own settled picks: does a residual correction beat both our chance and the market's?

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp3_props_box.py
    sudo -u qellys python3 research/exp3_props_box.py --sport nfl
    python3 research/exp3_props_box.py --db path/to/ledger.db

Research spec Part 8, Experiment 3, its player-prop arm (Ethan, 2026-10-17).
Runs where the data is: the site's journal (data/ledger.db, opened
READ-ONLY), whose every row is a real price observed when the pick was
posted, the chance we showed for it, and how it settled. Registry EXP-003b.
Its game-totals twin, runnable anywhere, is research/exp3_totals.py.

ROWS. Settled won or lost (a push or void has no outcome to score), in the
books the site publishes (Edge main + paper, Most Likely staked and paper,
the one board), with our chance (`hit_prob`) and the market's chance for
the side we took at pick time. Rows without one are counted and left out:
the market is never rebuilt from the price we took with a vig assumed off
it, and never from the close (that is after the pick).

AMENDMENT 1 (2026-10-17, after the first box run printed NOT YET and
before any comparison was ever printed): the market's chance was the
journaled `fair_consensus` alone, which only the Edge book writes — 790 of
28,320 settled rows. It is now pricetrust.attach_market's, the same
function pricetrust.py runs on this journal: the journaled fair when there
is one, otherwise rebuilt from our own snapshots (each book's last
two-sided quote at the bet's line in the hours before the pick, never
after it or the start, de-vigged, the median of at least the site's
minimum of books). And the rows are the published books only, as
pricetrust and lossaudit read them; the prediction-market and weather
books are different products. The bar is unchanged.

THE FOUR FORECASTS of the side we took:
  A  OURS: hit_prob as shown.
  B  OURS + RESIDUAL CORRECTION: a ridge logistic on logit(A), the sport,
     the market, the side, the price's implied chance and minutes before the
     start. It does NOT see the market's fair, so it measures what our own
     pre-game information was missing.
  C  THE MARKET: fair_consensus for that side.
  D  PRESPECIFIED BLEND: a logistic on logit(A) and logit(C) alone.

HOW. Week by week in order (ISO weeks of the pick's date). A week is scored
only when at least MIN_TRAIN settled rows came before it; B and D are fitted
on those earlier rows only and scored on that week, which chose nothing.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-17). Score: log loss. Three
comparisons, each at alpha 0.05 / 3, by a week-clustered bootstrap on the
pooled held-out weeks:  B < A (the correction carries information);
B < C and D < C (anything beats the market). A market edge is claimed
only if D < C passes. NOT YET when fewer than MIN_WEEKS weeks or MIN_HELD
rows were scored. A secondary table — printed, deciding nothing — shows the
flat-stake ROI of the held-out picks D still rates above the break-even of
the price they were taken at, against all held-out picks.

Read-only; writes nothing.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: A calendar day; the NFL's journal `date` is a week label ("2026-W03"),
#: so the row's `game_day` is read first.
E3DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
MIN_TRAIN = 300
MIN_WEEKS = 6
MIN_HELD = 600
TOP_MARKETS = 12
LAM = 1.0
ALPHA = 0.05 / 3
BOOT = 1000


def implied(odds: float) -> float:
    return -odds / (-odds + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sig(x: float) -> float:
    if x < -35:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _ll(p: float, y: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def week_of(date: str) -> str:
    y, w, _d = _dt.date.fromisoformat(date[:10]).isocalendar()
    return f"{y}-W{w:02d}"


#: The books the site publishes (pricetrust.BOOKS, lossaudit's split).
PUBLISHED = ("main", "paper", "likely_live", "likely", "board")


def load(db: str, sport: str | None, snapshots=None) -> tuple[list[dict], Counter]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    want = ["id", "ts", "sport", "date", "game_day", "player", "market", "side", "line", "odds",
            "hit_prob", "status", "category"]
    want = [c for c in want if c in cols] + [c for c in ("fair_consensus", "lead_min") if c in cols]
    sql = (f"SELECT {', '.join(want)} FROM bets WHERE status IN ('won','lost') AND hit_prob IS NOT NULL "
           f"AND category IN ({','.join('?' * len(PUBLISHED))})")
    args: list = list(PUBLISHED)
    if sport:
        sql += " AND sport = ?"
        args.append(sport)
    bets = [dict(r) for r in conn.execute(sql + " ORDER BY date", args)]
    conn.close()
    sys.path.insert(0, str(ROOT))
    import pricetrust
    pricetrust.attach_market(bets, snapshots)
    skipped: Counter = Counter()
    out = []
    for r in bets:
        if r.get("market_p") is None or not (0 < float(r["market_p"]) < 1):
            skipped["no market chance at pick time"] += 1
            continue
        day = str(r.get("game_day") or r.get("date") or "")
        if not r.get("odds") or not E3DATE.match(day):
            skipped["no price or date"] += 1
            continue
        out.append({"wk": week_of(day), "sport": r["sport"], "book": r.get("category") or "", "market": r["market"] or "",
                    "side": str(r.get("side") or "").upper(), "a": float(r["hit_prob"]),
                    "c": float(r["market_p"]), "src": r.get("market_src"), "odds": float(r["odds"]),
                    "lead": float(r.get("lead_min") or 0.0), "y": 1.0 if r["status"] == "won" else 0.0})
    return out, skipped


class Logit:
    """Ridge logistic regression by Newton's method (a few dozen columns)."""

    def __init__(self, X: list, y: list, lam: float = LAM, iters: int = 25):
        n = len(X[0])
        w = [0.0] * n
        for _ in range(iters):
            g = [0.0] * n
            H = [[0.0] * n for _ in range(n)]
            for xi, yi in zip(X, y):
                p = _sig(sum(a * b for a, b in zip(w, xi)))
                d = p * (1 - p)
                for i in range(n):
                    g[i] += (p - yi) * xi[i]
                    for j in range(i, n):
                        H[i][j] += d * xi[i] * xi[j]
            for i in range(n):
                for j in range(i):
                    H[i][j] = H[j][i]
                if i:
                    g[i] += lam * w[i]
                    H[i][i] += lam
            step = _solve(H, g)
            w = [a - b for a, b in zip(w, step)]
            if max(abs(s) for s in step) < 1e-6:
                break
        self.w = w

    def p(self, x: list) -> float:
        return _sig(sum(a * b for a, b in zip(self.w, x)))


def _solve(A: list, b: list) -> list:
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


def features(x: dict, markets: list, sports: list) -> list:
    """B's columns: everything known before the game except the market's fair."""
    return ([1.0, _logit(x["a"]), _logit(implied(x["odds"])), min(x["lead"], 2880.0) / 1440.0,
             1.0 if x["side"] == "UNDER" else 0.0]
            + [1.0 if x["sport"] == s else 0.0 for s in sports[1:]]
            + [1.0 if x["market"] == m else 0.0 for m in markets])


def walk(rows: list[dict]) -> list[dict]:
    weeks = sorted({x["wk"] for x in rows})
    scored = []
    for wk in weeks:
        before = [x for x in rows if x["wk"] < wk]
        now = [x for x in rows if x["wk"] == wk]
        if len(before) < MIN_TRAIN or not now:
            continue
        markets = [m for m, _n in Counter(x["market"] for x in before).most_common(TOP_MARKETS)]
        sports = sorted({x["sport"] for x in before})
        b = Logit([features(x, markets, sports) for x in before], [x["y"] for x in before])
        d = Logit([[1.0, _logit(x["a"]), _logit(x["c"])] for x in before], [x["y"] for x in before])
        for x in now:
            pb = b.p(features(x, markets, sports))
            pd = d.p([1.0, _logit(x["a"]), _logit(x["c"])])
            scored.append(dict(x, b=pb, d=pd))
    return scored


def compare(scored: list[dict], k1: str, k2: str, seed: int = 5) -> tuple:
    by = defaultdict(list)
    for x in scored:
        by[x["wk"]].append(_ll(x[k1], x["y"]) - _ll(x[k2], x["y"]))
    groups = [(sum(v), len(v)) for v in by.values()]
    n = sum(c for _s, c in groups)
    mean = sum(s for s, _c in groups) / n
    rng = random.Random(seed)
    stats = []
    for _ in range(BOOT):
        tot = cnt = 0.0
        for _ in range(len(groups)):
            s, c = groups[rng.randrange(len(groups))]
            tot += s
            cnt += c
        stats.append(tot / cnt)
    stats.sort()
    return mean, stats[int(BOOT * ALPHA / 2)], stats[min(BOOT - 1, int(BOOT * (1 - ALPHA / 2)))]


def roi(rows: list[dict]) -> tuple:
    if not rows:
        return 0, 0.0
    pnl = 0.0
    for x in rows:
        o = x["odds"]
        win = (o / 100.0) if o > 0 else (100.0 / -o)
        pnl += win if x["y"] else -1.0
    return len(rows), pnl / len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "ledger.db"))
    ap.add_argument("--sport")
    a = ap.parse_args(argv)
    rows, skipped = load(a.db, a.sport)
    print(f"EXP-003b — our settled picks against the market at pick time ({a.sport or 'every sport'})")
    src = Counter(x["src"] for x in rows)
    print(f"  usable rows {len(rows):,} (market chance: " + ", ".join(f"{k} {v:,}" for k, v in src.items()) + ")"
          + "".join(f"; left out ({k}) {v:,}" for k, v in skipped.items()))
    scored = walk(rows)
    weeks = len({x["wk"] for x in scored})
    print(f"  held-out weeks {weeks}, held-out rows {len(scored):,}")
    if weeks < MIN_WEEKS or len(scored) < MIN_HELD:
        print(f"  NOT YET: needs {MIN_WEEKS} weeks and {MIN_HELD} rows scored")
        return 0
    lls = {k: sum(_ll(x[k], x["y"]) for x in scored) / len(scored) for k in ("a", "b", "c", "d")}
    print("  log loss  ours (A) {a:.5f}  corrected (B) {b:.5f}  market (C) {c:.5f}  blend (D) {d:.5f}".format(**lls))
    print(f"  mean chance  ours {sum(x['a'] for x in scored) / len(scored):.3f}  market "
          f"{sum(x['c'] for x in scored) / len(scored):.3f}  hit {sum(x['y'] for x in scored) / len(scored):.3f}")
    verdicts = {}
    for k1, k2, name in (("b", "a", "B beats A (the correction)"), ("b", "c", "B beats C (the market)"),
                         ("d", "c", "D beats C (the market)")):
        mean, lo, hi = compare(scored, k1, k2)
        verdicts[name] = "PASSES" if hi < 0 else ("INCONCLUSIVE" if mean < 0 else "FAILS")
        print(f"  {name:<28} {mean:+.5f} [{lo:+.5f}, {hi:+.5f}]  {verdicts[name]}")
    print("\n  market edge claimed: " + ("YES — D beats the market held out" if verdicts["D beats C (the market)"] == "PASSES"
                                       else "NO"))
    kept = [x for x in scored if x["d"] > implied(x["odds"])]
    n_all, r_all = roi(scored)
    n_k, r_k = roi(kept)
    print(f"\n  secondary, decides nothing: flat 1u ROI, all held-out picks {r_all:+.3f} (n={n_all:,}); "
          f"those D still rates above the price's break-even {r_k:+.3f} (n={n_k:,})")
    print("\n  where, described (decides nothing): held-out picks by sport and book")
    print(f"    {'sport':<6} {'book':<12} {'n':>6}  {'ours':>5} {'market':>6} {'hit':>5}  {'LL ours':>8} {'LL mkt':>7}")
    by = defaultdict(list)
    for x in scored:
        by[(x["sport"], x["book"])].append(x)
    for (sp, bk), t in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(t) < 30:
            continue
        n = len(t)
        print(f"    {sp:<6} {bk:<12} {n:>6,}  {sum(x['a'] for x in t) / n:>5.3f} {sum(x['c'] for x in t) / n:>6.3f} "
              f"{sum(x['y'] for x in t) / n:>5.3f}  {sum(_ll(x['a'], x['y']) for x in t) / n:>8.4f} "
              f"{sum(_ll(x['c'], x['y']) for x in t) / n:>7.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
