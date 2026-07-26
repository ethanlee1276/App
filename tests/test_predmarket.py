"""Tests for Polymarket informed-flow detection (fixtures, no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import predmarket as pm


GAMMA = [
    {"slug": "fed-cut-march", "question": "Fed cuts rates in March?",
     "outcomes": '["Yes", "No"]', "outcomePrices": '["0.62", "0.38"]',
     "volume24hr": 2_400_000, "liquidity": 900_000, "endDate": "2026-03-18T00:00:00Z"},
    {"slug": "thin-market", "question": "Niche geopolitical event?",
     "outcomes": '["Yes", "No"]', "outcomePrices": '["0.07", "0.93"]',
     "volume24hr": 50_000, "liquidity": 12_000, "endDate": "2026-08-01T00:00:00Z"},
    {"slug": "broken", "question": "No prices", "outcomes": "[]",
     "outcomePrices": "[]", "volume24hr": 0},
]

NOW = 1_800_000_000


def _tape(wallet, slug, usd_price, size, ts, outcome="Yes", side="BUY"):
    return {"proxyWallet": wallet, "slug": slug, "title": slug,
            "price": usd_price, "size": size, "timestamp": ts,
            "outcome": outcome, "side": side, "transactionHash": f"0x{ts}"}


def test_parse_markets_handles_json_string_fields():
    ms = pm.parse_markets(GAMMA)
    assert [m["slug"] for m in ms] == ["fed-cut-march", "thin-market"]
    assert ms[0]["yes"] == 0.62 and ms[0]["vol24"] == 2_400_000
    assert ms[0]["end_date"] == "2026-03-18"


def test_parse_trades_computes_usd_and_drops_garbage():
    ts = pm.parse_trades([
        _tape("0xabc", "fed-cut-march", 0.62, 100_000, NOW),
        {"proxyWallet": "", "slug": "x", "price": 0.5, "size": 10, "timestamp": NOW},
        {"proxyWallet": "0xdef", "slug": "x", "price": "junk", "size": 10, "timestamp": NOW},
    ])
    assert len(ts) == 1
    assert ts[0]["usd"] == 62_000.0 and ts[0]["venue"] == "polymarket"


def test_tape_records_once_and_builds_wallet_history():
    from engine import db
    conn = db.connect(":memory:")
    trades = pm.parse_trades([
        _tape("0xwhale", "fed-cut-march", 0.62, 100_000, NOW - 90 * 86400),
        _tape("0xwhale", "thin-market", 0.07, 300_000, NOW),
        _tape("0xfresh", "thin-market", 0.07, 250_000, NOW),
    ])
    assert pm.store_trades(conn, trades) == 3
    assert pm.store_trades(conn, trades) == 0          # idempotent
    hist = pm.wallet_history(conn)
    assert hist["0xwhale"]["n"] == 2
    assert hist["0xwhale"]["first_ts"] == NOW - 90 * 86400
    assert hist["0xfresh"]["n"] == 1

    # Snapshots bucket to 10 minutes so a 60s refresh can't bloat the DB.
    ms = pm.parse_markets(GAMMA)
    assert pm.store_snapshot(conn, ms, now=NOW) == 2
    assert pm.store_snapshot(conn, ms, now=NOW + 30) == 0
    assert pm.store_snapshot(conn, ms, now=NOW + 700) == 2


def test_scoring_stacks_signals_and_shows_receipts():
    markets = {m["slug"]: m for m in pm.parse_markets(GAMMA)}
    hist = {"0xfresh": {"first_ts": NOW - 3600, "n": 1, "usd": 17_500},
            "0xold": {"first_ts": NOW - 90 * 86400, "n": 400, "usd": 9e6}}

    # Fresh wallet + real size into a thin market: the classic triad.
    triad = pm.score_trade(
        pm.parse_trades([_tape("0xfresh", "thin-market", 0.07, 250_000, NOW - 600)])[0],
        markets["thin-market"], hist, now=NOW)
    names = [s["name"] for s in triad["signals"]]
    assert "Fresh wallet" in names and "Niche market" in names
    assert "Order-book impact" in names            # 17.5k on a 50k/day market
    assert triad["score"] > 80                     # compounding bonus applied

    # A seasoned wallet's routine size in a deep market: low score, no drama.
    routine = pm.score_trade(
        pm.parse_trades([_tape("0xold", "fed-cut-march", 0.62, 20_000, NOW - 600)])[0],
        markets["fed-cut-march"], hist, now=NOW)
    assert routine["score"] < 30
    assert all(s["name"] != "Fresh wallet" for s in routine["signals"])

    # Below the floor: not in the feed at all.
    assert pm.score_trade(
        pm.parse_trades([_tape("0xold", "fed-cut-march", 0.62, 5_000, NOW)])[0],
        markets["fed-cut-march"], hist, now=NOW) is None


def test_actionability_live_chasing_historical():
    markets = {m["slug"]: m for m in pm.parse_markets(GAMMA)}
    hist = {}

    # Bought YES at 60c, market still 62c -> Live.
    live = pm.score_trade(
        pm.parse_trades([_tape("0xa", "fed-cut-march", 0.60, 40_000, NOW - 600)])[0],
        markets["fed-cut-march"], hist, now=NOW)
    assert live["status"] == "Live"

    # Bought NO at 20c; YES is 7c so NO is 93c now -> price ran, Chasing.
    chasing = pm.score_trade(
        pm.parse_trades([_tape("0xb", "thin-market", 0.20, 100_000, NOW - 600,
                               outcome="No")])[0],
        markets["thin-market"], hist, now=NOW)
    assert chasing["status"] == "Chasing"
    assert chasing["current_price"] == 0.93        # NO price = 1 - YES

    # A day-old flag is history regardless of price.
    old = pm.score_trade(
        pm.parse_trades([_tape("0xc", "fed-cut-march", 0.60, 40_000,
                               NOW - 30 * 3600)])[0],
        markets["fed-cut-march"], hist, now=NOW)
    assert old["status"] == "Historical"


def test_recent_tape_scores_across_pulls():
    """The flow feed scores the last 24h of RECORDED tape, not one pull's
    thin slice — big trades are rare per pull but accumulate on tape."""
    from engine import db
    conn = db.connect(":memory:")
    pm.store_trades(conn, pm.parse_trades([
        _tape("0xa", "fed-cut-march", 0.62, 40_000, NOW - 5 * 3600),   # older pull
        _tape("0xb", "fed-cut-march", 0.62, 30_000, NOW - 600),        # this pull
        _tape("0xc", "fed-cut-march", 0.62, 50_000, NOW - 40 * 3600),  # too old
    ]))
    tape = pm.recent_tape(conn, hours=24, now=NOW)
    assert [t["wallet"] for t in tape] == ["0xb", "0xa"]
    feed = pm.build_flow_feed(tape, pm.parse_markets(GAMMA),
                              pm.wallet_history(conn), now=NOW)
    assert len(feed) == 2


def test_leaderboard_parse_and_top_traders():
    leaders = pm.parse_leaderboard([
        {"proxyWallet": "0xking", "name": "TheKing", "amount": "1250000.5"},
        {"wallet": "0xquiet", "pnl": 400000},
        {"name": "no wallet — dropped"},
    ])
    assert leaders[0] == {"wallet": "0xking", "name": "TheKing", "pnl": 1250000.5}
    assert leaders[1]["wallet"] == "0xquiet" and leaders[1]["name"] == ""

    trades = {"0xking": pm.parse_trades([
        _tape("0xking", "fed-cut-march", 0.62, 100_000, NOW - 300),
        _tape("0xking", "thin-market", 0.07, 10_000, NOW - 9000),
    ])}
    top = pm.build_top_traders(leaders, trades, per_trader=5)
    assert top[0]["rank"] == 1 and top[0]["name"] == "TheKing"
    # Newest trade first, carrying the fields the page shows.
    assert top[0]["recent"][0]["market"] == "fed-cut-march"
    assert top[0]["recent"][0]["usd"] == 62_000.0
    assert top[1]["recent"] == []            # no trades pulled — still listed


def test_feed_ranks_by_score_then_size():
    markets = pm.parse_markets(GAMMA)
    hist = {"0xfresh": {"first_ts": NOW - 3600, "n": 1, "usd": 250_000}}
    trades = pm.parse_trades([
        _tape("0xold", "fed-cut-march", 0.62, 30_000, NOW - 300),
        _tape("0xfresh", "thin-market", 0.07, 250_000, NOW - 300),
    ])
    feed = pm.build_flow_feed(trades, markets, hist, now=NOW)
    assert [f["wallet"] for f in feed] == ["0xfresh", "0xold"]
    assert feed[0]["signals"] and feed[0]["score"] > feed[1]["score"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
