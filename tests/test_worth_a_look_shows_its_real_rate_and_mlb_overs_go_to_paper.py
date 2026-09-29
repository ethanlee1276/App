"""Two of Ethan's calls from the go-over, 2026-09-29.

1. "Worth a look" claimed 59% and hit 48% (123-132 on the one board) —
   "show the real hit rate". The board reads each tier's settled record
   (journal book `board`, the tier as the grade) and a Worth-a-look card
   carries its tier's real rate once RECORD_MIN_N picks have settled; the
   card's ring and its price to take both read that number.

2. MLB edge overs lost 26 units over the summer — "keep the bets but make
   it paper". A fresh MLB edge PROP on the over is journaled to the paper
   book: still sized, still graded, no dollars. Unders, other leagues and
   game bets are untouched.

Fixture ledgers in a temp directory — never the box's.

Run directly: `python3 tests/test_worth_a_look_shows_its_real_rate_and_mlb_overs_go_to_paper.py`
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, likelyboard as LB                    # noqa: E402

SOON = (dt.datetime.utcnow() + dt.timedelta(days=1)).date().isoformat()
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _ledger():
    conn = ledger.connect(Path(tempfile.mkdtemp()) / "l.db")
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1)
    return conn


# --- 1. the real hit rate ---------------------------------------------------
def _board_rows(conn, grade, won, lost, sport="nfl"):
    for i in range(won + lost):
        conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, hit_prob, "
                     "stake_units, status, category, grade) VALUES "
                     "('t',?,'2026-W03',?,'rec_yds','OVER',40.5,-150,0.6,0.1,?,'board',?)",
                     (sport, f"{grade} {i}", "won" if i < won else "lost", grade))
    conn.commit()


def test_the_tier_record_is_read_per_sport_and_tier():
    conn = _ledger()
    _board_rows(conn, "Worth a look", 12, 13)
    _board_rows(conn, "Strong", 16, 9)
    _board_rows(conn, "Worth a look", 9, 1, sport="mlb")
    got = LB.tier_record(conn, "nfl")
    assert got["look"] == {"n": 25, "hits": 12} and got["strong"] == {"n": 25, "hits": 16}
    assert LB.tier_record(conn, "mlb")["look"] == {"n": 10, "hits": 9}


def test_only_worth_a_look_with_enough_settled_gets_the_real_rate():
    seen = {"look": {"n": 255, "hits": 123}, "strong": {"n": 178, "hits": 111}}
    assert LB.real_rate(seen, "look") == (round(123 / 255, 4), 255)
    assert LB.real_rate(seen, "strong") == (None, 178), "Strong keeps our number"
    assert LB.real_rate({"look": {"n": 12, "hits": 9}}, "look") == (None, 12), "too few to say"
    assert LB.real_rate(None, "look") == (None, 0)
    assert LB.REAL_RATE_TIERS == ("look",)


def test_the_card_leads_with_the_real_rate_on_its_ring_and_its_price():
    i = APP.index("function obShownProb(r)")
    assert "r.tier_rate != null ? Number(r.tier_rate) : Number(r.model_prob || 0)" in APP[i:i + 200]
    ring = APP[APP.index("function obRingHTML(r)"):APP.index("function obFaceHTML(r)")]
    assert "obShownProb(r)" in ring and "picks have hit" in ring
    price = APP[APP.index("function obPriceHTML(r)"):APP.index("function obPriceHTML(r)") + 600]
    assert "const shown = obShownProb(r);" in price and "obFairAmerican(shown)" in price
    assert "<small>real hit rate</small>" in APP


def test_the_build_hands_the_record_to_the_board():
    src = (ROOT / "engine" / "likelyboard.py").read_text()
    assert "seen = tier_record(conn, sport)" in src
    assert "board = build(result, record=rec, sport=sport, tiers_seen=seen)" in src
    assert 'r["tier_rate"], r["tier_n"] = rate, n_seen' in src


# --- 2. MLB edge overs on paper -----------------------------------------------
def _prop(**kw):
    row = {"player": "A Judge", "team": "NYY", "opponent": "BOS",
           "market": "hits", "market_label": "Hits", "side": "OVER",
           "line": 1.5, "book": "fanduel", "odds": +120, "hit_prob": 0.49,
           "raw_prob": 0.49, "implied_prob": 0.45, "model_prob": 0.49,
           "projection": 1.3, "game_date": SOON, "date": SOON,
           "has_market": True, "recommended": True, "edge": 0.04,
           "confidence": 0.7, "grade": "B", "stake_units": 1.0,
           "logs": [], "recent_values": []}
    row.update(kw)
    return row


def test_an_mlb_edge_over_is_journaled_on_paper_still_sized():
    conn = _ledger()
    ledger.log_recommendations(conn, {"sport": "mlb", "date": SOON, "recommendations": [
        _prop(), _prop(player="R Devers", side="UNDER", market="total_bases")]})
    got = {r["player"]: dict(r) for r in conn.execute(
        "SELECT player, category, stake_units, stake_dollars FROM bets")}
    assert got["A Judge"]["category"] == "paper" and got["A Judge"]["stake_dollars"] == 0.0
    assert got["A Judge"]["stake_units"] > 0, "still sized, so it still measures"
    assert got["R Devers"]["category"] == "main" and got["R Devers"]["stake_dollars"] > 0


def test_other_leagues_and_the_rule_itself():
    assert ledger.PAPER_PROP_SIDES == {("mlb", "OVER")}
    assert ledger.prop_book("main", "mlb", "over") == "paper"
    assert ledger.prop_book("main", "mlb", "UNDER") == "main"
    assert ledger.prop_book("main", "nfl", "OVER") == "main"
    assert ledger.prop_book(ledger.BENCH_CATEGORY, "mlb", "OVER") == ledger.BENCH_CATEGORY, \
        "a benched league stays on its bench"
    conn = _ledger()
    ledger.log_recommendations(conn, {"sport": "nfl", "date": SOON, "recommendations": [
        _prop(player="J Allen", team="BUF", opponent="MIA", market="pass_yds", line=240.5)]})
    assert conn.execute("SELECT category FROM bets").fetchone()[0] == "main"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
