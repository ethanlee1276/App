"""What happened to the props the Edge board turned DOWN.

Task #164, "rebuild what it selects on", has carried one line since the
selection backtest ran on 2026-09-06:

    STILL UNANSWERABLE FROM THE JOURNAL: whether any ordering would have
    ADMITTED bets the edge gate refused.

That is the question that decides whether the gate is any good, and the
journal cannot answer it by construction: it holds the bets we PLACED,
so `recommended` is True on every row in it. `engine/selectorder.py`
says the same thing in its own docstring — "take the bets we actually
placed and settled".

THE DATA WAS ALREADY THERE. `backtest_from_stats` walks the season
forward, prices every prop from prior weeks only, and settles ALL of
them against the box score. `SettledProp` carries `recommended` beside
the outcome and `BacktestReport.settled` keeps every row. The candidate
surface with outcomes has existed the whole time; nothing ever read the
refused half of it. `n_bets`, `roi` and the rest of the report are
documented "recommended bets only".

So: `from_settled` adapts that surface into the row shape this module
already scores, and `gate_split` scores both arms at a flat 1u.

THE BOOTSTRAP IS NOT THE ONE ABOVE IT, and that is the part worth
getting right. `_boot_roi_diff` resamples ONE pool and re-cuts it,
because the arms it compares are two orderings of the same rows. Here
the arms are different rows — admitted and refused are disjoint — so
each is resampled within itself. Reusing the paired version would have
reported a narrower interval than the truth, which flatters exactly the
kind of result somebody wants to act on.

Run directly: `python3 tests/test_gate_refusals_scored.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import selectorder as S                            # noqa: E402
from engine.backtest import SettledProp                        # noqa: E402


def _sp(actual, line=50.0, odds=-110, recommended=True, basis="book",
        side="OVER", hit_prob=0.55):
    return SettledProp(player="A Man", market="rec_yds", line=line, odds=odds,
                       hit_prob=hit_prob, projection=line, actual=actual,
                       recommended=recommended, basis=basis, side=side)


# --- the adapter ------------------------------------------------------------
def test_the_candidate_surface_becomes_scoreable_rows():
    rows = S.from_settled([_sp(60.0), _sp(40.0, recommended=False)])
    assert [r["status"] for r in rows] == ["won", "lost"]
    assert [r["recommended"] for r in rows] == [True, False]
    assert all(r["basis"] == "book" for r in rows)


def test_an_under_is_scored_on_the_side_it_backed():
    """`SettledProp.outcome` already flips for an UNDER. If the adapter
    read `over_hit` instead, every under would grade backwards — the
    exact bug SettledProp's own comment says it exists to prevent."""
    rows = S.from_settled([_sp(40.0, side="UNDER")])
    assert [r["status"] for r in rows] == ["won"], rows


def test_a_push_is_dropped_rather_than_counted_as_a_loss():
    """A push returns the stake. Scoring it as a loss would bias
    whichever arm happens to hold more of them, and the arms here are
    different populations — so it cannot cancel out the way it would in
    a paired comparison."""
    rows = S.from_settled([_sp(50.0), _sp(60.0)])
    assert len(rows) == 1 and rows[0]["status"] == "won", rows


def test_the_journal_still_reads_as_all_admitted():
    """`usable` defaults `recommended` True, because a journal row is a
    bet we placed. Without that default every existing caller's rows
    would land in the refused arm."""
    rows = S.usable([{"status": "won", "hit_prob": 0.6, "odds": -110}])
    assert rows and rows[0]["recommended"] is True, rows


# --- the split --------------------------------------------------------------
def _arm(n, won, recommended, odds=-110, basis="book"):
    return [_sp(60.0 if i < won else 40.0, odds=odds,
                recommended=recommended, basis=basis) for i in range(n)]


def test_a_gate_whose_refusals_lose_earns_its_place():
    settled = _arm(80, 60, True) + _arm(80, 20, False)
    res = S.gate_split(S.from_settled(settled), reps=300)
    assert res["enough"], res
    assert res["admitted"]["bets"] == 80 and res["refused"]["bets"] == 80
    assert res["admitted"]["roi"] > res["refused"]["roi"], res
    assert res["diff"]["admitted-refused"]["lo"] > 0, res["diff"]
    assert "earns its place" in S.gate_reading(res), S.gate_reading(res)


def test_a_gate_whose_refusals_win_is_reported_as_costing_money():
    """THE FINDING THIS EXISTS TO CATCH. If the board would have done
    better taking what it turned down, nothing in the journal would ever
    say so."""
    settled = _arm(80, 20, True) + _arm(80, 60, False)
    res = S.gate_split(S.from_settled(settled), reps=300)
    assert res["diff"]["admitted-refused"]["hi"] < 0, res["diff"]
    say = S.gate_reading(res)
    assert "COSTING money" in say, say
    assert "worth more than what it takes" in say, say


def test_two_arms_that_ran_the_same_read_as_unproven():
    settled = _arm(80, 40, True) + _arm(80, 40, False)
    res = S.gate_split(S.from_settled(settled), reps=300)
    d = res["diff"]["admitted-refused"]
    assert d["lo"] <= 0 <= d["hi"], d
    assert "unproven either way" in S.gate_reading(res), S.gate_reading(res)


# --- the bars that keep it honest -------------------------------------------
def test_a_thin_arm_reports_how_thin_rather_than_a_number():
    settled = _arm(80, 40, True) + _arm(5, 3, False)
    res = S.gate_split(S.from_settled(settled), reps=100)
    assert not res["enough"], res
    assert res["admitted"] is None and res["refused"] is None
    assert "5 refused" in res["note"], res["note"]
    assert S.gate_reading(res) == res["note"]


def test_proxy_priced_rows_are_left_out_by_default():
    """A `naive` row was priced against the recent-form proxy at a
    synthetic -110, so beating it is the model scored against itself.
    `BacktestReport` segments on the same distinction."""
    settled = _arm(80, 60, True) + _arm(80, 20, False, basis="naive")
    res = S.gate_split(S.from_settled(settled), reps=100)
    assert res["n_refused"] == 0, res
    assert not res["enough"], res


def test_pooling_the_proxy_rows_says_the_number_is_not_market_relative():
    settled = _arm(80, 60, True, basis="naive") + _arm(80, 20, False, basis="naive")
    res = S.gate_split(S.from_settled(settled), basis="naive", reps=300)
    assert res["enough"], res
    assert "not a claim about beating a market" in S.gate_reading(res)


def test_the_bootstrap_is_two_sample_not_the_paired_one():
    """Read off the function, because the failure is invisible in the
    output: a paired interval on unpaired arms is simply narrower than
    the truth."""
    import inspect
    src = inspect.getsource(S.gate_split)
    assert "_boot_two_sample" in src, src[:200]
    assert "_boot_roi_diff" not in src, "the paired bootstrap is back"
    two = inspect.getsource(S._boot_two_sample)
    assert "_top(" not in two, "the two-sample bootstrap is re-cutting a slice"


def test_the_two_arms_never_share_a_row():
    """Disjoint by construction — the whole basis for reading the
    difference as the gate's doing."""
    settled = _arm(70, 35, True) + _arm(70, 35, False)
    rows = S.from_settled(settled)
    pool = S.usable(rows)
    took = [r for r in pool if r["recommended"]]
    left = [r for r in pool if not r["recommended"]]
    assert len(took) + len(left) == len(pool)
    assert len(took) == 70 and len(left) == 70


# --- the CLI reads it -------------------------------------------------------
def test_the_backtest_cli_can_print_it():
    src = open(os.path.join(ROOT, "backtest.py"), encoding="utf-8").read()
    assert '"--gate"' in src, "the flag is gone"
    assert "def gate_report(" in src
    assert "from engine.selectorder import from_settled, gate_split, gate_reading" in src
    assert "report.settled" in src, "the CLI is not reading the candidate surface"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
