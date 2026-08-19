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
    """A radar screen, not a betting product: meme coins never enter the
    journal this site grades itself on.

    RE-PINNED 2026-08-19. Rocket Radar grew a record of its own — did the
    coins we called go up? — and it lives in `engine/memeledger.py` with
    its own database, its own tables and no bets in it. The old check
    banned the substring "ledger" in memes_build.py, which the new
    import trips while the actual invariant is untouched.

    So the rule is now stated the way it is meant: the SPORTS ledger, the
    `bets` table, staking and the graded record stay out of the meme
    path. A separate record of separate claims in a separate file is the
    opposite of the thing this guards against — it is the same discipline
    applied twice."""
    for f in ("engine/memecoins.py", "engine/sources/dexes.py",
              "memes_build.py", "engine/memeledger.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        for banned in ("engine.ledger", "from engine import ledger",
                       "log_recommendations", "stake_units", "INTO bets",
                       "settle_from_history", "bankroll"):
            assert banned not in src, f"{banned} in {f}"

    # And the two records keep separate databases, so nothing a memecoin
    # does can ever move a number on the Record page.
    from engine import memeledger, ledger as sports
    assert str(memeledger.DEFAULT_DB) != str(sports.DEFAULT_DB)
    assert "meme" in str(memeledger.DEFAULT_DB)


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


def test_a_429_backs_the_scan_off_instead_of_hammering():
    """Measured on Ethan's machine: 20 back-to-back holder POSTs every
    15s = 429 on all 20, FOREVER, because failures write no cache and
    every tick re-fired the burst. Three brakes, each pinned:
    a cooldown stamp stands every lookup down for a window; the build
    stops a run's remaining lookups on the first 429; and live requests
    pace themselves."""
    import tempfile
    from pathlib import Path
    from unittest import mock
    from engine.sources import solrpc
    from engine.sources.fetch import DataUnavailable as DU
    import memes_build as mb

    with tempfile.TemporaryDirectory() as td:
        cd = Path(td)
        with mock.patch.object(solrpc, "CACHE_DIR", cd), \
             mock.patch.object(solrpc, "_COOLDOWN", cd / "sol_rpc_cooldown"):
            solrpc._note_429()
            try:
                solrpc.fetch_holder_slice("A" * 40)
                raise AssertionError("cooldown did not stand the lookup down")
            except DU as exc:
                assert exc.status == 429
                assert "cooling down" in str(exc)
            # The stamp expires: an old 429 must not gate forever.
            os.utime(cd / "sol_rpc_cooldown", (1, 1))
            assert solrpc._cooling() is None

    # Both shipped lookup loops carry the first-429 brake: one 429 ends
    # the run's remaining lookups instead of firing them into the limiter.
    src = open(os.path.join(ROOT, "memes_build.py"), encoding="utf-8").read()
    for section in ("solana rpc holders: {fails}", "rugcheck: {fails}"):
        i = src.index(section)          # the note line ENDS each loop
        loop = src[src.rindex("for r in rows[:", 0, i):i]
        assert 'status", None) == 429' in loop and "break" in loop, \
            f"the {section.split(':')[0]} loop lost its first-429 brake"
    sol = open(os.path.join(ROOT, "engine/sources/solrpc.py"),
               encoding="utf-8").read()
    assert "time.sleep(PACE_S)" in sol, "requests no longer pace themselves"
    assert "_note_429()" in sol


def test_unreadable_liquidity_cannot_sail_through_the_gate():
    """Ethan's first live board put a coin with NO liquidity reading on
    the rocket list at risk 50. Liquidity is the can-you-get-out number:
    for a protective gate, 'cannot verify an exit exists' is itself a
    risk — smaller than proven-thin, but never zero."""
    row = dict(_merged())
    row["liquidity"] = None
    s_unknown, why = mc.risk_score(row, mc.indicators(row))
    assert any("unreadable" in w for w in why)
    thin = dict(_merged(), liquidity=800.0)
    s_thin, _ = mc.risk_score(thin, mc.indicators(thin))
    known = dict(_merged())          # healthy liquidity from the fixture
    s_known, why_known = mc.risk_score(known, mc.indicators(known))
    assert s_known < s_unknown < s_thin, \
        "unknown must sit between healthy and proven-thin"
    assert not any("liquidity" in w for w in why_known)


def test_concurrent_builders_cannot_race_the_tape_or_the_board():
    """The 15s live loop and the 60s refresh_all cycle both run
    memes_build. Without exclusion, two at once each read the tape,
    append their own snapshot, and the second write DISCARDS the
    first's — and both truncate the board JSON under the page's poll.
    So: one instance lock (loser skips quietly, stale locks stolen), and
    every shared file lands by atomic os.replace, never truncate-write."""
    import memes_build as mb
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "board.json"
        lock1 = mb._acquire_lock(out)
        assert lock1 is not None, "first builder must win the lock"
        assert mb._acquire_lock(out) is None, "second builder must skip"
        # A stale lock (dead builder) is stolen rather than honored forever.
        os.utime(lock1, (1, 1))
        stolen = mb._acquire_lock(out)
        assert stolen is not None, "a dead builder's lock wedged the scan"
        stolen.rmdir()
    # And the writes themselves: replace, not truncate.
    build = open(os.path.join(ROOT, "memes_build.py"), encoding="utf-8").read()
    i = build.index("def _build(")
    assert "os.replace(tmp, out)" in build[i:]
    assert "out.write_text(" not in build[i:], "board still truncate-writes"
    eng = open(os.path.join(ROOT, "engine/memecoins.py"), encoding="utf-8").read()
    j = eng.index("def record_snapshots(")
    body = eng[j:eng.index("\ndef ", j + 10)]
    assert "replace(tmp, path)" in body, "the tape still truncate-writes"


def test_rugcheck_parser_is_tristate_and_never_reads_absent_as_safe():
    """True = the switch is ACTIVE, False = renounced, None = the API
    did not answer. The None case is the load-bearing one: a shape drift
    at RugCheck must degrade to 'unmeasured', never to 'all clear'."""
    from engine.sources import rugcheck as rc
    full = {"mintAuthority": "SomeDevKey111", "freezeAuthority": None,
            "markets": [{"lp": {"lpLockedPct": 12.5}},
                        {"lp": {"lpLockedPct": 98.0}}],
            "risks": [{"name": "Low Liquidity", "level": "warn"},
                      {"name": "Single holder ownership", "level": "danger"}]}
    rep = rc.parse_report(full)
    assert rep["mint_auth"] is True          # key present, non-null
    assert rep["freeze_auth"] is False       # key present, null = renounced
    assert rep["lp_locked_pct"] == 98.0      # best market speaks
    assert rep["dangers"] == ["Single holder ownership"]   # danger only
    # Keys absent entirely -> None, not False.
    sparse = rc.parse_report({"markets": [{"lp": {"lpLockedPct": 5}}]})
    assert sparse["mint_auth"] is None and sparse["freeze_auth"] is None
    # A payload that answered nothing is no report at all.
    assert rc.parse_report({}) is None
    assert rc.parse_report(None) is None
    assert rc.parse_report({"risks": [None, {"level": "danger"}]}) is None


def test_rug_switches_gate_and_unmeasured_scores_nothing():
    row = dict(_merged())
    row["rug"] = {"mint_auth": True, "freeze_auth": True,
                  "lp_locked_pct": 10.0, "dangers": ["Copycat token"]}
    s_bad, why = mc.risk_score(row, mc.indicators(row))
    assert s_bad >= mc.RISK_GATE, "both switches active must gate alone"
    assert any("honeypot" in w for w in why)
    assert any("printed" in w for w in why)
    assert any("locked" in w for w in why)
    assert any("RugCheck flags: Copycat token" in w for w in why)
    # Renounced-and-locked adds nothing; unmeasured adds nothing.
    row_ok = dict(_merged())
    row_ok["rug"] = {"mint_auth": False, "freeze_auth": False,
                     "lp_locked_pct": 100.0, "dangers": []}
    bare = dict(_merged())
    s_ok, _ = mc.risk_score(row_ok, mc.indicators(row_ok))
    s_bare, why_bare = mc.risk_score(bare, mc.indicators(bare))
    assert s_ok == s_bare
    assert not any("authority" in w for w in why_bare)


def test_a_coin_that_leaves_trending_is_carried_while_its_tape_lives():
    """A dying coin leaves trending IMMEDIATELY — exactly when the exit
    signals need their next sighting. The tracked list carries any mint
    with tape history, after discovery, inside the same budget."""
    import memes_build as mb
    good = "So1CarriedMint" + "x" * 30
    hist = {good: [{"ts": 100.0}], "not-base58!": [{"ts": 999.0}]}
    mints, carried = mb._tracked_mints(["A" * 32, "B" * 32], hist)
    assert mints[:2] == ["A" * 32, "B" * 32], "discovery order must win"
    assert good in mints and good in carried
    assert "not-base58!" not in mints, "a garbage mint must never be carried"
    # The budget still binds: discovery fills first, carry never overflows.
    many = {f"C{i:02d}" + "y" * 30: [{"ts": float(i)}] for i in range(100)}
    full, _ = mb._tracked_mints([f"D{i:02d}" + "z" * 30 for i in range(50)],
                                many)
    assert len(full) == mb.MAX_TRACKED


def test_new_and_carried_reach_the_page():
    """first_seen is exported by the build and the page badges it; the
    carried flag renders as the off-trending chip. A signal that stops
    at the JSON is a signal nobody sees."""
    build = open(os.path.join(ROOT, "memes_build.py"), encoding="utf-8").read()
    assert '"first_seen"' in build
    assert 'row["carried"]' in build
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    assert "function mcNewTag" in js
    assert "mcNewTag(c)" in js
    assert "off-trending" in js
    assert "freeze auth" in js and "mint auth" in js
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert "api.rugcheck.xyz" in launch, "RugCheck missing from preflight"


def test_the_live_cadence_is_fast_but_stays_under_the_free_limits():
    """Ethan: "check like every 5 seconds ... coins move in and out
    quick." The loop is 15s and discovery ~25s, NOT 5 — GeckoTerminal's
    free tier is ~30 req/min total and discovery costs two calls, so 5s
    would spend 24/min on discovery alone and the first 429 freezes
    everything. These pins are the margin math; loosening them is a
    rate-limit decision, not a style one."""
    from engine.sources import dexes
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    m = __import__("re").search(r"MEMES_LIVE_S\s*=\s*(\d+)", launch)
    assert m, "the dedicated meme loop lost its clock"
    tick = int(m.group(1))
    assert 10 <= tick <= 30, f"tick {tick}s — under 10 risks bans, over 30 is the old crawl"
    # Prices must actually refetch on each tick (TTL below the tick), and
    # discovery must stay inside GT's total budget (2 calls per TTL).
    assert dexes.HOT_TTL < tick, "every tick would be a cache no-op"
    assert 20 <= dexes.DISCOVERY_TTL <= 60, \
        f"discovery TTL {dexes.DISCOVERY_TTL}s breaks the 30/min GT budget math"
    assert "_live_memes_refresher" in launch
    assert "threading.Thread(target=_live_memes_refresher" in launch, \
        "the loop exists but nothing starts it"
    # And the tape window matches the density (nothing reads past 1h).
    assert mc.HISTORY_KEEP_S <= 3 * 3600


def test_the_page_polls_on_a_matching_clock_without_yanking_charts():
    """A self-refreshing terminal that reloads the chart you are reading
    every tick is worse than a stale one. The poll must refuse hidden
    tabs and open charts, and a re-render must restore the user's coin."""
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    i = js.index("const MEMES_POLL_MS")
    block = js[i:i + 900]
    assert 'state.view !== "memes"' in block, "polls every page, not just this one"
    assert "document.hidden" in block, "polls background tabs"
    assert "iframe" in block and "if (watching) return;" in block, \
        "an open live chart gets reloaded every tick"
    assert "_mcOpenMint" in js[js.index("window.mcShowChart"):
                               js.index("window.mcShowChart") + 600], \
        "the open coin is not remembered across re-renders"


def test_the_meme_page_is_a_charts_first_terminal():
    """Ethan: 'obv we wanna show charts and shit first.' The page uses
    the shared sub-tab rooms, Charts is the FIRST room, the terminal has
    a coin picker, and the top coin's chart auto-opens — landing on live
    candles, not on a menu. The preflight must probe all three hosts so
    --check answers 'can this machine even see the feeds'."""
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    body = js[js.index("async function renderMemes"):]
    body = body[:body.index("\nasync function renderFantasy")]
    assert 'subtabbedHTML("memes"' in body
    # Renamed "Charts" -> "Radar" 2026-08-10 (Ethan: the page "has no
    # direction") — the room is the watchlist + chart terminal, and its
    # name now says so. Still the first room; still lands on candles.
    assert body.index('["charts", "Radar"') < body.index('["rocket",')
    assert "mc-picker" in body and 'class="mc-pick"' in body
    # Auto-open restores the user's coin across the self-refresh, falling
    # back to the top of the board only when that coin left it.
    assert "mcShowChart(want, false)" in body
    assert "_mcOpenMint" in body and "chartable[0].mint" in body
    assert "bindSubtabs(host)" in body
    launch = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    for host_ in ("api.dexscreener.com", "api.geckoterminal.com",
                  "api.mainnet-beta.solana.com"):
        assert host_ in launch, f"{host_} missing from preflight"


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
