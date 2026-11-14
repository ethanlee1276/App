"""Polymarket's trade tape is read off Data API v2 (2026-11-14).

Polymarket retired Data API v1 on 2 November 2026: v1's /trades answers
"410 Gone". The money split's census named it (engine/moneysplit, step QN,
"HTTP Error 410: Gone" on every board) twelve days later, and the flow feed
(engine/predmarket) had been reading the same retired route, falling back
to the copy it had cached on 2 November. v2 wraps its rows in `data`,
spells its fields in snake_case and takes snake_case parameters.

    python3 tests/test_polymarket_reads_data_api_v2.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import predmarket as PM                      # noqa: E402

V2 = {"data": [{"proxy_wallet": "0xabc", "slug": "chiefs-bills", "transaction_hash": "0xt1",
                "timestamp": "2026-11-14T20:15:00Z", "price": 0.55, "size": 20000, "side": "BUY",
                "outcome": "Chiefs", "title": "Chiefs vs Bills", "name": "whale"},
               {"proxy_wallet": "0xdef", "slug": "chiefs-bills", "transaction_hash": "0xt2",
                "timestamp": 1794690000, "price": 0.45, "size": 100, "side": "SELL", "outcome": "Bills"}],
      "next_cursor": "c2"}


def _calls(body):
    sent = []

    def fake(url, cache_name, ttl=0, **kw):
        sent.append((url, cache_name))
        return json.dumps(body)
    return sent, fake


def test_the_three_tape_reads_ask_v2_in_its_own_words():
    sent, fake = _calls(V2)
    real = PM.fetch_text
    PM.fetch_text = fake
    try:
        PM.fetch_trades()
        PM.fetch_big_trades(min_cash=5000)
        PM.fetch_wallet_trades("0xabc")
    finally:
        PM.fetch_text = real
    urls = [u for u, _ in sent]
    assert all(u.startswith("https://data-api.polymarket.com/v2/trades?") for u in urls), urls
    assert "taker_only=true" in urls[0] and "takerOnly" not in " ".join(urls)
    assert "filter_type=CASH" in urls[1] and "filter_amount=5000" in urls[1], urls[1]
    assert "user=0xabc" in urls[2]
    assert [c for _, c in sent] == ["pm_trades_v2.json", "pm_big_trades_v2.json", "pm_wtrades2_0xabc.json"], \
        "new cache names: v1's last copies are never served as v2's"


def test_v2_rows_read_as_v1_and_the_parser_takes_them():
    rows = PM.v2_rows(V2)
    assert rows[0]["proxyWallet"] == "0xabc" and rows[0]["proxy_wallet"] == "0xabc"
    assert rows[0]["transactionHash"] == "0xt1"
    got = PM.parse_trades(rows)
    assert [t["tx"] for t in got] == ["0xt1", "0xt2"], got
    assert got[0]["ts"] == 1794687300 and got[1]["ts"] == 1794690000, "ISO stamps and epoch seconds both read"
    assert got[0]["usd"] == 11000.0 and got[0]["trader"] == "whale"
    assert PM.v2_rows([{"proxyWallet": "0x1"}]) == [{"proxyWallet": "0x1"}], "v1's bare list still reads"
    assert PM.v2_rows({"error": "Data API v1 has been retired"}) == []
    assert PM._epoch(1794690000000) == 1794690000 and PM._epoch("junk") == 0 and PM._epoch(None) == 0


def test_the_feed_probe_asks_v2():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"https://data-api.polymarket.com/v2/trades?limit=1"' in src
    assert '"https://data-api.polymarket.com/trades?limit=1"' not in src


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
