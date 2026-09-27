"""The prediction markets on the spread and the total, not only the winner.

Ethan, 2026-09-26: "we should also look into where we can use pollymarket
and kalshi odds for money lines and other bets". A Polymarket game event
carries its spread and total beside the moneyline; `polysports.parse_line`
reads them only when the kind AND the line are unambiguous, and
`crowd.crowd_lines` keeps a venue's price only on THE BOARD'S OWN line —
the same bet the books quote. Recorded to `crowd_lines` for crowdfit;
shown on the game page; moving no pick.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import crowd                                        # noqa: E402
from engine.sources import polysports as P                      # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def _m(q, outs, prices, bid=None, ask=None, liq=5000, kind=None, line=None):
    m = {"question": q, "outcomes": json.dumps(outs), "outcomePrices": json.dumps([str(p) for p in prices]),
         "liquidity": liq}
    if bid is not None:
        m.update(bestBid=bid, bestAsk=ask)
    if kind:
        m["sportsMarketType"] = kind
    if line is not None:
        m["line"] = line
    return m


def _event(markets):
    ml = _m("Bills vs. Chiefs", ["Bills", "Chiefs"], [0.45, 0.55], 0.44, 0.46)
    return {"slug": "nfl-buf-kc-2026-09-28", "startDate": "2026-09-28T20:25:00Z", "markets": [ml] + markets}


GAME = {"away": "BUF", "home": "KC", "away_name": "Buffalo Bills", "home_name": "Kansas City Chiefs",
        "date": "2026-09-28", "kickoff": "16:25", "spread": 2.5, "favorite": "KC", "total": 47.5,
        "home_ml": -135, "away_ml": 115}


def test_a_spread_and_a_total_are_read_off_the_game_event():
    rows = P.parse_events([_event([
        _m("Spread: Chiefs (-2.5)", ["Chiefs", "Bills"], [0.56, 0.44], 0.55, 0.57, kind="spreads"),
        _m("Bills vs. Chiefs: O/U 47.5", ["Over", "Under"], [0.47, 0.53], 0.46, 0.48),
    ])])
    lines = rows[0]["lines"]
    assert {"kind": "spread", "team": "Chiefs", "line": -2.5, "p": 0.56} == {k: lines[0][k] for k in ("kind", "team", "line", "p")}
    assert lines[1]["kind"] == "total" and lines[1]["line"] == 47.5 and lines[1]["p"] == 0.47


def test_what_cannot_be_read_cleanly_is_skipped_not_coerced():
    bad = [
        _m("Spread: Dolphins (-2.5)", ["Chiefs", "Bills"], [0.5, 0.5], 0.49, 0.51, kind="spreads"),  # names neither
        _m("Spread of the season?", ["Yes", "No"], [0.5, 0.5]),                                       # a yes/no
        _m("Bills vs. Chiefs: total", ["Over", "Under"], [0.5, 0.5]),                                  # no number
        _m("Will Mahomes throw 3+ TDs?", ["Yes", "No"], [0.3, 0.7]),
    ]
    assert P.parse_events([_event(bad)])[0]["lines"] == []


def test_only_the_boards_own_line_counts_and_a_thin_book_does_not():
    row = {"teams": ["Bills", "Chiefs"], "start": "2026-09-28", "lines": [
        {"kind": "spread", "team": "Chiefs", "line": -2.5, "p": 0.56, "price_basis": "book", "spread_cents": 2, "liquidity": 3000},
        {"kind": "total", "line": 48.5, "p": 0.40, "price_basis": "book", "spread_cents": 2, "liquidity": 3000},
    ]}
    got = crowd.crowd_lines(row, dict(GAME), False)
    assert got == {"spread_home_line": -2.5, "poly_home_cover": 0.56}, "48.5 is a different bet from 47.5"
    # the away club named at its own (plus) number is the same bet from the other side
    row["lines"] = [{"kind": "spread", "team": "Bills", "line": 2.5, "p": 0.45, "price_basis": "book",
                     "spread_cents": 2, "liquidity": 3000}]
    assert crowd.crowd_lines(row, dict(GAME), False)["poly_home_cover"] == 0.55
    # a last-trade price with no book behind it is not a price
    row["lines"][0]["price_basis"] = "last_trade"
    assert crowd.crowd_lines(row, dict(GAME), False) == {}


def test_the_board_hangs_them_and_records_them(tmp=None):
    import tempfile
    result = {"games": [dict(GAME)]}
    rows = [dict(r, sport="nfl") for r in P.parse_events([_event([
        _m("Spread: Chiefs (-2.5)", ["Chiefs", "Bills"], [0.56, 0.44], 0.55, 0.57, kind="spreads"),
        _m("Bills vs. Chiefs: O/U 47.5", ["Over", "Under"], [0.47, 0.53], 0.46, 0.48)])])]
    census = crowd.attach(result, "nfl", [], rows)
    assert census["poly_spread"] == 1 and census["poly_total"] == 1
    c = result["games"][0]["crowd"]
    assert c["poly_home_cover"] == 0.56 and c["poly_over"] == 0.47 and c["total_line"] == 47.5
    db = Path(tempfile.mkdtemp()) / "c.db"
    conn = crowd.connect(db)
    crowd.store(conn, "nfl", result["games"], now=0)
    got = sorted(conn.execute("SELECT kind, line, venue, p FROM crowd_lines").fetchall())
    assert got == [("over", 47.5, "polymarket", 0.47), ("spread_home", -2.5, "polymarket", 0.56)]


def test_the_game_page_shows_them_and_never_our_number():
    fn = APP[APP.index("function crowdLinesHTML("):APP.index("function crowdStripHTML(")]
    assert "c.poly_home_cover" in fn and "c.poly_over" in fn and "on Polymarket" in fn
    assert "win_prob" not in fn and "model" not in fn
    strip = APP[APP.index("function crowdStripHTML("):APP.index("function obGameHTML(")]
    assert "crowdLinesHTML(g, c)" in strip


def test_crowdfit_grades_them_on_the_final_score():
    """Graded against a coin flip, pushes left out, the latest bucket only."""
    from engine import crowdfit
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (sport TEXT, date TEXT, period TEXT, home TEXT, away TEXT, "
                 "home_score REAL, away_score REAL)")
    crowd.ensure_tables(conn)
    rows = []
    for i in range(6):
        a, h = f"A{i}", f"H{i}"
        # home wins by 7 every time: covers −3.5, and 27+20 = 47 stays under 47.5
        conn.execute("INSERT INTO games VALUES ('nfl','2026-09-28',NULL,?,?,27,20)", (h, a))
        conn.execute("INSERT INTO crowd_lines VALUES ('nfl','2026-09-28',?,?,100,'spread_home',-3.5,'polymarket',0.40,NULL)", (a, h))
        conn.execute("INSERT INTO crowd_lines VALUES ('nfl','2026-09-28',?,?,200,'spread_home',-3.5,'polymarket',0.60,NULL)", (a, h))
        conn.execute("INSERT INTO crowd_lines VALUES ('nfl','2026-09-28',?,?,200,'over',47.5,'polymarket',0.45,NULL)", (a, h))
    # a push on the spread (home by 7 against a 7) grades nothing
    conn.execute("INSERT INTO games VALUES ('nfl','2026-09-28',NULL,'HP','AP',27,20)")
    conn.execute("INSERT INTO crowd_lines VALUES ('nfl','2026-09-28','AP','HP',200,'spread_home',-7,'polymarket',0.6,NULL)")
    got = crowdfit.lines(conn)
    sp, ov = got["polymarket:spread_home"], got["polymarket:over"]
    assert sp["games"] == 6 and sp["lean_n"] == 6 and sp["lean_hit"] == 1.0, sp
    assert sp["brier_vs_even"] < 0, "0.60 on a side that won beats a coin flip"
    assert ov["lean_hit"] == 1.0 and ov["games"] == 6
    assert "not enough games yet" in sp["verdict"]
    assert "4. On the books' own spread and total" in crowdfit.report(
        {"games": 0, "by_sport": {}, "accuracy": {}, "crowd_vs_books": {}, "swings": {}, "lines": got})


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]
    for f in fns:
        f(); print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
