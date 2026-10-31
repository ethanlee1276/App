"""An exchange edge is measured after the venue's fee, and the row says so.

Audit 2026-09-30, B7-1 (roadmap #22). No fee handling existed anywhere: the
Kalshi desks (game contracts and weather) recommended on the gross gap
between our probability and the mid, and journaled the contract at the
bare price. Kalshi's taker fee is 0.07 x P x (1 - P) per $1 contract —
1.75 cents at 50 cents, about 7% of the expected profit mid-range — so a
3-point "edge" at the gate was a 1.25-point one that could actually be
bought. Now:

  * engine/exchangefees holds the schedule, one place;
  * each desk row carries `fee_bps` and `net_edge_pts`, and `rec` is decided
    on the NET number (the gross gap stays on the row for display);
  * the journal books the price actually paid, cost + fee, and stores
    `fee_bps`, so ROI and CLV are graded against a price that could be had;
  * the Pick of the Day's EV, on a row whose book IS an exchange, is net.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_the_kalshi_fee_is_seven_percent_of_p_times_one_minus_p():
    from engine import exchangefees as F
    assert abs(F.fee_per_contract("kalshi", 0.50) - 0.0175) < 1e-9
    assert abs(F.fee_per_contract("kalshi", 0.20) - 0.0112) < 1e-9
    assert abs(F.fee_per_contract("kalshi", 0.80) - 0.0112) < 1e-9, "symmetric: YES and NO pay alike"
    assert F.fee_per_contract("kalshi", 0.0) == 0.0 and F.fee_per_contract("kalshi", 1.0) == 0.0
    # 1.75 cents on a 50-cent contract is 350 basis points of the stake.
    assert F.fee_bps("kalshi", 0.50) == 350
    assert F.fee_per_contract("draftkings", 0.5) == 0.0 and F.fee_bps("draftkings", 0.5) == 0
    assert F.is_exchange("Kalshi") and not F.is_exchange("DraftKings")


def test_net_ev_subtracts_the_fee_from_what_the_contract_pays():
    from engine import exchangefees as F
    # Fair 55%, bought at 50 cents: gross +0.10 per unit; the fee costs
    # 1.75 cents, so the unit now buys fewer contracts.
    gross = F.net_expected_value(0.55, 0.50, "none")
    net = F.net_expected_value(0.55, 0.50, "kalshi")
    assert abs(gross - 0.10) < 1e-9
    assert abs(net - (0.55 / 0.5175 - 1)) < 1e-9 and net < gross
    assert abs(F.net_edge_pts(0.55, 0.50, "kalshi") - 3.25) < 1e-9


def test_the_game_desk_recommends_on_the_net_edge():
    from engine.sources import kalshi as K
    g = {"away": "DAL", "home": "NYG", "home_ml": -110, "away_ml": -110}
    # A 3.2-point gross gap at 50 cents clears a 3-point gate gross and not net.
    m = {"ticker": "KXNFLGAME-26SEP13DALNYG-NYG", "title": "New York G win?", "prob": 0.50,
         "price_basis": "book", "volume_24h": 10 ** 6, "spread_cents": 1}
    real = (K.sport_of, K.match_game, K.yes_team)
    K.sport_of = lambda m: "nfl"
    K.match_game = lambda m, games: g
    K.yes_team = lambda m, g: "home"
    try:
        out = K.board([m], {"nfl": [g]}, {("nfl", "DAL@NYG"): 0.50 + (K.KALSHI_MIN_EDGE_PTS + 0.2) / 100})
    finally:
        K.sport_of, K.match_game, K.yes_team = real
    row = out["rows"][0]
    assert row["edge_pts"] >= K.KALSHI_MIN_EDGE_PTS, "the gross gap clears the gate"
    assert row["fee_bps"] == 350 and row["net_edge_pts"] < row["edge_pts"]
    assert row["rec"] is False, "a gross edge the fee eats is not a recommendation"


def test_the_journal_books_the_price_paid_and_the_fee():
    from engine import ledger as L
    p = Path(tempfile.mkdtemp()) / "l.db"
    conn = L.connect(p)
    n = L.log_predmarket(conn, [{"rec": True, "ticker": "KXNFLGAME-26SEP13DALNYG-NYG",
                                 "prob": 0.50, "rec_side": "YES", "model_p": 0.56,
                                 "edge_pts": 6.0, "net_edge_pts": 4.25, "fee_bps": 350,
                                 "title": "x"}], date="2026-09-10")
    assert n == 1
    r = conn.execute("SELECT odds, edge, fee_bps, line FROM bets WHERE category='predmarket'").fetchone()
    # Paid 51.75 cents for a $1 contract: -107, not the -100 the mid implies.
    assert r["odds"] == L._price_to_american(0.5175) == -107
    assert abs(r["edge"] - 0.0425) < 1e-9 and r["fee_bps"] == 350
    assert r["line"] == 50.0, "the line stays the quoted price the desk saw"
    conn.close()


def test_the_weather_desk_is_net_too():
    import inspect
    from engine import kalshiweather as W
    src = inspect.getsource(W)
    assert "net_edge_pts" in src and "fee_bps" in src
    assert "rec = liquid and net >= WX_MIN_EDGE_PTS" in src, "rec is decided on the net number"


def test_the_pick_of_the_day_is_net_on_an_exchange_book():
    from engine import potd
    row = {"odds": -100, "exchange_fair": 0.55, "book": "Kalshi"}
    book = dict(row, book="DraftKings")
    assert potd.edge(row) < potd.edge(book), "a fee-bearing venue's EV is lower"
    assert abs(potd.edge(book) - 0.10) < 1e-9


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
