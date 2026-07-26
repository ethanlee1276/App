#!/usr/bin/env python3
"""One-shot probe: which UFC fighter-data sources actually answer, and
with what shape? Run it and paste the whole output back — it fetches a
handful of pages for one known fighter (Jan Blachowicz) and prints a
compact fingerprint of each response. Nothing is stored; ~10 requests.

    python3 ufc_probe.py
"""

from __future__ import annotations

import json
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

CANDIDATES = [
    ("espn-search-v3",
     "https://site.web.api.espn.com/apis/common/v3/search?query=blachowicz&limit=5"),
    ("espn-search-v2",
     "https://site.web.api.espn.com/apis/search/v2?query=blachowicz&limit=5"),
    ("espn-mma-scoreboard",
     "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"),
    ("espn-core-athletes",
     "https://sports.core.api.espn.com/v3/sports/mma/ufc/athletes?limit=3"),
    ("octagon-fighters",
     "https://api.octagon-api.com/fighters"),
    ("octagon-rankings",
     "https://api.octagon-api.com/rankings"),
]

# Filled in after the search probes above tell us Blachowicz's ESPN id —
# but try a likely known id shape anyway so we learn the endpoint format.
ESPN_ID_PROBES = [
    ("espn-athlete-overview",
     "https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{id}/overview"),
    ("espn-athlete-stats",
     "https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{id}/stats"),
    ("espn-athlete-fights",
     "https://site.web.api.espn.com/apis/common/v3/sports/mma/athletes/{id}/fights"),
    ("espn-core-athlete",
     "https://sports.core.api.espn.com/v2/sports/mma/athletes/{id}"),
    ("espn-core-records",
     "https://sports.core.api.espn.com/v2/sports/mma/athletes/{id}/records"),
    ("espn-core-stats",
     "https://sports.core.api.espn.com/v2/sports/mma/athletes/{id}/statistics"),
]


def get(url: str, timeout: int = 20) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200]
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode()


def fingerprint(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return "(empty)"
    if text[:1] in "[{":
        try:
            d = json.loads(text)
        except ValueError:
            return "json-ish but unparsable: " + text[:150]
        if isinstance(d, dict):
            keys = list(d.keys())[:10]
            return f"JSON dict, {len(text):,}B, keys={keys}"
        return (f"JSON list, {len(text):,}B, {len(d)} items, "
                f"first={json.dumps(d[0])[:180] if d else '[]'}")
    first = " ".join(text[:200].split())
    return f"HTML/text, {len(text):,}B: {first}"


def show(name: str, url: str) -> bytes:
    status, body = get(url)
    print(f"\n[{name}] {status}\n  {url}\n  {fingerprint(body)}")
    return body if status == 200 else b""


def main() -> None:
    espn_id = None
    for name, url in CANDIDATES:
        body = show(name, url)
        # Pull a Blachowicz athlete id out of whichever search answers.
        if espn_id is None and body and b"lachowicz" in body:
            import re
            m = (re.search(rb'"id"\s*:\s*"?(\d{6,8})"?[^}]{0,300}?lachowicz', body)
                 or re.search(rb'lachowicz[^}]{0,300}?"id"\s*:\s*"?(\d{6,8})"?', body)
                 or re.search(rb'/id/(\d{6,8})', body))
            if m:
                espn_id = m.group(1).decode()
                print(f"  → found ESPN athlete id: {espn_id}")

    if espn_id:
        for name, tmpl in ESPN_ID_PROBES:
            show(name, tmpl.format(id=espn_id))
    else:
        print("\n(no ESPN athlete id found in the search responses — "
              "the id-based probes were skipped; paste the output anyway)")

    # Octagon API detail probe: their /fighters payload keys fighters by slug.
    print("\nDone — paste everything above back into the chat.")


if __name__ == "__main__":
    main()
