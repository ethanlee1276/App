#!/usr/bin/env python3
"""What the prediction markets list beyond the winner — read on the box.

    python3 crowdprobe.py            # every league
    python3 crowdprobe.py nfl cfb

Prints, per league: how many Polymarket game events came back, how many
spread and total markets `polysports.parse_line` could read cleanly (with
a few samples), and how many markets each CANDIDATE Kalshi spread / total
series holds (with sample titles and strikes). The Polymarket half is live
in the builds; the Kalshi half is discovery — the series names below are
candidates, and this run is what says which are real before any of them
is wired in. Reads the venues' public APIs only; writes nothing.
"""
import sys

from engine.sources import kalshi, polysports

KALSHI_CANDIDATES = {
    "nfl": ("KXNFLSPREAD", "KXNFLTOTAL"),
    "cfb": ("KXNCAAFSPREAD", "KXNCAAFTOTAL"),
    "mlb": ("KXMLBSPREAD", "KXMLBTOTAL", "KXMLBRUNLINE"),
    "nba": ("KXNBASPREAD", "KXNBATOTAL"),
    "wnba": ("KXWNBASPREAD", "KXWNBATOTAL"),
}


def main(argv):
    leagues = argv or list(polysports.SPORT_TAGS)
    for lg in leagues:
        print(f"\n== {lg.upper()} ==")
        try:
            rows, report = polysports.fetch_sports([lg])
        except Exception as exc:                               # noqa: BLE001
            print(f"  Polymarket: unavailable ({type(exc).__name__}: {exc})")
            rows, report = [], {}
        lines = [ln for r in rows for ln in (r.get("lines") or [])]
        spreads = [ln for ln in lines if ln["kind"] == "spread"]
        totals = [ln for ln in lines if ln["kind"] == "total"]
        print(f"  Polymarket: {len(rows)} game moneylines · {len(spreads)} spreads · {len(totals)} totals · {report}")
        for ln in (spreads[:2] + totals[:2]):
            print(f"     {ln['kind']:6} {ln.get('team', ''):>14} {ln['line']:>6}  p={ln['p']}  "
                  f"{ln['price_basis']} {ln.get('spread_cents')}c liq={ln.get('liquidity')}")
        for series in KALSHI_CANDIDATES.get(lg, ()):
            try:
                events = kalshi.fetch_events(series)
            except Exception as exc:                           # noqa: BLE001
                print(f"  Kalshi {series}: error ({type(exc).__name__})")
                continue
            mk = [m for ev in events for m in (ev.get("markets") or [])]
            print(f"  Kalshi {series}: {len(events)} events · {len(mk)} markets")
            for m in mk[:3]:
                print(f"     {m.get('ticker')}  {m.get('title')!r}  "
                      f"floor={m.get('floor_strike')} cap={m.get('cap_strike')} type={m.get('strike_type')}")


if __name__ == "__main__":
    main(sys.argv[1:])
