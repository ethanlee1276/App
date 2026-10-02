#!/usr/bin/env python3
"""Which Most Likely picks should we stop taking? — tried on weeks it never saw.

    cd /srv/qellys && sudo -u qellys python3 likelyfit.py              # every sport, then each
    sudo -u qellys python3 likelyfit.py --sport nfl
    sudo -u qellys python3 likelyfit.py --book board                  # the one board, with its tiers
    sudo -u qellys python3 likelyfit.py --json /tmp/likelyfit.json

Ethan, 2026-10-02: "I feel like we have collected enough data for our most
likely bets too make the models better and start working on getting
better with the bets."

WHAT THE RECORD ALREADY SAYS. The Most Likely number is honest — NFL said
65% and hit 65% over 372 — so re-fitting the probability would move
nothing. What it does not do is beat the price: −0.6%. A calibrated board
that takes fair prices breaks even minus the vig. The only lever left is
WHICH picks it takes, so that is what this measures.

HOW, AND WHY THIS WAY. A rule fitted on a sample always improves that
sample; that demonstrates nothing (selfit.py says it at length, and the
repo's rule is never to change a model because a backtest improved). So
the journal is split by date: every rule picks its setting on the EARLIER
60% of days and is scored on the LATER 40%, which it never saw, against
taking every pick on those same later days. The difference is the rule's
worth; a day-block bootstrap gives it an interval.

WHAT IS COUNTED. The Most Likely picks as a reader saw them — the list's
own book (paper and staked) and the board's picks it did not hold, each
pick once (ledger.books_sql) — settled won or lost, at a flat 1 unit each
at the price taken, so a 0.1u paper row and a 0.25u staked row weigh the
same. `--book board` reads the board's rows alone, which carry a tier.

THE RULES, WRITTEN BEFORE ANY RUN (each with the settings it may choose
from; the earlier days choose, keeping at least 30 picks and 30% of them):

    price_cap    skip prices heavier than C        C in -300 -250 -200 -175 -150
    prob_floor   our chance at least F             F in .50 .55 .60 .65 .70
    edge_floor   our chance minus the book's
                 (vig in) at least E               E in -.02 0 .02 .04 .06
    fair_floor   our chance minus the de-vigged
                 market consensus at least E       E in -.02 0 .02 .04 .06
    shelf_cut    drop any sport-market-side that lost more than 5% on
                 30+ earlier picks
    side         overs only, or unders only
    late_only    taken within L minutes of start   L in 120 360 1440
    tier         (board only) Top only, or Top + Strong

A row a rule cannot judge (no edge, no consensus, no time to start) is
kept, and the coverage is printed beside the rule.

THE BAR, WRITTEN BEFORE ANY RUN — the contract:

  * PASSES when the later days' improvement is above zero at the bottom
    of its 99% interval, on at least 40 kept picks. 99%, not 95%: eight
    rules are tried at once, and at 95% pure noise passed one of them in
    one test run of three (tests/test_likelyfit_judges_on_days_it_never_saw).
  * HURTS when the top of that interval is below zero.
  * otherwise NOT PROVEN — not a soft pass. Wait for picks.

Even at 99%, eight rules tried means one can pass by luck about one run
in twenty-five. A rule is therefore applied to the board only after it PASSES on two runs
at least two weeks apart, the second scored on days the first never saw.
Changing these constants after seeing a run is fitting the bar.

Read-only: the ledger is opened read-only and nothing is written.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import ledger as L                                  # noqa: E402

TRAIN_SHARE = 0.60
MIN_KEEP = 30
MIN_KEEP_SHARE = 0.30
MIN_TEST_KEPT = 40
MIN_TEST = 60
BOOT = 2000
SEED = 20261002
SHELF_MIN_N = 30
SHELF_CUT_ROI = -0.05
#: The interval's ends (99%): see THE BAR above.
LO_Q, HI_Q = 0.005, 0.995

GRIDS = {
    "price_cap": (-300, -250, -200, -175, -150),
    "prob_floor": (0.50, 0.55, 0.60, 0.65, 0.70),
    "edge_floor": (-0.02, 0.0, 0.02, 0.04, 0.06),
    "fair_floor": (-0.02, 0.0, 0.02, 0.04, 0.06),
    "side": ("OVER", "UNDER"),
    "late_only": (120, 360, 1440),
    "tier": (("Top pick",), ("Top pick", "Strong")),
}
WORDS = {
    "price_cap": "skip prices heavier than {}",
    "prob_floor": "our chance at least {:.0%}",
    "edge_floor": "our chance beats the book's by {:+.0%} or more",
    "fair_floor": "our chance beats the market consensus by {:+.0%} or more",
    "shelf_cut": "drop {}",
    "side": "{} only",
    "late_only": "taken within {} minutes of the start",
    "tier": "tiers: {}",
}
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ro(path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def payout(odds) -> float:
    """Profit on 1 unit when it wins, at American odds."""
    o = float(odds)
    return o / 100.0 if o > 0 else 100.0 / abs(o)


def load(conn, sport: str | None = None, book: str = "likely") -> list[dict]:
    """The settled picks, one dict each, with a flat-stake return and the
    calendar day used to split earlier from later."""
    if book == "board":
        sql, args = "category=?", [L.BOARD_CATEGORY]
    else:
        sql, args = L.books_sql(L.LIKELY_BOOKS + (L.BOARD_CATEGORY,))
    q = (f"SELECT sport, market, UPPER(COALESCE(side,'')) side, odds, hit_prob, edge, fair_consensus, "
         f"status, grade, lead_min, game_day, date, ts FROM bets WHERE {sql} "
         "AND status IN ('won','lost') AND stake_units > 0 AND odds IS NOT NULL")
    if sport:
        q += " AND LOWER(sport)=?"
        args.append(sport.lower())
    out = []
    for r in conn.execute(q, args):
        try:
            if abs(float(r["odds"])) < 100:
                continue
            ret = payout(r["odds"]) if r["status"] == "won" else -1.0
        except (TypeError, ValueError):
            continue
        day = str(r["game_day"] or "")
        if not _ISO.match(day):
            day = str(r["date"] or "") if _ISO.match(str(r["date"] or "")) else str(r["ts"] or "")[:10]
        if not _ISO.match(day):
            continue
        d = dict(r)
        d["ret"], d["day"] = ret, day
        out.append(d)
    return out


def split(rows: list[dict]) -> tuple[list, list]:
    days = sorted({r["day"] for r in rows})
    if len(days) < 2:
        return rows, []
    cut = days[max(1, int(len(days) * TRAIN_SHARE)) - 1]
    return [r for r in rows if r["day"] <= cut], [r for r in rows if r["day"] > cut]


def roi(rows) -> float | None:
    return sum(r["ret"] for r in rows) / len(rows) if rows else None


def _rule(name, param, banned=None):
    """keep(row) -> bool, and whether the row could be judged at all."""
    if name == "price_cap":
        return lambda r: float(r["odds"]) >= param, lambda r: True
    if name == "prob_floor":
        return (lambda r: r["hit_prob"] is None or float(r["hit_prob"]) >= param,
                lambda r: r["hit_prob"] is not None)
    if name == "edge_floor":
        return (lambda r: r["edge"] is None or float(r["edge"]) >= param,
                lambda r: r["edge"] is not None)
    if name == "fair_floor":
        ok = lambda r: r["fair_consensus"] is not None and r["hit_prob"] is not None  # noqa: E731
        return (lambda r: not ok(r) or float(r["hit_prob"]) - float(r["fair_consensus"]) >= param, ok)
    if name == "side":
        return lambda r: r["side"] == param, lambda r: True
    if name == "late_only":
        return (lambda r: r["lead_min"] is None or float(r["lead_min"]) <= param,
                lambda r: r["lead_min"] is not None)
    if name == "tier":
        return (lambda r: not r["grade"] or r["grade"] in param, lambda r: bool(r["grade"]))
    if name == "shelf_cut":
        return (lambda r: (r["sport"], r["market"], r["side"]) not in banned, lambda r: True)
    raise KeyError(name)


def _choose(name, train):
    """The setting the earlier days pick: best ROI keeping enough picks."""
    floor = max(MIN_KEEP, int(len(train) * MIN_KEEP_SHARE))
    if name == "shelf_cut":
        groups: dict = {}
        for r in train:
            groups.setdefault((r["sport"], r["market"], r["side"]), []).append(r)
        banned = {k for k, v in groups.items() if len(v) >= SHELF_MIN_N and roi(v) < SHELF_CUT_ROI}
        kept = [r for r in train if (r["sport"], r["market"], r["side"]) not in banned]
        return (banned, banned) if banned and len(kept) >= floor else (None, None)
    best = None
    for p in GRIDS[name]:
        keep, _judged = _rule(name, p)
        kept = [r for r in train if keep(r)]
        if len(kept) < floor or len(kept) == len(train):
            continue
        v = roi(kept)
        if best is None or v > best[1]:
            best = (p, v)
    return (best[0], None) if best else (None, None)


def _boot(test, keep, n=BOOT, seed=SEED):
    """99% interval of (ROI kept − ROI all) on the later days, resampling
    whole days so one big slate cannot pass for many small ones."""
    by_day: dict = {}
    for r in test:
        by_day.setdefault(r["day"], []).append(r)
    days = list(by_day)
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        rows = [r for d in (rng.choice(days) for _ in days) for r in by_day[d]]
        kept = [r for r in rows if keep(r)]
        if kept and rows:
            diffs.append(roi(kept) - roi(rows))
    diffs.sort()
    if not diffs:
        return None, None
    return diffs[int(LO_Q * len(diffs))], diffs[min(len(diffs) - 1, int(HI_Q * len(diffs)))]


def study(rows: list[dict]) -> dict:
    train, test = split(rows)
    out = {"n": len(rows), "train": len(train), "test": len(test),
           "train_days": [train[0]["day"], max(r["day"] for r in train)] if train else [],
           "test_days": [min(r["day"] for r in test), max(r["day"] for r in test)] if test else [],
           "roi_all": roi(rows), "roi_test_all": roi(test), "rules": []}
    if len(test) < MIN_TEST:
        out["note"] = f"{len(test)} picks on the later days; {MIN_TEST} needed before a rule can be judged"
        return out
    names = ["price_cap", "prob_floor", "edge_floor", "fair_floor", "shelf_cut", "side", "late_only"]
    if any(r["grade"] for r in rows) and all(r["grade"] in ("Top pick", "Strong", "Worth a look", None, "")
                                             for r in rows):
        names.append("tier")
    for name in names:
        param, banned = _choose(name, train)
        if param is None:
            out["rules"].append({"rule": name, "verdict": "NOTHING TO CHOOSE",
                                 "why": "every setting either keeps every pick or keeps too few"
                                        " of the earlier ones (fewer than 30, or under 30%)"})
            continue
        keep, judged = _rule(name, param, banned)
        kt = [r for r in test if keep(r)]
        lo, hi = _boot(test, keep)
        diff = roi(kt) - roi(test) if kt else None
        verdict = ("PASSES" if lo is not None and lo > 0 and len(kt) >= MIN_TEST_KEPT
                   else "HURTS" if hi is not None and hi < 0 else "NOT PROVEN")
        shown = (", ".join(f"{s} {m} {sd.lower()}" for s, m, sd in sorted(param))
                 if name == "shelf_cut" else " / ".join(param) if name == "tier" else param)
        out["rules"].append({
            "rule": name, "setting": WORDS[name].format(shown),
            "train_kept": len([r for r in train if keep(r)]), "train_roi": roi([r for r in train if keep(r)]),
            "test_kept": len(kt), "test_roi": roi(kt), "test_all_roi": roi(test),
            "diff": diff, "lo": lo, "hi": hi, "verdict": verdict,
            "coverage": sum(1 for r in rows if judged(r)) / len(rows)})
    return out


def _pct(x):
    return "   —  " if x is None else f"{x * 100:+6.1f}%"


def report(label: str, res: dict) -> None:
    print(f"\n=== {label}: {res['n']} settled picks, {_pct(res['roi_all'])} at a flat unit")
    if not res["n"]:
        return
    print(f"    earlier days {res['train_days'][0]} – {res['train_days'][1]} ({res['train']} picks) choose;"
          + (f" later days {res['test_days'][0]} – {res['test_days'][1]} ({res['test']} picks) judge,"
             f" where taking every pick returned {_pct(res['roi_test_all']).strip()}" if res["test"] else ""))
    if res.get("note"):
        print(f"    {res['note']}.")
        return
    for r in res["rules"]:
        if "setting" not in r:
            print(f"    {r['rule']:11} {r['verdict']}: {r['why']}")
            continue
        cov = "" if r["coverage"] > 0.99 else f"  (judges {r['coverage']:.0%} of picks)"
        print(f"    {r['rule']:11} {r['verdict']:11} {r['setting']}{cov}")
        print(f"                later days: kept {r['test_kept']} of {res['test']}, {_pct(r['test_roi']).strip()}"
              f" against {_pct(r['test_all_roi']).strip()} — difference {_pct(r['diff']).strip()},"
              f" 99% {_pct(r['lo']).strip()} to {_pct(r['hi']).strip()}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="")
    ap.add_argument("--book", default="likely", choices=("likely", "board"))
    ap.add_argument("--db", default=str(ROOT / "data" / "ledger.db"))
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    conn = _ro(a.db)
    print("MOST LIKELY — WHICH PICKS TO STOP TAKING, judged on days the choice never saw (read-only)")
    print("A rule is applied only after it PASSES on two runs two weeks apart. See the top of likelyfit.py.")
    results = {}
    sports = [a.sport.lower()] if a.sport else ["all"] + [s for s in L.TRACKED_SPORTS]
    for sp in sports:
        rows = load(conn, None if sp == "all" else sp, a.book)
        if sp != "all" and not rows:
            continue
        results[sp] = study(rows)
        report("Every sport" if sp == "all" else sp.upper(), results[sp])
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1, default=str))
        print(f"\nwritten: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
