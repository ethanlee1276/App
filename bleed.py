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
    """Settled bets. `category="all"` drops the filter.

    The default is 'main' on purpose: that is the record with real money
    and a real ROI, and it is the only one whose P&L means anything. But
    the miner and the hypothesis lab read every category pooled, so the
    two see different books — on this journal, 227 bets against 3,134 —
    and "all" is how you compare them rather than wondering.
    """
    q = ("SELECT sport, date, player, market, side, line, book, odds, grade, "
         "status, pnl_units, stake_units, hit_prob, closing_line, category, "
         "ts, loss_cause, lineup_slot, lineup_conf, park_hr, wind_out, "
         "roofed, lead_min, rest_days, body_clock, pen_own, pen_opp "
         "FROM bets WHERE status IN ('won','lost')")
    args: list = []
    if category != "all":
        q += " AND category=?"
        args.append(category)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    if since:
        q += " AND date>=?"
        args.append(since)
    rows = [dict(r) for r in conn.execute(q + " ORDER BY date, id", args)]
    # horizon is derived the same way the miner derives it: days from the
    # bet being logged to the game being played.
    import datetime as _dt
    for b in rows:
        try:
            b["horizon_days"] = (_dt.date.fromisoformat(b["date"])
                                 - _dt.date.fromisoformat(
                                     str(b["ts"])[:10])).days
        except (TypeError, ValueError):
            b["horizon_days"] = None
    return rows


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


# The circumstance dimensions come from engine/losspatterns, banded by the
# MINER'S OWN functions rather than by edges invented here.
#
# This file used to band them itself, and the bands did not match: "rested"
# was under 2 weighted relief innings where the miner's "pen fresh" is
# under 3. That is not a cosmetic difference. A finding read off this
# report gets registered in the hypothesis lab, which speaks the miner's
# vocabulary, and a slice named here that does not exist there produces a
# hypothesis matching nothing — it collects at 0/40 forever and looks like
# missing data rather than a mistranslation.
#
# One vocabulary, so a number seen here can be tested there.
from engine.losspatterns import (clock_band, horizon_band,  # noqa: E402
                                 lead_band, lineup_band, park_band,
                                 pen_band, prob_band, rest_band, wind_band)


def _roofed(b) -> bool:
    return bool(b.get("roofed"))


DIMENSIONS = {
    "sport":       lambda b: b.get("sport") or "?",
    "market":      lambda b: b.get("market") or "?",
    # Only meaningful under --category all, where it answers the question
    # that comparison exists for: do the paper-track buckets calibrate
    # like the real one? The fitters pool them, so if they do not, a
    # correction fitted on the pool fits neither population.
    "bucket":      lambda b: b.get("category") or None,
    "side":        lambda b: (b.get("side") or "?").upper(),
    "book":        lambda b: (b.get("book") or "?") or "(none)",
    "grade":       lambda b: b.get("grade") or "?",
    "price":       odds_bucket,
    "claimed p":   lambda b: prob_band(b.get("hit_prob")),
    # loss_cause is deliberately NOT a slice. It is only ever written on a
    # bet that lost, so every bucket it makes is 0-N by construction and
    # scores -100% ROI at an enormous z — a tautology wearing the clothes
    # of the strongest finding on the page. It belongs in a breakdown of
    # the losses (which lost to variance, which to a blowout), never in a
    # comparison against bets that won.
    "lineup":      lambda b: lineup_band(b.get("lineup_slot"),
                                         bool(b.get("lineup_conf"))),
    "park":        lambda b: park_band(b.get("park_hr"), _roofed(b)),
    "wind":        lambda b: wind_band(b.get("wind_out"), _roofed(b),
                                       b.get("sport")),
    "roof":        lambda b: (None if b.get("roofed") is None
                              else "roof closed" if float(b["roofed"]) else
                              "open air"),
    "capture lag": lambda b: lead_band(b.get("lead_min")),
    "horizon":     lambda b: horizon_band(b.get("horizon_days")),
    "rest":        lambda b: rest_band(b.get("rest_days")),
    "clock":       lambda b: clock_band(b.get("body_clock")),
    "pen own":     lambda b: pen_band(b.get("pen_own")),
    "pen opp":     lambda b: pen_band(b.get("pen_opp")),
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
    """Either test clearing the bar convicts, and the label says which.

    They answer different questions and a slice can fail one without the
    other, so requiring both would let a real break hide behind stake
    variance. The bar is raised for the doubled number of looks in
    return — see `report`.
    """
    rate, unit = abs(s["z_rate"]) >= bar, abs(s["z"]) >= bar
    if rate and unit:
        return "CONVICTS"
    if rate:
        return "CONVICTS (rate)"
    if unit:
        return "CONVICTS (units)"
    return ""


def bets_needed(win_rate: float, be: float) -> float:
    """Settled bets for a win-rate gap this size to reach |z| = 2."""
    gap = abs(win_rate - be)
    if gap < 1e-9:
        return float("inf")
    return (2 * math.sqrt(be * (1 - be)) / gap) ** 2


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
    rate_sig, unit_sig = abs(top["z_rate"]) >= 2, abs(top["z"]) >= 2
    print()
    if rate_sig and unit_sig:
        print("  → SIGNIFICANT on both. The model picks below the rate these")
        print("    prices require, and the bankroll shows it.")
    elif rate_sig and not unit_sig:
        # The reading that needs saying out loud, because the two numbers
        # look like a contradiction and are not.
        print("  → SIGNIFICANT ON WIN RATE, not on units — and that is one")
        print("    finding, not two contradictory ones.")
        print()
        print("    The picks land well short of what these prices require:")
        print(f"    {top['win_rate']:.1%} against {top['breakeven']:.1%}, "
              f"z {top['z_rate']:+.2f}. That is a statement about the MODEL,")
        print("    and it is the one that is significant.")
        print()
        print("    The units test is quieter because stakes vary, and varying")
        print("    stakes add variance to the P&L that has nothing to do with")
        print("    pick quality. It is asking a different question — 'is the")
        print("    bankroll provably down' — and on this many bets it cannot")
        print("    yet say. Do not read that as the model being fine.")
    elif unit_sig and not rate_sig:
        print("  → SIGNIFICANT ON UNITS, not on win rate. The picks land")
        print("    about as often as the prices require, but the losses are")
        print("    landing on the bigger stakes. That is a sizing problem")
        print("    rather than a picking one.")
    else:
        need = bets_needed(top["win_rate"], top["breakeven"])
        print(f"  → NOT SIGNIFICANT on either test. A win-rate gap this size")
        print(f"    needs about {need:,.0f} settled bets to reach two sigma; "
              f"there are {top['n']}.")
        print("    The record cannot yet tell a broken model from a bad run.")
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
    # Two tests per slice, so two looks per slice. Correcting for the
    # slices and not for the tests would quietly halve the bar.
    bar = sidak_z(2 * len(cuts), alpha)
    print()
    print("=" * 74)
    print(f"SLICES — {len(cuts)} cut ×2 tests, so the bar is |z| ≥ {bar:.2f}")
    print(f"(a single look would be 1.96; {2 * len(cuts)} looks at "
          f"{alpha:.0%} family-wise is {bar:.2f})")
    print("=" * 74)
    print(f"  {'slice':<32}{'n':>5}{'W-L':>9}{'ROI':>8}"
          f"{'z:un':>7}{'z:rate':>8}{'CLV':>7}")
    print("  " + "-" * 74)
    cuts.sort(key=lambda c: (c[0], -max(abs(c[2]["z"]), abs(c[2]["z_rate"]))))
    convicted = []
    for dim, bucket, s in cuts:
        clv = f"{s['clv']:+.2f}" if s["clv"] is not None else "—"
        flag = _bar(s, bar)
        wl = f"{s['wins']}-{s['losses']}"
        print(f"  {(dim + ' · ' + str(bucket))[:31]:<32}{s['n']:>5}{wl:>9}"
              f"{s['roi']:>+8.1%}{s['z']:>+7.2f}{s['z_rate']:>+8.2f}{clv:>7}"
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
        for dim, bucket, s in sorted(
                convicted,
                key=lambda c: -max(abs(c[2]["z"]), abs(c[2]["z_rate"]))):
            print(f"  {dim} · {bucket}: {s['n']} bets, {s['roi']:+.1%}, "
                  f"z {s['z']:+.2f} on units / {s['z_rate']:+.2f} on rate "
                  f"— {_bar(s, bar)}")
            print(f"     survives a bar set for {2 * len(cuts)} "
                  f"simultaneous looks")
    for dim, bucket, s in whole:
        print(f"\n  ({dim} · {bucket} also clears, but it is {s['n']} of "
              f"{top['n']} bets —")
        print("   that is the headline relabelled, not a second finding.)")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description="Where the record is bleeding.")
    p.add_argument("--sport")
    p.add_argument("--category", default="main",
                   help="main (default), longshot, pricedout, loose — or 'all' to pool every bucket the way the miner and the hypothesis lab do")
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
