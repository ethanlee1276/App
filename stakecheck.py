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


def _rows(db: str, sport: str | None, since: str | None,
          measurement: bool = False):
    """Settled bets. BY DEFAULT, ONLY THE ONES THAT WERE REAL.

    THE MISTAKE THIS EXISTS TO PREVENT, made 2026-08-08 and caught by
    Ethan's own output rather than by me: the first version selected
    every settled row and reported 2,582 + 888 bets. The site's headline
    record is 292. The other three thousand are measurement buckets —
    `longshot` is journaled at a flat stake with ZERO dollar exposure,
    and `longshot_watch` was, in ledger.py's own words, "most of the
    journal by volume and all of the noise in it", a couple of hundred
    home-run rows a night.

    So every ROI in this tool's first three days of output described a
    population that was mostly paper. The tell was visible and I did not
    read it: 1,787 of 2,582 bets priced at +200 and longer, which is a
    home-run board, not a betting record.

    `ledger.py` scores the record as `category='main' AND stake_units >
    0`, and that is now the default here. Nothing else is a bet.
    """
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    q = ("SELECT date, sport, player, market, side, odds, hit_prob, grade, "
         "edge, stake_units, pnl_units, status, category, "
         "projection, line, actual FROM bets "
         "WHERE status IN ('won','lost')")
    if not measurement:
        q += " AND category='main' AND stake_units > 0"
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
    # WHAT IS IN THE SAMPLE, always, before any conclusion is drawn from
    # it. This line is here because its absence cost three days: the tool
    # reported 3,470 bets against a real record of 292 and nothing on
    # screen said the difference was paper.
    cats: dict = {}
    for r in rows:
        cats[r.get("category") or "?"] = cats.get(r.get("category") or "?", 0) + 1
    print("  bucket(s): " + ", ".join(f"{k} {v}" for k, v in sorted(cats.items())))
    if set(cats) - {"main"}:
        print("  ** measurement buckets included — `longshot` carries zero")
        print("  ** dollar exposure and `longshot_watch` is a calibration")
        print("  ** sample. Neither is money. Drop --include-measurement.")
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

    # --- the cap policies, replayed side by side ------------------------
    from engine.correlation import SLATE_CAP_U
    uni = simulate_uniform(rows, SLATE_CAP_U)
    trim = simulate_trim(rows, SLATE_CAP_U)
    if uni["kept"] or trim["kept"]:
        print("\n  CAP POLICIES, REPLAYED  (slate cap only — the journal "
              "stores the player\n  and the date but not the fixture, so the "
              "5u game cap cannot be modelled)")
        print(f"    {'policy':<28}{'kept':>6}{'dropped':>9}"
              f"{'staked':>10}{'net':>10}{'ROI':>9}")
        for label, s in (("uniform scale + floor drop", uni),
                         ("trim the weakest", trim)):
            if s["kept"]:
                print(f"    {label:<28}{s['kept']:>6}{s['dropped']:>9}"
                      f"{s['staked']:>9.2f}u{s['net']:>+9.2f}u"
                      f"{s['roi']:>9.2%}")
        print(f"    {'as actually staked':<28}{len(rows):>6}{0:>9}"
              f"{staked:>9.2f}u{net:>+9.2f}u{_roi(net, staked):>9.2%}")
        print("\n    Fair replays: dropping a bet does not change whether "
              "another won, and\n    no outcome decides which survive. The "
              "uniform line differs from the\n    asked-for ROI above by ONE "
              "thing — the low-Kelly tail the floor removes.")

    # --- does the model's probability mean anything? --------------------
    #
    # THE MEASUREMENT THE REST OF THIS TOOL WAS CIRCLING. Every line above
    # asks how the money was distributed. This one asks whether there was
    # an edge to distribute.
    #
    # Kelly stakes in proportion to claimed edge. If the claim is inflated
    # — and inflated most where it is most wrong — then staking more on a
    # bigger claim is staking more on a bigger error, and the ordering
    # flat > as-staked > asked-for is exactly what that looks like. Which
    # is the ordering the current era shows.
    #
    # A model that says 55% and hits 40% has no cap policy problem.
    cal = [r for r in rows if r.get("hit_prob") is not None]
    if cal:
        import math
        print("\n  CLAIMED vs REALIZED  (the model's own probability, "
              "against what happened)")
        print(f"    {'band':<20}{'bets':>6}{'claimed':>10}{'actual':>9}"
              f"{'gap':>9}{'noise (1 SE)':>14}")

        def _line(label, chunk):
            n = len(chunk)
            if not n:
                return
            claimed = sum(float(c["hit_prob"]) for c in chunk) / n
            actual = sum(1 for c in chunk if c["status"] == "won") / n
            se = math.sqrt(max(actual * (1 - actual), 1e-9) / n)
            print(f"    {label:<20}{n:>6}{claimed:>9.1%}{actual:>9.1%}"
                  f"{actual - claimed:>+9.1%}{'±' + format(se, '.1%'):>14}")

        _line("every bet", cal)
        for label in ("shorter than +100", "+100 to +119", "+120 to +199",
                      "+200 and longer"):
            _line(label, [c for c in cal if _band(int(c["odds"])) == label])
        print("\n    A negative gap wider than about two of those noise "
              "figures is the\n    model claiming an edge it does not have — "
              "and Kelly multiplies\n    that error rather than hedging it.")

    # --- is the ranking predictive at all? ------------------------------
    #
    # THE ASSUMPTION UNDER EVERY CAP RULE. Trimming a slate to fit means
    # choosing which bets to keep, and the only defensible basis is the
    # model's own pre-game confidence. If A+ does not beat B+ then no cap
    # policy can help, because there is nothing to sort on — and a rule
    # that keeps the top grades is then actively harmful.
    #
    # The last column is the one that matters: ROI at the stake the rules
    # asked for is exactly what a trim harvests from that grade.
    print("\n  IS THE GRADE PREDICTIVE?  (the ranking every cap rule sorts on)")
    print(f"    {'grade':<8}{'bets':>6}{'hit rate':>10}{'ROI as staked':>15}"
          f"{'ROI at asked':>14}")
    by_grade: dict = {}
    for r in rows:
        by_grade.setdefault(r.get("grade") or "?", []).append(r)
    # EVERY grade present, not a list of the ones I expected. The first
    # version iterated a hardcoded ("A+", "A", "B+", "Pass", "?") and
    # silently dropped 442 of 888 rows — the table added up to half the
    # sample and said so nowhere. A report that omits what it did not
    # anticipate is worse than one that crashes.
    _order = {"A+": 0, "A": 1, "B+": 2, "Pass": 8, "?": 9}
    for g in sorted(by_grade, key=lambda k: (_order.get(k, 5), k)):
        chunk = by_grade.get(g)
        if not chunk:
            continue
        s = sum(c["stake_units"] or 0.0 for c in chunk)
        n = sum(c["pnl_units"] or 0.0 for c in chunk)
        w = sum(1 for c in chunk if c["status"] == "won")
        wn = ws = 0.0
        for c in chunk:
            iw = intended_stake(c)
            if not iw:
                continue
            ws += iw
            wn += (american_to_decimal(int(c["odds"])) - 1.0) * iw \
                if c["status"] == "won" else -iw
        asked_roi = f"{_roi(wn, ws):+.1%}" if ws else "—"
        print(f"    {g:<8}{len(chunk):>6}{w / len(chunk):>9.1%}"
              f"{_roi(n, s):>14.1%}{asked_roi:>14}")
    print("\n    A+ below B+ in that last column means the confidence signal "
          "is\n    inverted, and no cap policy can fix a ranking that points "
          "the wrong way.")

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


_GRADE_RANK = {"A+": 3, "A": 2, "B+": 1}


def simulate_trim(rows: list[dict], cap: float) -> dict:
    """Replay the slate cap as TRIMMING instead of scaling.

    Ethan chose the rule on 2026-08-08 and it shipped the same day. This
    replays it against the bets already settled, so the choice can be
    checked before more money goes through it.

    IT IS A FAIR REPLAY, not a fitted one. Dropping a bet does not change
    whether any other bet won, so the surviving subset's P&L is exactly
    what it would have been. Nothing is refitted and no outcome is used
    to decide what to keep — the ranking is the model's own pre-game
    grade and edge.

    TWO HONEST LIMITS.

    Only the SLATE cap is simulated. The 5u per-game cap needs to know
    which bets shared a game, and the journal stores the player and the
    date but not the fixture. The slate cap is the larger lever here by
    far — the model asked for roughly six times it — but the game cap
    would drop more bets still, so this is a floor on how much gets cut,
    not a forecast of it.

    And the live rule ranks on `quality` first, which is not journaled.
    This ranks on grade then edge, the two that are. If the simulation
    and the shipped rule ever disagree it will be here.
    """
    from collections import defaultdict
    slates = defaultdict(list)
    for r in rows:
        w = intended_stake(r)
        if w:
            slates[(r["sport"], r["date"])].append((r, w))

    kept_n = dropped_n = 0
    net = staked = 0.0
    for bets in slates.values():
        order = sorted(bets, key=lambda rw: (
            _GRADE_RANK.get(rw[0].get("grade") or "", 0),
            float(rw[0].get("edge") or 0.0)), reverse=True)   # strongest first
        running = 0.0
        full = False
        for r, w in order:
            # STOP, do not skip. The shipped rule drops from the weakest
            # end until the total fits, which keeps the strongest PREFIX.
            # Skipping an over-large bet and taking smaller weaker ones
            # behind it would pack the budget fuller and model a rule that
            # does not exist — a simulation of the wrong thing is worse
            # than no simulation.
            if full or running + w > cap:
                full = True
                dropped_n += 1
                continue
            running += w
            staked += w
            kept_n += 1
            net += (american_to_decimal(int(r["odds"])) - 1.0) * w \
                if r["status"] == "won" else -w
    return {"kept": kept_n, "dropped": dropped_n, "net": net,
            "staked": staked, "roi": _roi(net, staked),
            "slates": len(slates)}


def simulate_uniform(rows: list[dict], cap: float) -> dict:
    """Replay the slate cap as ONE uniform scale plus a floor drop.

    The policy that shipped 2026-08-08 after the trim replay came back
    against trimming. Same replay discipline: nothing refitted, no
    outcome touches which bets survive.

    The interesting property is that this is ALMOST ROI-neutral by
    construction. A uniform factor cannot move the ratio at all; the only
    thing that can is the floor drop, which removes the smallest
    intended stakes. So the gap between this line and the asked-for line
    is a clean measurement of one thing: what dropping the low-Kelly tail
    costs or earns. Nothing else differs.

    Same limits as `simulate_trim`: slate cap only, because the journal
    stores the player and the date but not the fixture.
    """
    from collections import defaultdict
    from engine.staking import MIN_STAKE_UNITS

    slates = defaultdict(list)
    for r in rows:
        w = intended_stake(r)
        if w:
            slates[(r["sport"], r["date"])].append((r, w))

    kept_n = dropped_n = 0
    net = staked = 0.0
    for bets in slates.values():
        total = sum(w for _, w in bets)
        factor = min(1.0, cap / total) if total else 1.0
        for r, w in bets:
            s = w * factor
            if s < MIN_STAKE_UNITS:
                dropped_n += 1
                continue
            kept_n += 1
            staked += s
            net += (american_to_decimal(int(r["odds"])) - 1.0) * s \
                if r["status"] == "won" else -s
    return {"kept": kept_n, "dropped": dropped_n, "net": net,
            "staked": staked, "roi": _roi(net, staked),
            "slates": len(slates)}


def fit_report(rows: list[dict]) -> None:
    """Fit the overconfidence on one era, test it on the next.

    THE FINDING THIS ANSWERS, measured 2026-08-09 on 292 real bets:

        old era   claimed 59.7%   actual 49.7%   gap -9.9%  (2.8 SE)
        new era   claimed 51.3%   actual 40.0%   gap -11.3% (2.3 SE)
        pooled    claimed 57.0%   actual 46.5%   gap -10.4% (3.6 SE)

    Two independent samples, the same answer, and pooled it is past three
    standard errors. The model claims about ten points more than it
    delivers, and Kelly stakes in proportion to the claim.

    WHY THIS FITS FROM THE JOURNAL AND NOT FROM history.db, which is
    where `calibrate.py` fits today. history.db holds projections against
    outcomes for every player-game. The journal holds only the bets we
    MADE — which is a selected sample, selected by the model's own error.
    A bet exists precisely when the model's estimate sat far enough above
    the market's, so the bets placed are the ones where an overestimate
    was most likely. Fitting on all projections cannot see that; fitting
    on the journal is the only place it shows up.

    OUT OF SAMPLE, because a correction fitted and tested on the same
    rows will always look like it worked. The unit-scale change on
    2026-08-04 gives a natural split, and the fit never sees the test
    era. The numbers below are therefore honest about the correction's
    value and NOT a promise about the future — 95 held-out bets is a
    small test and the eras differ in more than sizing.
    """
    from engine.calibrate import apply_temperature, brier, fit_correction

    train = [r for r in rows if (r["date"] or "") < RESCALE_DAY
             and r.get("hit_prob") is not None]
    test = [r for r in rows if (r["date"] or "") >= RESCALE_DAY
            and r.get("hit_prob") is not None]
    if len(train) < 50 or len(test) < 20:
        print(f"\nNot enough on one side of {RESCALE_DAY} to fit and test "
              f"({len(train)} / {len(test)}). Nothing fitted.")
        return

    pairs = [(float(r["hit_prob"]), 1 if r["status"] == "won" else 0)
             for r in train]
    # The library floor is 200 and the training era is 197. Lowered on
    # purpose and said out loud: this is a diagnostic, not a fit anyone
    # should ship off 197 rows.
    t, b = fit_correction(pairs, min_samples=50)

    print(f"\n{'='*70}\n  FITTING THE OVERCONFIDENCE, OUT OF SAMPLE\n{'='*70}")
    print(f"    fit on   {train[0]['date']} → {train[-1]['date']}   "
          f"{len(train)} bets")
    print(f"    test on  {test[0]['date']} → {test[-1]['date']}   "
          f"{len(test)} bets")
    print(f"\n    fitted correction: temperature {t:.2f}, intercept {b:+.2f}")
    # Describe what was FITTED, not what I expected to be fitted. A
    # constant bias is absorbed almost entirely by the intercept and can
    # leave the temperature below 1, so a line that always says "shrinks
    # toward 50%" would be describing the wrong correction half the time.
    print("      temperature " + (
        f"{t:.2f} — every probability pulled toward 50%" if t > 1.02 else
        f"{t:.2f} — spread left alone" if t > 0.98 else
        f"{t:.2f} — spread widened, so the bias is in the shift below"))
    print("      intercept   " + (
        f"{b:+.2f} — the whole book moved DOWN, which is the model "
        f"claiming\n                  more than it delivers on every bet"
        if b < -0.02 else
        f"{b:+.2f} — the whole book moved up" if b > 0.02 else
        f"{b:+.2f} — no systematic shift"))

    tp = [(float(r["hit_prob"]), 1 if r["status"] == "won" else 0)
          for r in test]
    before, after = brier(tp, 1.0, 0.0), brier(tp, t, b)
    claimed = sum(p for p, _ in tp) / len(tp)
    corrected = sum(apply_temperature(p, t, b) for p, _ in tp) / len(tp)
    actual = sum(o for _, o in tp) / len(tp)
    print(f"\n  ON THE HELD-OUT ERA")
    print(f"    mean claimed   {claimed:>7.1%}  →  {corrected:>7.1%} corrected")
    print(f"    actually won   {actual:>7.1%}")
    print(f"    gap            {actual - claimed:>+7.1%}  →  "
          f"{actual - corrected:>+7.1%}")
    print(f"    Brier          {before:>7.4f}  →  {after:>7.4f}"
          f"   ({'better' if after < before else 'WORSE'})")

    # --- and what it would have stopped us betting ----------------------
    kept, dropped = [], 0
    for r in test:
        p = apply_temperature(float(r["hit_prob"]), t, b)
        breakeven = 1.0 / american_to_decimal(int(r["odds"]))
        if p > breakeven:
            kept.append(r)
        else:
            dropped += 1
    print(f"\n  WHAT IT WOULD HAVE STOPPED")
    print(f"    {dropped} of {len(test)} bets no longer clear BREAK-EVEN at "
          f"the price taken —")
    print(f"    not the model's gates, just the arithmetic of the odds.")
    if kept:
        s = sum(r["stake_units"] or 0.0 for r in kept)
        n = sum(r["pnl_units"] or 0.0 for r in kept)
        w = sum(1 for r in kept if r["status"] == "won")
        print(f"    the {len(kept)} that survive: {w}-{len(kept) - w}, "
              f"{n:+.2f}u on {s:.2f}u staked, ROI {_roi(n, s):+.2%}")
        ts = sum(r["stake_units"] or 0.0 for r in test)
        tn = sum(r["pnl_units"] or 0.0 for r in test)
        print(f"    against all {len(test)}:      "
              f"{sum(1 for r in test if r['status'] == 'won')}-"
              f"{len(test) - sum(1 for r in test if r['status'] == 'won')}, "
              f"{tn:+.2f}u on {ts:.2f}u staked, ROI {_roi(tn, ts):+.2%}")
    print("\n    A fair replay — the survivors are chosen by a correction "
          "fitted on\n    an earlier era and a price known before kickoff. "
          "No outcome is read.\n    It is still 95 bets. Treat it as a "
          "direction, not a number.")


def spread_report(rows: list[dict]) -> None:
    """Is the model's projection distribution too narrow?

    THE HYPOTHESIS, and why it is worth testing before applying the
    shrinkage. `--fit` recovered a temperature of 1.64, meaning every
    probability has to be pulled hard toward 50%. Probabilities that are
    too extreme in BOTH directions is the signature of one specific
    defect: a projection whose spread is understated.

    If the model believes a hitter's total bases are 1.4 ± 0.5 when they
    are really 1.4 ± 0.75, its mean is perfect and its probabilities are
    still wrong — P(over 1.5) comes out further from 50% than it should.
    Correcting that with a temperature works. Fixing the spread works
    better, because it keeps the bets whose edge is real instead of
    shrinking those too.

    HOW IT IS CHECKED, using only columns the journal already stores. A
    probability at a line implies a spread:

        OVER :  (line - projection) / sigma = invcdf(1 - hit_prob)
        UNDER:  (line - projection) / sigma = invcdf(hit_prob)

    so sigma falls out. Against it stands the spread that actually
    happened — the standard deviation of (actual - projection) over the
    same bets. A ratio above 1 means reality is wider than the model
    thought, and the ratio itself is roughly the temperature that would
    be needed to paper over it.

    THREE LIMITS, stated because this is an approximation and reads like
    a measurement:

      * it assumes a normal shape to invert. Several of these markets are
        counts and are priced from discrete distributions, so sigma here
        is "the normal spread that would produce this probability", not
        a number the model holds.
      * a bet near its own line carries almost no information about
        spread — dividing by a z-score near zero explodes. Those rows are
        dropped, which biases the sample toward confident calls.
      * the journal is a selected sample. Selection is on the model's
        mean against the market, not on the outcome, so the realized
        spread is still a fair estimate — but the bets are not a random
        draw and the two columns are not measured on identical footing.
    """
    from statistics import NormalDist, StatisticsError, stdev
    nd = NormalDist()

    by_market: dict = {}
    for r in rows:
        proj, line, p = r.get("projection"), r.get("line"), r.get("hit_prob")
        act = r.get("actual")
        if proj is None or line is None or p is None or act is None:
            continue
        if not 0.02 < float(p) < 0.98:
            continue
        side = (r.get("side") or "OVER").upper()
        z = nd.inv_cdf(1 - float(p)) if side == "OVER" else nd.inv_cdf(float(p))
        if abs(z) < 0.15:            # the bet sits on its own line
            continue
        sigma = (float(line) - float(proj)) / z
        if sigma <= 0:
            continue
        by_market.setdefault(r.get("market") or "?", []).append(
            (sigma, float(act) - float(proj)))

    if not by_market:
        print("\n  No row carries projection, line, hit_prob and actual "
              "together — nothing to check.")
        return

    print(f"\n{'='*70}\n  IS THE PROJECTION'S SPREAD TOO NARROW?\n{'='*70}")
    print("  The model's own probability at its own line implies a spread.")
    print("  Beside it: the spread that actually happened.\n")
    print(f"    {'market':<16}{'bets':>6}{'model sigma':>13}"
          f"{'real sigma':>12}{'ratio':>8}")
    tot_i = tot_r = 0.0
    tot_n = 0
    for m in sorted(by_market, key=lambda k: -len(by_market[k])):
        pairs = by_market[m]
        if len(pairs) < 8:
            continue
        imp = sum(s for s, _ in pairs) / len(pairs)
        try:
            real = stdev([d for _, d in pairs])
        except StatisticsError:
            continue
        tot_i += imp * len(pairs)
        tot_r += real * len(pairs)
        tot_n += len(pairs)
        print(f"    {m:<16}{len(pairs):>6}{imp:>13.3f}{real:>12.3f}"
              f"{real / imp if imp else 0:>8.2f}")
    if tot_n:
        ratio = (tot_r / tot_n) / (tot_i / tot_n)
        print(f"    {'ALL':<16}{tot_n:>6}{tot_i / tot_n:>13.3f}"
              f"{tot_r / tot_n:>12.3f}{ratio:>8.2f}")
        print(f"\n  A ratio near 1.00 means the spread is honest and the "
              f"overconfidence\n  comes from the MEAN being wrong, or from "
              f"selection. Above about 1.2\n  means the distribution is too "
              f"narrow, and the ratio is roughly the\n  temperature needed to "
              f"cover for it — compare it to the {1.64:.2f} that\n  --fit "
              f"recovered. If they match, that is the root cause named.")
    print("\n  Approximate: normal shape assumed to invert, bets sitting on "
          "their own\n  line dropped, and the sample is selected. See "
          "spread_report's docstring.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/ledger.db")
    ap.add_argument("--sport")
    ap.add_argument("--since", help="ISO date; only bets on or after it")
    ap.add_argument("--spread", action="store_true",
                    help="check whether the projections' distributions are "
                         "too narrow — the defect a large fitted temperature "
                         "points at. Reports only")
    ap.add_argument("--fit", action="store_true",
                    help="fit the model's overconfidence on the pre-rescale "
                         "era and test it on the current one. Reports only; "
                         "writes nothing and changes no model")
    ap.add_argument("--include-measurement", action="store_true",
                    help="also count the longshot and longshot_watch "
                         "buckets. They are NOT money — zero dollar "
                         "exposure and a calibration sample — so this is "
                         "for inspecting them, never for judging a record")
    ap.add_argument("--all-eras", action="store_true",
                    help="one combined report instead of splitting at the "
                         "day the unit scale changed")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"No ledger at {args.db}.")
        return
    rows = _rows(args.db, args.sport, args.since,
                 measurement=args.include_measurement)
    if args.spread:
        spread_report(rows)
        print("\n  read-only; nothing was written.\n")
        return
    if args.fit:
        fit_report(rows)
        print("\n  read-only; nothing was written.\n")
        return
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
