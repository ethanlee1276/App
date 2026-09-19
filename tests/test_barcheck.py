"""The bar sweep that must not recommend a bar.

Sweeping edge bars over settled history and taking the best ROI is the most
inviting mistake available in this repo. 247 settled bets carry a 2-sigma
bar of ±6.3 points, so the best of six nested retrospective subsets is a
maximum-of-draws — it produces a "finding" on data with no signal at all.

barcheck exists to answer one question with arithmetic instead: is a floor
that covers the measured over-claim even reachable, given that the gate
also refuses to believe an edge above MAX_CREDIBLE_EDGE × shrink? It is
not, by roughly a factor of three, and that is the report.

Run directly: `python3 tests/test_barcheck.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import barcheck as bc                                           # noqa: E402
from engine import ledger                                       # noqa: E402
from engine.betting import MAX_CREDIBLE_EDGE                    # noqa: E402
from engine.quality import TIER_MIN_EDGE, TIER_SHRINK           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the arithmetic that is the whole answer ---------------------------------
def test_the_window_is_read_from_the_code_not_restated():
    """Both ends must come from the constants the gate actually uses, or
    this report drifts away from the thing it describes."""
    for t in (1, 2):
        lo, hi = bc.window(t)
        assert lo == TIER_MIN_EDGE[t]
        assert hi == MAX_CREDIBLE_EDGE * TIER_SHRINK[t]


def test_the_window_is_only_a_couple_of_points_wide():
    """The premise. Tier 1 runs 2.5% to 5.0% and tier 2 is narrower still,
    which is why a 12-point correction cannot fit inside either."""
    assert bc.window(1) == (0.025, 0.05)
    assert round(bc.window(2)[1], 4) == 0.045


def test_a_twelve_point_gap_makes_the_floor_unreachable():
    """The finding, in one assertion. An honest floor is about three times
    the largest edge the model is permitted to claim."""
    for t in (1, 2):
        h = bc.honest_bar(t, 0.12)
        assert h["reachable"] is False
        assert h["short"] > 0.09, h          # short by 9+ points, not a sliver
        assert h["need"] > 2.5 * h["ceiling"]


def test_a_small_gap_is_reachable_so_the_test_can_say_yes():
    """A diagnostic that can only return one answer is not a diagnostic.
    A 1-point over-claim fits inside tier 1's window and must report so."""
    h = bc.honest_bar(1, 0.01)
    assert h["reachable"] is True
    assert h["need"] == 0.035 and h["short"] < 0


def test_the_verdict_wording_follows_reachability_not_the_gap_size():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bc.report(ledger.connect(":memory:"), "mlb")
    out = buf.getvalue()
    assert "IMPOSSIBLE" in out
    assert "NOT NARROWED, IT IS INVERTED" in out
    assert "A higher bar is not" in out


# --- it must not become a bar-picker -----------------------------------------
def test_it_never_names_a_recommended_bar():
    """The trap. Every other number in this file is descriptive; the moment
    one row is singled out as the answer, this becomes a fitter over six
    nested subsets of one thin journal."""
    src = open(os.path.join(ROOT, "barcheck.py"), encoding="utf-8").read()
    body = src[src.index("def report("):]
    for banned in ("max(", "best_bar", "argmax", "sorted(rows, key=lambda"):
        assert banned not in body, banned
    assert "DO NOT PICK THE BEST ROW" in body


def test_the_sweep_is_labelled_context():
    import contextlib
    import io
    conn = _journal(120)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bc.report(conn, "mlb")
    out = buf.getvalue()
    assert "CONTEXT, NOT A MENU" in out
    assert "maximum-of-draws" in out


def test_it_writes_nothing():
    src = open(os.path.join(ROOT, "barcheck.py"), encoding="utf-8").read()
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "commit()",
                      "write_text"):
        assert forbidden not in src, forbidden


# --- the survivor arithmetic --------------------------------------------------
def _journal(n, edge_lo=0.02, edge_hi=0.06):
    conn = ledger.connect(":memory:")
    for i in range(n):
        edge = edge_lo + (edge_hi - edge_lo) * (i / max(n - 1, 1))
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,odds,"
            "hit_prob,edge,status,category,stake_units,pnl_units) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-08-01", "mlb", "2026-08-01", f"P{i}", "total_bases", "OVER",
             1.5, "dk", -110, 0.58, edge, "won" if i % 2 else "lost", "main",
             0.5, 0.45 if i % 2 else -0.5))
    conn.commit()
    return conn


def test_raising_a_bar_is_a_subset_operation():
    """Why this can be read off the journal at all: no bet that failed the
    old bar is being invented back in, so the higher-bar rows are real
    history rather than a counterfactual."""
    rows = bc.load(_journal(100), "mlb")
    a = {id(r) for r in rows if float(r["edge"]) >= 0.03}
    b = {id(r) for r in rows if float(r["edge"]) >= 0.05}
    assert b < a and b


def test_survivors_counts_and_roi_match_a_hand_sum():
    rows = [{"edge": 0.04, "status": "won", "stake_units": 1.0,
             "pnl_units": 0.9, "hit_prob": 0.6},
            {"edge": 0.02, "status": "lost", "stake_units": 1.0,
             "pnl_units": -1.0, "hit_prob": 0.6},
            {"edge": 0.06, "status": "lost", "stake_units": 1.0,
             "pnl_units": -1.0, "hit_prob": 0.6}]
    s = bc.survivors(rows, 0.03)
    assert s["n"] == 2 and s["won"] == 1
    assert abs(s["staked"] - 2.0) < 1e-9
    assert abs(s["pnl"] + 0.1) < 1e-9
    assert abs(s["roi"] + 0.05) < 1e-9


def test_the_gap_is_measured_not_assumed_when_a_journal_exists():
    g = bc.measured_gap(bc.load(_journal(100), "mlb"))
    assert g["n"] == 100
    assert abs(g["claimed"] - 0.58) < 1e-9
    assert abs(g["landed"] - 0.50) < 1e-9
    assert abs(g["gap"] - 0.08) < 1e-9


def test_an_empty_journal_still_answers_the_arithmetic():
    """The finding does not depend on the journal — it is two constants and
    a measured gap. With no rows it says so and uses the published figure
    rather than reporting nothing."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bc.report(ledger.connect(":memory:"), "mlb")
    out = buf.getvalue()
    assert "No settled mlb recommendations on this machine" in out
    assert "The arithmetic does not depend on it" in out
    assert "IMPOSSIBLE" in out


def test_a_thin_survivor_row_is_not_quoted():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bc.report(_journal(60), "mlb")
    assert f"under {bc.MIN_ROW}, not quoted" in buf.getvalue()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
