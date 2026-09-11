#!/usr/bin/env python3
"""Does the home-run model actually rank longshots, or just price them?

    python3 longshot_skill.py

The settled bucket says the model is well calibrated overall (claimed
12.75%, delivered 13.55%) and still lost 13.4%, because winners came in
at +539 while losers averaged +698. Calibration answers "is the average
right"; it says nothing about whether the model can tell one longshot
from another. That is discrimination, and it is what would have to
improve for this board to ever be bettable.

Two things get measured, both from the journal alone:

  * **rank skill** — split settled long shots into quantiles by the
    model's claimed probability and compare hit rates. If the top group
    hits meaningfully more than the bottom, there is signal to sharpen.
    If the groups are flat, the model is not ranking at all and no amount
    of tuning the existing inputs will fix it.
  * **where the money went** — hit rate and ROI by price band, because
    the board's selection rule (expected value) is drawn toward the
    longest prices, which is exactly where the market's tax is heaviest.
"""

from __future__ import annotations

import argparse
from engine import ledger


def _bucket_stats(rows):
    n = len(rows)
    if not n:
        return None
    wins = sum(1 for r in rows if r["status"] == "won")
    net = sum(r["pnl_units"] or 0 for r in rows)
    staked = sum(r["stake_units"] or 0 for r in rows)
    return {
        "n": n, "wins": wins, "hit": wins / n,
        "model_p": sum(r["hit_prob"] or 0 for r in rows) / n,
        "avg_odds": sum(r["odds"] for r in rows) / n,
        "roi": net / staked if staked else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ledger.db")
    ap.add_argument("--groups", type=int, default=4)
    args = ap.parse_args()

    conn = ledger.connect(args.db)
    rows = [dict(r) for r in conn.execute(
        "SELECT status, odds, hit_prob, pnl_units, stake_units FROM bets "
        "WHERE category='longshot' AND status IN ('won','lost') "
        "AND hit_prob IS NOT NULL ORDER BY hit_prob")]
    if len(rows) < 40:
        print(f"Only {len(rows)} settled long shots — too few to measure "
              f"ranking skill. Come back after a few more slates.")
        return

    overall = _bucket_stats(rows)
    print(f"\n{overall['n']} settled long shots · model said "
          f"{overall['model_p']:.1%} · actually hit {overall['hit']:.1%} · "
          f"ROI {overall['roi']:+.1%}\n")

    # --- can it rank? -------------------------------------------------
    g = args.groups
    size = len(rows) // g
    print(f"RANK SKILL — split into {g} groups by the model's own probability")
    hdr = f"  {'group':<22}{'n':>6}{'model':>9}{'actual':>9}{'avg odds':>10}{'ROI':>9}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    stats = []
    for i in range(g):
        chunk = rows[i * size:(i + 1) * size] if i < g - 1 else rows[i * size:]
        st = _bucket_stats(chunk)
        stats.append(st)
        label = f"{'lowest' if i == 0 else 'highest' if i == g - 1 else f'group {i + 1}'}"
        print(f"  {label:<22}{st['n']:>6}{st['model_p']:>8.1%}{st['hit']:>9.1%}"
              f"{st['avg_odds']:>+10.0f}{st['roi']:>+9.1%}")

    lo, hi = stats[0], stats[-1]
    spread = hi["hit"] - lo["hit"]
    print(f"\n  top group hit {hi['hit']:.1%} vs bottom {lo['hit']:.1%} "
          f"→ spread {spread * 100:+.1f} pts")
    # Rough significance of the difference in two proportions.
    import math
    p = (hi["wins"] + lo["wins"]) / (hi["n"] + lo["n"])
    se = math.sqrt(p * (1 - p) * (1 / hi["n"] + 1 / lo["n"])) or 1e-9
    z = spread / se
    print(f"  z = {z:.2f}")
    if z > 1.64:
        print("  → The model DOES rank longshots. Sharpening is worth doing:\n"
              "    bet only the top group and the tax gets easier to clear.")
    elif z < -1.64:
        print("  → The ranking is INVERTED — the ones it likes least hit most.\n"
              "    Something in the selection is backwards; that is a bug, not tuning.")
    else:
        print("  → No measurable ranking skill yet. The model prices the group\n"
              "    correctly on average but cannot tell members apart, so tuning\n"
              "    the existing inputs will not help — it needs a signal it does\n"
              "    not currently have (park/pitcher/batted-ball splits), or more\n"
              "    settled bets before this test can see anything.")

    # --- where the money went ----------------------------------------
    print("\nBY PRICE — the board's EV rule is pulled toward the longest odds,")
    print("which is exactly where the market's tax is heaviest.")
    bands = [(0, 400, "+399 and shorter"), (400, 700, "+400 to +699"),
             (700, 1100, "+700 to +1099"), (1100, 10 ** 9, "+1100 and out")]
    print(f"  {'band':<22}{'n':>6}{'model':>9}{'actual':>9}{'ROI':>9}")
    for lo_o, hi_o, label in bands:
        chunk = [r for r in rows if lo_o <= r["odds"] < hi_o]
        if len(chunk) < 15:
            continue
        st = _bucket_stats(chunk)
        print(f"  {label:<22}{st['n']:>6}{st['model_p']:>8.1%}"
              f"{st['hit']:>9.1%}{st['roi']:>+9.1%}")


if __name__ == "__main__":
    main()
