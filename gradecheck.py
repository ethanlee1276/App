#!/usr/bin/env python3
"""Does the grade ladder point the right way?

Ethan, 2026-08-13, reading `stakecheck --since 2026-06-01`: the six grade
labels came back with the two WEAKEST at the top — Lean +8.8%, Play
-2.2%, Strong Play -20.0% — and A+ below A. He asked for that tested
properly before anything is changed on the strength of it.

THE FIRST THING A PROPER TEST HAS TO DO IS STOP MIXING TWO LADDERS.
`A+ / A / B+` is the PROP grade (engine/betting.py, which documents that
it has no Lean tier on purpose). `Strong Play / Play / Lean` is the
GAME-BET grade (engine/gamebets.py, thresholded on EV at 0.06 and 0.035).
Different engines, different products, different scales. Ranking all six
in one column compares a prop grade against a game line, and the apparent
"inversion" is partly that. Each ladder is tested on its own here.

WHAT THE TEST IS. Within one ladder, per-bet profit at a FLAT 1u is
regressed on the grade's rank, and the slope is the whole question:

    slope > 0   the ladder ranks bets correctly
    slope ~ 0   the grade carries no information
    slope < 0   the ladder is INVERTED — conviction is anti-predictive

Flat stakes, because the question is whether the RANKING is informative;
leaving the sizing in would let a stake policy answer a question about
grades. The p-value is a permutation test — the grade labels are shuffled
against the outcomes many times and the observed slope is placed in that
distribution. No distributional assumption, no scipy, and it answers the
right question: how often would chance alone produce a slope this steep?

WHY A HELD-OUT SPLIT IS THE REAL VERDICT. A slope fitted on all the data
is the same statistic that made the six-label table look decisive, and
six labels give six chances to find a pattern. The journal is therefore
cut in half CHRONOLOGICALLY: the slope is fitted on the older half and
the sign is checked on the newer one. A ranking that is genuinely
backwards is backwards in both halves. One that flips was noise, and
acting on it would be the most expensive kind of mistake — rebuilding the
gate around a coin flip.

AND SIGN AGREEMENT ALONE IS NOT ENOUGH, which this tool learned the hard
way. Run against a synthetic book with NO signal — every grade at a 50%
win rate — the two halves agreed on the sign and the output read like a
working ladder. Two halves agree by chance half the time. So the newer
half also carries its own permutation test, and only "same sign AND the
newer half significant on its own" is reported as worth acting on.

READ-ONLY. Opens the ledger immutably and writes nothing.

    python3 gradecheck.py
    python3 gradecheck.py --sport mlb
    python3 gradecheck.py --since 2026-07-25
"""

from __future__ import annotations

import argparse
import os
import random
import sqlite3
import sys

#: The two ladders, weakest first. Rank is the index, so a positive slope
#: means "better grade, better result".
LADDERS = {
    "player props (engine/betting.py)": ["B+", "A", "A+"],
    "game bets (engine/gamebets.py)": ["Lean", "Play", "Strong Play"],
}
#: Bets that were never money. Same exclusions the record uses.
BOOKS = ("main", "paper")
PERMUTATIONS = 20000


def _rows(db, sport=None, since=None):
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    q = ("SELECT date, sport, player, market, grade, odds, hit_prob, status "
         "FROM bets WHERE status IN ('won','lost') "
         f"AND category IN ({','.join('?' * len(BOOKS))}) AND stake_units > 0")
    args = list(BOOKS)
    if sport:
        q += " AND sport = ?"; args.append(sport)
    if since:
        q += " AND date >= ?"; args.append(since)
    out = [dict(r) for r in conn.execute(q + " ORDER BY date, id", args)]
    conn.close()
    return out


def _profit(r):
    """Units won or lost on a FLAT 1u stake at this bet's price."""
    if r["status"] != "won":
        return -1.0
    o = r["odds"]
    if o is None:
        return 0.0
    return (o / 100.0) if o > 0 else (100.0 / -o)


def _slope(pairs):
    """Least-squares slope of profit on grade rank. None if degenerate."""
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    if sxx <= 0:
        return None                       # every bet on one rung
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    return sxy / sxx


def _permutation_p(pairs, observed, rounds=PERMUTATIONS, seed=7):
    """How often chance alone produces a slope at least this steep."""
    rnd = random.Random(seed)
    ys = [y for _, y in pairs]
    xs = [x for x, _ in pairs]
    hits = 0
    for _ in range(rounds):
        rnd.shuffle(ys)
        s = _slope(list(zip(xs, ys)))
        if s is not None and abs(s) >= abs(observed):
            hits += 1
    return (hits + 1) / (rounds + 1)      # +1: never report p = 0


def _band(vals):
    """(mean, 1 standard error) for a list of per-bet profits."""
    n = len(vals)
    if not n:
        return 0.0, 0.0
    m = sum(vals) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return m, (var / n) ** 0.5


def report(rows, name, ladder):
    rank = {g: i for i, g in enumerate(ladder)}
    mine = [r for r in rows if r["grade"] in rank]
    print(f"\n  {name}")
    if len(mine) < 20:
        print(f"    {len(mine)} settled bet(s) — too few to say anything. "
              f"Nothing is reported rather than reported thinly.")
        return
    by = {g: [] for g in ladder}
    for r in mine:
        by[r["grade"]].append(_profit(r))

    print(f"    {'grade':<14}{'bets':>6}{'ROI at 1u':>12}{'±1se':>9}"
          f"{'  hit':>7}")
    for g in reversed(ladder):                    # strongest first, as read
        v = by[g]
        if not v:
            print(f"    {g:<14}{0:>6}{'—':>12}")
            continue
        m, se = _band(v)
        hit = sum(1 for r in mine if r["grade"] == g and r["status"] == "won")
        print(f"    {g:<14}{len(v):>6}{m * 100:>11.1f}%{se * 100:>8.1f}%"
              f"{hit / len(v) * 100:>6.0f}%")

    pairs = [(rank[r["grade"]], _profit(r)) for r in mine]
    s = _slope(pairs)
    if s is None:
        print("    every bet sits on one rung — no ladder to test.")
        return
    p = _permutation_p(pairs, s)
    direction = ("points the RIGHT way" if s > 0 else "is INVERTED")
    print(f"\n    slope {s:+.4f}u per rung  ·  p = {p:.3f}  "
          f"({PERMUTATIONS:,} permutations)")
    if p >= 0.05:
        print(f"    VERDICT: not distinguishable from chance. The ladder "
              f"{direction}\n             in this sample, but a shuffle "
              f"produces a slope this steep {p * 100:.0f}% of the time.")
    else:
        print(f"    VERDICT: the ladder {direction}, and chance produces "
              f"this only {p * 100:.1f}% of the time.")

    # THE HELD-OUT HALF — the part that decides whether to act.
    half = len(mine) // 2
    old, new = mine[:half], mine[half:]
    so = _slope([(rank[r["grade"]], _profit(r)) for r in old])
    sn = _slope([(rank[r["grade"]], _profit(r)) for r in new])
    print(f"\n    chronological halves   older {len(old)} bets: "
          f"{'—' if so is None else f'{so:+.4f}'}"
          f"   ·   newer {len(new)} bets: "
          f"{'—' if sn is None else f'{sn:+.4f}'}")
    if so is None or sn is None:
        print("    one half has no spread of grades — no out-of-sample read.")
        return
    # SIGN AGREEMENT IS A COIN FLIP UNDER THE NULL, and "it did it twice"
    # would be this tool overclaiming. Caught by running it against a
    # synthetic book with NO signal at all — every grade at a 50% win
    # rate — where the halves agreed on the sign and the output read like
    # a working ladder. The newer half therefore gets its OWN permutation
    # test: out-of-sample evidence is a p-value on data the slope was not
    # fitted to, not a matching arithmetic sign.
    pn = _permutation_p([(rank[r["grade"]], _profit(r)) for r in new], sn)
    agree = (so > 0) == (sn > 0)
    print(f"    newer half on its own: p = {pn:.3f}")
    if agree and pn < 0.05:
        print("    Same sign AND the newer half stands on its own. This is "
              "the one\n    combination worth acting on.")
    elif agree:
        print("    Same sign, but the newer half does not reach significance "
              "by itself.\n    Two halves agree by chance half the time — "
              "suggestive, not settled.")
    else:
        print("    The halves DISAGREE on the sign. That is what noise "
              "looks like, and\n    rebuilding the gate around it would be "
              "the expensive kind of mistake.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/ledger.db")
    ap.add_argument("--sport")
    ap.add_argument("--since")
    a = ap.parse_args(argv)
    if not os.path.exists(a.db):
        print(f"  No ledger at {a.db}.")
        return 1
    rows = _rows(a.db, a.sport, a.since)
    scope = " · ".join(filter(None, [a.sport or "every sport", a.since and f"since {a.since}"]))
    print(f"\n  {len(rows)} settled bet(s) · {scope}"
          f"  ·  flat 1u, so the RANKING is the only variable")
    print("\n  Two ladders, tested apart. A+/A/B+ grades player props; "
          "Lean/Play/Strong Play\n  grades game lines. They are different "
          "engines on different scales — ranking all\n  six in one column "
          "compares a prop against a game line.")
    for name, ladder in LADDERS.items():
        report(rows, name, ladder)
    seen = {r["grade"] for r in rows}
    other = seen - {g for l in LADDERS.values() for g in l}
    if other:
        print(f"\n  not on either ladder: {', '.join(sorted(map(str, other)))}")
    print("\n  read-only; nothing was written.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
