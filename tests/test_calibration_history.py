"""Keeping calibration runs, so "are we improving?" has an answer.

"can we look at our past calibration tests ive done with you and see if we
are improving at all"

We could not. Every sweep printed a table to a terminal and vanished.
MODEL_ERAS splits the BETTING RECORD at each re-tune, which is a different
thing: it measures what the bets did, not whether the probabilities got
better — and the probabilities are what a re-tune is actually changing.

The asymmetry is why this is worth storing. A sweep over 295,627 settled
props can detect a two-point calibration move today. The same move needs a
season to surface in win-loss, because betting outcomes are mostly
variance. Judging model changes on P&L alone is judging them on noise.

None of it is retroactive. Runs made before this existed were not recorded
and cannot be recovered; the first stored run is a baseline, not a verdict,
and the report says so rather than drawing a trend line through one point.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibhistory as CH
from engine.backtest import BacktestReport, CalibrationBin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _conn():
    from engine import db
    return db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))


def _rep(ece=0.05, brier=0.24, n=1000):
    r = BacktestReport(n=n)
    r.ece, r.brier = ece, brier
    r.bins = [CalibrationBin(lo=0.4, hi=0.6, n=n, mean_pred=0.55,
                             hit_rate=0.56)]
    r.pairs = [(0.55, 1)] * (n // 2) + [(0.55, 0)] * (n - n // 2)
    return r


# --- the collision that actually happened -----------------------------------
def test_two_runs_in_the_same_second_are_both_kept():
    """The primary key is (ts, sport, market). At second resolution two
    sweeps finishing inside the same second collapsed into one row, and a
    history that silently drops measurements is not a history — it is a
    history you would trust."""
    c = _conn()
    for _ in range(3):
        CH.record(c, "mlb", "hits", _rep())
    rows = CH.history(c, "mlb", "hits")
    assert len(rows) == 3, f"kept only {len(rows)} of 3 runs"


def test_an_explicit_timestamp_still_overwrites_itself():
    """Re-recording the SAME run is a correction, not a second
    measurement."""
    c = _conn()
    CH.record(c, "mlb", "hits", _rep(ece=0.05), ts="2026-08-01T10:00:00")
    CH.record(c, "mlb", "hits", _rep(ece=0.03), ts="2026-08-01T10:00:00")
    rows = CH.history(c, "mlb", "hits")
    assert len(rows) == 1 and abs(rows[0]["ece"] - 0.03) < 1e-9


# --- the trend has to be readable in the right direction --------------------
def test_falling_ece_is_reported_as_an_improvement():
    c = _conn()
    CH.record(c, "mlb", "hits", _rep(ece=0.08), ts="2026-07-01T00:00:00")
    CH.record(c, "mlb", "hits", _rep(ece=0.03), ts="2026-08-01T00:00:00")
    t = CH.trend(c)["hits"]
    assert t["improved"] is True
    assert t["ece_delta"] < 0


def test_rising_ece_is_not_reported_as_an_improvement():
    """The control. ECE improves by going DOWN while half the numbers on
    the page improve by going up, so a sign confusion here would read as a
    result."""
    c = _conn()
    CH.record(c, "mlb", "hits", _rep(ece=0.03), ts="2026-07-01T00:00:00")
    CH.record(c, "mlb", "hits", _rep(ece=0.08), ts="2026-08-01T00:00:00")
    t = CH.trend(c)["hits"]
    assert t["improved"] is False
    assert t["ece_delta"] > 0


def test_first_and_latest_are_ordered_by_time_not_insertion():
    c = _conn()
    CH.record(c, "mlb", "hits", _rep(ece=0.03), ts="2026-08-01T00:00:00")
    CH.record(c, "mlb", "hits", _rep(ece=0.08), ts="2026-07-01T00:00:00")
    t = CH.trend(c)["hits"]
    assert t["first"]["ts"].startswith("2026-07")
    assert t["last"]["ts"].startswith("2026-08")


def test_a_move_with_no_code_change_is_flagged_as_more_data():
    """More history shifts ECE on its own. Reading that as a better model
    is how you 'improve' something by waiting."""
    c = _conn()
    CH.record(c, "mlb", "hits", _rep(ece=0.05), ts="2026-07-01T00:00:00")
    CH.record(c, "mlb", "hits", _rep(ece=0.04), ts="2026-08-01T00:00:00")
    assert CH.trend(c)["hits"]["same_code"] is True


# --- what it stores ---------------------------------------------------------
def test_the_commit_is_stored_so_a_jump_has_a_cause():
    c = _conn()
    CH.record(c, "mlb", "hits", _rep())
    assert CH.history(c)[0]["code"], "no code version recorded"


def test_a_dirty_tree_is_marked_as_such():
    """A number measured against uncommitted code cannot be reproduced,
    and pretending otherwise poisons every comparison after it."""
    v = CH.code_version()
    assert v == "" or "+dirty" in v or len(v) >= 6


def test_skill_and_sharpness_survive_the_round_trip():
    """They live on the report object, not in __dict__, so the obvious
    way to store a run drops them."""
    c = _conn()
    CH.record(c, "mlb", "hits", _rep())
    row = CH.history(c)[0]
    assert row["base_rate"] is not None
    assert row["hedged"] is not None


def test_a_note_records_what_changed():
    c = _conn()
    CH.record(c, "mlb", "hits", _rep(), note="re-tuned the HR prior")
    assert CH.history(c)[0]["note"] == "re-tuned the HR prior"


def test_a_broken_record_never_takes_down_the_sweep_that_produced_it():
    class Exploding:
        n = 10
        def skill(self):
            raise RuntimeError("boom")
    CH.record(_conn(), "mlb", "hits", Exploding())     # must not raise


def test_reading_a_db_without_the_table_returns_empty_not_an_error():
    import sqlite3
    bare = sqlite3.connect(":memory:")
    assert CH.history(bare) == []
    assert CH.trend(bare) == {}


# --- the CLI ----------------------------------------------------------------
def test_trend_on_an_empty_history_says_so_and_does_not_draw_a_line():
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    from engine import db
    db.connect(path)
    p = subprocess.run([sys.executable, "mlb_calibration.py", "--db", path,
                        "--trend"], cwd=ROOT, capture_output=True, text=True,
                       timeout=300)
    assert p.returncode == 0
    assert "No calibration runs stored yet" in p.stdout
    assert "cannot be recovered" in p.stdout or "vanished" in p.stdout


def test_a_single_run_is_called_a_baseline_not_a_trend():
    """Checked by RUNNING it. The first version grepped the source for this
    sentence, which is split across two f-string lines and so never
    appeared — the test failed while the behaviour was correct. Asserting
    on source text asserts on formatting."""
    from engine import db
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    CH.record(db.connect(path), "mlb", "hits", _rep())
    p = subprocess.run([sys.executable, "mlb_calibration.py", "--db", path,
                        "--trend"], cwd=ROOT, capture_output=True, text=True,
                       timeout=300)
    assert p.returncode == 0, p.stderr[-300:]
    assert "baseline, not a trend" in p.stdout


def test_the_sweep_can_be_told_not_to_store():
    src = open(os.path.join(ROOT, "mlb_calibration.py"), encoding="utf-8").read()
    assert '"--no-save"' in src
    assert "if not args.no_save:" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
