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
from engine.sources import solrpc

#: Enrich at most this many mints per run — two DexScreener batch calls.
MAX_TRACKED = 60
#: Holder-concentration lookups per run: one RPC POST each, ten-minute
#: cache, discovery order (trending first — the coins read first get
#: measured first). The public RPC's rate limits are why this is not 60.
HOLDER_LOOKUPS = 20
#: Sparkline points exported per coin — the page draws price over our
#: own tape, so the series is capped where the drawing stops earning.
#: 120 points at the 15-second live tick is a ~30-minute window, which
#: is a meme coin's whole arc.
SPARK_POINTS = 120


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
            row.setdefault("pool", gt.get("pool"))
        rows.append(row)

    # Holder concentration off the public Solana RPC — the one
    # Phantom/Axiom holder metric the free tier reaches. Failures are
    # counted, not fatal: a coin without the measurement shows "—", and
    # unmeasured never scores as safe (or as dangerous).
    fails = 0
    for r in rows[:HOLDER_LOOKUPS]:
        try:
            h = solrpc.parse_holder_slice(
                solrpc.fetch_holder_slice(r["mint"]))
            if h:
                r["holders"] = h
        except DataUnavailable:
            fails += 1
    if fails:
        notes.append(f"solana rpc holders: {fails}/"
                     f"{min(len(rows), HOLDER_LOOKUPS)} lookup(s) declined")
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
        hist = load_history()
        board.update(build_board(rows, hist))
        # Per-coin price series off our own tape (the sighting recorded
        # above is already in it) — the page's sparkline. Compact pairs,
        # capped, because the board JSON ships to every visitor.
        for c in board["coins"]:
            c["spark"] = [[round(h["ts"]), h["price"]]
                          for h in hist.get(c.get("mint"), [])
                          if h.get("ts") and h.get("price") is not None
                          ][-SPARK_POINTS:]
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
