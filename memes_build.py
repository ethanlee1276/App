#!/usr/bin/env python3
"""Rocket Radar build: discover → enrich → score → web/data/memecoins.json.

Free tier end to end. Discovery is GeckoTerminal's new + trending Solana
pools plus DexScreener's paid-boost roster (a risk flag that helpfully
also names tokens someone wants seen); enrichment is ONE batched
DexScreener call per 30 mints; scoring is engine/memecoins.py. Each run
appends to the snapshot tape, so acceleration — the spec's core signal —
sharpens with every refresh the launcher makes.

    python3 memes_build.py --out web/data/memecoins.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

from engine.memecoins import (build_board, load_history, record_snapshots,
                              RISK_GATE)
from engine.sources.dexes import (fetch_new_pools, fetch_pairs_for,
                                  fetch_top_boosts, fetch_trending_pools,
                                  parse_boosts, parse_dex_pairs,
                                  parse_gt_pools)
from engine.sources.fetch import DataUnavailable

#: Enrich at most this many mints per run — two DexScreener batch calls.
MAX_TRACKED = 60


def gather() -> tuple[list[dict], list[str]]:
    """Discovery + enrichment,each source failing independently."""
    notes: list[str] = []
    gt_rows: list[dict] = []
    for name, fn in (("new", fetch_new_pools), ("trending",
                                                fetch_trending_pools)):
        try:
            gt_rows += parse_gt_pools(fn())
        except DataUnavailable as exc:
            notes.append(f"geckoterminal {name}: {exc}")
    boosted: list[str] = []
    try:
        boosted = parse_boosts(fetch_top_boosts())
    except DataUnavailable as exc:
        notes.append(f"dexscreener boosts: {exc}")

    # Order matters: trending first (they have the volume), then new,
    # then boosted-only mints — trimmed to the tracking budget.
    seen, mints = set(), []
    for m in ([r["mint"] for r in gt_rows] + boosted):
        if m not in seen:
            seen.add(m)
            mints.append(m)
    mints = mints[:MAX_TRACKED]

    dex: dict = {}
    for i in range(0, len(mints), 30):
        try:
            dex.update(parse_dex_pairs(fetch_pairs_for(mints[i:i + 30])))
        except DataUnavailable as exc:
            notes.append(f"dexscreener pairs: {exc}")

    # Merge: DexScreener row is the base (richer), GT contributes the
    # unique buyer/seller counts DexScreener's free tier lacks.
    gt_by_mint = {r["mint"]: r for r in gt_rows}
    rows = []
    for m in mints:
        row = dex.get(m) or gt_by_mint.get(m)
        if not row:
            continue
        gt = gt_by_mint.get(m)
        if gt and row is not gt:
            for k in ("tx_m5", "tx_m15", "tx_m30", "tx_h1", "tx_h24"):
                if gt.get(k):
                    row[k] = gt[k]
            row.setdefault("created_at", gt.get("created_at"))
        rows.append(row)
    return rows, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/memecoins.json")
    args = ap.parse_args(argv)

    rows, notes = gather()
    board = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
             "status": "live" if rows else "unavailable",
             "notes": notes, "risk_gate": RISK_GATE}
    if rows:
        n_snap = record_snapshots(rows, ts=time.time())
        board.update(build_board(rows, load_history()))
        print(f"Rocket Radar: {board['n']} coin(s) scored, "
              f"{board['gated']} behind the risk gate, "
              f"{len(board['rocket'])} on the rocket list, "
              f"{len(board['exits'])} flashing exit — "
              f"{n_snap} snapshot(s) taped.")
    else:
        board.update({"coins": [], "rocket": [], "exits": [],
                      "gated": 0, "n": 0})
        print("Rocket Radar: no data — every source declined. "
              + ("; ".join(notes) if notes else ""))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=1))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
