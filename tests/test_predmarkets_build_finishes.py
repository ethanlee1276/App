"""The prediction-market build finishes inside its ceiling, and its charts ship.

Ethan's droplet, 2026-09-23 (`journalctl`, six hours of it): pm_build.py
"timed out after 180 seconds" on every cycle. Only a success stamped the
ten-minute floor, so a killed build was tried again the next cycle — 180 of
each 599-second cycle, on a one-core box at a load of 3, while the sports
boards waited behind it — and the page kept its morning copy all day.

Now: a failed build backs off half an hour (launch.PREDMARKETS_FAIL_BACKOFF_S);
the build keeps its own clock under the kill (pm_build.BUDGET_S), prints
every step's time, and past it skips the optional network steps and keeps
the last published copy of them. And the price tape that has been recorded
since August is finally attached: it ran after `conn.close()`, every read
raised, `_attach_tape` swallowed each one, and no market ever had a chart.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pm_build                                                   # noqa: E402
from engine import predmarket as pm                               # noqa: E402
from engine.db import connect                                     # noqa: E402
from engine.sources.fetch import DataUnavailable                  # noqa: E402

RAW_MARKET = {"slug": "s1", "question": "Will it?", "outcomes": '["Yes", "No"]',
              "outcomePrices": '["0.4", "0.6"]', "volume24hr": "1000", "liquidity": "500",
              "endDate": "2026-12-01"}


def _run(tree: Path, budget=None, leaderboard=None):
    db = tree / "h.db"
    saved = {k: getattr(pm_build, k) for k in ("build_kalshi", "connect", "BUDGET_S")}
    saved_pm = {k: getattr(pm, k) for k in ("fetch_markets", "fetch_trades", "fetch_big_trades",
                                            "fetch_leaderboard", "resolve_flags")}
    argv = sys.argv
    pm_build.build_kalshi = lambda *a, **k: None
    pm_build.connect = lambda: connect(str(db))
    if budget is not None:
        pm_build.BUDGET_S = budget
    pm.fetch_markets = lambda *a, **k: [RAW_MARKET]
    pm.fetch_trades = lambda *a, **k: []
    pm.fetch_big_trades = lambda *a, **k: []
    pm.resolve_flags = lambda *a, **k: 0

    def _lb(*a, **k):
        if leaderboard is None:
            raise DataUnavailable("no leaderboard here")
        return leaderboard(*a, **k)
    pm.fetch_leaderboard = _lb
    out = tree / "web" / "data" / "predmarkets.json"
    sys.argv = ["pm_build.py", "--out", str(out)]
    try:
        pm_build.main()
    finally:
        sys.argv = argv
        for k, v in saved.items():
            setattr(pm_build, k, v)
        for k, v in saved_pm.items():
            setattr(pm, k, v)
    return json.loads((tree / "data" / "built" / "predmarkets.json").read_text())


def _tree():
    t = Path(tempfile.mkdtemp())
    (t / "web" / "data").mkdir(parents=True)
    conn = connect(str(t / "h.db"))
    now = time.time()
    for i, y in enumerate((0.36, 0.38, 0.40)):
        pm.store_snapshot(conn, [{"slug": "s1", "question": "Will it?", "yes": y, "vol24": 1000,
                                  "liquidity": 500, "end_date": "2026-12-01"}], now=now - 1900 + i * 650)
    conn.close()
    return t


def test_the_price_tape_ships_on_the_market_it_was_recorded_for():
    got = _run(_tree())
    m = got["markets"][0]
    assert m["slug"] == "s1" and len(m.get("tape") or []) >= 3, m
    assert [round(p[1], 2) for p in m["tape"]][:3] == [0.36, 0.38, 0.40]


def test_over_budget_the_leaderboard_is_skipped_and_the_last_copy_stands():
    t = _tree()
    (t / "data" / "built").mkdir(parents=True)
    (t / "data" / "built" / "predmarkets.json").write_text(json.dumps(
        {"top_traders": [{"wallet": "0xabc", "name": "Kept"}], "traders_note": "from the last build"}))

    def _never(*a, **k):
        raise AssertionError("the leaderboard was fetched over budget")
    got = _run(t, budget=-1, leaderboard=_never)
    assert got["top_traders"] == [{"wallet": "0xabc", "name": "Kept"}]
    assert got["traders_note"] == "from the last build"
    assert got["markets"][0]["slug"] == "s1", "the core still ships"


def test_every_step_prints_its_clock_and_the_budget_sits_under_the_kill():
    src = (ROOT / "pm_build.py").read_text()
    for step in ("kalshi board", "polymarket pull", "tape + flow", "validation", "top traders", "price tape"):
        assert f'_lap("{step}")' in src, step
    assert pm_build.BUDGET_S < 180
    body = src[src.index("def main("):]
    assert body.index("_attach_tape(conn, display_markets") < body.index("\n    conn.close()\n")


def test_a_failed_build_backs_off_instead_of_retrying_every_cycle():
    src = (ROOT / "launch.py").read_text()
    assert "PREDMARKETS_FAIL_BACKOFF_S = 1800" in src
    at = src.index("def refresh_predmarkets(")
    body = src[at:src.index("\ndef ", at + 10)]
    assert 'if quiet and not _due(".pm_failed", PREDMARKETS_FAIL_BACKOFF_S):' in body
    assert '_stamp(".pm_failed")' in body
    assert body.index('_due(".pm_failed"') < body.index("_run_build(")


def test_the_by_hand_indexes_make_the_wallet_query_index_only():
    conn = connect(":memory:")
    pm.ensure_tables(conn)
    assert pm.build_indexes(conn) and len(pm.BUILD_INDEXES) == 2
    plan = " ".join(str(tuple(r)) for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT wallet, MIN(ts), COUNT(*), SUM(usd) FROM pm_trades "
        "WHERE wallet IN ('a','b') GROUP BY wallet"))
    assert "COVERING INDEX idx_pm_trades_wallet_usd" in plan, plan
    src = (ROOT / "engine" / "predmarket.py").read_text()
    body = src[src.index("def ensure_tables("):src.index("def ensure_tables(") + 1500]
    assert "idx_pm_trades_wallet_usd" not in body, "never built inside a timed build"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
