"""Read-only: does the settle pass's one recent read of the snapshot file
give the closes the whole file gives? (engine/ledger._PassSnapshots;
runbook step LQ.)

For the journal's open bets this builds the line, price and same-book
closes both ways: the recent read the settle pass does since 8 November,
and each reader on the whole file, as it did before. It compares every
close filed on or after the first day the recent read serves (the only
ones it is used for), prints the seconds each way and every close that
differs (none are expected), and writes nothing.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 tools/snapcheck.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _compare(name: str, whole, recent, first: str) -> int:
    """Every close filed on or after ``first`` in either index that the two
    give differently, printed; how many."""
    ka = {k for k in whole if str(k[2]) >= first}
    kb = {k for k in recent if str(k[2]) >= first}
    diff = sorted((k for k in ka | kb if whole.get(k) != recent.get(k)), key=str)
    print(f"{name}: {len(ka)} closes from {first} on | differ {len(diff)}")
    for k in diff[:8]:
        print("   ", k, "whole file:", whole.get(k), "| recent read:", recent.get(k))
    return len(diff)


def main() -> int:
    from engine import db, ledger
    from engine.closebook import SameBookCloses
    from engine.sources.oddsapi import normalize_name
    lconn, hconn = ledger.connect(), db.connect()
    rows = lconn.execute("SELECT * FROM bets WHERE status=?", ("open",)).fetchall()
    want = {(normalize_name(b["player"]), b["market"]) for b in rows}
    days = ledger._close_days(hconn, rows)
    parts: dict = {}
    snap = ledger._PassSnapshots(want, rows, hconn, days, parts)
    print(f"open bets {len(rows)} | the recent read serves {snap.first_day or 'nothing (no recent prop)'} on")
    if not snap.since:
        return 0
    t0 = time.monotonic()
    recent = snap._read(snap.since)
    t_recent = time.monotonic() - t0
    t0 = time.monotonic()
    lines = ledger._snapshot_closes(want)
    odds = ledger._snapshot_close_odds(want=want)
    sb = SameBookCloses(hconn, days=days)
    sb.prepare([dict(r) for r in rows if r["market"] not in ledger.GAME_MARKETS])
    t_whole = time.monotonic() - t0
    print(f"the recent read {t_recent:.1f}s ({parts.get('snapshot_share')} of the file) | "
          f"the three whole-file reads {t_whole:.1f}s")
    first = snap.first_day
    bad = _compare("line closes", lines, recent["lines"], first)
    bad += _compare("price closes", odds, recent["odds"], first)
    st_whole = {k for k in getattr(lines, "stamped", ()) if str(k[2]) >= first}
    st_recent = {k for k in getattr(recent["lines"], "stamped", ()) if str(k[2]) >= first}
    print(f"closes cut at a recorded start that differ: {len(st_whole ^ st_recent)}")
    bad += len(st_whole ^ st_recent)
    other = recent["samebook"].get("_samebook")
    if other is not None:
        bad += _compare("same-book closes", sb._snap or {}, other._snap or {}, first)
    print("SAME: every close the recent read serves is the whole file's" if not bad
          else f"DIFFERENT: {bad} closes. Paste this to Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
