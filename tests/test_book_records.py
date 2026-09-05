"""Every book keeps its own record spot, per sport, markets labeled.

Ethan, 2026-09-01: "add to the record page for each sport sections to
the records, like the edge bets have a certain section and record spot,
the most likely bets have a record spot, and excetra. We should also
label homers and touchdowns and hits and receptions and rebounds and 3
pointers and shit like that."

The ledger already knows all of it — every bet carries its sport, its
category (the book), and its market. `book_records` reads it back in
one scan; the page renders each book's W-L and ROI with the market rows
underneath, labeled by the shipped `market_words` rather than a second
hand-kept list (the splits table already paid for that lesson).

Run directly: `python3 tests/test_book_records.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger

_SEQ = [0]


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


def _bet(conn, sport, category, market, status, pnl):
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
        "hit_prob,edge,stake_units,stake_dollars,ts,status,category,"
        "pnl_units) VALUES (?,?,?,?,'OVER',0.5,-120,'DK',0.6,0,1.0,0,"
        "'now',?,?,?)",
        (sport, "2026-09-01", f"P{_SEQ[0]}", market, status, category, pnl))
    conn.commit()


def test_each_book_keeps_its_own_spot_per_sport():
    c = _conn()
    _bet(c, "mlb", "main", "home_runs", "won", 2.5)
    _bet(c, "mlb", "main", "hits", "lost", -1.0)
    _bet(c, "mlb", "likely", "hits", "won", 0.4)
    _bet(c, "mlb", "likely", "total_bases", "lost", -1.0)
    _bet(c, "nfl", "longshot", "anytime_td", "won", 3.0)
    got = ledger.book_records(c)
    mlb = got["mlb"]
    assert set(mlb) == {"edge", "likely"}
    assert mlb["edge"]["label"] == "Edge bets"
    assert mlb["edge"]["w"] == 1 and mlb["edge"]["l"] == 1
    assert set(mlb["edge"]["markets"]) == {"home_runs", "hits"}
    assert mlb["likely"]["label"] == "Most Likely"
    assert mlb["likely"]["markets"]["hits"]["w"] == 1
    assert got["nfl"]["longshots"]["markets"]["anytime_td"]["w"] == 1
    assert "edge" not in got["nfl"], \
        "a book a sport never journaled is absent, not zeroed"


def test_roi_is_per_book_and_paper_pools_with_the_edge_record():
    c = _conn()
    _bet(c, "mlb", "main", "hits", "won", 0.8)
    _bet(c, "mlb", "paper", "hits", "lost", -1.0)
    got = ledger.book_records(c)["mlb"]["edge"]
    assert got["n"] == 2, "paper rides with main — same section, same P&L"
    assert abs(got["roi"] - (-0.2 / 2.0)) < 1e-9
    m = got["markets"]["hits"]
    assert m["w"] == 1 and m["l"] == 1 and abs(m["roi"] + 0.1) < 1e-9


def test_the_export_carries_it_and_the_page_renders_it():
    with open(os.path.join(ROOT, "engine", "ledger.py"),
              encoding="utf-8") as f:
        led = f.read()
    assert '"book_records": book_records(conn, since=since),' in led
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    assert "function recBookSections(br, scope)" in js
    assert "recBookSections(d.book_records, scope)" in js
    at = js.index("function recBookSections")
    body = js[at:js.index("\nfunction ", at + 10)]
    assert "marketWord(m)" in body, \
        "labels come from the shipped market_words, never retyped"
    assert "Records by book" in body


def _js():
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        return f.read()


def test_a_sports_record_leads_with_its_book_sections():
    """Ethan, 2026-09-05, the same sentence as 09-01 — because the
    sections rendered LAST on a tab whose first screen is the curve. On
    the sport scope they now sit under the verdict, above the KPI cards."""
    js = _js()
    i = js.index("const receipts = verdict +")
    lead = js[i:js.index('<div class="stat-cards rec-kpis">', i)]
    assert 'scoped ? recBookSections(d.book_records, scope) : ""' in lead, lead


def test_the_all_scope_keeps_them_after_the_receipts_and_does_not_repeat():
    js = _js()
    i = js.index("function _recordRooms(")
    body = js[i:js.index("\nfunction ", i + 10)]
    assert '(scoped ? "" : recBookSections(d.book_records, scope))' in body
    assert body.count("recBookSections(") == 1, "rendered twice on one scope"


def test_a_thin_book_says_so_by_the_ledgers_own_bar():
    js = _js()
    at = js.index("function recBookSections")
    body = js[at:js.index("\nfunction ", at + 10)]
    assert "n < _recMinGraded" in body and "thin sample" in body
    assert "_recMinGraded = (Object.values(d.by_sport || {})[0] || {}).min_graded || 30" in js, \
        "the bar is the shipped min_graded, not a second hand-kept number"


def test_settled_rows_print_the_markets_word_not_its_id():
    """"label homers and touchdowns and hits and receptions and rebounds
    and 3 pointers" — the recent-picks list printed `home_runs`."""
    js = _js()
    at = js.index("function recSettledRow")
    body = js[at:js.index("\nfunction ", at + 10)]
    assert "escapeHtml(marketWord(b.market))" in body
    assert "escapeHtml(b.market)" not in body


def test_market_words_cover_every_journaled_market_name():
    """The words the page will label these sections with exist for the
    markets the boards journal — homers, touchdowns, hits, receptions,
    rebounds, threes, the lot."""
    from engine import markets
    w = markets.words()
    for m in ("home_runs", "anytime_td", "hits", "total_bases",
              "receptions", "reb", "fg3m", "pts", "ast"):
        assert w.get(m), m


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
