#!/usr/bin/env python3
"""Score the home-run long-shot model against what actually happened.

    python3 hr_backtest.py                     # everything stored
    python3 hr_backtest.py --seasons 2026
    python3 hr_backtest.py --naive             # ignore harvested book lines

The per-market sweep's "Home Runs" row is NOT this model. That row walks
the generic prop model over home runs — a market it never bets, which is
why it reports 0 bets. The Long Shots board runs
``engine.mlb.homeruns.hr_probability``, and nothing measured it until now.

On a summer night the Long Shots board is often the only board holding
open bets, so the one model taking money was the one nobody had scored.

Read the output in this order:

  1. **Inputs** first, not the score. Statcast profiles are not stored
     historically, so this measures the model's FALLBACK path — the same
     one it uses live for a hitter with no profile. A good number here is
     a floor, not the live board's number.
  2. **said → actual**. Home runs are a ~10%-per-game event. If the model
     says 25% and reality says 10%, every long shot it likes is priced off
     a probability more than twice too high, and no odds filter downstream
     can repair that.
  3. **Skill** against always guessing the base rate. On a rare event a
     Brier near 0.09 is what you get for predicting "no" every time, so
     the raw number flatters badly here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import db
from engine.mlb.hrbacktest import backtest_hr


def main() -> None:
    ap = argparse.ArgumentParser(description="Home-run long-shot backtest.")
    ap.add_argument("--db", default="data/history.db")
    ap.add_argument("--min-history", type=int, default=20,
                    help="games of prior history before a player is scored")
    ap.add_argument("--seasons", type=int, nargs="*", default=None)
    ap.add_argument("--naive", action="store_true",
                    help="ignore harvested book lines")
    args = ap.parse_args()

    conn = db.connect(args.db)
    stored = conn.execute(
        "SELECT COUNT(*) FROM player_game_logs WHERE sport='mlb' "
        "AND market='home_runs'").fetchone()[0]
    if not stored:
        print(f"\nNo MLB home-run game logs in {args.db}.\n"
              f"  Nothing to score the model against.\n"
              f"  Fix: python3 ingest.py mlb --seasons <year>\n")
        return

    report, cov, settled = backtest_hr(
        conn, min_history=args.min_history, seasons=args.seasons,
        use_real_lines=not args.naive)

    print(f"\nHome-run LONG SHOT model · walk-forward on {args.db}")
    print(f"  {stored:,} stored home-run game log(s)\n")
    if not report.n:
        print(f"  No player reached {args.min_history}+ prior games. "
              f"Try --min-history {max(1, args.min_history // 2)}.\n")
        return

    print(report.summary())
    for line in cov.lines():
        print(line)

    # Ranking, which is what the board actually uses the model FOR — it
    # takes three names off the top, never the population. Brier cannot see
    # this: on a ~10% event, no-discrimination and perfect-discrimination
    # are separated by about two points of skill score, while the entire
    # value of the board lives in the gap below.
    from engine.mlb.hrbacktest import lift
    bands = lift(settled)
    if bands:
        print("\n  Ranking — does the model's top group actually homer more?")
        print(f"    {'group':<26}{'n':>8}{'said':>9}{'actual':>9}")
        names = {1: "bottom fifth", 2: "second", 3: "middle",
                 4: "fourth", 5: "TOP fifth (it bets here)"}
        for b in bands:
            print(f"    {names.get(b['bucket'], b['bucket']):<26}{b['n']:>8,}"
                  f"{b['said']:>8.1%}{b['actual']:>9.1%}")
        lo, hi = bands[0]["actual"], bands[-1]["actual"]
        if hi <= lo * 1.05:
            print(f"    → NO ranking ability. The hitters it likes best homer "
                  f"{hi:.1%} of the time;\n      the ones it likes least, "
                  f"{lo:.1%}. Picking three names off the top of this\n"
                  f"      list is picking three names at random.")
        else:
            print(f"    → Its top fifth homers {hi / lo:.1f}x as often as its "
                  f"bottom fifth ({hi:.1%} vs {lo:.1%}).")

    # The number the whole thing exists for, stated in one sentence.
    said = sum(s.hit_prob for s in settled) / len(settled)
    actual = sum(1 for s in settled if s.actual > HR_HIT) / len(settled)
    print(f"\n  Overall: the model says a hitter homers {said:.1%} of the "
          f"time.\n           He actually does {actual:.1%} of the time.")
    ratio = said / actual if actual else 0
    if ratio > 1.15:
        print(f"           It is {ratio:.1f}x too high. Every long shot it "
              f"likes is priced off a\n           probability that far "
              f"above reality — no odds filter downstream\n           can "
              f"repair that.")
    elif ratio < 0.87:
        print(f"           It is {1 / ratio:.1f}x too LOW — it will pass on "
              f"home runs worth taking.")
    else:
        print("           Those agree. The rate is right; any problem is in "
              "which\n           hitters it picks, not how often it thinks "
              "they go deep.")

    if not args.naive and not cov.with_book_line:
        print("\n  ⚠️  No harvested home-run prices matched, so there is no "
              "market-relative\n      number here at all. The calibration "
              "above still stands — it grades\n      against OUTCOMES. To "
              "price against books:\n      python3 harvest_odds.py mlb "
              "--from <date> --to <date>")
    print()


HR_HIT = 0.0          # "hit at least one" — the side the board always backs


if __name__ == "__main__":
    main()
