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
import os
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
from engine.sources import rugcheck, solrpc

#: Enrich at most this many mints per run — two DexScreener batch calls.
MAX_TRACKED = 60
#: Holder-concentration lookups per run: one RPC POST each, ten-minute
#: cache, board order (the coins read first get measured first). The
#: public RPC's rate limits are why this is not 60.
HOLDER_LOOKUPS = 20
#: RugCheck lookups per run — mint/freeze authority, LP lock, named
#: dangers. Its rate limits are undocumented and the loop ticks every
#: 15s, so this stays conservative: 15-minute cache means a coin costs
#: ONE request per 15 minutes however fast the loop runs.
RUGCHECK_LOOKUPS = 15
#: Sparkline points exported per coin — the page draws price over our
#: own tape, so the series is capped where the drawing stops earning.
#: 120 points at the 15-second live tick is a ~30-minute window, which
#: is a meme coin's whole arc.
SPARK_POINTS = 120


def _tracked_mints(discovered: list[str],
                   history: dict) -> tuple[list[str], set[str]]:
    """Discovery order, then CARRIED coins — mints with a live tape that
    just fell off the trending/new lists.

    A dying coin leaves trending IMMEDIATELY, which is exactly the
    moment the danger channel needs its next sighting most — dropping it
    right then blinded the exit signals at their one useful hour, and a
    pumping coin that rotated off trending vanished mid-move. So any
    mint with tape history stays on the scan until its tape ages out
    (HISTORY_KEEP_S, 2h): the carry costs nothing extra, because the
    DexScreener batch prices any mint it is handed. Carried coins fill
    AFTER discovery, newest-sighting first, inside the same budget.
    """
    seen = set(discovered)
    out = list(discovered)
    carried: set[str] = set()
    for m in sorted(history,
                    key=lambda k: -(history[k][-1].get("ts") or 0)):
        if len(out) >= MAX_TRACKED:
            break
        if m in seen or not solrpc.B58.match(m or ""):
            continue
        seen.add(m)
        out.append(m)
        carried.add(m)
    return out[:MAX_TRACKED], carried


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

    # Order matters, and it is NEW first on purpose (an earlier comment
    # here claimed trending-first while the code did this — the code was
    # right): the freshest pools are the ones that move in and out in
    # minutes, and board order decides who gets the holder and RugCheck
    # lookups. Trending follows, then boosted-only mints, then CARRY.
    discovered, seen = [], set()
    for m in ([r["mint"] for r in gt_rows] + boosted):
        if m not in seen:
            seen.add(m)
            discovered.append(m)
    mints, carried = _tracked_mints(discovered, load_history())

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
        row["carried"] = m in carried
        rows.append(row)

    # Holder concentration off the public Solana RPC — the one
    # Phantom/Axiom holder metric the free tier reaches. Failures are
    # counted, not fatal: a coin without the measurement shows "—", and
    # unmeasured never scores as safe (or as dangerous).
    fails, first_err = 0, None
    for r in rows[:HOLDER_LOOKUPS]:
        try:
            h = solrpc.parse_holder_slice(
                solrpc.fetch_holder_slice(r["mint"]))
            if h:
                r["holders"] = h
        except DataUnavailable as exc:
            fails += 1
            # Keep the FIRST error's text: "20/20 declined" from Ethan's
            # first live run said something was wrong and nothing about
            # what — the count without the cause is a symptom report.
            if first_err is None:
                first_err = str(exc)[:160]
            if getattr(exc, "status", None) == 429:
                # One 429 means the window is spent. Firing the rest of
                # the lookups into a rate limiter is how a cooldown never
                # ends — that WAS the 20/20 pattern on the first live run.
                break
    if fails:
        notes.append(f"solana rpc holders: {fails}/"
                     f"{min(len(rows), HOLDER_LOOKUPS)} lookup(s) declined"
                     + (f" — first error: {first_err}" if first_err else ""))
    # RugCheck: mint/freeze authority, LP lock, named dangers — the two
    # worst switches a dev holds, previously in the doc's PARKED table.
    fails = 0
    for r in rows[:RUGCHECK_LOOKUPS]:
        try:
            rep = rugcheck.parse_report(rugcheck.fetch_report(r["mint"]))
            if rep:
                r["rug"] = rep
        except DataUnavailable as exc:
            fails += 1
            if getattr(exc, "status", None) == 429:
                break              # same lesson as the Solana loop
    if fails:
        notes.append(f"rugcheck: {fails}/"
                     f"{min(len(rows), RUGCHECK_LOOKUPS)} lookup(s) declined")
    return rows, notes


#: A second builder holding the lock longer than this is not "still
#: running", it is dead mid-crash — steal the lock rather than letting
#: one wedged process stop the scan forever (the .nightly.lock lesson).
LOCK_STALE_S = 120


def _acquire_lock(out: Path):
    """One builder at a time, or the tape's read-modify-rewrite races.

    The 15-second live loop and the 60-second refresh_all cycle both run
    this script; two at once each read the tape, each append their own
    snapshot, and the second write silently discards the first one's —
    plus both truncate the board JSON under the page's 20-second poll.
    mkdir is the atomic test-and-set; the loser exits quietly, because
    its sibling is already doing the identical work.
    """
    lock = out.parent / ".memes_build.lock"
    try:
        lock.mkdir(parents=True)
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime < LOCK_STALE_S:
                return None
            os.utime(lock)                   # steal, and restamp the clock
        except OSError:
            return None
        return lock
    return lock


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/memecoins.json")
    args = ap.parse_args(argv)

    lock = _acquire_lock(Path(args.out))
    if lock is None:
        print("Rocket Radar: another build is already running — skipped.")
        return 0
    try:
        return _build(args)
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass


def _build(args) -> int:
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
            tape = hist.get(c.get("mint"), [])
            c["spark"] = [[round(h["ts"]), h["price"]] for h in tape
                          if h.get("ts") and h.get("price") is not None
                          ][-SPARK_POINTS:]
            # First sighting on OUR tape — the page's "new" badge. The
            # pair's on-chain age says when the coin was born; this says
            # when it reached the radar, which is the moment that matters
            # for "what just landed".
            if tape and tape[0].get("ts"):
                c["first_seen"] = round(tape[0]["ts"])
        print(f"Rocket Radar: {board['n']} coin(s) scored, "
              f"{board['gated']} behind the risk gate, "
              f"{len(board['rocket'])} on the rocket list, "
              f"{len(board['exits'])} flashing exit — "
              f"{n_snap} snapshot(s) taped.")

        # THE RECORD. Ethan, 2026-08-19: "track which meme coins we
        # recommend and if they actually gain value or lose value after we
        # recommend them." Both channels are filed at the price on this
        # build, every open call is re-marked against the same prices, and
        # nothing is ever deleted — including the coins that vanish, which
        # is most of the truth about this asset class.
        #
        # Its own failure domain, like every other layer here: a broken
        # ledger costs the record, never the board.
        try:
            from engine import memeledger
            mconn = memeledger.connect()
            try:
                new_calls = memeledger.log_calls(mconn, board)
                marks = memeledger.mark(mconn, board)
                memeledger.export_json(mconn, "web/data/memerecord.json")
            finally:
                mconn.close()
            print(f"  Record: {new_calls} new call(s), "
                  f"{marks['marked']} re-marked, {marks['stamped']} horizon(s) "
                  f"stamped, {marks['gone']} coin(s) gone from the feed.")
        except Exception as exc:                               # noqa: BLE001
            print(f"  ⚠️  Record skipped — {exc}")
    else:
        board.update({"coins": [], "rocket": [], "exits": [],
                      "gated": 0, "n": 0})
        print("Rocket Radar: no data — every source declined. "
              + ("; ".join(notes) if notes else ""))

    out = Path(args.out)
    # THROUGH THE GATE, since 2026-08-22. `coins`, `rocket` and `exits`
    # became paid keys when memecoins.json moved out of gate.FREE_FILES,
    # and this builder was still writing the whole board straight to the
    # public path — so the scan went back on the open web on the next
    # 20-second cycle, every cycle, no matter how recently `--seal` had
    # been run. Gating a key and leaving its builder writing directly is
    # a paywall that is true for exactly as long as it takes to rebuild.
    #
    # publish() is atomic on both copies for the same reason the direct
    # write was: this file is polled every ~20 seconds while it is being
    # rewritten, and a truncate-and-write caught mid-poll serves half a
    # JSON document.
    from engine import gate
    gate.publish(board, out, out.name)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
