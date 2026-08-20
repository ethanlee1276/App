"""Kalshi as a pricing source — the Exchange-Native pillar's second venue.

The competitive recipe is specific about why this exists and what it must
not become: an exchange's mid IS the market's probability (no vig to
strip), Kalshi publishes no trader identity (so it enters as a PRICE, never
as flow — predmarket.py records that decision), and the feed is the
venue's own public API rather than anything scraped off a book.

Parsers are pure and tested offline against the documented market shape;
the fetch layer degrades to DataUnavailable like every other source here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import kalshi as kx                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mkt(**over):
    m = {"ticker": "KXMLBGAME-26AUG03-NYYBOS-NYY",
         "event_ticker": "KXMLBGAME-26AUG03-NYYBOS",
         "title": "Yankees beat the Red Sox",
         "subtitle": "Aug 3 at Fenway Park",
         "yes_bid": 55, "yes_ask": 59, "last_price": 57,
         "volume_24h": 41500, "open_interest": 12800,
         "close_time": "2026-08-04T02:00:00Z", "category": "Baseball"}
    m.update(over)
    return m


# --- the parse ---------------------------------------------------------------
def test_the_mid_of_a_two_sided_book_is_the_probability():
    rows = kx.parse_markets([_mkt()])
    assert rows[0]["prob"] == 0.57            # (55 + 59) / 2 cents
    assert rows[0]["price_basis"] == "book"
    assert rows[0]["spread_cents"] == 4


def test_a_one_sided_book_falls_back_to_the_last_trade_and_says_so():
    """A fair value with no book behind it is a weaker claim. It still
    shows — a price is information — but labelled, because a reader
    comparing our model to a stale print deserves to know."""
    rows = kx.parse_markets([_mkt(yes_bid=None, yes_ask=None, last_price=62)])
    assert rows[0]["prob"] == 0.62
    assert rows[0]["price_basis"] == "last_trade"
    assert rows[0]["spread_cents"] is None


def test_a_market_with_no_price_at_all_is_not_a_row():
    assert kx.parse_markets([_mkt(yes_bid=None, yes_ask=None,
                                  last_price=None)]) == []


def test_busiest_markets_lead():
    rows = kx.parse_markets([_mkt(ticker="A", volume_24h=100),
                             _mkt(ticker="B", volume_24h=90000)])
    assert [r["ticker"] for r in rows] == ["B", "A"]


def test_sports_are_tagged_and_the_rest_pass_through_untagged():
    mlb = kx.parse_markets([_mkt()])[0]
    assert kx.sport_of(mlb) == "mlb"
    fed = kx.parse_markets([_mkt(ticker="KXFED-26SEP", event_ticker="KXFED-26SEP",
                                 category="Economics",
                                 title="Fed cuts rates in September")])[0]
    assert kx.sport_of(fed) is None


# --- the matcher -------------------------------------------------------------
GAMES = [{"home": "BOS", "away": "NYY",
          "home_name": "Boston Red Sox", "away_name": "New York Yankees"},
         {"home": "LAD", "away": "SD",
          "home_name": "Los Angeles Dodgers", "away_name": "San Diego Padres"}]


def test_a_market_matches_only_when_both_teams_appear():
    """One name matches half the league's markets — every future series,
    every award. Both teams or nothing, because a wrong match here hangs an
    edge claim on somebody else's game."""
    row = kx.parse_markets([_mkt()])[0]
    g = kx.match_game(row, GAMES)
    assert g is not None and g["home"] == "BOS"
    lone = kx.parse_markets([_mkt(title="Yankees make the playoffs",
                                  subtitle="", event_ticker="KXMLBPLAYOFF")])[0]
    assert kx.match_game(lone, GAMES) is None


def test_the_board_states_three_numbers_and_the_gap_in_points():
    """RE-PINNED 2026-08-12 (the prediction-desk build): this test used
    to assert model_p == P(home) against the YES price — but the fixture
    market's YES pays on the YANKEES, the away team (the ticker ends in
    -NYY and the title says "Yankees beat the Red Sox"). That WAS the
    sign bug: the board now resolves the YES side first, so with
    P(home BOS)=0.63 the YES-on-NYY claim is worth 0.37 against a 57c
    price — a 20-point NO edge, not a 6-point YES one."""
    rows = kx.parse_markets([_mkt()])
    board = kx.board(rows, {"mlb": GAMES},
                     {("mlb", "NYY@BOS"): 0.63})
    r = board["rows"][0]
    assert r["matchup"] == "NYY@BOS"
    assert r["yes_side"] == "away"
    assert r["prob"] == 0.57 and r["model_p"] == 0.37
    assert r["edge_pts"] == -20.0
    assert r["rec"] and r["rec_side"] == "NO"
    assert board["n_matched"] == 1 and board["n_modeled"] == 1


def test_a_missing_model_number_never_invents_an_edge():
    """A price with no comparison is still information; a comparison with
    an invented leg is fiction. The row shows, the edge stays blank."""
    rows = kx.parse_markets([_mkt()])
    board = kx.board(rows, {"mlb": GAMES}, {})
    r = board["rows"][0]
    assert r["matchup"] == "NYY@BOS"
    assert r["model_p"] is None and r["edge_pts"] is None


def test_non_sports_markets_stay_off_the_board():
    rows = kx.parse_markets([_mkt(),
                             _mkt(ticker="KXFED-26SEP", event_ticker="KXFED-26SEP",
                                  category="Economics",
                                  title="Fed cuts rates in September")])
    board = kx.board(rows, {"mlb": GAMES}, {})
    assert board["n_markets"] == 1
    assert board["sports_seen"] == ["mlb"]


# --- the tape ----------------------------------------------------------------
def test_snapshots_bucket_and_never_duplicate():
    from engine.db import connect
    conn = connect(":memory:")
    rows = kx.parse_markets([_mkt()])
    kx.store_snapshot(conn, rows, now=1000.0)
    kx.store_snapshot(conn, rows, now=1100.0)       # same 10-minute bucket
    assert conn.execute(
        "SELECT COUNT(*) FROM kalshi_snapshots").fetchone()[0] == 1
    kx.store_snapshot(conn, rows, now=1700.0)       # next bucket
    assert conn.execute(
        "SELECT COUNT(*) FROM kalshi_snapshots").fetchone()[0] == 2


# --- the venue's role, pinned ------------------------------------------------
def test_kalshi_is_a_price_never_a_flow_tracker():
    """predmarket.py records the decision: no public trader identity means
    no flow module. This adapter must not grow one by accident."""
    src = open(os.path.join(ROOT, "engine", "sources", "kalshi.py"),
               encoding="utf-8").read()
    # Function shapes, not words — the module's own docstring legitimately
    # says "wallets" while explaining why Polymarket gets a flow module and
    # this venue does not. Prose that explains a rule necessarily contains
    # the rule's vocabulary; the fourth comment-matching trap this session.
    for banned in ("def fetch_wallet", "wallet_names(", "def fetch_leaderboard",
                   "build_flow_feed", "trader_id"):
        assert banned not in src, banned
    assert "pricing source, not a flow tracker" in src


def test_the_build_keeps_each_venue_in_its_own_failure_domain():
    """Kalshi down must not cost the Polymarket build, and vice versa —
    different hosts, different outages, one page."""
    src = open(os.path.join(ROOT, "pm_build.py"), encoding="utf-8").read()
    assert "def build_kalshi(" in src
    i = src.index("def build_kalshi(")
    block = src[i:src.index("\ndef ", i + 1)]
    assert "DataUnavailable" in block
    assert "keeping last board" in block
    # And it runs BEFORE the Polymarket fetch that can SystemExit.
    assert src.index("build_kalshi(") < src.index("pm.fetch_markets()")


def test_the_model_probability_is_home_fixed_not_pick_relative():
    """game_bets carry win_prob for the PICK, which flips team every game.
    The board needs one convention or half the edges are sign-flipped."""
    src = open(os.path.join(ROOT, "pm_build.py"), encoding="utf-8").read()
    assert 'p if b.get("pick_is_home") else 1 - p' in src


def test_the_page_shows_both_venues_and_names_their_roles():
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    # The sidebar item became a chip in the top Markets row (Ethan,
    # 2026-08-12: "the Polly market page ... up here"), renamed
    # 2026-08-18: "change the name of the polly market page to
    # 'prediction market'" — the page reads two venues, so the chip
    # stopped wearing one venue's name.
    assert 'data-sport="intel"' in html and ">PREDICT</button>" in html
    assert "Prediction Market" in html
    flat = " ".join(html.split())
    assert "Kalshi" in flat and "Polymarket" in flat
    # One board out of two venues (Ethan, 2026-08-12: "combine the
    # kalshi and polly market board ... they are basically the same
    # thing"). The Kalshi-only section it replaced is gone.
    assert "function predBoardHTML" in app
    assert "function kalshiSectionHTML" not in app
    # boardFetch since 2026-08-20 — the wrapper that tells a refused
    # wire apart from an empty payload. Same URL, same caching.
    assert 'boardFetch("data/kalshi.json' in app
    # Named phone columns — every cell is a <span>, and :nth-of-type counts
    # tags, so positional selectors grab the sport chip or nothing.
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    i = css.index(".kx-row")
    seg = css[i:i + 2200]
    import re
    assert ":nth-of-type" not in re.sub(r"/\*.*?\*/", "", seg, flags=re.S)
    for cls in (".kx-k", ".kx-m", ".kx-e"):
        assert cls in seg, cls



def test_one_board_carries_both_venues_without_faking_symmetry():
    """Ethan, 2026-08-12: "Combine the kalshi and polly market board.
    There is too much too scroll through and they are basically the same
    thing."

    They are, as PRICES — so venue became a column and the two tables
    became one, ranked by the single measure both venues report the same
    way. What must NOT be flattened is the part where they differ:
    Kalshi runs a two-sided book we price against, Polymarket does not,
    so a Polymarket row shows a dash in the model and edge columns
    rather than a number nobody computed."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    fn = app[app.index("function pmVenueRows("):]
    fn = fn[:fn.index("\nconst PM_BOARD_SHOWN")]
    assert '"KALSHI"' in fn and '"POLY"' in fn
    # Kalshi rows carry our number; Polymarket rows explicitly do not.
    assert "model: r.model_p" in fn and "edge: r.edge_pts" in fn
    assert "model: null" in fn and "edge: null" in fn
    # One ranking, and it is the one both venues actually report.
    assert "sort(" in fn and "vol" in fn
    row = app[app.index("function pmBoardRowHTML("):]
    row = row[:row.index("\nfunction ")]
    assert 'r.model == null ? "—"' in row, "a missing model must read as a dash"
    assert 'r.edge == null' in row


def test_the_prediction_page_is_rooms_not_one_long_scroll():
    """Three questions, three tabs: what to bet, who is betting, and
    whether the flow signal has ever been right. The scroll Ethan hit was
    all three stacked."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("async function renderIntel()")
    fn = app[i:app.index("\n/* =====", i)]
    assert 'subtabbedHTML("intel"' in fn, "the page is still one scroll"
    for room in ('"board"', '"flow"', '"proof"'):
        assert room in fn, room
    # Flow is Polymarket-only by nature and must say why rather than
    # implying Kalshi has a tape we failed to fetch.
    assert "Kalshi does not publish" in fn or "Kalshi carries no public" in fn

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
