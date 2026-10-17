"""CLV and the market Brier compare like with like.

Audit 2026-09-30, P1-2 and P1-3 (roadmap #5):

  * PRICE CLV scored the price we SHOPPED TO — the best on the screen —
    against the field's MEDIAN close. Shopping selects the price furthest
    from the field, so a bet read as beating the close with no movement at
    all. The matched measure compares the field with the field: the de-vigged
    consensus fair at pick time (`fair_consensus`, journaled) against the
    de-vigged close for the same side (`closing_fair`, new).
  * The "market" Brier was `hit_prob - edge` — the fair of the book we bet,
    which is the outlier shopping picked. The consensus Brier scores the
    field's fair on the same bets, and the page says which is which.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, odds                                       # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _bet(**kw):
    b = {"side": "OVER", "line": 0.5, "odds": 150, "closing_line": 0.5,
         "closing_odds": 130, "fair_consensus": 0.42, "closing_fair": 0.42}
    b.update(kw)
    return b


def test_best_price_against_the_median_reads_as_edge_the_matched_one_does_not():
    b = _bet()
    assert ledger._bet_price_clv(b) > 0.03, "the old measure: +150 shopped vs +130 median"
    assert ledger._bet_clv_matched(b) == 0.0, "the field did not move: no value"


def test_the_matched_measure_reads_a_real_move_and_its_side():
    assert round(ledger._bet_clv_matched(_bet(closing_fair=0.47)), 4) == 0.05
    under = _bet(side="UNDER", fair_consensus=0.42, closing_fair=0.55)
    # The under's fair at pick was 0.58; the close says 0.55 — against us.
    assert round(ledger._bet_clv_matched(under), 4) == -0.03


def test_no_consensus_or_no_close_is_no_reading():
    assert ledger._bet_clv_matched(_bet(fair_consensus=None)) is None
    assert ledger._bet_clv_matched(_bet(closing_fair=None)) is None
    assert ledger._bet_clv_matched({"side": "OVER"}) is None


def test_the_close_is_devigged_through_the_one_devig():
    fair = ledger._close_fair_from({"line": 1.5, "over_odds": -120, "under_odds": 100},
                                   1.5, "OVER")
    want = odds.devig_two_way(-120, 100)[0]
    assert abs(fair - want) < 1e-9
    under = ledger._close_fair_from({"over": -120, "under": 100}, None, "UNDER")
    assert abs(under - odds.devig_two_way(-120, 100)[1]) < 1e-9
    assert ledger._close_fair_from({"line": 2.5, "over_odds": -120, "under_odds": 100},
                                   1.5, "OVER") is None, "another line is another bet"
    assert ledger._close_fair_from({"line": 1.5, "over_odds": -120, "under_odds": 0},
                                   1.5, "OVER") is None, "one side is not a two-way close"


def test_the_brier_against_the_field_is_the_field_fairs_own():
    conn = ledger.connect(":memory:")
    rows = [(0.60, 0.05, 0.50, "OVER", "won"), (0.70, 0.10, 0.55, "OVER", "lost"),
            (0.55, 0.02, 0.40, "UNDER", "won")]
    for i, (p, e, fc, side, st) in enumerate(rows):
        conn.execute("INSERT INTO bets (sport,date,player,market,side,line,odds,hit_prob,"
                     "edge,fair_consensus,status,stake_units,category) VALUES "
                     "('mlb','2026-07-01',?,'hits',?,0.5,-110,?,?,?,?,1,'main')",
                     (f"P{i}", side, p, e, fc, st))
    conn.commit()
    cal = ledger.calibration(conn)
    fair = [0.50, 0.55, 0.60]            # the under's side is 1 - 0.40
    won = [1, 0, 1]
    want = sum((f - w) ** 2 for f, w in zip(fair, won)) / 3
    assert cal["brier_consensus"] == round(want, 4) and cal["n_consensus"] == 3
    assert cal["brier_market_basis"] == "the book we bet"


def test_coverage_and_performance_carry_both_measures():
    conn = ledger.connect(":memory:")
    p = ledger.performance(conn)
    assert "avg_matched_clv" in p and "matched_clv_n" in p
    import inspect
    assert "_bet_clv_matched(" in inspect.getsource(ledger.clv_coverage)


def test_settling_and_the_backfill_store_the_devigged_close():
    import inspect
    assert "closing_fair" in inspect.getsource(ledger.settle_from_history)
    assert "closing_fair" in inspect.getsource(ledger.repair_closing_odds)


def test_the_page_names_each_benchmark():
    i = APP.index("function recordVerdictHTML(")
    v = APP[i:APP.index("\n}\n", i)]
    assert "the book we bet" in v and "brier_consensus" in v
    assert "avg_matched_clv" in v
    assert 'price_clv_n === 1 ? "" : "s"' in v and "on ${o.price_clv_n ?? 0} bet" in v, \
        '"on M overs" counted every bet, overs and unders'


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
