#!/usr/bin/env python3
"""Which way the NBA board leans, and why — read-only.

    cd /srv/qellys && sudo -u qellys python3 nbalean.py

Ethan, 2026-10-29: "almost ever nba most likely bet is an under bet so that
seems wrong and we need to work on that and calibrate that more."

Three reads, all off what the box already holds; nothing is fetched and
nothing is written.

  1. THE BOARD. Tonight's NBA Most Likely picks (web/data/nba.json), over
     against under, by market.
  2. THE LEVEL. Every NBA prop the build priced at its main line, the
     model's projection against the mean the market's own price implies
     there: the de-vigged chance of the over, turned back into a mean
     through the model's own curve for that stat (`engine.nba.prob.p_over`),
     so the two are read on one scale. A market that is efficient on
     average sits at a ratio of 1.00; a model that sits below it on most
     props seats the under on most props, because the board ranks by our
     chance at a number near −250, where a few percent of mean is several
     points of chance. Per market: the median ratio, and the share of
     props where we sit under the market.
  3. THE RECORD. The graded NBA Most Likely picks (the ledger, as
     likelyfit.py reads it), by side: how many, how often they hit, how
     often we said they would, and the return at a flat unit. Then the
     close: whether the market moved our way after each pick went up, the
     test a pro trusts long before a win rate settles (a few hundred picks
     decide a hit rate; the close says something after a few dozen).
  4. THE MINUTES BASE THIS SEASON (engine/nba/window, which the build
     measures each day and acts on): every game played this season by a man
     with three earlier ones this season, his minutes against the base read
     before it, over the board's twenty-game window (early on mostly last
     season's end: a lottery club's April, a contender's playoffs) and over
     this season's games alone, and which one the board is reading. Then
     whether the teammate-out minutes (engine/nba/vacancy) are on.

WHAT MOVED (2026-10-29, engine/nba/minutes.context_norms): the minutes
model laid tonight's blowout and rest haircuts on a base that already
held its games' own, so every starter read light — about 2% on an even
club, about 7% on one favoured most nights. Read the LEVEL before and
after that ships: the ratios should come up toward 1.00 and the board
should stop being one side.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: A market with fewer priced props than this tonight prints no level.
MIN_PROPS = 8


def implied_mean(stat: str, line: float, q_over: float) -> float | None:
    """The mean at which the model's own curve gives the over ``q_over`` at
    ``line`` — the market's price read as a projection. None when the price
    sits outside what the curve can reach."""
    from engine.nba.prob import p_over
    if not (0.02 < q_over < 0.98) or line <= 0:
        return None
    lo, hi = 0.01, max(3.0 * line, line + 15.0)
    if p_over(stat, hi, line) < q_over or p_over(stat, lo, line) > q_over:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if p_over(stat, mid, line) < q_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def board_sides(doc: dict) -> dict:
    """``{market: Counter(side)}`` of tonight's Most Likely rows."""
    out: dict = defaultdict(Counter)
    for r in doc.get("most_likely") or []:
        if (r.get("kind") or "prop") != "prop":
            continue
        side = str(r.get("side") or "").lower()
        side = "over" if side in ("over", "yes") else "under" if side in ("under", "no") else side
        out[r.get("market") or "?"][side] += 1
    return out


def levels(doc: dict) -> dict:
    """``{market: [model projection / the market's implied mean, ...]}``."""
    out: dict = defaultdict(list)
    for r in doc.get("recommendations") or []:
        try:
            proj, line, fair = float(r["projection"]), float(r["line"]), float(r["fair_prob"])
        except (KeyError, TypeError, ValueError):
            continue
        side = str(r.get("side") or "").upper()
        q_over = fair if side == "OVER" else 1.0 - fair if side == "UNDER" else None
        if q_over is None or proj <= 0:
            continue
        mean = implied_mean(r.get("market") or "", line, q_over)
        if mean:
            out[r.get("market") or "?"].append(proj / mean)
    return out


def record(conn) -> dict:
    """``{side: {"n", "won", "said", "ret"}}`` of the graded NBA Most Likely
    picks, each pick once at a flat unit (likelyfit.load)."""
    import likelyfit
    out: dict = {}
    for r in likelyfit.load(conn, sport="nba"):
        side = "over" if r["side"] in ("OVER", "YES") else "under" if r["side"] in ("UNDER", "NO") else r["side"].lower()
        s = out.setdefault(side, {"n": 0, "won": 0, "said": 0.0, "ret": 0.0})
        s["n"] += 1
        s["won"] += int(r["status"] == "won")
        s["said"] += float(r["hit_prob"] or 0)
        s["ret"] += float(r["ret"])
    return out


def _implied(odds) -> float:
    o = float(odds)
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def clv(conn) -> dict:
    """``{side: {"n", "price", "beat", "n_line", "line"}}`` — how the NBA Most
    Likely picks fared against the close, each pick once (ledger.books_sql),
    settled or not. At the same number: the close's chance for our side
    less the price's we took (``price``, vig in both; positive means the
    market came our way after we took it) and the share that did
    (``beat``). Where the number moved: the points it moved our way
    (``line``: a lower number on an over, a higher one on an under)."""
    from engine import ledger as L
    sql, args = L.books_sql(L.LIKELY_BOOKS + (L.BOARD_CATEGORY,))
    out: dict = {}
    for r in conn.execute(f"SELECT UPPER(COALESCE(side,'')) side, line, odds, closing_line, closing_odds "
                          f"FROM bets WHERE {sql} AND LOWER(sport)='nba' AND odds IS NOT NULL "
                          f"AND closing_odds IS NOT NULL", args):
        side = "over" if r[0] in ("OVER", "YES") else "under" if r[0] in ("UNDER", "NO") else ""
        if not side:
            continue
        try:
            odds, close = float(r[2]), float(r[4])
            if abs(odds) < 100 or abs(close) < 100:
                continue
        except (TypeError, ValueError):
            continue
        s = out.setdefault(side, {"n": 0, "price": 0.0, "beat": 0, "n_line": 0, "line": 0.0})
        try:
            moved = r[1] is not None and r[3] is not None and abs(float(r[1]) - float(r[3])) > 1e-9
        except (TypeError, ValueError):
            moved = False
        if moved:
            pts = float(r[3]) - float(r[1]) if side == "over" else float(r[1]) - float(r[3])
            s["n_line"] += 1
            s["line"] += pts
            continue
        gain = _implied(close) - _implied(odds)
        s["n"] += 1
        s["price"] += gain
        s["beat"] += int(gain > 0)
    for s in out.values():
        if s["n"]:
            s["price"], s["beat"] = s["price"] / s["n"], s["beat"] / s["n"]
        if s["n_line"]:
            s["line"] /= s["n_line"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--board", default=str(ROOT / "web" / "data" / "nba.json"))
    args = ap.parse_args(argv)
    try:
        doc = json.loads(Path(args.board).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"No NBA board to read at {args.board} ({type(exc).__name__}).")
        doc = {}

    sides = board_sides(doc)
    total = sum((c for c in sides.values()), Counter())
    print(f"NBA board for {doc.get('date') or '?'}, built {doc.get('generated_at') or doc.get('built_at') or '?'}")
    if total:
        n = sum(total.values())
        print(f"  Most Likely: {n} picks — {total['over']} over, {total['under']} under "
              f"({total['under'] / n:.0%} under)")
        for market, c in sorted(sides.items()):
            print(f"    {market:8} {c['over']:3} over {c['under']:3} under")
    else:
        print("  Most Likely: no NBA picks on the board.")

    lv = levels(doc)
    if lv:
        print("  Our projection against the market's own number (1.00 = level; under 1 = we sit below):")
        for market, xs in sorted(lv.items()):
            if len(xs) < MIN_PROPS:
                print(f"    {market:8} {len(xs):4} props (too few to read)")
                continue
            below = sum(1 for x in xs if x < 1.0) / len(xs)
            print(f"    {market:8} {len(xs):4} props  median {statistics.median(xs):.3f}  "
                  f"below the market on {below:.0%}")
    else:
        print("  No priced NBA props on the board to compare.")

    try:
        from engine.db import connect
        from engine.seasons import season_of
        import datetime as _dt
        from engine.nba import window as W
        hconn = connect()
        try:
            mc = W.measure(hconn, "nba", season_of("nba", doc.get("date") or _dt.date.today().isoformat()))
        finally:
            hconn.close()
        if mc.get("mae_twenty") is not None:
            print(f"  Minutes base this season, {mc['n']} games with three of this season's before them:")
            print(f"    the twenty-game window   off by {mc['mae_twenty']:.2f} min a game, "
                  f"minutes over base {mc['ratio_twenty']:.3f} (over 1.00: it runs light)")
            print(f"    this season's games      off by {mc['mae_season']:.2f} min a game, "
                  f"minutes over base {mc['ratio_season']:.3f}")
            print(f"    the board reads: {W.choose(mc)} (this season's alone once {W.MIN_GAMES}+ games "
                  f"say they are {W.MARGIN:g} min closer)")
        else:
            print(f"  Minutes base this season: {mc['n']} games with three before them — too few to read yet.")
    except Exception as exc:                                # noqa: BLE001 — no history, no check
        print(f"  Minutes base this season: not readable here ({type(exc).__name__}).")
    try:
        from engine.nba import vacancy as V
        v = V.verdict("nba")
        if v:
            print(f"  Teammate-out minutes (nbavacancy.py --heldout): "
                  f"{'on, k ' + format(V.k_for('nba'), 'g') if v.get('holds') else 'measured, did not hold — off'}")
        else:
            print("  Teammate-out minutes: not measured on this box yet (nbavacancy.py --heldout) — off")
    except Exception as exc:                                # noqa: BLE001
        print(f"  Teammate-out minutes: not readable here ({type(exc).__name__}).")
    try:
        from engine import ledger as L
        conn = L.connect()
        try:
            rec = record(conn)
            closes = clv(conn)
        finally:
            conn.close()
    except Exception as exc:                                # noqa: BLE001 — no ledger, no record
        print(f"  Graded record: not readable here ({type(exc).__name__}).")
        return 0
    if not rec:
        print("  Graded record: no NBA Most Likely picks graded yet.")
    else:
        print("  Graded NBA Most Likely picks, each once at a flat unit:")
        for side in ("over", "under"):
            s = rec.get(side)
            if not s:
                print(f"    {side:5}  none graded")
                continue
            print(f"    {side:5}  {s['n']:4} picks  hit {s['won'] / s['n']:.0%}  "
                  f"we said {s['said'] / s['n']:.0%}  return {s['ret'] / s['n']:+.1%} a pick")
    if closes:
        print("  Against the close (a pro's first test: does the market come our way after we take it?):")
        for side in ("over", "under"):
            c = closes.get(side)
            if not c:
                continue
            parts = []
            if c["n"]:
                parts.append(f"{c['n']} at the same number: {c['price'] * 100:+.1f} points of chance on "
                             f"average, {c['beat']:.0%} beat it")
            if c["n_line"]:
                parts.append(f"{c['n_line']} where the number moved: {c['line']:+.2f} a pick our way")
            print(f"    {side:5}  " + "; ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
