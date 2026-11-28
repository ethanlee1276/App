#!/usr/bin/env python3
"""Is the money split reading the real tapes? Read-only, on the box.

    cd /srv/qellys && python3 moneyprobe.py            # NFL
    python3 moneyprobe.py cfb

Prints one raw trade from each venue's tape (the field names the parser in
engine/moneysplit reads), then every game on the built board with its
money split — or why it has none. Fetches with plain urllib and writes
nothing, so running it as root leaves no file the service cannot replace.
"""

import json
import sys
import urllib.request

from engine.moneysplit import KALSHI_TRADES, POLY_TRADES

BOARDS = {"nfl": "data/built/recommendations.json", "cfb": "data/built/cfb.json",
          "mlb": "data/built/mlb_recommendations.json"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "qellys-moneyprobe"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main(argv):
    sport = (argv[1] if len(argv) > 1 else "nfl").lower()
    series = {"nfl": "KXNFLGAME", "cfb": "KXNCAAFGAME", "mlb": "KXMLBGAME"}.get(sport, "KXNFLGAME")
    try:
        mk = _get(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&status=open&limit=5")
        t = (mk.get("markets") or [{}])[0].get("ticker")
        tr = _get(KALSHI_TRADES.format(t=t, n=2)).get("trades") or []
        print(f"Kalshi tape {t}: {json.dumps(tr[0], sort_keys=True) if tr else 'no trades yet'}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"Kalshi tape: unreachable ({type(exc).__name__}: {exc})")
    try:
        ev = _get("https://gamma-api.polymarket.com/markets?closed=false&limit=1&order=volume24hr&ascending=false")
        cid = (ev or [{}])[0].get("conditionId")
        tr = _get(POLY_TRADES.format(c=cid, n=2))
        print(f"Polymarket tape {str(cid)[:14]}…: {json.dumps(tr[0], sort_keys=True)[:400] if tr else 'no trades'}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"Polymarket tape: unreachable ({type(exc).__name__}: {exc})")
    try:
        b = json.load(open(BOARDS.get(sport, BOARDS["nfl"])))
    except (OSError, ValueError) as exc:
        print(f"board: unreadable ({exc})")
        return 1
    print(f"\nboard built {b.get('built_at')} · census {b.get('money_census')}")
    for g in b.get("games") or []:
        m = g.get("money")
        name = f"{g.get('away')}@{g.get('home')}"
        if not m:
            print(f"  {name:10} no split (started, unmatched, or too thin)")
            continue
        bits = []
        if m.get("ml"):
            bits.append(f"ML {g.get('away')} {m['ml']['away']:.0%} / {g.get('home')} {m['ml']['home']:.0%}"
                        f" (${m['ml']['usd']:,} · {m['ml']['n']} trades)")
        if m.get("spread"):
            bits.append(f"spread home {m['spread']['line']:+} {m['spread']['home']:.0%}")
        if m.get("total"):
            bits.append(f"total {m['total']['line']} over {m['total']['over']:.0%}")
        print(f"  {name:10} {' · '.join(bits)}  [{', '.join(m.get('venues') or [])}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
