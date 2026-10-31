#!/usr/bin/env python3
"""Which bets and which stakes make money — the study behind engine/stakeplan.

    python3 tools/stake_study.py                      # reads the live receipts
    python3 tools/stake_study.py --csv receipts.csv   # or a saved copy

Ethan, 2026-10-31: "I feel like we're winning a lot of bets, but not winning
money ... find what bets and what unit bets ... works best for our ROI to be
positive and our units to be positive." This reruns every number in
docs/STAKES.md from the public receipts (/api/record/receipts.csv: every
graded pick the journal holds, with its book, price, our chance, stake and
result). Read-only; writes nothing.

WHAT IT MEASURES, on the headline record (the books ledger.POOLED_BOOKS
names, each pick once, from the record's epoch, benched leagues out):

  1. each half — Edge and Most Likely — as placed and at flat stakes;
  2. whether our own claimed edge over the price predicts the result (if it
     did, staking on it would pay);
  3. a set of stake rules WALKED FORWARD one day at a time — each day's
     rule read only from the days before it — through 2026-10-15 and after
     it, so a rule that only fits the past shows up as one;
  4. the v4 rule engine/stakeplan runs, on the same walk.

Standard library only.
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import math
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import stakeplan as SP                               # noqa: E402

URL = "https://qellysbook.com/api/record/receipts.csv"
EPOCH = "2026-08-06"
SPLIT = "2026-10-15"
POOLED = ("main", "paper", "likely_live", "likely", "board")
BENCHED = ("wnba",)


def load(path: str | None = None) -> list:
    """Every graded row of the receipts, typed."""
    if path:
        text = open(path, encoding="utf-8").read()
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:      # noqa: S310
            text = r.read().decode("utf-8")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("status") not in ("won", "lost", "push"):
            continue
        try:
            r["odds"] = int(float(r["odds"]))
        except (TypeError, ValueError):
            continue
        if abs(r["odds"]) < 100:
            continue
        r["hit_prob"] = float(r["hit_prob"]) if r.get("hit_prob") not in ("", None) else None
        r["stake_units"] = float(r.get("stake_units") or 0)
        r["pnl_units"] = float(r.get("pnl_units") or 0)
        r["day"] = r["date"]
        out.append(r)
    return out


def headline(rows: list) -> list:
    """The headline record's rows: POOLED books, staked, each pick once."""
    twins = {(r["sport"], r["date"], r["player"], r["market"], (r["side"] or "").upper())
             for r in rows if r["category"] in ("likely", "likely_live") and r["stake_units"] > 0}
    out = []
    for r in rows:
        if r["category"] not in POOLED or r["stake_units"] <= 0:
            continue
        if r["sport"].lower() in BENCHED or ("-W" not in r["date"] and r["date"] < EPOCH):
            continue
        if r["category"] == "board" and (r["sport"], r["date"], r["player"], r["market"],
                                         (r["side"] or "").upper()) in twins:
            continue
        r["half"] = SP.half_of(r["category"])
        out.append(r)
    return out


def flat(r) -> float:
    return SP.flat_return(r["odds"], r["status"]) or 0.0


def line(label: str, res: list) -> str:
    """bets, hit, staked, net, ROI, z for [(row, stake)]."""
    graded = [(r, s) for r, s in res if s > 0 and r["status"] != "push"]
    n = len(graded)
    st = sum(s for _r, s in graded)
    pl = [s * flat(r) for r, s in graded]
    net = sum(pl)
    w = sum(1 for r, _s in graded if r["status"] == "won")
    m = net / n if n else 0.0
    v = sum((x - m) ** 2 for x in pl) / max(1, n - 1) if n else 0.0
    z = m / math.sqrt(v / n) if n and v > 0 else 0.0
    return (f"  {label:46s} {n:5d} bets  {w / n if n else 0:5.1%} won  {st:8.1f}u staked  "
            f"{net:+8.2f}u  {net / st if st else 0:+6.2%}  z {z:+.2f}")


def walk(rows: list, stake, keyf=None):
    """[(row, stake)] with ``stake(row, books)`` decided from earlier days only;
    ``books`` are SP.Book per ``keyf(row)``."""
    rows = sorted(rows, key=lambda r: SP.sort_day(r["day"]))
    books: dict = collections.defaultdict(SP.Book)
    out, i = [], 0
    while i < len(rows):
        d = SP.sort_day(rows[i]["day"])
        j = i
        while j < len(rows) and SP.sort_day(rows[j]["day"]) == d:
            j += 1
        day = rows[i:j]
        out += [(r, stake(r, books)) for r in day]
        if keyf:
            for r in day:
                if r["status"] != "push":
                    books[keyf(r)].add(flat(r))
        i = j
    return out


def gate(keyf, nmin=30):
    """Stake 1u unless this key's earlier picks lost money (n >= nmin)."""
    def stake(r, books):
        b = books.get(keyf(r))
        return 0.0 if b and b.n >= nmin and b.roi() < 0 else 1.0
    return stake


def credibility(keyf, tau=0.03, mref=0.02, kmax=2.0):
    """Stake in proportion to the key's shrunk record (more where it won)."""
    def stake(r, books):
        b = books.get(keyf(r))
        m = 0.0
        if b and b.n:
            mean = b.s / b.n
            var = max(0.25, (b.ss - b.n * mean * mean) / max(1, b.n - 1))
            m = (mean * b.n / var) / (1 / tau ** 2 + b.n / var)
        return max(0.0, min(kmax, m / mref))
    return stake


def report(rows: list) -> None:
    H = headline(rows)
    print(f"{len(H)} graded picks on the headline record "
          f"({min(r['date'] for r in H)} to {max(SP.sort_day(r['day']) for r in H)})\n")

    print("1. EACH HALF")
    for half in ("edge", "likely"):
        R = [r for r in H if r["half"] == half]
        print(line(f"{half}: as placed", [(r, r["stake_units"]) for r in R]))
        print(line(f"{half}: flat 1u", [(r, 1.0) for r in R]))

    print("\n2. DOES OUR CLAIMED EDGE OVER THE PRICE PREDICT THE RESULT? (flat 1u)")
    for half in ("edge", "likely"):
        bins = collections.defaultdict(list)
        for r in H:
            if r["half"] != half or r["hit_prob"] is None:
                continue
            ev = r["hit_prob"] * (1 + (r["odds"] / 100 if r["odds"] > 0 else 100 / abs(r["odds"]))) - 1
            k = ("a. worse than the price" if ev < 0 else "b. 0-5% better" if ev < 0.05
                 else "c. 5%+ better")
            bins[k].append((r, 1.0))
        for k in sorted(bins):
            print(line(f"{half}: we said {k[3:]}", bins[k]))

    print(f"\n3. STAKE RULES, WALKED FORWARD (through {SPLIT} | after it)")
    rules = {
        "as placed": (lambda r, b: r["stake_units"], None),
        "flat 1u, every pick": (lambda r, b: 1.0, None),
        "flat 1u, Edge only": (lambda r, b: 1.0 if r["half"] == "edge" else 0.0, None),
        "drop losing markets": (gate(lambda r: (r["half"], r["sport"], r["market"], r["side"].upper())),
                                lambda r: (r["half"], r["sport"], r["market"], r["side"].upper())),
        "drop losing leagues": (gate(lambda r: (r["half"], r["sport"])),
                                lambda r: (r["half"], r["sport"])),
        "drop losing sportsbooks": (gate(lambda r: (r["half"], r["book"]), 50),
                                    lambda r: (r["half"], r["book"])),
        "more where it has won (league)": (credibility(lambda r: (r["half"], r["sport"])),
                                           lambda r: (r["half"], r["sport"])),
    }
    for name, (stake, keyf) in rules.items():
        res = walk(H, stake, keyf)
        early = [(r, s) for r, s in res if SP.sort_day(r["day"]) <= SPLIT]
        late = [(r, s) for r, s in res if SP.sort_day(r["day"]) > SPLIT]
        print(line(f"{name} (through)", early))
        print(line(f"{name} (after)", late))

    print("\n4. THE v4 RULE (engine/stakeplan), WALKED FORWARD")
    flags, state = SP.replay(H)
    staked = [(r, r["stake_units"] if on else 0.0) for r, on in zip(H, flags)]
    print(line("staked picks, all", staked))
    print(line("staked picks (through)", [(r, s) for r, s in staked if SP.sort_day(r["day"]) <= SPLIT]))
    print(line("staked picks (after)", [(r, s) for r, s in staked if SP.sort_day(r["day"]) > SPLIT]))
    print(f"  tracked, not staked: {sum(1 for on in flags if not on)} picks")
    print("\n  what it stakes next:")
    for sport, halves in sorted(SP.plan_from(state).items()):
        for h in ("edge", "likely"):
            if h in halves:
                print(f"    {sport.upper():5s} {'Edge' if h == 'edge' else 'Most Likely':12s} {halves[h]['why']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", help="a saved copy of the receipts (default: the live site)")
    a = ap.parse_args(argv)
    report(load(a.csv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
