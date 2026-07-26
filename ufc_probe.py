#!/usr/bin/env python3
"""Probe round 2: pin down the exact ESPN athlete id + endpoint shapes,
and measure Octagon API coverage. Run and paste the whole output.

    python3 ufc_probe.py
"""

from __future__ import annotations

import json
import re
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url: str, timeout: int = 20) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300]
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode()


def jget(url: str):
    status, body = get(url)
    if status != 200:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return status, None


def main() -> None:
    # 1) Find Blachowicz the RIGHT way: walk search-v2's player results.
    status, d = jget("https://site.web.api.espn.com/apis/search/v2"
                     "?query=jan%20blachowicz&limit=10")
    espn_id = None
    print(f"[search-v2] {status}")
    for rt in (d or {}).get("results", []):
        if rt.get("type") != "player":
            continue
        for item in rt.get("contents", []):
            print("  player item:", json.dumps(item)[:400])
            m = re.search(r"/id/(\d+)", json.dumps(item))
            if m and espn_id is None:
                espn_id = m.group(1)
    if not espn_id:
        espn_id = "3949584"          # widely-cited Blachowicz id — verify below
        print(f"  no player hit parsed — trying fallback id {espn_id}")
    else:
        print(f"  → athlete id {espn_id}")

    # 2) ESPN endpoint battery with a real id.
    probes = [
        ("v3-base", f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{espn_id}"),
        ("v3-overview", f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{espn_id}/overview"),
        ("v3-stats", f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{espn_id}/stats"),
        ("v3-gamelog", f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{espn_id}/gamelog"),
        ("v3-eventlog", f"https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{espn_id}/eventlog"),
        ("core-league-athlete", f"https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/athletes/{espn_id}"),
        ("core-league-records", f"https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/athletes/{espn_id}/records"),
        ("core-league-eventlog", f"https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/athletes/{espn_id}/eventlog"),
        ("core-league-stats", f"https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/athletes/{espn_id}/statistics"),
    ]
    for name, url in probes:
        status, body = get(url)
        text = body.decode("utf-8", errors="replace")
        print(f"\n[{name}] {status}  {url}")
        print("  " + " ".join(text[:500].split()))

    # 3) The fighter web page's embedded JSON (fallback source).
    status, body = get(f"https://www.espn.com/mma/fighter/stats/_/id/{espn_id}")
    text = body.decode("utf-8", errors="replace")
    print(f"\n[espn-fighter-page] {status}  {len(text):,}B")
    if status == 200:
        print("  has __espnfitt__:", "__espnfitt__" in text)
        for token in ("sigStrikes", "takedown", "SLpM", "strikeAccuracy",
                      "fighterHistory", "statistics"):
            print(f"  contains '{token}':", token.lower() in text.lower())

    # 4) Octagon API: coverage + one detail record.
    status, d = jget("https://api.octagon-api.com/fighters")
    if d:
        keys = list(d.keys())
        print(f"\n[octagon-fighters] {status}  {len(keys)} fighters total")
        for probe_name in ("jan-blachowicz", "aleksandar-rakic", "marcin-tybura",
                           "hailey-cowan", "carlos-ulberg"):
            print(f"  has {probe_name}:", probe_name in d)
        sample = keys[0]
        print(f"  sample record [{sample}]:",
              json.dumps(d[sample])[:500])

    print("\nDone — paste everything above back into the chat.")


if __name__ == "__main__":
    main()
