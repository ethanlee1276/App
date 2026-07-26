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

    conn = connect()
    new_trades = pm.store_trades(conn, trades)
    pm.store_snapshot(conn, markets)
    history = pm.wallet_history(conn)
    total_trades = conn.execute("SELECT COUNT(*) FROM pm_trades").fetchone()[0]

    feed = pm.build_flow_feed(trades, markets, history)
    conn.close()

    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "venue": "polymarket",
        "markets": markets[:50],
        "flow": feed,
        "tape": {"stored_total": total_trades, "new_this_pull": new_trades,
                 "wallets_seen": len(history)},
    }
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print(f"Polymarket: {len(markets)} markets, {new_trades} new trade(s) "
          f"recorded ({total_trades:,} on tape, {len(history):,} wallets), "
          f"{len(feed)} flow flag(s) ≥ ${pm.FEED_FLOOR_USD:,}. Wrote {args.out}")


if __name__ == "__main__":
    main()
