#!/usr/bin/env python3
"""Build the Prediction Market Intelligence page's data.

    python3 pm_build.py --out web/data/predmarkets.json

Pulls Polymarket's top markets (Gamma API) and the public trade tape
(Data API) — both free, keyless — records everything into the history DB
(the tape cannot be backfilled, so recording runs before any analysis),
then scores the large flow and writes the page's JSON.
"""

from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

from engine import predmarket as pm
from engine.db import connect
from engine.sources.fetch import DataUnavailable


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/predmarkets.json")
    args = ap.parse_args()

    try:
        markets = pm.parse_markets(pm.fetch_markets())
        trades = pm.parse_trades(pm.fetch_trades())
    except DataUnavailable as exc:
        print(f"⚠️  Polymarket unreachable — keeping last data.\n   {exc}")
        raise SystemExit(2)
    # Dedicated big-trade pull: the general feed is nearly all retail-sized
    # fills, so without this a 500-row slice can contain zero whales.
    try:
        trades += pm.parse_trades(pm.fetch_big_trades())
    except DataUnavailable:
        pass

    conn = connect()
    new_trades = pm.store_trades(conn, trades)
    pm.store_snapshot(conn, markets)
    history = pm.wallet_history(conn)
    names = pm.wallet_names(conn)
    total_trades = conn.execute("SELECT COUNT(*) FROM pm_trades").fetchone()[0]

    # Score the last 24h of RECORDED tape, not just this pull's thin slice —
    # big trades are a few per hour, and the tape accumulates them.
    feed = pm.build_flow_feed(pm.recent_tape(conn), markets, history)
    for f in feed:
        f["name"] = names.get(f["wallet"], "")

    # Validation loop: persist every flag, settle the ones whose markets
    # resolved, and publish the report card. An ungraded flag is decoration.
    new_flags = pm.store_flags(conn, feed)
    try:
        settled = pm.resolve_flags(conn)
    except Exception:
        settled = 0
    validation = pm.flag_report(conn)
    for w in validation.get("wallets", []):
        w["name"] = names.get(w["wallet"], "")
    conn.close()

    # Top traders by realized P&L (Polymarket's own leaderboard), each with
    # their latest trades. Falls back to our tape's most-active wallets if
    # the leaderboard endpoint is unreachable.
    top_traders, traders_note = [], ""
    try:
        leaders, window_label = [], ""
        for window, label in pm.LEADERBOARD_WINDOWS:
            try:
                leaders = pm.parse_leaderboard(pm.fetch_leaderboard(window))[:10]
            except (DataUnavailable, ValueError):
                continue
            if leaders:
                window_label = label
                break
        if not leaders:
            raise DataUnavailable("no leaderboard window answered")
        by_wallet, pnl_by_wallet = {}, {}
        for ld in leaders:
            try:
                by_wallet[ld["wallet"]] = pm.parse_trades(
                    pm.fetch_wallet_trades(ld["wallet"]))
            except DataUnavailable:
                by_wallet[ld["wallet"]] = []
            try:
                # One-month cumulative P&L curve, straight from the same
                # endpoint Polymarket's own profile chart uses.
                pnl_by_wallet[ld["wallet"]] = pm.parse_pnl_series(
                    pm.fetch_pnl_series(ld["wallet"]))
            except (DataUnavailable, ValueError):
                pnl_by_wallet[ld["wallet"]] = []
        top_traders = pm.build_top_traders(leaders, by_wallet, pnl_by_wallet)
        traders_note = (f"ranked by realized profit over {window_label} "
                        f"(Polymarket leaderboard)")
    except (DataUnavailable, ValueError) as exc:
        ranked = sorted(history.items(), key=lambda kv: -kv[1]["usd"])[:10]
        top_traders = pm.build_top_traders(
            [{"wallet": w, "name": names.get(w, ""), "pnl": 0.0}
             for w, _ in ranked], {})
        traders_note = (f"leaderboard unreachable ({exc}) — showing our "
                        f"tape's most-active wallets instead")

    # Display board: live prices only — a settled market pinned at 0/100¢
    # (finished esports series etc.) is clutter, not information.
    display_markets = [m for m in markets if 0.02 <= m["yes"] <= 0.98]

    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "venue": "polymarket",
        "markets": display_markets[:50],
        "flow": feed,
        "validation": validation,
        "top_traders": top_traders,
        "traders_note": traders_note,
        "tape": {"stored_total": total_trades, "new_this_pull": new_trades,
                 "wallets_seen": len(history)},
    }
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print(f"Polymarket: {len(markets)} markets, {new_trades} new trade(s) "
          f"recorded ({total_trades:,} on tape, {len(history):,} wallets), "
          f"{len(feed)} flow flag(s) ≥ ${pm.FEED_FLOOR_USD:,}; "
          f"{new_flags} flag(s) stored, {settled} settled, "
          f"{validation.get('graded', 0)} graded all-time. Wrote {args.out}")


if __name__ == "__main__":
    main()
