#!/usr/bin/env python3
"""What we actually staked, against what the sizing rules asked for.

Ethan, 2026-08-08, reading the settled list on his phone: "Look at the
amount of money spent on each bet compared to the amount of money being
returned. We got .05 units back for a +100 bet. Our units per bet is too
low or something."

He is right that the arithmetic does not close, and the reason is
checkable rather than arguable. A +106 winner returning 0.05u was staked
0.047u — BELOW `staking.MIN_STAKE_UNITS`, which is 0.1 and is supposed to
be a floor. Nothing in the sizing path can emit that number. Something
downstream of the floor is shrinking stakes.

WHAT THIS TOOL IS FOR. The ledger stores `hit_prob` and `odds` on every
bet, which is everything quarter-Kelly needs, so the stake each bet was
SUPPOSED to get can be recomputed exactly and diffed against the stake it
actually carries. That turns "the numbers feel off" into a number.

And it answers the only question that matters about a bad ROI, which is
which half of the machine is producing it:

    if flat-staked ROI is much better than actual   -> sizing
    if flat-staked ROI is also bad                  -> the model

Those have opposite fixes and the headline figure cannot tell them apart.

READ-ONLY. It opens the ledger in immutable mode and writes nothing.

    python3 stakecheck.py
    python3 stakecheck.py --sport mlb
    python3 stakecheck.py --since 2026-08-04     # post-rescale only
    python3 stakecheck.py --db data/ledger.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.odds import american_to_decimal
from engine.staking import (BANKROLL_UNITS, MIN_STAKE_UNITS, kelly_units,
                            price_cap_units)
from engine.quality import STAKE_CAP_U

# The day the unit scale changed (commit 3f86208, "One scale for every
# stake"). Stakes before it were sized on a 20-unit bankroll and are NOT
# comparable to today's rules — restating them would be inventing a
# history we did not bet. Reported separately, never mixed.
RESCALE_DAY = "2026-08-04"


def _rows(db: str, sport: str | None, since: str | None):
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    q = ("SELECT date, sport, player, market, side, odds, hit_prob, grade, "
         "stake_units, pnl_units, status, category FROM bets "
         "WHERE status IN ('won','lost')")
    args: list = []
    if sport:
        q += " AND sport = ?"
        args.append(sport)
    if since:
        q += " AND date >= ?"
        args.append(since)
    out = [dict(r) for r in conn.execute(q + " ORDER BY date", args)]
    conn.close()
    return out


def intended_stake(r: dict) -> float | None:
    """The stake the sizing rules ask for, recomputed from what is stored.

    None when the row lacks the inputs — an old bet with no `hit_prob`
    cannot be re-derived, and guessing one would put a fabricated number
    in the middle of a measurement.
    """
    p, odds = r.get("hit_prob"), r.get("odds")
    if p is None or odds is None:
        return None
    cap = STAKE_CAP_U.get(r.get("grade") or "", float("inf"))
    return kelly_units(float(p), int(odds), 0.25, cap)


def _roi(net: float, staked: float) -> float:
    return net / staked if staked else 0.0


def _flat(rows: list[dict]) -> tuple[float, float]:
    """(net, staked) if every one of these had been a flat 1u bet.

    The comparison is deliberately crude. It is not a proposal — flat
    staking throws away the whole point of Kelly. It is a control: the
    same bets, the same outcomes, one variable removed.
    """
    net = 0.0
    for r in rows:
        if r["status"] == "won":
            net += american_to_decimal(int(r["odds"])) - 1.0
        else:
            net -= 1.0
    return net, float(len(rows))


def _band(odds: int) -> str:
    if odds >= 200:
        return "+200 and longer"
    if odds >= 120:
        return "+120 to +199"
    if odds >= 100:
        return "+100 to +119"
    return "shorter than +100"


def report(rows: list[dict]) -> None:
    if not rows:
        print("No settled bets match. Nothing to measure.")
        return

    staked = sum(r["stake_units"] or 0.0 for r in rows)
    net = sum(r["pnl_units"] or 0.0 for r in rows)
    won = sum(1 for r in rows if r["status"] == "won")
    fnet, fstaked = _flat(rows)

    print(f"\n{'='*70}\n  {len(rows)} settled bets  ·  "
          f"{rows[0]['date']} → {rows[-1]['date']}\n{'='*70}")
    print(f"\n  AS STAKED       {won}-{len(rows)-won}   "
          f"{staked:8.2f}u staked   {net:+8.2f}u   ROI {_roi(net, staked):+7.2%}")
    print(f"  AT FLAT 1u      {won}-{len(rows)-won}   "
          f"{fstaked:8.2f}u staked   {fnet:+8.2f}u   ROI {_roi(fnet, fstaked):+7.2%}")
    print("\n  Same bets, same results, one variable removed. A large gap "
          "between\n  these two lines is the sizing; no gap means the model.")

    # --- the floor -----------------------------------------------------
    below = [r for r in rows
             if 0 < (r["stake_units"] or 0) < MIN_STAKE_UNITS]
    zero = [r for r in rows if (r["stake_units"] or 0) == 0]
    print(f"\n  BELOW THE {MIN_STAKE_UNITS}u FLOOR")
    print(f"    {len(below):>4} settled bet(s) staked under the documented "
          f"minimum")
    print(f"    {len(zero):>4} settled bet(s) staked ZERO — graded into the "
          f"win/loss record,")
    print(f"         contributing nothing to P&L, which flatters or "
          f"flattens the line")
    if below:
        lo = min(r["stake_units"] for r in below)
        print(f"    smallest: {lo:.3f}u  "
              f"({below[0]['player']} {below[0]['market']}, "
              f"{below[0]['date']})")
        print(f"    `staking.to_units` cannot emit these. Whatever produced "
              f"them ran AFTER\n         the floor was applied — see "
              f"`correlation.apply_exposure_caps`.")

    # --- intended vs actual ---------------------------------------------
    have = [(r, intended_stake(r)) for r in rows]
    have = [(r, w) for r, w in have if w is not None]
    if have:
        want_t = sum(w for _, w in have)
        got_t = sum(r["stake_units"] or 0.0 for r, _ in have)
        shrunk = [(r, w) for r, w in have
                  if (r["stake_units"] or 0) < w - 0.005]
        print(f"\n  WHAT THE RULES ASKED FOR  (quarter-Kelly from the stored "
              f"hit_prob\n  and odds, capped by grade and by price — the same "
              f"path the bet took)")
        print(f"    asked  {want_t:8.2f}u   over {len(have)} bets")
        print(f"    staked {got_t:8.2f}u   "
              f"({got_t / want_t:.1%} of it)" if want_t else "")
        print(f"    {len(shrunk)} bet(s) carry LESS than the rules asked for")
        # And what the P&L would have been at the asked-for size.
        wnet = 0.0
        for r, w in have:
            wnet += (american_to_decimal(int(r["odds"])) - 1.0) * w \
                if r["status"] == "won" else -w
        print(f"\n    at the asked-for stakes: {wnet:+8.2f}u   "
              f"ROI {_roi(wnet, want_t):+7.2%}")
        print(f"    as actually staked:      "
              f"{sum(r['pnl_units'] or 0 for r, _ in have):+8.2f}u   "
              f"ROI {_roi(sum(r['pnl_units'] or 0 for r, _ in have), got_t):+7.2%}")

    # --- does stake size predict the result? ----------------------------
    print("\n  DOES STAKE SIZE PREDICT THE RESULT?")
    print("    If we bet more on the ones we lose, ROI is worse than the "
          "hit rate\n    deserves and no model change fixes it.\n")
    ranked = sorted(rows, key=lambda r: r["stake_units"] or 0.0)
    k = max(1, len(ranked) // 4)
    print(f"    {'quartile':<12}{'bets':>6}{'avg stake':>11}"
          f"{'hit rate':>10}{'ROI':>10}")
    for i, label in enumerate(("smallest", "2nd", "3rd", "largest")):
        chunk = ranked[i * k:(i + 1) * k] if i < 3 else ranked[3 * k:]
        if not chunk:
            continue
        s = sum(c["stake_units"] or 0.0 for c in chunk)
        n = sum(c["pnl_units"] or 0.0 for c in chunk)
        w = sum(1 for c in chunk if c["status"] == "won")
        print(f"    {label:<12}{len(chunk):>6}{s / len(chunk):>10.3f}u"
              f"{w / len(chunk):>9.1%}{_roi(n, s):>10.1%}")

    # --- by price band ---------------------------------------------------
    print("\n  BY PRICE BAND  (the other lever — `staking.price_cap_units`)")
    print(f"    {'band':<20}{'bets':>6}{'avg stake':>11}{'cap':>8}"
          f"{'hit rate':>10}{'ROI':>10}")
    bands: dict[str, list] = {}
    for r in rows:
        bands.setdefault(_band(int(r["odds"])), []).append(r)
    for label in ("shorter than +100", "+100 to +119", "+120 to +199",
                  "+200 and longer"):
        chunk = bands.get(label)
        if not chunk:
            continue
        s = sum(c["stake_units"] or 0.0 for c in chunk)
        n = sum(c["pnl_units"] or 0.0 for c in chunk)
        w = sum(1 for c in chunk if c["status"] == "won")
        cap = price_cap_units(int(chunk[0]["odds"]))
        cap_s = "—" if cap == float("inf") else f"{cap:.1f}u"
        print(f"    {label:<20}{len(chunk):>6}{s / len(chunk):>10.3f}u"
              f"{cap_s:>8}{w / len(chunk):>9.1%}{_roi(n, s):>10.1%}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/ledger.db")
    ap.add_argument("--sport")
    ap.add_argument("--since", help="ISO date; only bets on or after it")
    ap.add_argument("--all-eras", action="store_true",
                    help="one combined report instead of splitting at the "
                         "day the unit scale changed")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"No ledger at {args.db}.")
        return
    rows = _rows(args.db, args.sport, args.since)
    if args.all_eras or args.since:
        report(rows)
    else:
        old = [r for r in rows if (r["date"] or "") < RESCALE_DAY]
        new = [r for r in rows if (r["date"] or "") >= RESCALE_DAY]
        if old:
            print(f"\n### BEFORE {RESCALE_DAY} — the 20-unit-bankroll era.")
            print("### Sized by rules that no longer exist. Shown because "
                  "it is most of\n### the record, and ignored when judging "
                  "the rules in force today.")
            report(old)
        if new:
            print(f"\n\n### FROM {RESCALE_DAY} — the current 1u = 1% scale. "
                  "THIS is the one\n### that says whether the sizing in "
                  "force right now is working.")
            report(new)
        if not old and not new:
            report(rows)
    print(f"\n  scale: 1u = 1/{BANKROLL_UNITS:.0f} of bankroll · "
          f"floor {MIN_STAKE_UNITS}u · grade caps "
          + ", ".join(f"{g} {c}u" for g, c in STAKE_CAP_U.items()))
    print("  read-only; nothing was written.\n")


if __name__ == "__main__":
    main()
