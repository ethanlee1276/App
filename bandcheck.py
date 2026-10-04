#!/usr/bin/env python3
"""Near-even picks where we claim far more than the price: real leak, or noise?

    cd /srv/qellys && sudo -u qellys python3 bandcheck.py

Ethan's loss audit, 2026-10-04: the one board's picks priced −149 to −111
went 147-177. They claimed 62%, the price asked 56%, they hit 45%: −6.1
units, z −3.8 against the price. The −110 to +120 band went 45-60 (claimed
57%, needed 51%). Shorter favourites on the same board landed on their
claim. The reading: near even money, a big claim over the price is the
model disagreeing with the market, and the market is right.

That was found by looking, so it is not yet proof. This splits the same
picks the ways that could break it, and the rule is written here BEFORE
any run of this file:

THE BAND is a price that asks 45.4% to 59.9% (+120 to −149). THE GAP is
our claimed chance minus the price's implied chance (hold left in).

THE RULE HOLDS, for a book, only if all four are true:
  1. band picks with a gap of GAP_PTS or more hit below the price (needed)
     with z ≤ −2 pooled, on MIN_N or more;
  2. in every sport with MIN_SPORT or more such picks, they hit below
     the price — all but one sport may not disagree;
  3. in BOTH halves of the dates (earlier and later), they hit below the
     price — the leak is not one bad week;
  4. band picks with a gap under GAP_PTS do better than the big-gap ones
     (the gap is the cause, not the price band itself).

If it holds for the one board, the change proposed is: those picks go to
paper (still posted, still graded on the Record page, no stake), made by
hand in a separate commit. Read-only; it writes nothing.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "data" / "ledger.db"
BOOKS = (("The one board", ("board",)), ("Most Likely, staked", ("likely_live",)),
         ("Most Likely, paper", ("likely",)), ("Edge picks", ("main",)))
BAND = (0.454, 0.600)          # +120 (45.45%) in, +121 out; −149 in, −150 out
GAP_PTS = 0.04
MIN_N = 60
MIN_SPORT = 25
GAP_BUCKETS = ((-1.0, 0.0, "claim under the price"), (0.0, 0.04, "0-4 pts over"),
               (0.04, 0.08, "4-8 pts over"), (0.08, 1.0, "8+ pts over"))


def implied(o) -> float | None:
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (100.0 - o)


def load(conn, cats) -> list[dict]:
    q = ("SELECT sport, COALESCE(game_day, date) AS day, odds, hit_prob, status, pnl_units FROM bets "
         f"WHERE status IN ('won','lost') AND category IN ({','.join('?' * len(cats))}) "
         "AND hit_prob IS NOT NULL ORDER BY day")
    out = []
    for sp, day, odds, claim, status, pnl in conn.execute(q, cats):
        need = implied(odds)
        if need is None or not (BAND[0] <= need < BAND[1]):
            continue
        out.append({"sport": (sp or "").upper(), "day": str(day or ""), "need": need,
                    "claim": float(claim), "gap": float(claim) - need, "won": status == "won",
                    "pnl": float(pnl or 0.0)})
    return out


def score(rs: list[dict]) -> dict:
    n = len(rs)
    if not n:
        return {"n": 0}
    hit = sum(r["won"] for r in rs) / n
    need = sum(r["need"] for r in rs) / n
    claim = sum(r["claim"] for r in rs) / n
    se = math.sqrt(max(need * (1 - need), 1e-9) / n)
    return {"n": n, "w": sum(r["won"] for r in rs), "hit": hit, "need": need, "claim": claim,
            "z": (hit - need) / se, "units": sum(r["pnl"] for r in rs)}


def judge(rs: list[dict]) -> dict:
    big = [r for r in rs if r["gap"] >= GAP_PTS]
    small = [r for r in rs if r["gap"] < GAP_PTS]
    pooled, rest = score(big), score(small)
    by_sport = defaultdict(list)
    for r in big:
        by_sport[r["sport"]].append(r)
    sports = {s: score(v) for s, v in sorted(by_sport.items()) if len(v) >= MIN_SPORT}
    days = sorted({r["day"] for r in big})
    cut = days[len(days) // 2] if days else ""
    halves = {"earlier": score([r for r in big if r["day"] < cut]),
              "later": score([r for r in big if r["day"] >= cut])}
    c1 = pooled["n"] >= MIN_N and pooled["z"] <= -2.0
    c2 = sum(1 for s in sports.values() if s["hit"] >= s["need"]) <= (1 if len(sports) > 1 else 0)
    c3 = all(h["n"] and h["hit"] < h["need"] for h in halves.values())
    c4 = bool(rest["n"]) and rest["hit"] - rest["need"] > pooled.get("hit", 0) - pooled.get("need", 0)
    return {"big": pooled, "small": rest, "sports": sports, "halves": halves, "cut": cut,
            "checks": [c1, c2, c3, c4], "holds": c1 and c2 and c3 and c4}


def _line(label: str, s: dict) -> str:
    if not s.get("n"):
        return f"    {label:24} —"
    return (f"    {label:24} {s['w']:4}-{s['n'] - s['w']:<4} hit {s['hit']:.0%}  claimed {s['claim']:.0%}  "
            f"needed {s['need']:.0%}  {s['units']:+.2f}u  z {s['z']:+.1f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bandcheck.py")
    ap.add_argument("--db", default=str(LEDGER))
    a = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    print(f"NEAR-EVEN PICKS (+120 to −149): does a claim {GAP_PTS * 100:.0f}+ pts over the price lose?\n")
    for label, cats in BOOKS:
        rs = load(conn, cats)
        if not rs:
            continue
        j = judge(rs)
        print(f"{label} — {len(rs)} settled picks in the band")
        for lo, hi, name in GAP_BUCKETS:
            print(_line(name, score([r for r in rs if lo <= r["gap"] < hi])))
        print(f"  the {GAP_PTS * 100:.0f}+ pt picks, by sport ({MIN_SPORT}+ picks):")
        for s, sc in j["sports"].items():
            print(_line(s, sc))
        print(f"  by time (split at {j['cut']}):")
        for h, sc in j["halves"].items():
            print(_line(h, sc))
        names = ("pooled z ≤ −2", "every sport but one", "both halves", "small gaps do better")
        marks = ", ".join(f"{n} {'yes' if c else 'NO'}" for n, c in zip(names, j["checks"]))
        print(f"  RULE: {'HOLDS — move these to paper' if j['holds'] else 'does not hold'}  ({marks})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
