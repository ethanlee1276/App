"""Rocket Radar — the spec's rules, pinned before any live data exists.

The two rules that make this page defensible, straight from the build
spec (docs/MEMECOIN_MODEL.md):

  MOMENTUM AND RISK STAY SEPARATE, and risk is a GATE. "Never blend them
  into one number that hides danger."
  COHORT-RELATIVE, NOT ABSOLUTE. "A raw $50k volume means nothing
  without context."

The sandbox cannot reach DexScreener or GeckoTerminal (403 at the proxy,
like statsapi and Savant, both of which work on the machine that runs the
builds) — so the parsers are proven against fixtures in each provider's
documented shape, and `launch.py --memes` verifies live shape at home.

Run directly: `python3 tests/test_memecoins.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import memecoins as mc                             # noqa: E402
from engine.sources import dexes                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINT = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"

GT_POOL = {
    "data": [{
        "id": "solana_POOLADDR",
        "attributes": {
            "name": "WIF / SOL",
            "address": "POOLADDR",
            "base_token_price_usd": "0.0021",
            "fdv_usd": "2100000",
            "market_cap_usd": "2100000",
            "reserve_in_usd": "180000",
            "pool_created_at": "2026-08-10T18:00:00Z",
            "price_change_percentage": {"m5": 4.2, "h1": 12.0,
                                        "h6": 30.0, "h24": 80.0},
            "volume_usd": {"m5": 9000, "h1": 60000, "h6": 200000,
                           "h24": 500000},
            "transactions": {
                "m5": {"buys": 120, "sells": 60, "buyers": 95, "sellers": 40},
                "h1": {"buys": 900, "sells": 700, "buyers": 500,
                       "sellers": 320},
            },
        },
        "relationships": {"base_token": {"data": {"id": f"solana_{MINT}"}}},
    }]
}

DEX_PAIRS = [
    {"chainId": "solana", "dexId": "raydium", "url": "https://dexscreener.com/x",
     "pairAddress": "PAIR1",
     "baseToken": {"address": MINT, "symbol": "WIF", "name": "dogwifhat"},
     "priceUsd": "0.0021", "fdv": 2100000, "marketCap": 2100000,
     "pairCreatedAt": 1754800000000,
     "priceChange": {"m5": 4.2, "h1": 12.0, "h6": 30.0, "h24": 80.0},
     "volume": {"m5": 6000, "h1": 40000, "h6": 150000, "h24": 400000},
     "txns": {"m5": {"buys": 80, "sells": 40},
              "h1": {"buys": 600, "sells": 500},
              "h6": {"buys": 1000, "sells": 900},
              "h24": {"buys": 2000, "sells": 1800}},
     "liquidity": {"usd": 120000, "base": 1, "quote": 1},
     "info": {"socials": [{"type": "twitter", "url": "x"}]},
     "boosts": {"active": 0}},
    # A second, smaller pool for the SAME mint — the dedupe case.
    {"chainId": "solana", "dexId": "orca", "pairAddress": "PAIR2",
     "baseToken": {"address": MINT, "symbol": "WIF", "name": "dogwifhat"},
     "priceUsd": "0.0022", "fdv": 2100000,
     "pairCreatedAt": 1754800000000,
     "priceChange": {"m5": 5.0, "h1": 13.0},
     "volume": {"m5": 1000, "h1": 8000, "h6": 20000, "h24": 50000},
     "txns": {"m5": {"buys": 10, "sells": 5}, "h1": {"buys": 50, "sells": 40},
              "h6": {"buys": 80, "sells": 70},
              "h24": {"buys": 100, "sells": 90}},
     "liquidity": {"usd": 30000}},
]


# --- parsers -----------------------------------------------------------------
def test_gt_parser_keys_by_mint_not_by_pool():
    """One token trades in many pools; the pool address is NOT the token.
    The mint lives in relationships.base_token, prefixed `solana_`."""
    rows = dexes.parse_gt_pools(GT_POOL)
    assert len(rows) == 1
    r = rows[0]
    assert r["mint"] == MINT, "must strip the network prefix"
    assert r["name"] == "WIF"
    assert r["tx_m5"]["buyers"] == 95, "unique buyers are the point of GT"
    assert r["liquidity"] == 180000.0


def test_dex_parser_aggregates_pools_under_the_primary():
    """Liquidity and volume SUM across a token's pools; price and age come
    from the largest pool — the spec's own dedupe rule."""
    out = dexes.parse_dex_pairs(DEX_PAIRS)
    assert list(out) == [MINT]
    r = out[MINT]
    assert r["pools"] == 2
    assert r["liquidity"] == 150000
    assert r["volume"]["h1"] == 48000
    assert r["txns"]["m5"] == {"buys": 90, "sells": 45}
    assert r["price_usd"] == 0.0021, "price from the PRIMARY (bigger) pool"
    assert r["dex"] == "raydium"
    assert r["has_socials"] is True and r["boosted"] is False


def test_boost_parser_keeps_solana_only():
    payload = [{"chainId": "solana", "tokenAddress": "A"},
               {"chainId": "base", "tokenAddress": "B"},
               {"chainId": "solana"}]
    assert dexes.parse_boosts(payload) == ["A"]


def test_parsers_survive_garbage():
    assert dexes.parse_gt_pools({}) == []
    assert dexes.parse_gt_pools({"data": [{"attributes": {}}]}) == []
    assert dexes.parse_dex_pairs([]) == {}
    assert dexes.parse_dex_pairs({"pairs": None}) == {}


# --- indicators --------------------------------------------------------------
def _merged():
    row = dexes.parse_dex_pairs(DEX_PAIRS)[MINT]
    gt = dexes.parse_gt_pools(GT_POOL)[0]
    row["tx_m5"], row["tx_h1"] = gt["tx_m5"], gt["tx_h1"]
    return row


def test_the_wash_rule_is_the_arxiv_thresholds():
    """Volume spiking >5x its hourly pace while price moves <5% is volume
    with nobody in it — the study's exact construction."""
    row = _merged()
    row["volume"] = {"m5": 50000, "h1": 60000, "h6": 1, "h24": 1}
    row["price_change"] = {"m5": 1.0, "h1": 2.0, "h6": 0, "h24": 0}
    ind = mc.indicators(row)
    assert ind["vol_spike"] == 10.0
    assert ind["wash_flag"] is True
    # Same spike WITH a real price move is not wash — it is a rocket.
    row["price_change"]["m5"] = 40.0
    assert mc.indicators(row)["wash_flag"] is False


def test_acceleration_needs_three_sightings_and_says_none_before():
    assert mc.accel([1000], [0]) is None
    assert mc.accel([1000, 2000], [0, 60]) is None
    a = mc.accel([1000, 2000, 4000], [0, 60, 120])
    assert a is not None and a > 0, "1k/min then 2k/min = accelerating"
    # THE FIXTURE THAT WAS WRONG FIRST: 4000→2000→1000 is a DECAYING fall
    # — the drop is slowing, so the second derivative is positive, and
    # the first draft of this test demanded it be negative. The genuine
    # negative case is the stall: still rising, but the rise dying — the
    # exact "momentum rolling over" shape the exit channel watches for.
    d = mc.accel([1000, 2000, 2100], [0, 60, 120])
    assert d is not None and d < 0


def test_the_tape_prunes_itself():
    """Six hours of history on a shared disk, not forever."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "tape.jsonl"
        mc.record_snapshots([{"mint": "A", "price_usd": 1, "volume": {},
                              "liquidity": 1}], ts=1000, path=p)
        mc.record_snapshots([{"mint": "A", "price_usd": 2, "volume": {},
                              "liquidity": 1}],
                            ts=1000 + mc.HISTORY_KEEP_S + 10, path=p)
        hist = mc.load_history(p)
        assert len(hist["A"]) == 1, "the old row must be pruned"
        assert hist["A"][0]["price"] == 2


# --- the two rules -----------------------------------------------------------
def test_momentum_and_risk_are_two_numbers_and_risk_gates():
    """The spec's first rule, structurally: a coin over the risk line
    never reaches the rocket list however hard it accelerates."""
    hot_but_deadly = dict(_merged(), liquidity=800.0, mint="DANGER",
                          has_socials=False)
    safe = dict(_merged(), mint=MINT)
    board = mc.build_board([hot_but_deadly, safe])
    danger = next(c for c in board["coins"] if c["mint"] == "DANGER")
    assert danger["risk"] >= mc.RISK_GATE
    assert "DANGER" not in board["rocket"]
    assert MINT in board["rocket"]
    assert board["gated"] == 1
    assert isinstance(danger["momentum"], int), (
        "momentum is still computed and shown — gated, not hidden")


def test_scores_are_cohort_percentiles_not_absolutes():
    """Identical coins score identically; the one with more buyer
    acceleration outranks, whatever the raw dollar numbers are."""
    a = dict(_merged(), mint="A")
    b = dict(_merged(), mint="B")
    hist = {"A": [{"ts": 0, "vol_m5": 100, "price": 1, "buyers_m5": 10,
                   "liq": 1e5},
                  {"ts": 60, "vol_m5": 200, "price": 1.1, "buyers_m5": 20,
                   "liq": 1e5},
                  {"ts": 120, "vol_m5": 800, "price": 1.5, "buyers_m5": 80,
                   "liq": 1e5}],
            "B": [{"ts": 0, "vol_m5": 100, "price": 1, "buyers_m5": 10,
                   "liq": 1e5},
                  {"ts": 60, "vol_m5": 110, "price": 1.0, "buyers_m5": 11,
                   "liq": 1e5},
                  {"ts": 120, "vol_m5": 115, "price": 1.0, "buyers_m5": 11,
                   "liq": 1e5}]}
    board = mc.build_board([a, b], hist)
    A = next(c for c in board["coins"] if c["mint"] == "A")
    B = next(c for c in board["coins"] if c["mint"] == "B")
    assert A["momentum"] > B["momentum"]


def test_the_lp_pull_proxy_fires_from_our_own_tape():
    """The spec ranks liquidity removal the single most destructive
    event. Free tier has no LP-burn feed — the tape is the only eye."""
    row = dict(_merged(), liquidity=60000.0)
    hist = [{"ts": 0, "vol_m5": 1, "price": 1, "liq": 120000},
            {"ts": 60, "vol_m5": 1, "price": 1, "liq": 110000}]
    ind = mc.indicators(row, hist)
    assert ind["liq_drop"] is not None and ind["liq_drop"] > 0.2
    assert any("LIQUIDITY LEAVING" in s for s in mc.exit_signals(ind))


def test_the_exit_channel_ignores_the_risk_gate():
    """A dangerous coin crashing is exactly what the danger channel is
    for — gating the exit list would hide crashes on the worst coins."""
    dying = dict(_merged(), mint="DYING", liquidity=800.0)
    dying["tx_m5"] = {"buys": 10, "sells": 80, "buyers": 8, "sellers": 60}
    dying["tx_h1"] = {"buys": 900, "sells": 700, "buyers": 500,
                      "sellers": 320}
    board = mc.build_board([dying])
    assert "DYING" in board["exits"]


def test_ratio_inversion_is_an_exit_signal():
    ind = {"ratio_m5": 0.4, "ratio_h1": 1.6, "buyers_m5": 50,
           "sellers_m5": 40}
    assert any("flipped under 1" in s for s in mc.exit_signals(ind))


def test_paying_for_promotion_is_a_risk_not_a_quality():
    row = dict(_merged(), boosted=True)
    _, why = mc.risk_score(row, mc.indicators(row))
    assert any("PAYING" in w for w in why)


def test_no_classic_ta_anywhere():
    """The spec's verdict, adopted wholesale: RSI/MACD/Bollinger are
    noise at meme timeframes. Order flow is the model, and a later
    'improvement' reintroducing them should trip this."""
    for f in ("engine/memecoins.py", "engine/sources/dexes.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        low = src.lower()
        for banned in ("def rsi", "def macd", "bollinger("):
            assert banned not in low, f"{banned} in {f}"


def test_nothing_journals_and_nothing_touches_the_sports_model():
    """A radar screen, not a betting product: no bet rows, no ledger
    writes, no edge — meme coins never enter the journal this site
    grades itself on."""
    for f in ("engine/memecoins.py", "engine/sources/dexes.py",
              "memes_build.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert "ledger" not in src, f
        assert "log_recommendations" not in src, f


def test_holder_parser_excludes_the_pool_reading_and_reports_both():
    """getTokenLargestAccounts returns token ACCOUNTS, and for a live
    coin the largest is almost always the pool vault. The parser reports
    the raw top-1 AND the ex-largest top-10 so the risk rules can judge
    wallets without hand-maintaining AMM authority lists."""
    from engine.sources import solrpc
    payload = [
        {"id": 0, "result": {"value": {"amount": "1000000"}}},
        {"id": 1, "result": {"value": [
            {"address": "P", "amount": "500000"},   # the pool vault
            {"address": "A", "amount": "200000"},   # the real whale
            {"address": "B", "amount": "50000"},
            {"address": "C", "amount": "30000"},
        ]}},
    ]
    h = solrpc.parse_holder_slice(payload)
    assert h["top1_share"] == 0.5
    assert h["top10_ex1_share"] == 0.28          # 200k+50k+30k / 1M
    assert h["second_share"] == 0.2
    # Unanswerable stays None, never zeros: "unmeasured" and "perfectly
    # dispersed" must not look identical downstream.
    assert solrpc.parse_holder_slice([]) is None
    assert solrpc.parse_holder_slice(
        [{"id": 0, "result": {"value": {"amount": "0"}}},
         {"id": 1, "result": {"value": [{"amount": "1"}]}}]) is None


def test_a_garbage_mint_never_reaches_the_wire():
    """Mints come from third-party feeds and end up in URLs and cache
    filenames — anything that fails the base58 shape is refused before
    a request exists."""
    from engine.sources import solrpc
    from engine.sources.fetch import DataUnavailable as DU
    for bad in ("", None, "with space", "0OIl_not_b58", "x" * 51,
                "../../../etc/passwd"):
        try:
            solrpc.fetch_holder_slice(bad)
            raise AssertionError(f"accepted {bad!r}")
        except DU:
            pass


def test_insider_concentration_scores_and_unmeasured_never_does():
    row = dict(_merged())
    row["holders"] = {"top1_share": 0.5, "top10_ex1_share": 0.45,
                      "second_share": 0.20, "n_accounts": 20}
    ind = mc.indicators(row)
    s_with, why = mc.risk_score(row, ind)
    assert any("insider-heavy" in w for w in why)
    assert any("single seller" in w for w in why)
    bare = dict(_merged())
    s_wo, why_wo = mc.risk_score(bare, mc.indicators(bare))
    assert s_with == s_wo + 20 + 15
    assert not any("hold" in w for w in why_wo)


def test_the_launcher_actually_refreshes_the_board():
    """Wiring, not mention: refresh_memes must exist, run memes_build
    with the path the page fetches, and be CALLED from refresh_all —
    a defined-but-never-called refresh is a board that silently ages."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def refresh_memes")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "memes_build.py" in body
    assert "web/data/memecoins.json" in body
    j = src.index("def refresh_all")
    all_body = src[j:src.index("\ndef ", j + 10)]
    assert "refresh_memes(" in all_body
    # And the probe is reachable from the command line.
    assert '"--memes" in argv' in src


def test_the_page_is_wired_end_to_end():
    """The nav button, the view section, the standalone-mode entry, the
    router line and the renderer must all exist and agree on the name —
    any one missing renders as a blank page with no error anywhere."""
    html = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()
    assert 'data-sport="memes"' in html
    assert 'id="view-memes"' in html
    assert 'id="memes-body"' in html
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    assert "async function renderMemes" in js
    assert 'data/memecoins.json' in js
    assert 'if (name === "memes") renderMemes();' in js
    modes = js[js.index("const STANDALONE_MODES"):]
    assert '"memes"' in modes[:modes.index("]")]
    order = js[js.index("const VIEW_ORDER"):]
    assert '"memes"' in order[:order.index("]")]


def test_holders_and_charts_are_wired_end_to_end():
    """The build must fetch holders and export the sparkline series; the
    page must validate addresses BEFORE they touch an onclick or an
    iframe src — token feeds are attacker-controlled strings."""
    build = open(os.path.join(ROOT, "memes_build.py"), encoding="utf-8").read()
    assert "parse_holder_slice" in build and "HOLDER_LOOKUPS" in build
    assert '"spark"' in build
    dx = open(os.path.join(ROOT, "engine/sources/dexes.py"),
              encoding="utf-8").read()
    assert '"pair": prime.get("pairAddress")' in dx
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    assert "function mcSpark" in js
    fn = js[js.index("window.mcShowChart"):]
    fn = fn[:fn.index("\n};")]
    assert fn.index("MC_B58.test") < fn.index("<iframe"), \
        "the address must be validated before the iframe src is built"
    assert "mc-chart-dock" in js
    assert "top10_share" in js and "Top 10" in js


def test_the_page_shows_the_base_rates_not_just_the_scores():
    """The spec's most important content is the honesty block — the page
    must carry the base rates and the not-advice framing, and they must
    render before an empty-state return can cut the function short."""
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    i = js.index("MC_BASE_RATES")
    body = js[i:js.index("\nasync function renderFantasy", i)]
    for fact in ("1.4%", "82.8%", "wash trading", "62 seconds"):
        assert fact in body, fact
    assert "buy signal" in body.lower()
    assert body.index("honesty") < body.index("rocketCards")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
