#!/usr/bin/env python3
"""Probe round 3 (final): the exact row shapes inside ESPN's stats and
eventlog payloads — the last unknowns before the adapter is built.

    python3 ufc_probe.py
"""

from __future__ import annotations

import json
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ID = "2506250"      # Jan Blachowicz, verified in round 2


def jget(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001
        print("  fetch error:", e)
        return 0, None


def trim(obj, n=700) -> str:
    return json.dumps(obj)[:n]


def main() -> None:
    # 1) v3-stats: category names, labels, and ONE full row from each.
    st, d = jget(f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{ID}/stats")
    print(f"[v3-stats] {st}  top keys: {list((d or {}).keys())}")
    for cat in (d or {}).get("categories", []):
        keys = list(cat.keys())
        print(f"\n  category '{cat.get('displayName') or cat.get('name')}' keys={keys}")
        print(f"    labels: {cat.get('labels')}")
        for rowkey in ("events", "statistics", "totals"):
            rows = cat.get(rowkey)
            if isinstance(rows, list) and rows:
                print(f"    {rowkey}: {len(rows)} rows; first row FULL:")
                print(f"      {trim(rows[0])}")
            elif rows is not None:
                print(f"    {rowkey}: {trim(rows, 300)}")
    # Any top-level event metadata map (dates/opponents/results)?
    for k in (d or {}):
        if k not in ("categories", "filters", "glossary"):
            v = d[k]
            sample = v
            if isinstance(v, dict) and v:
                fk = next(iter(v))
                sample = {fk: v[fk]}
            print(f"\n  top-level '{k}': {trim(sample, 600)}")

    # 2) v3-eventlog: one full item.
    st, d = jget(f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{ID}/eventlog")
    print(f"\n[v3-eventlog] {st}  top keys: {list((d or {}).keys())}")
    evs = (d or {}).get("events")
    if isinstance(evs, dict):
        print("  events keys:", list(evs.keys())[:6])
        items = evs.get("items") or []
        if items:
            print("  first item FULL:", trim(items[0], 900))
    elif isinstance(evs, list) and evs:
        print("  first item FULL:", trim(evs[0], 900))

    # 3) fight history candidates.
    for path in ("fighthistory", "history", "results"):
        st, d = jget(f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{ID}/{path}")
        print(f"\n[v3-{path}] {st}", end="")
        if d:
            print(f"  keys={list(d.keys())}")
            print("  sample:", trim(d, 500))
        else:
            print()

    # 4) core eventlog → follow one competition ref for result/method shape.
    st, d = jget(f"https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/athletes/{ID}/eventlog")
    items = (((d or {}).get("events") or {}).get("items") or [])
    print(f"\n[core-eventlog] {st}  {len(items)} items on page 1")
    if items:
        comp_ref = (items[0].get("competition") or {}).get("$ref", "")
        comp_ref = comp_ref.replace("http://", "https://")
        print("  following competition ref:", comp_ref)
        st, c = jget(comp_ref)
        if c:
            print(f"  competition keys: {list(c.keys())}")
            print("  status:", trim(c.get("status"), 400))
            print("  type:", trim(c.get("type"), 300))
            comps = c.get("competitors") or []
            if comps:
                print("  competitor[0]:", trim(comps[0], 400))
            for k in ("details", "notes", "format"):
                if k in c:
                    print(f"  {k}:", trim(c[k], 300))

    print("\nDone — paste everything above back into the chat.")


if __name__ == "__main__":
    main()
