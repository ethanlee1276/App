#!/usr/bin/env python3
"""Per-market calibration sweep — the honest health check on the model.

    python3 mlb_calibration.py                # every market, from the DB
    python3 mlb_calibration.py --naive        # skip harvested book lines

Runs the walk-forward backtest across every MLB prop market at once and
prints one compact table, because the question that matters isn't "is
the model good" but "WHICH markets can it price". Today's board showed
the model claiming implausible edges on 42% of props and overstating
favourites by ~21 points; this says where that comes from, market by
market, on thousands of real games instead of a few dozen bets.

Read the output like this:

  * **ECE** (expected calibration error) — average gap between what the
    model said and what happened. Under ~0.03 is trustworthy, over ~0.08
    means the probabilities are fiction in that market.
  * **Brier** — overall forecast accuracy, lower is better. Always
    compare it to the base-rate column: beating 0.25 on a coin-flip
    market is easy, beating the base rate is not.
  * **Bins** — "said 63% → actual 78%" is the readout that matters. Said
    ABOVE actual means overconfident: the source of every guard we've
    had to bolt on.
  * **real lines** — how much of the betting result was priced against a
    number a bettor could actually have taken. Low coverage means the
    ROI column is "beats a trailing average", not "beats the book".
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine import db as _db
from engine.mlb.backtest import backtest_from_logs
from engine.mlb.models import MARKET_LABELS
from engine.rules import RuleConfig

MARKETS = ("total_bases", "hits", "home_runs", "strikeouts")
ROOT = Path(__file__).parent


def sweep(db_path: str, markets=MARKETS, min_history: int = 6,
          use_real_lines: bool = True) -> list[dict]:
    from engine.sources.oddsapi import normalize_name
    conn = _db.connect(db_path)
    rows = []
    for market in markets:
        entries = _db.entries_for_market(conn, "mlb", market,
                                         min_games=min_history + 1)
        if not entries:
            rows.append({"market": market, "n": 0})
            continue
        real_lines = {}
        if use_real_lines:
            for (player, date), q in _db.closing_odds_by_date(
                    conn, "mlb", market).items():
                real_lines[(normalize_name(player), date)] = q
        rep = backtest_from_logs(entries, market, min_history=min_history,
                                 config=RuleConfig(), real_lines=real_lines)
        d = rep.__dict__ if hasattr(rep, "__dict__") else dict(rep)
        d["market"] = market
        # Carry the report itself: skill()/sharpness live on the object and
        # do not survive __dict__, and the history store needs them.
        d["_report"] = rep
        rows.append(d)
    return rows


def _get(d, *names, default=None):
    for n in names:
        v = d.get(n) if isinstance(d, dict) else getattr(d, n, None)
        if v is not None:
            return v
    return default


def _stock(db_path: str) -> dict:
    """What is in the DB, counted rather than assumed."""
    from engine import db as _db
    conn = _db.connect(db_path)
    logs = conn.execute("SELECT COUNT(*) FROM player_game_logs "
                        "WHERE sport='mlb'").fetchone()[0]
    by_market: dict = {}
    for r in conn.execute("SELECT market, COUNT(*) n FROM player_game_logs "
                          "WHERE sport='mlb' GROUP BY market"):
        by_market[r[0]] = r[1]
    try:
        odds = conn.execute("SELECT COUNT(*) FROM odds_history "
                            "WHERE sport='mlb'").fetchone()[0]
    except Exception:
        odds = 0
    return {"logs": logs, "by_market": by_market, "odds": odds}


def _show_trend(db_path: str) -> None:
    """Every stored run, and whether the probabilities are getting better.

    Direction is spelled out rather than left to the reader: ECE going DOWN
    is an improvement, while half the numbers on this page improve by going
    up. A sign confusion here would be read as a result.
    """
    from engine import calibhistory as _ch
    conn = _db.connect(db_path)
    t = _ch.trend(conn, "mlb")
    if not t:
        print("\nNo calibration runs stored yet.\n"
              "  Nothing before today was recorded — every sweep printed to a "
              "terminal and\n  vanished, so there is no history to compare "
              "against. Run the sweep once and\n  it becomes the baseline:  "
              "python3 mlb_calibration.py\n")
        return
    print(f"\nMLB calibration over time · {db_path}\n")
    hdr = (f"{'market':<14}{'runs':>6}{'first ECE':>11}{'latest ECE':>12}"
           f"{'move':>9}   {'first seen':<12}{'latest code':<14}")
    print(hdr)
    print("-" * len(hdr))
    for m, d in sorted(t.items()):
        f, l = d["first"], d["last"]
        arrow = "better" if d["improved"] else (
            "same" if abs(d["ece_delta"]) < 0.0005 else "WORSE")
        print(f"{MARKET_LABELS.get(m, m)[:13]:<14}{d['runs']:>6}"
              f"{f['ece']:>11.3f}{l['ece']:>12.3f}"
              f"{d['ece_delta']:>+9.3f}   {str(f['ts'])[:10]:<12}"
              f"{str(l['code'] or '?'):<14}  {arrow}")
    single = [m for m, d in t.items() if d["runs"] < 2]
    if single:
        print(f"\n  {len(single)} market(s) have only one stored run — a "
              f"baseline, not a trend.")
    same = [m for m, d in t.items() if d["runs"] > 1 and d["same_code"]]
    if same:
        print(f"  {len(same)} market(s) moved without the code changing: "
              f"that is more data, not a better model.")
    print("\n  ECE falling = the stated probabilities are getting closer to "
          "what happens.\n  Nothing before this feature existed was recorded "
          "and none of it can be recovered.\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/history.db")
    ap.add_argument("--min-history", type=int, default=6)
    ap.add_argument("--naive", action="store_true",
                    help="ignore harvested book lines (baseline pricing only)")
    ap.add_argument("--no-save", action="store_true",
                    help="do not append this run to the calibration history")
    ap.add_argument("--trend", action="store_true",
                    help="show stored runs over time instead of sweeping")
    ap.add_argument("--note", default="",
                    help="what changed since the last run (stored with it)")
    args = ap.parse_args()

    if args.trend:
        _show_trend(args.db)
        return

    # What the DB actually holds, BEFORE the sweep. Without this the empty
    # case blamed --min-history for everything, including "there are no MLB
    # logs at all" — a confident wrong reason, which is worse than none,
    # because it sends you tuning a knob that was never the problem.
    stock = _stock(args.db)
    if not stock["logs"]:
        print(f"\nNo MLB player game logs in {args.db}.\n"
              f"  Nothing to calibrate against — the sweep would report an "
              f"empty table for every market.\n"
              f"  Fix: python3 ingest.py mlb --seasons <year>\n")
        return

    rows = sweep(args.db, min_history=args.min_history,
                 use_real_lines=not args.naive)

    # Kept, so "are we improving?" stops being a question nobody can answer.
    # A sweep detects a 2-point calibration change in thousands of settled
    # props today; the same change takes a season to surface in win-loss,
    # because betting outcomes are mostly variance. Judging model changes on
    # P&L alone is judging them on noise.
    if not args.no_save:
        from engine import calibhistory as _ch
        conn = _db.connect(args.db)
        for d in rows:
            if _get(d, "n", default=0) and d.get("_report") is not None:
                _ch.record(conn, "mlb", d["market"], d["_report"],
                           note=args.note)

    print(f"\nMLB per-market calibration · walk-forward on {args.db}")
    print(f"  {stock['logs']:,} MLB log row(s) · {stock['odds']:,} harvested "
          f"book line(s)")
    if not stock["odds"] and not args.naive:
        print("  ⚠️  No harvested odds, so the ROI column below is predictive "
              "skill only.\n      ECE and Brier are unaffected — they grade "
              "against OUTCOMES, not lines.\n      To price against real "
              "books: python3 harvest_odds.py mlb --from <d> --to <d>")
    print()
    hdr = (f"{'market':<14}{'props':>8}{'Brier':>9}{'ECE':>8}"
           f"{'bets':>7}{'win%':>7}{'ROI':>9}{'real lines':>12}")
    print(hdr)
    print("-" * len(hdr))
    for d in rows:
        label = MARKET_LABELS.get(d["market"], d["market"])[:13]
        n = _get(d, "n", default=0)
        if not n:
            have = stock["by_market"].get(d["market"], 0)
            why = (f"(no {label.lower()} rows stored at all)" if not have
                   else f"({have:,} row(s) stored, none with "
                        f"{args.min_history + 1}+ prior games — "
                        f"try --min-history {max(1, args.min_history - 3)})")
            print(f"{label:<14}{'—':>8}   {why}")
            continue
        brier = _get(d, "brier", default=float("nan"))
        ece = _get(d, "ece", default=float("nan"))
        bets = _get(d, "n_bets", default=0)
        wins = _get(d, "wins", default=0)
        roi = _get(d, "roi", default=0.0)
        used = _get(d, "used_real_lines", default=0)
        winpct = (wins / bets * 100) if bets else 0.0
        # Home runs are quarantined on the Long Shots board, which runs a
        # DIFFERENT model (engine/mlb/homeruns.py). This sweep walks the
        # generic prop model over them — a market it never bets, which is
        # why the row always reports 0 bets. Its ECE is real and it is
        # about a model nobody uses.
        #
        # Left in rather than hidden, because the fit derived from these
        # errors is what pushed mlb:home_runs to the edge of the search
        # grid, and correction_for's refusal to apply a boundary fit is the
        # only thing stopping that correction from being handed to the good
        # model. But labelled, because unlabelled it reads as "the home-run
        # model is broken" — which it is not, and which cost two rounds of
        # chasing before hr_backtest.py measured the real one at ECE 0.011.
        note = ("   ← generic model, NOT the Long Shots board "
                "(see hr_backtest.py)" if d["market"] == "home_runs" else "")
        print(f"{label:<14}{n:>8,}{brier:>9.4f}{ece:>8.3f}"
              f"{bets:>7}{winpct:>6.1f}%{roi:>+8.1%}{used:>12,}{note}")

    # The distinction that decides whether any of this is real: bets priced
    # against a harvested BOOK line are the only ones that answer "would
    # this have beaten the market?". Baseline-priced bets only show the
    # model beats a trailing average, which no sportsbook offers.
    print("\nBets priced against a REAL book line vs a naive baseline:")
    hdr2 = (f"{'market':<14}{'basis':<10}{'bets':>7}{'win%':>7}{'ROI':>9}"
            f"{'net u':>9}")
    print(hdr2)
    print("-" * len(hdr2))
    any_book = False
    for d in rows:
        segs = _get(d, "segments", default=None) or {}
        for basis in ("book", "naive"):
            g = segs.get(basis)
            if not g or not g.get("n_bets"):
                continue
            if basis == "book":
                any_book = True
            label = MARKET_LABELS.get(d["market"], d["market"])[:13]
            n = g["n_bets"]
            wr = g.get("wins", 0) / n * 100 if n else 0.0
            staked = g.get("staked", 0.0)
            net = g.get("net", 0.0)
            roi = (net / staked) if staked else 0.0
            tag = "vs BOOK" if basis == "book" else "baseline"
            print(f"{label:<14}{tag:<10}{n:>7}{wr:>6.1f}%{roi:>+8.1%}{net:>+9.2f}")
    if not any_book:
        print("  (no harvested book lines matched — the ROI column above is "
              "predictive skill only, NOT an edge over the market)")

    print("\nReliability — what the model said vs what happened:")
    for d in rows:
        bins = _get(d, "bins", default=None)
        if not bins:
            continue
        print(f"\n  {MARKET_LABELS.get(d['market'], d['market'])}")
        for b in bins:
            lo, hi = _get(b, "lo", default=0.0), _get(b, "hi", default=0.0)
            pred = _get(b, "mean_pred", "predicted")
            act = _get(b, "hit_rate", "actual")
            cnt = _get(b, "n", default=0)
            if pred is None or act is None or not cnt:
                continue
            gap = (act - pred) * 100
            verdict = ("overconfident" if gap < -3 else
                       "under-confident" if gap > 3 else "well calibrated")
            print(f"    p {lo:.1f}-{hi:.1f}: said {pred:5.1%} → actual {act:5.1%}"
                  f"  (n={cnt:,})  {gap:+5.1f}pts  {verdict}")

    print("\nECE under ~0.03 = trustworthy · over ~0.08 = the probabilities are "
          "fiction in that market.\n'said' above 'actual' is overconfidence — "
          "the thing every guard we added is compensating for.")


if __name__ == "__main__":
    main()
