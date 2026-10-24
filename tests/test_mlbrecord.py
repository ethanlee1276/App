"""The MLB record tool, pinned on a ledger whose answers were worked by hand.

Ethan's MLB readiness brief (2026-09-01), Phase 4: "Number of bets — the
first number in the report, not the last. Hit rate vs. breakeven at the
average price. ROI at bet price and ROI at closing price ... Average CLV
in points of implied probability, and share of bets beating the close.
Calibration by probability bucket, with a Brier score ... Max drawdown in
units and longest losing streak. Flat stakes vs. Kelly-sized. Parlays
scored separately from straight bets."

`engine/mlbrecord.py` computes each of those from journal columns. This
file feeds it six bets and three parlays whose every number below was
computed on paper first, so a regression in any formula is a number
that stops matching, not a report that quietly changes shape.

Run directly: `python3 tests/test_mlbrecord.py`
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, mlbrecord as M


def _conn():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    cols = ("ts, sport, date, player, market, side, line, odds, hit_prob, "
            "stake_units, pnl_units, status, category, closing_odds")
    rows = [
        # A: won at +150, closed +120, 1u
        ("t", "mlb", "2026-07-01", "A", "hits", "OVER", 0.5, 150, 0.45, 1.0, 1.5, "won", "main", 120),
        # B: lost at -110, closed -130, 1u
        ("t", "mlb", "2026-07-02", "B", "hits", "OVER", 0.5, -110, 0.55, 1.0, -1.0, "lost", "main", -130),
        # C: HR prop lost at +400, no close, 0.5u
        ("t", "mlb", "2026-08-01", "C", "home_runs", "OVER", 0.5, 400, 0.20, 0.5, -0.5, "lost", "paper", None),
        # D: game total won at -120, closed -110, 1u
        ("t", "mlb", "2026-08-02", "D", "total", "OVER", 8.5, -120, 0.60, 1.0, 0.8333, "won", "main", -110),
        # E: a push — not evidence either way
        ("t", "mlb", "2026-08-03", "E", "hits", "OVER", 1.5, -110, 0.50, 1.0, 0.0, "push", "main", None),
        # F: the HR board's measurement row — not money
        ("t", "mlb", "2026-08-03", "F", "home_runs", "OVER", 0.5, 500, 0.12, 0.1, -0.1, "lost", "longshot", None),
        # G: zero stake — journaled, never a bet
        ("t", "mlb", "2026-08-04", "G", "hits", "OVER", 0.5, 100, 0.55, 0.0, 0.0, "won", "main", None),
        # H: a different sport
        ("t", "nfl", "2026-09-07", "H", "spread", "OVER", -3.0, -110, 0.55, 1.0, -1.0, "lost", "main", None),
    ]
    conn.executemany(f"INSERT INTO bets ({cols}) VALUES ({','.join('?' * 14)})", rows)
    conn.execute("CREATE TABLE IF NOT EXISTS parlays (id INTEGER PRIMARY KEY, ts TEXT, "
                 "sport TEXT, date TEXT, legs_key TEXT, n_legs INTEGER, status TEXT, "
                 "stake_units REAL, notional_units REAL, pnl_units REAL, "
                 "singles_pnl_units REAL)")
    pcols = "ts, sport, date, legs_key, n_legs, status, stake_units, notional_units, pnl_units, singles_pnl_units"
    conn.executemany(f"INSERT INTO parlays ({pcols}) VALUES ({','.join('?' * 10)})", [
        ("t", "mlb", "2026-07-05", "k1", 2, "won", 0.5, 1.0, 1.0, 0.9),
        ("t", "mlb", "2026-07-06", "k2", 3, "lost", 0.0, 1.0, -1.0, -0.5),
        ("t", "mlb", "2026-07-07", "k3", 2, "void", 0.5, 1.0, 0.0, 0.0),
        ("t", "mlb", "2026-07-08", "k4", 2, "open", 0.5, 1.0, None, None),
    ])
    conn.commit()
    return conn


def _close(a, b, tol=1e-3):
    return a is not None and abs(a - b) <= tol


def test_the_population_is_the_record_pages_population():
    r = M.report(_conn())
    o = r["overall"]
    # A, B, C, D count; E is a push; F is measurement; G has no stake; H is NFL.
    assert o["n"] == 4 and o["wins"] == 2 and o["losses"] == 2 and o["pushes"] == 1


def test_hit_rate_against_breakeven_at_the_average_price():
    o = M.report(_conn())["overall"]
    assert o["hit_rate"] == 0.5
    # implied: +150 → .4000, -110 → .5238, +400 → .2000, -120 → .5455; mean .4173
    assert _close(o["breakeven"], 0.4173, 1e-4)


def test_roi_at_price_is_net_over_staked():
    o = M.report(_conn())["overall"]
    # net 1.5 − 1 − 0.5 + 0.8333 = 0.8333 over 3.5u staked
    assert _close(o["net"], 0.8333) and o["staked"] == 3.5
    assert _close(o["roi_at_price"], 0.2381, 1e-4)


def test_roi_at_close_replays_the_same_results_at_the_closing_price():
    o = M.report(_conn())["overall"]
    assert o["n_with_close"] == 3                       # A, B, D — C has none
    # A won at +120 → +1.2; B lost → −1; D won at −110 → +0.9091; over 3u
    assert _close(o["roi_at_close"], 0.3697, 1e-4)
    # and the price-side ROI of that SAME subset is printed beside it
    assert _close(o["roi_at_price_closed_subset"], 0.4444, 1e-4)


def test_clv_is_in_implied_probability_points_close_minus_taken():
    o = M.report(_conn())["overall"]
    # A: .4545 − .4000 = +.0545; B: .5652 − .5238 = +.0414; D: .5238 − .5455 = −.0216
    assert _close(o["clv_mean_pts"], 0.0248, 1e-4)
    assert _close(o["clv_beat_share"], 2 / 3, 1e-3)


def test_flat_control_and_drawdown_and_streak():
    o = M.report(_conn())["overall"]
    # flat 1u: +1.5 −1 −1 +0.8333 = +0.3333 over 4 bets
    assert _close(o["flat_roi"], 0.0833, 1e-4)
    # cumulative: 1.5 → 0.5 → 0.0 → 0.8333; peak 1.5, trough 0.0
    assert _close(o["max_drawdown_u"], 1.5)
    assert o["longest_losing_streak"] == 2           # B then C
    lo, hi = o["flat_roi_ci95"]
    assert lo < 0 < hi, "four bets cannot distinguish an edge from zero"


def test_breakouts_by_type_month_and_market():
    r = M.report(_conn())
    assert set(r["by_type"]) == {"other player props", "HR props", "totals"}
    assert r["by_type"]["HR props"]["n"] == 1
    assert r["by_type"]["other player props"]["pushes"] == 1
    assert list(r["by_month"]) == ["2026-07", "2026-08"]
    assert r["by_month"]["2026-07"]["n"] == 2 and r["by_month"]["2026-08"]["n"] == 2
    assert r["by_market"]["total"]["n"] == 1


def test_calibration_scores_stored_probabilities_and_counts_the_rest():
    r = M.report(_conn())
    c = r["calibration"]
    assert c["n"] == 4 and c["n_without_prob"] == 0
    # (.55² + .55² + .2² + .4²) / 4 = .805 / 4
    assert _close(c["brier"], 0.20125, 1e-4)
    hr = r["hr_calibration_money"]
    assert hr["n"] == 1 and hr["buckets"][0]["range"] == "20%–100%"
    meas = r["hr_calibration_measurement"]
    assert meas["n"] == 1 and meas["buckets"][0]["range"] == "10%–15%"
    assert r["hr_measurement_rows"] == 1


def test_the_5_to_15_band_is_split_not_pooled():
    assert (0.05, 0.10) in M.HR_BUCKETS and (0.10, 0.15) in M.HR_BUCKETS


def test_parlays_are_scored_apart_and_against_their_own_singles():
    p = M.report(_conn())["parlays"]
    assert p["n"] == 2 and p["won"] == 1 and p["voided"] == 1
    assert p["with_money"] == 1                     # the paper ticket had stake 0
    assert p["staked"] == 0.5 and _close(p["net"], 0.0)
    assert _close(p["roi_notional"], 0.0)            # +1 −1 over 2u notional
    assert p["singles_n_legs"] == 5 and _close(p["singles_net_flat"], 0.4)
    assert _close(p["singles_roi_flat"], 0.08)


def test_the_verdict_refuses_under_the_sample_floor():
    r = M.report(_conn())
    assert r["verdict"].startswith("profitability is unverified")
    assert "4 settled bets" in r["verdict"]
    assert M.verdict({"n": 0}) .startswith("profitability is unverified")


def test_the_verdict_flags_a_roi_above_ten_percent_as_a_bug():
    s = dict(n=500, roi_at_price=0.12, roi_at_close=0.11, clv_mean_pts=0.01,
             n_with_close=400, flat_roi_ci95=(0.02, 0.2))
    v = M.verdict(s)
    assert "ABOVE 10%" in v and "distinguishable from zero" in v


def test_the_verdict_names_a_ci_that_spans_zero():
    s = dict(n=500, roi_at_price=0.01, roi_at_close=None, clv_mean_pts=None,
             n_with_close=0, flat_roi_ci95=(-0.03, 0.05))
    assert "spans zero" in M.verdict(s)


def test_a_push_pays_nothing_at_any_price():
    assert M.pnl_at({"status": "push"}, 150, 1.0) == 0.0
    assert M.pnl_at({"status": "won"}, 150, 2.0) == 3.0
    assert M.pnl_at({"status": "lost"}, -300, 2.0) == -2.0


def test_since_cuts_the_population_by_date():
    r = M.report(_conn(), since="2026-08-01")
    assert r["overall"]["n"] == 2 and list(r["by_month"]) == ["2026-08"]


def test_it_never_writes_to_the_ledger():
    import inspect
    src = inspect.getsource(M)
    assert "mode=ro" in src
    for verb in ("INSERT", "UPDATE", "DELETE", "CREATE"):
        assert verb not in src.replace("READ-ONLY", ""), verb


def test_the_text_render_leads_with_the_count_and_the_verdict():
    r = M.report(_conn())
    txt = M.render(r)
    lines = txt.splitlines()
    assert lines[2].startswith("VERDICT:")
    assert lines[4].startswith("Bets: 4 settled")
    assert "NOT money" in txt and "Month by month" in txt


def test_market_types_follow_the_brief():
    assert M.market_type("home_runs") == "HR props"
    assert M.market_type("moneyline") == "sides" and M.market_type("run_line") == "sides"
    assert M.market_type("total") == "totals" and M.market_type("team_total") == "totals"
    assert M.market_type("f5_total") == "F5"
    for m in ("hits", "total_bases", "strikeouts", "outs"):
        assert M.market_type(m) == "other player props", m


def test_the_cli_runs_read_only_end_to_end(capsys=None):
    conn = _conn()
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    conn.close()
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = M.main(["--db", path])
    assert rc == 0 and "VERDICT:" in buf.getvalue()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = M.main(["--db", path, "--json"])
    import json
    assert rc == 0 and json.loads(buf.getvalue())["overall"]["n"] == 4
    assert M.main(["--db", path + ".missing"]) == 2


def test_roi_at_close_is_also_scored_on_the_same_line_subset():
    """A closing price for a DIFFERENT line is not comparable to the price
    taken. The droplet run printed +17.2% at close against −5.7% at
    price — a rule-5 number — so the same-line subset is printed beside
    it. Here every close carries its own line (A, B, D at the line bet),
    so the subset is the whole closed set."""
    o = M.report(_conn())["overall"]
    assert o["n_same_line_close"] == 3
    assert _close(o["roi_at_close_same_line"], o["roi_at_close"], 1e-6)
    assert _close(o["roi_at_price_same_line"], o["roi_at_price_closed_subset"], 1e-6)


def test_a_close_for_a_moved_line_is_counted_out_of_the_same_line_subset():
    conn = _conn()
    conn.execute("UPDATE bets SET closing_line=1.5 WHERE player='A'")
    conn.commit()
    o = M.report(conn)["overall"]
    assert o["n_with_close"] == 3 and o["n_same_line_close"] == 2
    # B lost at close −130 (−1), D won at −110 (+.9091): −.0909 over 2u
    assert _close(o["roi_at_close_same_line"], -0.0455, 1e-3)


def test_the_verdict_compares_the_close_against_the_same_rows():
    """The droplet's -5.7% at price / +17.2% at close read as "the market
    moved against these bets" until the closed subset's own price-side
    ROI was looked at. Against the same rows the close paid less, which
    is positive CLV — and the journal said +1.22 pts, 74% beating."""
    s = dict(n=803, roi_at_price=-0.057, roi_at_close=0.172,
             roi_at_price_closed_subset=0.21, clv_mean_pts=0.0122,
             clv_beat_share=0.74, n_with_close=295, flat_roi_ci95=(-0.1, 0.02))
    v = M.verdict(s)
    assert "on the 295 with a close: +21.0% at price vs +17.2% at the close" in v
    assert "market moved toward these bets" in v and "AGAINST" not in v
    assert "+1.22 pts, 74% beat the close" in v
    assert "ROI AT CLOSE ABOVE 10%" in v
    s = dict(n=500, roi_at_price=0.02, roi_at_close=0.05,
             roi_at_price_closed_subset=0.01, clv_mean_pts=-0.01,
             clv_beat_share=0.4, n_with_close=295, flat_roi_ci95=(-0.1, 0.05))
    assert "AGAINST" in M.verdict(s)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
