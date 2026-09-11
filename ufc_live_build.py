#!/usr/bin/env python3
"""Live fight state → web/data/ufc_live.json.

Separate from `ufc_build.py` on purpose. The card build is a model run
that costs odds credits and takes seconds; this is a small read of a free
feed that has to happen every few seconds while a fight is on. Tying them
together would mean either a stale diagram or a card rebuilt 200 times a
night.

Usage:
    python3 ufc_live_build.py
    python3 ufc_live_build.py --date 2026-08-09
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.ufc import live

OUT = Path("web/data/ufc_live.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    try:
        blob = live.refresh(args.date or None)
    except Exception as exc:  # noqa: BLE001
        # A payload that SAYS the feed failed, never a silently empty one:
        # "no fights" and "we could not look" are opposite facts and the
        # page must be able to tell them apart.
        blob = {"status": "unavailable", "bouts": [], "note": str(exc),
                "disclaimer": ""}

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(blob, indent=2))

    live_n = blob.get("live_count", 0)
    if blob["status"] == "live":
        for b in blob["bouts"]:
            if not b["status"]["live"]:
                continue
            names = " vs ".join(f["name"] for f in b["fighters"])
            s = b["status"]
            print(f"LIVE  {names}  R{s['round']} {s['clock']}"
                  + ("" if b["has_targets"] else "  (no target data)"))
    else:
        print(f"UFC live: {blob['status']} — {blob.get('note', '')[:80]}")
    if live_n and not any(b["has_targets"] for b in blob["bouts"]):
        print("  ⚠️  no head/body/leg counts — run "
              "`python3 launch.py --probe-live`")


if __name__ == "__main__":
    main()
