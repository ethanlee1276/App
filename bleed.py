#!/usr/bin/env python3
"""Where is the money actually going? Slice the journal and test each cut.

    python3 bleed.py                    # the whole record
    python3 bleed.py --sport mlb
    python3 bleed.py --min-n 15         # smaller slices, more noise
    python3 bleed.py --since 2026-07-01

WHY THIS IS NOT JUST A SORT

A losing record invites one move: sort the slices by ROI, look at the
worst, and turn it off. That move is wrong twice over, and both are worth
saying out loud because they are the whole reason this file exists.

**A headline ROI is usually not evidence yet.** Betting near -110, the
break-even win rate is 52.4%. Two hundred settled bets carry a standard
error of about 3.4 points on the win rate, so anything inside roughly six
points of break-even is indistinguishable from a coin. A record can read
-9% and mean nothing at all. The report says so before it says anything
else, with the z out loud, because "we are losing" and "we can show we are
losing" are different claims and only the second justifies a change.

**Slicing multiplies false findings.** Cut a coin-flip record fifteen ways
and some cut lands two sigma out — that is what two sigma MEANS at fifteen
tries. So the bar here rises with the number of slices actually tested
(Šidák), and every slice is printed with its own n and z rather than
ranked by ROI, so a big number on eight bets cannot masquerade as a
finding.

**CLV converges faster than ROI, so read it first.** Whether a bet beat
the closing line is nearly noiseless per bet, where whether it won is
mostly variance. A book of bets with positive CLV and negative ROI is a
book that is priced right and running bad; negative on both is a model
genuinely behind the market. Those need opposite responses, and ROI alone
cannot tell them apart.

WHAT IT WILL NOT DO

Recommend turning anything off. It reports what the record can and cannot
support; the decision is yours, and on this much data the honest answer is
usually "keep betting and look again at 700".
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict

#: Slices smaller than this are counted but never convicted — the z is
#: meaningless and printing it as a finding invites acting on eight bets.
MIN_N = 25
#: Family-wise error rate the Šidák bar is set to hold across every slice
#: tested in one run.
ALPHA = 0.05


# --- statistics --------------------------------------------------------------
def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def sidak_z(n_tests: int, alpha: float = ALPHA) -> float:
    """Two-sided z that holds `alpha` across `n_tests` independent looks.

    One slice at 5% is z=1.96; sixty slices at a family-wise 5% is z≈3.0.
    Using 1.96 sixty times is how a coin-flip journal produces three
    confident findings.
    """
    if n_tests <= 1:
        return 1.96
    per = 1.0 - (1.0 - alpha) ** (1.0 / n_tests)
    lo, hi = 0.0, 8.0
    for _ in range(200):                    # bisect the normal tail
        mid = (lo + hi) / 2
        if 2 * (1 - _phi(mid)) > per:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def breakeven(odds: float) -> float:
    """The win rate an American price needs just to break even."""
    o = float(odds)
    return (100.0 / (o + 100.0)) if o > 0 else (-o / (-o + 100.0))


def decimal(odds: float) -> float:
    o = float(odds)
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / -o)


def rate_z(rows: list[dict]) -> float:
    """Did we win as OFTEN as the prices require?

    Poisson-binomial, not a mean-rate approximation: each bet has its own
    break-even, so the variance is the sum of p(1-p) over the bets actually
    made. On a book mixing -300 favourites with +150 dogs the two differ
    enough to move a verdict.
    """
    num = var = 0.0
    for b in rows:
        be = breakeven(b.get("odds") or -110)
        num += (1.0 if b["status"] == "won" else 0.0) - be
        var += be * (1.0 - be)
    return num / math.sqrt(var) if var > 0 else 0.0


def roi_z(rows: list[dict]) -> float:
    """Did we win as MUCH as the prices require? The test on units.

    This is the one that matters, and it is not the same question. A book
    that wins its long prices and loses its short ones can sit under the
    required win RATE while making money, and the reverse. Under the null
    each bet is fairly priced, so profit has mean zero and variance
    stake² · (p·b² + (1-p)) with p the break-even and b the payout.
    """
    num = var = 0.0
    for b in rows:
        stake = float(b.get("stake_units") or 0)
        if stake <= 0:
            continue
        be = breakeven(b.get("odds") or -110)
        payout = decimal(b.get("odds") or -110) - 1.0
        num += float(b.get("pnl_units") or 0)
        var += (stake ** 2) * (be * payout ** 2 + (1.0 - be))
    return num / math.sqrt(var) if var > 0 else 0.0


# --- the journal -------------------------------------------------------------
def load(conn, sport=None, category="main", since=None) -> list[dict]:
    q = ("SELECT sport, date, player, market, side, line, book, odds, grade, "
         "status, pnl_units, stake_units, hit_prob, closing_line, "
         "loss_cause, lineup_slot, park_hr, wind_out, roofed, lead_min, "
         "rest_days, body_clock, pen_own, pen_opp "
         "FROM bets WHERE status IN ('won','lost') AND category=?")
    args: list = [category]
    if sport:
        q += " AND sport=?"
        args.append(sport)
    if since:
        q += " AND date>=?"
        args.append(since)
    return [dict(r) for r in conn.execute(q + " ORDER BY date, id", args)]


def clv_of(b: dict) -> float | None:
    """Side-aware closing-line value, in line points. Positive = our way."""
    if b.get("closing_line") is None or b.get("line") is None:
        return None
    move = float(b["closing_line"]) - float(b["line"])
    return move if (b.get("side") or "OVER").upper() == "OVER" else -move


# --- slicing -----------------------------------------------------------------
def odds_bucket(b) -> str:
    o = float(b.get("odds") or -110)
    if o <= -150:
        return "odds ≤ -150 (heavy favourite)"
    if o < -100:
        return "odds -149..-101"
    if o < 150:
        return "odds +100..+149"
    return "odds ≥ +150 (plus money)"


def prob_bucket(b) -> str:
    p = b.get("hit_prob")
    if p is None:
        return "prob unknown"
    p = float(p)
    return ("prob < 50%" if p < 0.5 else "prob 50-60%" if p < 0.6
            else "prob 60-70%" if p < 0.7 else "prob ≥ 70%")


def _bucketed(b, col, edges, unit=""):
    v = b.get(col)
    if v is None:
        return None
    v = float(v)
    for hi, label in edges:
        if v < hi:
            return f"{col} {label}{unit}"
    return f"{col} {edges[-1][1]}+{unit}"


DIMENSIONS = {
    "sport":       lambda b: b.get("sport") or "?",
    "market":      lambda b: b.get("market") or "?",
    "side":        lambda b: (b.get("side") or "?").upper(),
    "book":        lambda b: (b.get("book") or "?") or "(none)",
    "grade":       lambda b: b.get("grade") or "?",
    "price":       odds_bucket,
    "claimed p":   prob_bucket,
    # loss_cause is deliberately NOT a slice. It is only ever written on a
    # bet that lost, so every bucket it makes is 0-N by construction and
    # scores -100% ROI at an enormous z — a tautology wearing the clothes
    # of the strongest finding on the page. It belongs in a breakdown of
    # the losses (which lost to variance, which to a blowout), never in a
    # comparison against bets that won.
    "lineup slot": lambda b: (None if b.get("lineup_slot") is None else
                              f"slot {int(float(b['lineup_slot']))}"),
    "park HR":     lambda b: _bucketed(b, "park_hr", [(0.95, "pitchers'"),
                                                      (1.05, "neutral"),
                                                      (99, "hitters'")]),
    "wind":        lambda b: _bucketed(b, "wind_out", [(-4, "blowing in"),
                                                       (4, "calm"),
                                                       (99, "blowing out")]),
    "roof":        lambda b: (None if b.get("roofed") is None
                              else "roof closed" if float(b["roofed"]) else
                              "open air"),
    "capture lag": lambda b: _bucketed(b, "lead_min", [(60, "< 1h to first pitch"),
                                                       (240, "1-4h out"),
                                                       (1e9, "> 4h out")]),
    "bullpen own": lambda b: _bucketed(b, "pen_own", [(2, "rested"),
                                                      (5, "used"),
                                                      (1e9, "gassed")]),
}


def measure(rows: list[dict]) -> dict:
    """Record, ROI, CLV and the z against the prices' own break-even."""
    n = len(rows)
    wins = sum(1 for b in rows if b["status"] == "won")
    staked = sum(float(b.get("stake_units") or 0) for b in rows)
    pnl = sum(float(b.get("pnl_units") or 0) for b in rows)
    # Break-even is the AVERAGE of each bet's own required rate, not a flat
    # -110 assumption — a slice of plus-money bets has a different bar.
    exp = (sum(breakeven(b.get("odds") or -110) for b in rows) / n) if n else 0.0
    clvs = [c for c in (clv_of(b) for b in rows) if c is not None]
    return {
        "n": n, "wins": wins, "losses": n - wins,
        "roi": (pnl / staked) if staked else 0.0,
        "pnl": pnl, "staked": staked,
        "win_rate": (wins / n) if n else 0.0,
        "breakeven": exp,
        # Two different questions, reported separately because they can
        # disagree: often enough, and by enough.
        "z": roi_z(rows),
        "z_rate": rate_z(rows),
        "clv": (sum(clvs) / len(clvs)) if clvs else None,
        "clv_n": len(clvs),
        # Beat / tied / behind, kept apart. A line that never moved is not a
        # loss, and folding ties into "did not beat" made a book that mostly
        # takes the closing number look like one the market runs over.
        "clv_beat": (sum(1 for c in clvs if c > 0) / len(clvs)) if clvs else None,
        "clv_tied": (sum(1 for c in clvs if c == 0) / len(clvs)) if clvs else None,
        "clv_behind": (sum(1 for c in clvs if c < 0) / len(clvs)) if clvs else None,
    }


def slices(rows: list[dict], min_n: int) -> list[tuple]:
    """(dimension, bucket, stats) for every bucket at or above the floor."""
    out = []
    for dim, key in DIMENSIONS.items():
        groups: dict = defaultdict(list)
        for b in rows:
            k = key(b)
            if k is not None:
                groups[k].append(b)
        for bucket, rs in groups.items():
            if len(rs) >= min_n:
                out.append((dim, bucket, measure(rs)))
    return out


# --- reporting ---------------------------------------------------------------
def _bar(s: dict, bar: float) -> str:
    return "CONVICTS" if abs(s["z"]) >= bar else ""


def report(rows: list[dict], min_n: int = MIN_N, alpha: float = ALPHA) -> int:
    if not rows:
        print("No settled bets match. Nothing to measure.")
        return 0
    top = measure(rows)
    print("=" * 74)
    print("THE HEADLINE, TESTED")
    print("=" * 74)
    print(f"  {top['wins']}-{top['losses']}  ·  {top['n']} settled  ·  "
          f"{top['pnl']:+.2f}u on {top['staked']:.1f}u  ·  ROI {top['roi']:+.1%}")
    print(f"  win rate {top['win_rate']:.1%} against a break-even of "
          f"{top['breakeven']:.1%} implied by the prices actually taken")
    print(f"  z on units {top['z']:+.2f}   ·   z on win rate "
          f"{top['z_rate']:+.2f}")
    if abs(top["z"]) < 2:
        gap = abs(top["win_rate"] - top["breakeven"])
        need = ((2 * math.sqrt(top["breakeven"] * (1 - top["breakeven"]))
                 / gap) ** 2) if gap > 1e-9 else float("inf")
        print(f"\n  → NOT SIGNIFICANT. A gap this size needs about "
              f"{need:,.0f} settled bets to clear two sigma; there are "
              f"{top['n']}.")
        print("    The record cannot yet tell a broken model from a bad run.")
    else:
        print("\n  → SIGNIFICANT at two sigma on the headline.")
    # A break-even far above -110 means the book is buying short prices,
    # and that changes what the win rate has to be before it means
    # anything. Worth saying, because 47.6% reads as unlucky against 52.4%
    # and as a different problem entirely against 58%.
    if top["breakeven"] > 0.55:
        print(f"\n  Note the break-even: {top['breakeven']:.1%}, not the 52.4% a")
        print(f"  -110 book would need. These are short prices, so they have to")
        print(f"  land far more often just to stay level.")

    print()
    print("=" * 74)
    print("CLV — the faster instrument")
    print("=" * 74)
    if not top["clv_n"]:
        print("  No closing lines captured. CLV is the signal that converges")
        print("  fastest at this sample size, and without it the only")
        print("  available reading is ROI, which needs hundreds more bets.")
    else:
        cov = top["clv_n"] / top["n"]
        print(f"  {top['clv_n']} of {top['n']} bets have a close ({cov:.0%})")
        print(f"  average CLV {top['clv']:+.3f} line points")
        print(f"  beat {top['clv_beat']:.0%}  ·  tied {top['clv_tied']:.0%}"
              f"  ·  behind {top['clv_behind']:.0%}")
        if top["clv_tied"] and top["clv_tied"] > 0.3:
            print(f"    ({top['clv_tied']:.0%} of lines never moved at all — "
                  f"those are ties, not losses)")
        if top["clv"] > 0.01:
            print("\n  → Positive CLV with a negative ROI is the signature of")
            print("    a book that is priced right and running bad. That is a")
            print("    reason to keep betting, not to change the model.")
        elif top["clv"] < -0.01:
            print("\n  → Negative CLV AND negative ROI. The market is moving")
            print("    against these picks, which is the model being behind")
            print("    the market rather than unlucky. This is the one")
            print("    reading on the page that justifies changing pricing.")
        else:
            print("\n  → CLV is flat: we are taking the closing number, no")
            print("    better. No edge visible here, and none being given up.")

    cuts = slices(rows, min_n)
    bar = sidak_z(len(cuts), alpha)
    print()
    print("=" * 74)
    print(f"SLICES — {len(cuts)} tested, so the bar is |z| ≥ {bar:.2f}")
    print(f"(a single look would be 1.96; {len(cuts)} looks at "
          f"{alpha:.0%} family-wise is {bar:.2f})")
    print("=" * 74)
    print(f"  {'slice':<34}{'n':>5}{'W-L':>10}{'ROI':>9}{'z':>7}{'CLV':>8}")
    print("  " + "-" * 74)
    cuts.sort(key=lambda c: (c[0], -abs(c[2]["z"])))
    convicted = []
    for dim, bucket, s in cuts:
        clv = f"{s['clv']:+.2f}" if s["clv"] is not None else "—"
        flag = _bar(s, bar)
        wl = f"{s['wins']}-{s['losses']}"
        print(f"  {(dim + ' · ' + str(bucket))[:33]:<34}{s['n']:>5}{wl:>10}"
              f"{s['roi']:>+9.1%}{s['z']:>+7.2f}{clv:>8}"
              + (f"  {flag}" if flag else ""))
        if flag:
            convicted.append((dim, bucket, s))

    # A slice covering nearly the whole book is the headline wearing a
    # label. "sport · mlb" on a book that is 96% baseball convicts for the
    # same reason the headline does and adds nothing — worse, it reads as
    # an independent confirmation of itself.
    whole = [c for c in convicted if c[2]["n"] >= 0.9 * top["n"]]
    convicted = [c for c in convicted if c not in whole]

    print()
    print("=" * 74)
    print("WHAT THE RECORD WILL SUPPORT")
    print("=" * 74)
    if not convicted:
        print(f"  Nothing. No slice clears |z| ≥ {bar:.2f}, which is what the")
        print("  bar has to be once you look this many times.")
        print()
        print("  That is a real answer, not a failure to find one: on "
              f"{top['n']} bets")
        print("  the losing slices and the winning slices are the same size as")
        print("  the noise. Turning off the worst-looking one would be fitting")
        print("  the last two months of variance.")
    else:
        for dim, bucket, s in sorted(convicted, key=lambda c: -abs(c[2]["z"])):
            print(f"  {dim} · {bucket}: {s['n']} bets, {s['roi']:+.1%}, "
                  f"z {s['z']:+.2f}")
            print(f"     survives a bar set for {len(cuts)} simultaneous looks")
    for dim, bucket, s in whole:
        print(f"\n  ({dim} · {bucket} also clears, but it is {s['n']} of "
              f"{top['n']} bets —")
        print("   that is the headline relabelled, not a second finding.)")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description="Where the record is bleeding.")
    p.add_argument("--sport")
    p.add_argument("--category", default="main")
    p.add_argument("--since", help="only bets dated on or after (YYYY-MM-DD)")
    p.add_argument("--min-n", type=int, default=MIN_N,
                   help=f"slice floor (default {MIN_N})")
    p.add_argument("--alpha", type=float, default=ALPHA)
    p.add_argument("--db", help="ledger path (default the configured one)")
    a = p.parse_args(argv)

    from engine import ledger
    conn = ledger.connect(a.db) if a.db else ledger.connect()
    rows = load(conn, a.sport, a.category, a.since)
    return report(rows, a.min_n, a.alpha)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
