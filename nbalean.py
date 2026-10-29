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
     often we said they would, and the return at a flat unit.
  4. THE MINUTES BASE THIS SEASON. Every game played this season by a man
     with three earlier ones this season: his minutes against the base the
     board would have read before it, over the board's own window (his last
     twenty games, which early on are mostly last season's end: a lottery
     club's April, a contender's playoffs) and over this season's games
     alone. The median of minutes over base: above 1.00 the base runs light,
     which reads as unders, below it heavy. If this season's own games read
     nearer 1.00 than the twenty, the window is the next thing to change.

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


def minutes_check(conn, season: int, min_prior: int = 3) -> dict:
    """``{"n", "window", "season_only"}``: the median of a game's minutes
    over the base read before it (engine/nba/minutes), on the board's
    twenty-game window and on this season's games alone, over every game of
    ``season`` with ``min_prior`` earlier ones in it. Nothing for fewer
    than 20 such games."""
    from engine.nba.minutes import base_minutes, role_minutes
    games: dict = defaultdict(list)                       # player -> [(date, season, minutes)]
    for r in conn.execute("SELECT player, period, season, value FROM player_game_logs "
                          "WHERE sport='nba' AND market='min' AND season IN (?, ?) ORDER BY period",
                          (season, season - 1)):
        games[r[0]].append((str(r[1]), int(r[2]), float(r[3] or 0.0)))
    window, own = [], []
    for rows in games.values():
        for i, (_day, sea, actual) in enumerate(rows):
            if sea != season or actual <= 0:
                continue
            before = [m for _d, _s, m in reversed(rows[:i])][:20]
            this = [m for _d, s_, m in reversed(rows[:i]) if s_ == season][:20]
            if len(this) < min_prior:
                continue
            b_all = base_minutes(role_minutes(before)[0])
            b_own = base_minutes(role_minutes(this)[0])
            if b_all and b_own:
                window.append(actual / b_all)
                own.append(actual / b_own)
    if len(window) < 20:
        return {"n": len(window)}
    return {"n": len(window), "window": statistics.median(window), "season_only": statistics.median(own)}


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
        hconn = connect()
        try:
            mc = minutes_check(hconn, season_of("nba", doc.get("date") or _dt.date.today().isoformat()))
        finally:
            hconn.close()
        if mc.get("window"):
            print(f"  Minutes against the base read before each game, {mc['n']} games this season "
                  f"(median; over 1.00 the base runs light): the board's twenty-game window "
                  f"{mc['window']:.3f}, this season's games alone {mc['season_only']:.3f}")
        else:
            print(f"  Minutes base this season: {mc['n']} games with three before them — too few to read yet.")
    except Exception as exc:                                # noqa: BLE001 — no history, no check
        print(f"  Minutes base this season: not readable here ({type(exc).__name__}).")
    try:
        from engine import ledger as L
        conn = L.connect()
        try:
            rec = record(conn)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
