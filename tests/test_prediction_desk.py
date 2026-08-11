"""The prediction desk — Ethan, 2026-08-11: "I've never once seen a
recommended bet for our prediction market."

What these tests pin, in the order the failure was found:

1. The YES-side identity bug: the board compared P(home) to every
   market's YES price, and Kalshi's YES is a NAMED TEAM that is the away
   side half the time. yes_team resolves it; ambiguity means unmodeled,
   never a coin flip.
2. The gate: a recommendation requires a real two-sided book, live
   volume, and a written edge bar — and produces a side.
3. The weather desk: NWS forecast against bracket markets is plain
   normal-distribution arithmetic, tested against hand-computed numbers.
4. The paper journal: flat stakes, idempotent, binary payout math exact,
   its own bucket in the record — never the headline book.
5. The honest refusals: politics gets no recommendations (no public
   number to price against), and the page says why a quiet night is
   quiet.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import kalshiweather as kw            # noqa: E402
from engine import ledger                          # noqa: E402
from engine.sources import kalshi as kx            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
PM = open(os.path.join(ROOT, "pm_build.py"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()

GAME = {"home": "BOS", "away": "NYY",
        "home_name": "Boston Red Sox", "away_name": "New York Yankees"}


def _mkt(**kw_):
    # The realistic Kalshi shape: the title is the event question naming
    # BOTH teams; the subtitle names the single club YES pays on.
    m = {"ticker": "KXMLB-NYY", "event_ticker": "KXMLB-NYYBOS",
         "title": "Yankees at Red Sox Winner?",
         "subtitle": "New York Yankees",
         "prob": 0.50, "price_basis": "book", "spread_cents": 2.0,
         "volume_24h": 5000.0, "open_interest": 100.0,
         "close_time": "2026-08-11T23:00:00Z", "category": "Baseball"}
    m.update(kw_)
    return m


def test_yes_side_is_the_named_team_not_the_home_team():
    # The ticker's own tail decides first — the exchange's naming.
    assert kx.yes_team(_mkt(), GAME) == "away"
    assert kx.yes_team(_mkt(ticker="KXMLB-NYYBOS-BOS"), GAME) == "home"
    # A neutral ticker: the subtitle, then a single-club title, decides.
    assert kx.yes_team(_mkt(ticker="KXMLB-GAME1",
                            subtitle="Boston Red Sox"), GAME) == "home"
    assert kx.yes_team(_mkt(ticker="KXMLB-GAME1", subtitle="",
                            title="Will the Yankees win?"), GAME) == "away"
    # Both clubs in the title: English puts the team the market is about
    # first — "Yankees at Red Sox Winner?" pays on the Yankees.
    assert kx.yes_team(_mkt(ticker="KXMLB-GAME1", subtitle=""),
                       GAME) == "away"
    # Nothing decides — the board leaves the row unmodeled rather than
    # guessing.
    assert kx.yes_team(_mkt(ticker="KXMLB-GAME1", subtitle="",
                            title="Who takes game one?"), GAME) is None


def test_the_away_yes_market_prices_against_the_away_probability():
    """The sign bug, pinned. Model says P(home BOS)=0.62, so YES on the
    Yankees is worth 0.38 — against a 50c price that is a NEGATIVE 12-pt
    edge (buy NO), where the old math reported +12 (buy YES)."""
    out = kx.board([_mkt()], {"mlb": [GAME]}, {("mlb", "NYY@BOS"): 0.62})
    row = out["rows"][0]
    assert row["yes_side"] == "away"
    assert abs(row["model_p"] - 0.38) < 1e-9
    assert row["edge_pts"] == -12.0
    assert row["rec"] and row["rec_side"] == "NO"
    assert out["n_rec"] == 1


def test_the_gate_refuses_what_it_should():
    probs = {("mlb", "NYY@BOS"): 0.62}
    games = {"mlb": [GAME]}
    # A stale last-trade print is not a price to claim an edge over.
    r = kx.board([_mkt(price_basis="last_trade", spread_cents=None)],
                 games, probs)["rows"][0]
    assert r["edge_pts"] is not None and not r["rec"]
    # Dead market: no volume, no rec.
    assert not kx.board([_mkt(volume_24h=10)], games, probs)["rows"][0]["rec"]
    # Wide book: the mid of a 15-cent spread is not a real number.
    assert not kx.board([_mkt(spread_cents=15)], games, probs)["rows"][0]["rec"]
    # Inside the bar: 4 points is model noise.
    r = kx.board([_mkt(prob=0.42)], games, probs)["rows"][0]
    assert r["edge_pts"] == -4.0 and not r["rec"]


def test_weather_brackets_parse_all_three_label_shapes():
    assert kw.parse_bracket("83° or above") == (82.5, None)
    assert kw.parse_bracket("72° or below") == (None, 72.5)
    assert kw.parse_bracket("78° to 79°") == (77.5, 79.5)
    assert kw.parse_bracket("no temperature here") is None
    assert kw.parse_bracket("85° to 80°") is None       # inverted = garbage


def test_bracket_probabilities_are_a_partition():
    """Adjacent brackets under one forecast must sum to ~1 — the desk
    prices a partition of outcomes, not a set of overlapping claims."""
    mu, sigma = 78.0, 2.0
    total = (kw.bracket_prob(None, 72.5, mu, sigma)
             + kw.bracket_prob(72.5, 77.5, mu, sigma)
             + kw.bracket_prob(77.5, 79.5, mu, sigma)
             + kw.bracket_prob(79.5, None, mu, sigma))
    assert abs(total - 1.0) < 1e-9
    # Hand check: P(high in [77.5, 79.5)) with mu=78, sigma=2 is
    # Phi(0.75) - Phi(-0.25) ≈ 0.7734 - 0.4013 = 0.3721.
    p = kw.bracket_prob(77.5, 79.5, mu, sigma)
    assert abs(p - 0.3721) < 0.001


def test_the_weather_board_prices_and_gates():
    m = _mkt(ticker="KXHIGHNY-26AUG11-B78", title="Highest temperature in NYC",
             subtitle="78° to 79°", prob=0.20,
             close_time="2026-08-11T23:00:00Z")
    rows = kw.weather_board({"KXHIGHNY": [m]},
                            {("KXHIGHNY", "2026-08-11"): 78.0},
                            today="2026-08-11")
    assert len(rows) == 1
    r = rows[0]
    assert r["city"] == "New York" and r["lead_days"] == 0
    assert abs(r["model_p"] - 0.3721) < 0.001
    assert r["edge_pts"] == 17.2 and r["rec"] and r["rec_side"] == "YES"
    # A market two-plus days out uses the wider sigma; four days out is
    # not priced at all — the forecast isn't good enough to claim an edge.
    far = dict(m, close_time="2026-08-15T23:00:00Z")
    assert kw.weather_board({"KXHIGHNY": [far]},
                            {("KXHIGHNY", "2026-08-15"): 78.0},
                            today="2026-08-11") == []
    # An unknown series ticker is inert, never a crash.
    assert kw.weather_board({"KXHIGHXX": [m]},
                            {("KXHIGHXX", "2026-08-11"): 78.0},
                            today="2026-08-11") == []


def _rec(**kw_):
    r = {"rec": True, "rec_side": "YES", "ticker": "KXHIGHNY-B78",
         "sport": "weather", "desk": "kalshi_wx", "prob": 0.20,
         "model_p": 0.37, "edge_pts": 17.0, "title": "NYC high 78-79"}
    r.update(kw_)
    return r


def test_the_paper_journal_is_flat_idempotent_and_pays_binary_math():
    conn = ledger.connect(":memory:")
    assert ledger.log_predmarket(conn, [_rec()], date="2026-08-11") == 1
    # Same rec on the same build cycle: one row, not two.
    assert ledger.log_predmarket(conn, [_rec()], date="2026-08-11") == 0
    row = conn.execute("SELECT * FROM bets WHERE category='predmarket'").fetchone()
    assert row["stake_units"] == ledger.PREDMARKET_FLAT_STAKE
    assert row["stake_dollars"] == 0, "paper means zero dollars, always"
    assert row["line"] == 20.0                      # YES cost, in cents
    # Resolve: YES at 20c wins -> (1-0.2)/0.2 = 4x the stake.
    assert ledger.resolve_predmarket(conn, {"KXHIGHNY-B78": "yes"}) == 1
    row = conn.execute("SELECT * FROM bets WHERE category='predmarket'").fetchone()
    assert row["status"] == "won" and abs(row["pnl_units"] - 0.4) < 1e-9
    # A NO recommendation pays on the complement price.
    ledger.log_predmarket(conn, [_rec(ticker="T2", rec_side="NO", prob=0.60)],
                          date="2026-08-11")
    ledger.resolve_predmarket(conn, {"T2": "yes"})   # NO bet, YES result
    r2 = conn.execute("SELECT * FROM bets WHERE player='T2'").fetchone()
    assert r2["status"] == "lost" and r2["pnl_units"] == -0.1
    assert r2["line"] == 40.0                       # NO cost = 100 - 60
    rep = ledger.predmarket_report(conn)
    assert rep["settled"] == 2 and rep["wins"] == 1
    # The bucket never leaks into the headline book.
    assert ledger.performance(conn)["settled"] == 0


def test_the_parser_reads_the_dollars_fields_the_live_api_sends():
    """The live autopsy on Ethan's machine (2026-08-11): Kalshi migrated
    to dollar-decimal price fields (yes_bid_dollars as strings like
    "0.4300") and *_fp volumes, and the cent-integer fields come back
    None — which made the parser reject every real market on the
    exchange. Pinned against the exact shape the autopsy printed."""
    live_shape = {
        "ticker": "KXMLBGAME-26AUG111840CLEDET-CLE",
        "event_ticker": "KXMLBGAME-26AUG111840CLEDET",
        "title": "Guardians at Tigers Winner?", "yes_sub_title": "Cleveland Guardians",
        "status": "active",
        "yes_bid": None, "yes_ask": None, "last_price": None,
        "yes_bid_dollars": "0.4200", "yes_ask_dollars": "0.4600",
        "last_price_dollars": "0.4400",
        "volume_24h_fp": "5321.00", "open_interest_fp": "1200",
        "close_time": "2026-08-14T22:40:00Z",
    }
    rows = kx.parse_markets([live_shape])
    assert len(rows) == 1
    r = rows[0]
    assert r["prob"] == 0.44 and r["price_basis"] == "book"
    assert r["spread_cents"] == 4.0
    assert r["volume_24h"] == 5321.0 and r["open_interest"] == 1200.0
    # One-sided book in the new shape falls back to the last trade.
    onesided = dict(live_shape, yes_bid_dollars=None)
    assert kx.parse_markets([onesided])[0]["price_basis"] == "last_trade"
    # Truly unpriced still says nothing.
    assert kx.parse_markets([dict(live_shape, yes_bid_dollars=None,
                                  yes_ask_dollars=None,
                                  last_price_dollars=None)]) == []
    # The legacy cent shape keeps parsing — old fixtures and stored
    # snapshots land in the same 0-1 space (test_kalshi covers it too).
    legacy = {"ticker": "T", "title": "t", "yes_bid": 55, "yes_ask": 59,
              "volume_24h": 100}
    assert kx.parse_markets([legacy])[0]["prob"] == 0.57


def test_sports_markets_are_fetched_by_series_not_hoped_for():
    """Ethan's first live --desk run (2026-08-11): the feed was healthy
    and the desk still saw ZERO sports markets, because the general
    /markets page is an arbitrary 200 of thousands of listings —
    politics wall-to-wall before any ballgame. Pinned: the sports series
    are fetched by name, a dead series name records 0 and costs nothing,
    an erroring one records "error" without sinking the rest, and the
    first live alias wins so the same game never loads twice."""
    calls = []
    def fake_events(series, **kw_):
        calls.append(series)
        if series == "KXMLBGAME":
            return [{"markets": [{"ticker": "KXMLBGAME-NYY", "title": "t",
                                  "yes_bid": 40, "yes_ask": 44,
                                  "volume_24h": 100}]}]
        if series == "KXNFLGAME":
            raise RuntimeError("catalog moved")
        return []
    orig = kx.fetch_events
    kx.fetch_events = fake_events
    try:
        markets, report = kx.fetch_sports_markets(kx.parse_markets)
    finally:
        kx.fetch_events = orig
    assert [m["ticker"] for m in markets] == ["KXMLBGAME-NYY"]
    assert report["KXMLBGAME"] == 1
    assert "MLBGAME" not in report, "the found sport's aliases still ran"
    assert report["KXNFLGAME"] == "error"
    assert report["NFLGAME"] == 0
    # The build merges series + page deduped, and reports both sources.
    assert "fetch_sports_markets" in PM
    assert 'if m["ticker"] not in seen' in PM
    assert '"sources"' in PM and "series_report" in PM
    assert 'src.get("series")' in LAUNCH
    # The ledger ops run on the LEDGER's own connection — the history db
    # has no bets table, and handing it over crashed the first live
    # build. The paper block is also its own failure domain: the board
    # must ship even when the journal hiccups.
    assert "lconn = ledger.connect()" in PM
    assert "ledger.log_predmarket(lconn" in PM
    assert '"error": str(exc)' in PM


def test_the_desk_never_recommends_without_its_reasons():
    """Page + build pins: the desk section exists, leads the intel page,
    says PAPER out loud, explains a quiet night, and politics stays with
    the graded flow detector rather than gaining an oracle."""
    assert "function deskSectionHTML(" in APP
    assert APP.index("deskSectionHTML(kx)") < APP.index("kalshiSectionHTML(kx)")
    fn = APP[APP.index("function deskSectionHTML("):]
    fn = fn[:fn.index("\nfunction kalshiSectionHTML")]
    assert "PAPER" in fn and "No market clears the gate" in fn
    assert "Politics carries no recommendations" in APP
    # Build wiring: journal, settle, and the exception surfaced in words.
    assert "ledger.log_predmarket" in PM and "resolve_predmarket" in PM
    assert "fetch_markets_by_tickers" in PM
    assert "unreachable from this machine — {exc}" in PM
    # The probe exists so "why no recs" is one command at home.
    assert '"--desk" in argv' in LAUNCH and "def show_desk" in LAUNCH
    # The record carries the bucket.
    LEDGER_SRC = open(os.path.join(ROOT, "engine/ledger.py"),
                      encoding="utf-8").read()
    assert '"predmarket": predmarket_report(conn),' in LEDGER_SRC


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
