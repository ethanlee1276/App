#!/usr/bin/env python3
"""Which sportsbooks does The Odds API offer us, region by region? Read-only.

    cd /srv/qellys && sudo -u qellys env $(sudo cat /etc/qellys/env | grep ^ODDS_API_KEY | xargs) python3 bookprobe.py

Ethan, 2026-09-28: bet365 was the best price on all three legs of a
research report and it is not among the books the site pulls. This asks
the API for one market (moneyline) in each region and prints the
bookmaker keys that answer, with the credits it spent (one per region
per market — about six). The key is read from the environment and never
printed.
"""

import json
import os
import sys
import urllib.parse
import urllib.request

REGIONS = ("us", "us2", "us_ex", "uk", "eu", "au")


def main() -> int:
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        print("ODDS_API_KEY is not in the environment — run it as the runbook line shows.")
        return 1
    ours = set()
    try:
        from engine.sources.oddsapi import BOOK_TITLES
        ours = set(BOOK_TITLES)
    except Exception:                                          # noqa: BLE001
        pass
    for region in REGIONS:
        q = urllib.parse.urlencode({"apiKey": key, "regions": region, "markets": "h2h", "oddsFormat": "american"})
        url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?{q}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                left = r.headers.get("x-requests-remaining")
                games = json.loads(r.read().decode("utf-8"))
        except Exception as exc:                               # noqa: BLE001
            print(f"{region:6} unreachable ({type(exc).__name__})")
            continue
        books = sorted({b.get("key") for g in games or [] for b in g.get("bookmakers") or [] if b.get("key")})
        new = [b for b in books if b not in ours]
        print(f"{region:6} {len(books):2} books · {', '.join(books) or 'none'}"
              + (f"\n       not pulled today: {', '.join(new)}" if new else "")
              + (f" · credits left {left}" if left else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
