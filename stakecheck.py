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
          measurement: bool = False, category: str | None = None):
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
    args: list = []
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    q = ("SELECT date, sport, player, market, side, odds, hit_prob, grade, "
         "edge, stake_units, pnl_units, status, category, closing_odds, "
         "line FROM bets "
         "WHERE status IN ('won','lost')")
    if category:
        q += " AND category=? AND stake_units > 0"
        args_pre = [category]
    elif not measurement:
        q += " AND category='main' AND stake_units > 0"
        args_pre = []
    else:
        args_pre = []
    if sport:
        q += " AND sport = ?"
        args.append(sport)
    if since:
        q += " AND date >= ?"
        args.append(since)
    out = [dict(r) for r in conn.execute(q + " ORDER BY date",
                                        args_pre + args)]
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
    return kelly_units(float(p), int(odds), 0.25)


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


def _auc(scores: list[float], labels: list[int]) -> float | None:
    """Probability that a random winner outranks a random loser.

    Mann-Whitney U, computed on MIDRANKS so ties count as half a win
    rather than as a coin flip resolved by list order. That matters here:
    prices cluster hard on round numbers, so dozens of bets share an
    implied probability exactly, and sorting them arbitrarily would let
    the answer depend on the order rows came out of SQLite.

    0.5 is no discrimination at all. Below 0.5 means the score sorts
    winners BELOW losers, which is information pointing backwards.
    """
    pairs = sorted(zip(scores, labels))
    n = len(pairs)
    ranks = [0.0] * n
    i = 0
    while i < n:                      # average the ranks within each tie
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        mid = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = mid
        i = j + 1
    pos = sum(1 for _, y in pairs if y)
    neg = n - pos
    if not pos or not neg:
        return None                   # all winners or all losers: undefined
    rank_sum = sum(r for r, (_, y) in zip(ranks, pairs) if y)
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def _boot_auc(scores, labels, reps: int = 2000, seed: int = 20260809):
    """Percentile bootstrap CI for one AUC."""
    import random
    rng = random.Random(seed)
    n = len(scores)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        a = _auc([scores[i] for i in idx], [labels[i] for i in idx])
        if a is not None:
            out.append(a)
    if len(out) < reps // 2:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def _boot_auc_diff(a_scores, b_scores, labels, reps: int = 2000,
                   seed: int = 20260809):
    """PAIRED bootstrap of AUC(a) − AUC(b).

    Paired because both scores describe the SAME bets: resampling them
    independently would throw away the correlation between the model's
    number and the market's, and that correlation is most of what makes
    the difference measurable at this sample size.
    """
    import random
    rng = random.Random(seed)
    n = len(labels)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        ys = [labels[i] for i in idx]
        aa = _auc([a_scores[i] for i in idx], ys)
        bb = _auc([b_scores[i] for i in idx], ys)
        if aa is not None and bb is not None:
            out.append(aa - bb)
    if len(out) < reps // 2:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def info_report(rows: list[dict]) -> None:
    """DOES OUR NUMBER KNOW ANYTHING THE PRICE DOESN'T?

    CLV answers a different question — "did the market move toward us?" —
    and a null there is what a merely-decent model would produce anyway,
    because this book is far too small to move a line. So a flat CLV
    cannot distinguish "the model is worthless" from "the model is fine
    and we are simply not sharp enough to be front-run".

    This can. Rank every settled bet three ways and ask which ranking
    sorts winners above losers:

        the model's hit_prob
        the market's implied probability, from the price we took
        THE CLAIMED EDGE ITSELF (hit_prob − implied)

    The third is the one that decides things. Every gate, threshold and
    stake rule in this repo is a function of `edge`. If bets with more
    claimed edge do not win more often than bets with less, then `edge`
    is noise, and no amount of tuning a threshold on a noise variable
    produces money. That is a much sharper statement than "no CLV", and
    it is answerable from data already sitting in the journal.

    AUC is rank-based, which is what makes it usable on the prices we
    actually paid: the vig shifts every implied probability up by roughly
    the same amount, and a monotone shift cannot change a ranking. No
    de-vigging, no fair-value reconstruction, nothing to get wrong.

    WHAT IT CANNOT SAY. These are the bets we chose to make, so every
    number here is conditional on that selection. The model's AUC is not
    "how good the model is at baseball", it is "how well it sorted the
    spots it liked". That is the right question for deciding whether to
    keep betting this way, and the wrong one for deciding whether the
    projections have any merit in general.
    """
    from engine.odds import american_to_prob
    use = [r for r in rows
           if r["status"] in ("won", "lost")
           and r.get("hit_prob") is not None and r.get("odds") is not None]
    print(f"\n{'='*70}\n  DOES OUR NUMBER KNOW ANYTHING THE PRICE DOESN'T?"
          f"\n{'='*70}")
    if len(use) < 40:
        print(f"  {len(use)} settled bets carry both a hit_prob and a price. "
              f"Too few\n  to rank anything — this needs a couple of hundred "
              f"before the\n  intervals are narrower than the effect.")
        return
    y = [1 if r["status"] == "won" else 0 for r in use]
    model = [float(r["hit_prob"]) for r in use]
    market = [american_to_prob(int(r["odds"])) for r in use]
    edge = [m - k for m, k in zip(model, market)]
    wins = sum(y)
    print(f"  {len(use)} settled bets, {wins} winners and {len(use)-wins} "
          f"losers.")
    print(f"  AUC = the chance a random winner is ranked above a random "
          f"loser.\n  0.50 is a coin flip. Below 0.50 is information "
          f"pointing backwards.\n")
    rows_out = []
    for label, sc in (("the model's hit_prob", model),
                      ("the market's price", market),
                      ("OUR CLAIMED EDGE", edge)):
        a = _auc(sc, y)
        lo, hi = _boot_auc(sc, y)
        rows_out.append((label, a, lo, hi))
        star = "  <-- the one that decides things" if "EDGE" in label else ""
        print(f"    {label:<22} AUC {a:.3f}   95% CI "
              f"[{lo:.3f}, {hi:.3f}]{star}")
    d, dlo, dhi = (_auc(model, y) - _auc(market, y),
                   *_boot_auc_diff(model, market, y))
    print(f"\n  model minus market   {d:+.3f}   95% CI [{dlo:+.3f}, "
          f"{dhi:+.3f}]")
    print(f"    Paired — both scores describe the same bets, and throwing "
          f"away\n    that pairing would widen this interval for no reason.")

    # --- what it means, stated before the numbers can be admired --------
    _, e_auc, e_lo, e_hi = rows_out[2]
    print(f"\n  READ IT LIKE THIS")
    if e_lo <= 0.5 <= e_hi:
        print(f"    The claimed edge cannot be told apart from noise: its "
              f"interval\n    [{e_lo:.3f}, {e_hi:.3f}] contains 0.5. Bets we "
              f"said were better did\n    not win more often than bets we "
              f"said were worse. Every gate\n    and stake rule in the repo "
              f"is a function of that number, so\n    tuning any of them is "
              f"tuning a threshold on noise.")
    elif e_lo > 0.5:
        print(f"    The claimed edge DOES sort winners from losers — its "
              f"whole\n    interval sits above 0.5. The number means "
              f"something, and the\n    losses are coming from somewhere "
              f"else: price, timing, sizing,\n    or which markets we take "
              f"it into.")
    else:
        print(f"    The claimed edge sorts winners BELOW losers, with the "
              f"whole\n    interval under 0.5. That is worse than useless: "
              f"it is signal\n    with its sign inverted, and the gates are "
              f"selecting against us.")
    if dlo <= 0 <= dhi:
        print(f"\n    Model against market is a wash. On the spots we chose, "
              f"our\n    number ranks outcomes about as well as the price "
              f"does — which,\n    after the vig, is a losing proposition no "
              f"matter how it is sized.")
    elif dlo > 0:
        print(f"\n    The model out-ranks the market on these bets. That is "
              f"the one\n    result that argues for keeping money on it.")
    else:
        print(f"\n    The market out-ranks the model on our own chosen "
              f"spots. The\n    price knows more about these bets than we "
              f"do.")
    print(f"\n  read-only; nothing was written.\n")


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
    if set(cats) == {"paper"}:
        # NOT the longshot warning. A paper book is deliberate and its
        # numbers are the point; telling Ethan to "drop
        # --include-measurement" when he passed --paper would be the tool
        # scolding him for doing exactly what he decided to do.
        print("  ** THE PAPER BOOK — same picks, same settling, zero")
        print("  ** dollars. Every figure below is what the model WOULD")
        print("  ** have returned. None of it is money won or lost.")
    elif set(cats) - {"main"}:
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
    from engine.calibrate import (apply_temperature, brier, fit_correction,
                                  _INTERCEPTS)

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
    # INTERCEPT ONLY, fitted the same way with the spread left alone.
    #
    # The reliability curve says the gap is negative in EVERY confidence
    # band — no sign change, the least-confident bets underperform too.
    # That is a flat handicap, which an intercept describes and a
    # temperature does not. So the temperature may be fitting noise, and
    # it is not a free parameter: it is what shrinks a 70% claim to 58%
    # instead of 64%, and what took 89 of 95 bets off the board.
    #
    # Two parameters must EARN the second one on data they have not seen.
    b_only = min(_INTERCEPTS, key=lambda c: brier(pairs, 1.0, c))

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
    claimed = sum(p for p, _ in tp) / len(tp)
    actual = sum(o for _, o in tp) / len(tp)
    print(f"\n  ON THE HELD-OUT ERA   ({len(test)} bets, "
          f"claimed {claimed:.1%}, actually won {actual:.1%})")
    print(f"    {'correction':<24}{'Brier':>9}{'mean claim':>12}"
          f"{'gap':>9}{'bets left':>11}{'ROI':>10}")
    for label, tt, bb in (("none", 1.0, 0.0),
                          ("shift only", 1.0, b_only),
                          ("shift + temperature", t, b)):
        corrected = sum(apply_temperature(p, tt, bb) for p, _ in tp) / len(tp)
        keep = [r for r in test
                if apply_temperature(float(r["hit_prob"]), tt, bb)
                > 1.0 / american_to_decimal(int(r["odds"]))]
        ks = sum(r["stake_units"] or 0.0 for r in keep)
        kn = sum(r["pnl_units"] or 0.0 for r in keep)
        roi = f"{_roi(kn, ks):+.1%}" if keep else "—"
        print(f"    {label:<24}{brier(tp, tt, bb):>9.4f}{corrected:>12.1%}"
              f"{actual - corrected:>+9.1%}{len(keep):>11}{roi:>10}")
    print("\n    The second parameter has to EARN itself here, on bets the fit")
    print("    never saw. If 'shift only' matches 'shift + temperature' on")
    print("    Brier, prefer it — it is one parameter instead of two and it")
    print("    leaves far more bets on the board.")

    print("\n    A fair replay throughout — survivors are chosen by a "
          "correction fitted\n    on an earlier era and a price known before "
          "kickoff. No outcome is read.\n    It is still "
          f"{len(test)} bets. Treat it as a direction, not a number.")


def spread_report(rows: list[dict]) -> None:
    """Does the model's confidence mean what it says?

    WHAT THIS REPLACED, and why. The first two versions tried to back a
    standard deviation out of each bet — the model's probability at its
    own line implies one — and compare it to the spread that actually
    happened. The estimator was fixed once (mean-of-ratios exploded on a
    book of coin-flips) and the answer was still nonsense: implied
    sigmas of 2.5 for total bases, 1.46 for hits, and 0.048 for pitcher
    outs, a ratio of 60.

    The reason is not the estimator. It is the premise. These markets are
    COUNTS, priced from discrete distributions, and the lines sit on half
    integers. Inverting a normal out of "P(hits >= 1) = 0.60" at a line
    of 0.5 returns 1.58 for a quantity whose real spread is near 0.86 —
    inflated by roughly the factor the whole table showed. The number was
    an artefact of assuming a shape the model never used.

    SO ASK THE QUESTION WITHOUT ASSUMING A SHAPE. Bucket the bets by the
    probability the model claimed, and in each bucket compare that claim
    to how often it actually happened. No distribution is inverted and
    nothing is assumed about the market.

    It also separates the two hypotheses, which the sigma table never
    could:

      * gap negative in the confident buckets AND POSITIVE in the timid
        ones means every probability sits too far from 50%. The spread is
        too narrow and a temperature is the fix.
      * gap negative in EVERY bucket by about the same amount means a
        systematic overclaim — or the winner's curse of only ever betting
        your own outliers. A shift is the fix.
      * both patterns at once means both, which is what `--fit` found.

    Buckets are equal-count rather than fixed-width. This book crowds
    into 40-60%, and fixed bands would put almost every bet in one row
    and call the rest a finding.
    """
    cal = [r for r in rows if r.get("hit_prob") is not None]
    if len(cal) < 25:
        print(f"\n  Only {len(cal)} bet(s) carry a model probability. "
              f"Nothing to say yet.")
        return

    import math
    cal.sort(key=lambda r: float(r["hit_prob"]))
    k = 5 if len(cal) >= 100 else 3
    size = len(cal) // k

    print(f"\n{'='*70}\n  DOES THE MODEL'S CONFIDENCE MEAN WHAT IT SAYS?"
          f"\n{'='*70}")
    print("  Bets grouped by the probability the model claimed, against how")
    print("  often it happened. Nothing is assumed about the distribution.\n")
    print(f"    {'claimed range':<18}{'bets':>6}{'claimed':>10}{'actual':>9}"
          f"{'gap':>9}{'1 SE':>9}")
    rows_out = []
    for i in range(k):
        chunk = cal[i * size:] if i == k - 1 else cal[i * size:(i + 1) * size]
        if not chunk:
            continue
        lo = float(chunk[0]["hit_prob"])
        hi = float(chunk[-1]["hit_prob"])
        claimed = sum(float(c["hit_prob"]) for c in chunk) / len(chunk)
        actual = sum(1 for c in chunk if c["status"] == "won") / len(chunk)
        se = math.sqrt(max(actual * (1 - actual), 1e-9) / len(chunk))
        rows_out.append((claimed, actual, se, len(chunk)))
        print(f"    {f'{lo:.0%} - {hi:.0%}':<18}{len(chunk):>6}{claimed:>10.1%}"
              f"{actual:>9.1%}{actual - claimed:>+9.1%}"
              f"{'±' + format(se, '.1%'):>9}")

    # --- where is the gap? ---------------------------------------------
    #
    # The pooled number is an average and averages hide subsets. The
    # +100 to +119 price band already came back near honest while the
    # book as a whole did not, which is worth chasing: if one market or
    # one sport is calibrated, that is where a bet lives.
    #
    # AND THIS IS WHERE A MEASUREMENT TURNS INTO A STORY IF NOBODY IS
    # COUNTING. Slice 292 bets eight ways and the best-looking slice will
    # sit about two standard errors from the truth by chance alone. The
    # bar is printed with the table rather than left to the reader.
    import math as _m

    def _slice(title, key):
        groups: dict = {}
        for r in cal:
            groups.setdefault(r.get(key) or "?", []).append(r)
        groups = {k: v for k, v in groups.items() if len(v) >= 15}
        if len(groups) < 2:
            return 0
        print(f"\n  BY {title.upper()}")
        print(f"    {title:<16}{'bets':>6}{'claimed':>10}{'actual':>9}"
              f"{'gap':>9}{'1 SE':>9}{'SE from 0':>11}")
        for k in sorted(groups, key=lambda g: -len(groups[g])):
            chunk = groups[k]
            c = sum(float(x["hit_prob"]) for x in chunk) / len(chunk)
            a = sum(1 for x in chunk if x["status"] == "won") / len(chunk)
            se = _m.sqrt(max(a * (1 - a), 1e-9) / len(chunk))
            print(f"    {str(k):<16}{len(chunk):>6}{c:>10.1%}{a:>9.1%}"
                  f"{a - c:>+9.1%}{'±' + format(se, '.1%'):>9}"
                  f"{abs(a - c) / se if se else 0:>11.1f}")
        return len(groups)

    n_sl = _slice("sport", "sport") + _slice("market", "market")
    if n_sl >= 2:
        bar = _m.sqrt(2 * _m.log(n_sl))
        print(f"\n    {n_sl} slices shown. With that many, the most extreme "
              f"one sits about\n    {bar:.1f} SE from the truth by chance "
              f"alone — so treat anything under\n    that as the sample "
              f"breathing, not a place to bet.")

    print("\n  READ IT LIKE THIS")
    print("    negative at the top and POSITIVE at the bottom -> every")
    print("      probability sits too far from 50%. The spread is too narrow")
    print("      and a temperature is the fix.")
    print("    negative in EVERY row by about the same amount -> a systematic")
    print("      overclaim, or the winner's curse of only betting your own")
    print("      outliers. A shift is the fix.")
    print("    both patterns -> both corrections, which is what --fit found.")
    if len(rows_out) >= 2:
        top, bot = rows_out[-1], rows_out[0]
        tgap, bgap = top[1] - top[0], bot[1] - bot[0]
        noise = math.sqrt(top[2] ** 2 + bot[2] ** 2)
        print(f"\n  Most confident row {tgap:+.1%}, least confident row "
              f"{bgap:+.1%};")
        print(f"  the difference is {tgap - bgap:+.1%} against {noise:.1%} of "
              f"noise on it.")
        if abs(tgap - bgap) < 2 * noise:
            print("  That difference is inside the noise, so this book cannot "
                  "yet tell a\n  too-narrow spread from a flat overclaim. "
                  "More settled bets, or the\n  answer comes from the "
                  "projections rather than the journal.")


def rederived_closes() -> dict:
    """Correct closing prices, rebuilt from the raw snapshot history.

    ETHAN, 2026-08-09: "we cant test what we have been doing against our
    past wins and losses to see if we would have improved."

    Half right, and the half that is wrong is the useful half. The CLV
    bug was in the LOOKUP, not the storage: every snapshot ever taken
    still sits in `cache/line_history.jsonl` with BOTH `over_odds` and
    `under_odds` on it. What was lost is the number the settle pass
    computed from them, and that number can simply be computed again —
    side-aware this time, and without the guard that threw away any row
    whose over price was missing.

    So CLV on the whole book is recoverable, not gone.

    WHAT IS GENUINELY GONE, and it is a different and more important
    limit: there is no record of the bets the model DECLINED. The journal
    holds what it chose. That means a change which FILTERS the existing
    picks can be replayed exactly — the sizing replays, the corrections,
    the cap policies all are — but a change that would make the model bet
    something new cannot be scored against history at all. It has to be
    tested forward.
    """
    try:
        from engine.linemoves import load_history, closing_odds_by_date
    except Exception:
        return {}
    try:
        return closing_odds_by_date(load_history())
    except Exception:
        return {}


def clv_report(rows: list[dict]) -> None:
    """Did the market move toward us by kickoff?

    THE SHARPEST TEST AVAILABLE AT THIS SAMPLE SIZE, and the reason it is
    worth building after everything else. 292 win/loss outcomes give a
    hit rate to about three points either way, which is too blunt to
    separate a small real edge from none. Closing line value is not a
    coin flip — it is a continuous measurement on every bet, so the same
    292 rows say far more.

    IT IS ALSO THE ONE MEASUREMENT THE WINNER'S CURSE CANNOT FAKE. The
    calibration gap came back as a uniform handicap: -9.6, -8.6, -10.5,
    -5.5 across four markets, every price band, every confidence level.
    Nothing market-specific looks like that. The one thing identical
    everywhere is the SELECTION — a bet exists when our estimate beat the
    market, by the same rule in every market — so the gap is consistent
    with the projections being fine and the act of picking adding the
    optimism.

    That story and "there is no edge" predict the same calibration table
    and OPPOSITE closing lines. A bettor who is actually finding stale
    prices beats the close on average even across a losing stretch,
    because the market comes to them. A bettor whose apparent edge is
    their own estimation noise does not, because there was nothing there
    to come to.

    Measured on PRICE, not on the line. Prop lines are sticky at half
    integers and mostly do not move; the juice does. Positive means the
    price we took was better than the price at close.
    """
    import math
    from engine.sources.oddsapi import normalize_name

    banked = [r for r in rows if r.get("closing_odds") not in (None, "")
              and r.get("odds") is not None]
    # REBUILT FROM THE SNAPSHOTS, side-aware, because the banked numbers
    # were recorded by the code that had the side bug and half of them
    # are the wrong side of the market. See `rederived_closes`.
    fresh = rederived_closes()
    have = []
    # COLLECTED IN THE LOOP, not derived afterwards. The first version
    # computed this as `[r for r in rows if r not in have]`, and `have`
    # holds freshly-built dicts rather than the originals — so nothing
    # ever matched and it reported all 307 settled bets as having no
    # close, on the same screen that said 113 did. Two numbers from one
    # loop must come out of that loop.
    missing = []
    for r in rows:
        if r.get("odds") is None:
            missing.append(r)
            continue
        sides = fresh.get((normalize_name(r["player"] or ""), r["market"],
                           r["date"],
                           round(float(r["line"]), 1)
                           if r.get("line") is not None else None)) or {}
        px = sides.get("under" if (r.get("side") or "OVER").upper() == "UNDER"
                       else "over")
        # Guarded here too, and deliberately not only at the source: this
        # report also reads whatever a future close-builder hands it, and
        # a single -5 moved the headline by nearly a point.
        if px is not None and abs(float(px)) >= 100 and abs(int(r["odds"])) >= 100:
            # `_banked` rides along so the banked column can be audited
            # against this rebuild below. Never used to COMPUTE the CLV —
            # that stays rebuilt-only, so a bad banked value cannot reach
            # the headline number even if the audit is somehow wrong.
            have.append(dict(r, closing_odds=int(px),
                             _banked=r.get("closing_odds"),
                             _band=_band(int(r["odds"]))))
        else:
            missing.append(r)
    print(f"\n{'='*70}\n  DID THE MARKET COME TO US BY KICKOFF?\n{'='*70}")
    print(f"  {len(have)} of {len(rows)} settled bets have a closing price "
          f"rebuilt from\n  the raw snapshots, side-aware.")
    # THE BANKED COLUMN, AUDITED RATHER THAN DISMISSED. This line used to
    # say the banked closes came from the code with the side bug and were
    # ignored here. After `launch.py --repair-closes` that is no longer
    # true, and a note that describes a fixed problem is worse than none —
    # it teaches you to distrust a column that is now correct.
    #
    # Both numbers exist for the same rows now, derived the same way, so
    # they can be checked against each other. Agreement is the evidence
    # that the repair took and that nothing has drifted since;
    # disagreement means the settle path and this report have diverged
    # again, which is the exact failure that hid for twelve days.
    both = [r for r in have if r.get("_banked") is not None]
    disagree = [r for r in both if int(r["_banked"]) != int(r["closing_odds"])]
    if both:
        if disagree:
            print(f"  ** {len(disagree)} of {len(both)} banked closes "
                  f"DISAGREE with the rebuild.")
            print(f"  ** The settle path and this report have diverged. "
                  f"Run:")
            print(f"  **     python3 launch.py --repair-closes")
            for r in disagree[:5]:
                print(f"  **     {r['date']}  {str(r['player'])[:20]:<20} "
                      f"banked {int(r['_banked']):+d}  rebuilt "
                      f"{int(r['closing_odds']):+d}")
        else:
            print(f"  {len(both)} of those also carry a banked close, and "
                  f"every one agrees\n  with the rebuild — the banked "
                  f"column and this report are in step.")
    # WHY THE OTHER ROWS HAVE NO CLOSE, which the coverage number alone
    # never said. Historical unders cannot be rebuilt at all: the
    # snapshots held only the over price until 2026-08-09, so an under
    # has nothing legal to read. Saying so turns a flat "113 of 307" into
    # a number with a known cause and a known recovery date.
    if missing:
        m_under = sum(1 for r in missing
                      if (r.get("side") or "OVER").upper() == "UNDER")
        # Phrased around the mutation-guard test, which scans this
        # function's whole source — comments and string literals included
        # — for the verbs of persistence. A real guard that sometimes
        # costs a synonym beats a loose one that can be talked past.
        print(f"\n  {len(missing)} have none. {m_under} of those are UNDERS, "
              f"which cannot be\n  rebuilt at all before 2026-08-09 — the "
              f"snapshots held only the over\n  price until then. That half "
              f"of the book is invisible here, not\n  unprofitable, and it "
              f"becomes measurable from that date onward.")
    if len(have) < 20:
        print("\n  Too few to say anything — and WHICH of the two reasons "
              "matters:")
        if banked:
            print(f"    {len(banked)} bets banked a close but the snapshot "
                  f"history cannot rebuild\n    them. The raw file "
                  f"(cache/line_history.jsonl) is missing, thin, or does\n"
                  f"    not cover these dates. That file is the only place "
                  f"a correct close\n    can come from now, so it is the "
                  f"thing to protect.")
        else:
            print("    Nothing is being captured at all. Closing prices come "
                  "from the\n    snapshot pull; until it runs, the sharpest "
                  "read on whether an edge\n    exists is simply not "
                  "available.")
        return

    def _clv(r):
        """Value taken, in PROBABILITY POINTS.

        The implied probability of the close minus the implied
        probability we paid. Positive means the market ended up needing
        a bigger number than we did — we bought it cheap.

        NOT the ratio of decimal prices, which was the first version.
        That is convex, and American odds jump across the +/-100 line, so
        averaging it puts a positive bias on a book with NO edge: a
        synthetic with zero true movement came back +0.42% at t = +1.9,
        which reads as a finding and is arithmetic.

        Probability points are also the same unit as the calibration gap
        above, so the two numbers can be set beside each other: the model
        claims about ten points it does not have — does the market agree
        by even one?
        """
        return (1.0 / american_to_decimal(int(r["closing_odds"]))
                - 1.0 / american_to_decimal(int(r["odds"])))

    vals = [_clv(r) for r in have]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1)
    se = math.sqrt(var / len(vals))
    beat = sum(1 for v in vals if v > 0)
    # A t needs a spread to divide by. Identical rows give se ~ 0 and a
    # t in the quadrillions, which is not a strong result — it is a
    # degenerate one, and printing it as a number invites reading it.
    tstat = (f"{mean / se:+.1f}" if se > 1e-6 else "— (no spread to test)")
    print(f"\n  mean CLV      {mean:+.2%} of a probability point   "
          f"± {se:.2%} (1 SE)   t = {tstat}")
    print(f"  beat the close on {beat} of {len(have)} "
          f"({beat / len(have):.0%})")
    print("\n  READ IT LIKE THIS")
    print("    positive and past about 2 SE -> real edge. The market moved to")
    print("      us, which a losing stretch does not undo. Keep betting and")
    print("      fix the sizing.")
    print("    indistinguishable from zero -> no demonstrated edge. The")
    print("      calibration gap is our own selection noise, and no")
    print("      correction, cap or stake rule turns that into money.")
    print("    negative -> we are consistently on the wrong side of the")
    print("      market's own revision, which is worse than no edge.")

    # --- where do the bad ones live? ------------------------------------
    #
    # THE ONE STRUCTURAL LEAD IN THE DATA. 69% of bets beat the close and
    # the MEAN is still negative, so a minority of large misses outweighs
    # a majority of small wins. If those misses are identifiable BEFORE
    # kickoff — a market, a price band — then dropping them moves the mean
    # without needing the model to get smarter.
    #
    # Exploratory, and the same multiple-look discipline applies: slice
    # enough ways and the worst-looking slice is worst by chance.
    import statistics as _st
    pairs = list(zip(have, vals))
    worst = sorted(pairs, key=lambda pv: pv[1])[:max(1, len(pairs) // 10)]
    rest_mean = (sum(v for _, v in pairs[len(worst):]) /
                 max(len(pairs) - len(worst), 1))
    print(f"\n  THE WORST DECILE, BY NAME")
    print(f"    {len(worst)} bets averaging {sum(v for _, v in worst) / len(worst):+.2%}")
    # NAMED, because at this magnitude the question stops being statistical.
    # A CLV of -20 points means a price that implied 50% closed implying
    # 27% — scratch-level, not ordinary prop movement. Eleven of those in
    # 116 is a data question with a factual answer, and a tally cannot be
    # checked against a box score.
    #
    # IT ALSO GUARDS THE TRAP. Delete the worst tenth of ANY null sample
    # and the remainder looks positive; that is arithmetic, not evidence.
    # These rows may only be excluded for a reason established WITHOUT
    # looking at their CLV — a scratch, a wrong game, a stale snapshot.
    # Printing them is what makes that check possible.
    for r, v in worst[:12]:
        print(f"      {v:+7.1%}  {r['date']}  {r['player'][:22]:<22} "
              f"{(r['side'] or '')[:5]:<5} {r['market'][:12]:<12} "
              f"{r['line']}  took {r['odds']:+d} -> closed "
              f"{int(r['closing_odds']):+d}")
    print(f"    the other {len(pairs) - len(worst)} average "
          f"{(sum(v for _, v in pairs) - sum(v for _, v in worst)) / max(len(pairs) - len(worst), 1):+.2%}")
    print(f"    median CLV overall {_st.median(vals):+.2%} against a mean of "
          f"{mean:+.2%}")
    print("    A median well above the mean is the skew: many small wins, a "
          "few\n    large misses.")
    print("\n    DO NOT READ THE 'other' LINE AS EDGE. Removing the worst "
          "tenth of any\n    null sample leaves a positive remainder — that "
          "is arithmetic. It counts\n    only if those rows are excluded for "
          "a reason found WITHOUT looking at\n    their CLV. Check the names "
          "above against what actually happened: a\n    scratch, the wrong "
          "game of a doubleheader, a snapshot taken hours\n    before "
          "kickoff. If they are genuine moves, they stay and the mean "
          "stands.")

    def _clv_slice(title, key):
        groups: dict = {}
        for r, v in pairs:
            groups.setdefault(r.get(key) or "?", []).append(v)
        raw = {k: len(v) for k, v in groups.items()}
        groups = {k: v for k, v in groups.items() if len(v) >= 12}
        if len(groups) < 2:
            # SAY SO. A slice that silently prints nothing is
            # indistinguishable from a slice that does not exist, and the
            # counts are usually the interesting part: "only OVER has
            # enough closes" is a finding about the SNAPSHOT PIPELINE, not
            # an absence of one about betting.
            print(f"\n  CLV BY {title.upper()}: not shown — "
                  + (", ".join(f"{k} {n}" for k, n in sorted(raw.items(),
                                                             key=lambda kv: -kv[1]))
                     or "no rows")
                  + f"\n    (needs two groups of 12+; a group that thin is "
                    f"a gap in the closes,\n    not a gap in the betting)")
            return
        print(f"\n  CLV BY {title.upper()}")
        print(f"    {title:<18}{'bets':>6}{'mean':>10}{'median':>10}"
              f"{'1 SE':>9}{'SE from 0':>11}")
        for k in sorted(groups, key=lambda g: -len(groups[g])):
            vv = groups[k]
            m = sum(vv) / len(vv)
            sd = math.sqrt(sum((x - m) ** 2 for x in vv) / max(len(vv) - 1, 1))
            e = sd / math.sqrt(len(vv))
            print(f"    {str(k):<18}{len(vv):>6}{m:>10.2%}{_st.median(vv):>10.2%}"
                  f"{'±' + format(e, '.2%'):>9}{abs(m) / e if e else 0:>11.1f}")

    _clv_slice("market", "market")
    _clv_slice("price band", "_band")
    # SIDE, and this one was not fished for. Every bet in the worst
    # decile is an OVER, and every one of them closed longer — the
    # market moving away from the side we took. Two groups, specified
    # from the pattern in the outliers rather than from a sweep.
    _clv_slice("side", "side")

    # And whether CLV predicts the result, which is the internal check
    # that the closing prices being read are the right ones.
    pos = [r for r, v in zip(have, vals) if v > 0]
    neg = [r for r, v in zip(have, vals) if v <= 0]
    if pos and neg:
        def _wr(g):
            return sum(1 for r in g if r["status"] == "won") / len(g)
        print(f"\n  win rate when we beat the close   {_wr(pos):.1%}  "
              f"({len(pos)} bets)")
        print(f"  win rate when we did not          {_wr(neg):.1%}  "
              f"({len(neg)} bets)")
        print("    A large gap the WRONG way is a data problem, not a "
              "betting one —\n    it would mean the closing prices being "
              "read are not the ones we\n    were graded against.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="data/ledger.db")
    ap.add_argument("--sport")
    ap.add_argument("--since", help="ISO date; only bets on or after it")
    ap.add_argument("--clv", action="store_true",
                    help="closing line value: did the market move toward "
                         "us by kickoff? The sharpest edge test available "
                         "on a few hundred bets. Reports only")
    ap.add_argument("--spread", action="store_true",
                    help="bucket the bets by the probability the model "
                         "claimed and compare each bucket to how often it "
                         "happened. Reports only")
    ap.add_argument("--fit", action="store_true",
                    help="fit the model's overconfidence on the pre-rescale "
                         "era and test it on the current one. Reports only; "
                         "writes nothing and changes no model")
    ap.add_argument("--info", action="store_true",
                    help="does our number know anything the price does not? "
                         "Ranks bets by model, by market, and by claimed edge")
    ap.add_argument("--paper", action="store_true",
                    help="measure the PAPER book instead of the real one — "
                         "same picks, same settling, zero dollars")
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
                 category="paper" if args.paper else None,
                 measurement=args.include_measurement)
    if args.info:
        # Its own trailer is printed inside, since it ends on the reading
        # rather than on a table.
        info_report(rows)
        return
    if args.clv:
        clv_report(rows)
        print("\n  read-only; nothing was written.\n")
        return
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
