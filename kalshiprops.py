#!/usr/bin/env python3
"""What Kalshi lists for NFL players — read on the box.

    python3 kalshiprops.py            # every series that looks like an NFL player stat
    python3 kalshiprops.py --all      # also print the sports series that did not match

Ethan's Bills @ Rams report 2 (2026-10-12) priced Stafford 250+ passing yards
at "Kalshi 68.5¢". The site reads Kalshi's NFL game, spread and total series
(engine/sources/kalshi.SPORT_SERIES, LINE_SERIES) and no player series,
because none was known. This is the discovery run, the way crowdprobe.py
found KXNFLSPREAD and KXNFLTOTAL before they were wired in: it lists Kalshi's
sports series, keeps the ones whose ticker or title reads as an NFL player
stat, and prints how many open events and markets each holds, with sample
titles, strikes and prices. Candidate tickers are tried as well, in case the
listing leaves a series out. Kalshi's market data is public and keyless.
Reads only; the responses land in data/cache like every Kalshi read.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.sources import kalshi                                 # noqa: E402
from engine.sources.fetch import fetch_text                       # noqa: E402

#: Words a player-stat series carries in its ticker or title.
STAT_WORDS = ("yard", "yds", "reception", "rec", "receiving", "rushing", "rush",
              "passing", "pass", "touchdown", "td", "completion", "attempt",
              "interception", "player", "prop")
NFL_WORDS = ("nfl", "football", "pro football")
#: Tickers tried directly, whatever the listing says. Guesses on purpose:
#: one that does not exist fetches nothing and costs nothing.
CANDIDATES = ("KXNFLPASSYDS", "KXNFLRUSHYDS", "KXNFLRECYDS", "KXNFLREC",
              "KXNFLPASSTD", "KXNFLANYTD", "KXNFLTD", "KXNFLPLAYER",
              "KXNFLPROPS", "KXNFLPLAYERPROPS")
SERIES_URL = f"{kalshi.KALSHI}/series?category=Sports"


def _get(url: str, cache: str) -> dict:
    return json.loads(fetch_text(url, cache, ttl=600))


def _words(text: str) -> set:
    return set(re.findall(r"[a-z]+", str(text or "").lower()))


def is_nfl_player_series(s: dict) -> bool:
    """An NFL series whose ticker or title names a player stat. The game,
    spread and total series the site already reads are not this."""
    ticker = str(s.get("ticker") or "")
    text = f"{ticker} {s.get('title') or ''} {' '.join(s.get('tags') or [])}".lower()
    if ticker in {t for v in kalshi.LINE_SERIES.values() for t in v} or \
            ticker in {t for v in kalshi.SPORT_SERIES.values() for t in v}:
        return False
    nfl = any(w in text for w in NFL_WORDS) or ticker.upper().startswith(("KXNFL", "NFL"))
    stat = bool(_words(text) & set(STAT_WORDS)) or any(w in ticker.lower() for w in ("yds", "rec", "td"))
    return nfl and stat


def describe(series: str, events: list) -> list[str]:
    """Lines to print for one series: counts, then up to three markets."""
    mk = [m for ev in events for m in (ev.get("markets") or [])]
    out = [f"  {series}: {len(events)} open events · {len(mk)} markets"]
    for m in mk[:3]:
        out.append(f"     {m.get('ticker')}  {m.get('title')!r}  floor={m.get('floor_strike')} "
                   f"yes {m.get('yes_bid_dollars', m.get('yes_bid'))}/{m.get('yes_ask_dollars', m.get('yes_ask'))}"
                   f" vol={m.get('volume')}")
    return out


def main(argv=None, get=_get, events=kalshi.fetch_events) -> int:
    argv = list(argv or [])
    try:
        listed = (get(SERIES_URL, "kalshi_series_sports.json") or {}).get("series") or []
    except Exception as exc:                                       # noqa: BLE001
        print(f"Kalshi series list: unavailable ({type(exc).__name__}: {exc})")
        listed = []
    hits = [s for s in listed if is_nfl_player_series(s)]
    print(f"Kalshi sports series listed: {len(listed)} · NFL player-stat series: {len(hits)}")
    for s in hits:
        print(f"  {s.get('ticker')}  {s.get('title')!r}  tags={s.get('tags')}")
    if "--all" in argv:
        for s in listed:
            if s not in hits:
                print(f"     (other) {s.get('ticker')}  {s.get('title')!r}")
    tried = [str(s.get("ticker")) for s in hits] + [c for c in CANDIDATES
                                                    if c not in {str(s.get('ticker')) for s in hits}]
    print("\nOpen events and markets:")
    found = 0
    for series in tried:
        try:
            evs = events(series)
        except Exception as exc:                                   # noqa: BLE001
            print(f"  {series}: error ({type(exc).__name__})")
            continue
        if evs:
            found += 1
        for line in describe(series, evs):
            print(line)
    print(f"\n{found} series with open events. Paste this back; nothing is wired in until a series is real.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
