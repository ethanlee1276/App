"""The capture that makes an already-corrected market refittable.

A market that has been fitted once is frozen: journalfit.fit_temperatures
skips any key it already owns, because that key's later journal rows were
produced UNDER the correction, and fitting a temperature on corrected
claims and then storing it in the correction's place destroys the
correction. The site's "Last new fit" stamp sits still for exactly that
reason, and it is correct behaviour, not a broken feature.

What unfreezing would need is the model's own uncorrected claim. These
tests pin the two halves that make that recoverable:

  * ``calibrate.undo_temperature`` inverts ``apply_temperature`` exactly.
  * the journal stores ``raw_prob`` (the claim before the market shrink)
    beside ``cal_temp`` / ``cal_bias`` (the correction live when the row
    was logged), so the pair can be inverted per row.

The last test is the one that matters: it demonstrates the destruction on
real fitted numbers, and demonstrates that un-correcting first is stable.
Nothing here unfreezes anything — no market's refit behaviour changes.

Run directly: `python3 tests/test_refit_capture.py`
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate as cal
from engine import ledger


# --- the inverse -----------------------------------------------------------
def test_undo_temperature_inverts_apply_across_the_grid():
    for p in (0.02, 0.15, 0.37, 0.5, 0.63, 0.88, 0.97):
        for t in (0.4, 0.75, 1.0, 1.6, 3.0, 6.0):
            for b in (-0.8, -0.1, 0.0, 0.25, 1.2):
                back = cal.undo_temperature(cal.apply_temperature(p, t, b), t, b)
                assert abs(back - p) < 1e-9, (p, t, b, back)


def test_undo_temperature_is_identity_when_no_correction_was_applied():
    # The overwhelmingly common journal row: a market with nothing stored.
    for p in (0.05, 0.44, 0.9):
        assert cal.undo_temperature(p, 1.0, 0.0) == p


def test_undo_temperature_leaves_a_degenerate_temperature_alone():
    # apply_temperature returns p untouched at t <= 0, so its inverse must
    # too — otherwise inverting a row would invent a correction that was
    # never applied to it.
    assert cal.undo_temperature(0.6, 0.0) == 0.6
    assert cal.undo_temperature(0.6, -2.0) == 0.6


def test_undo_temperature_moves_the_probability_the_other_way():
    # Guards against an inverse that happens to round-trip because it is
    # secretly the same function.
    hot = cal.apply_temperature(0.8, 2.0)     # flattened toward 50%
    assert hot < 0.8
    assert cal.undo_temperature(0.8, 2.0) > 0.8


# --- the journal capture ---------------------------------------------------
def _result(**over):
    base = {
        "sport": "mlb", "date": "2026-08-05",
        "recommendations": [
            {"player": "A", "market": "total_bases", "side": "OVER",
             "line": 1.5, "book": "FanDuel", "odds": -110, "projection": 1.8,
             "hit_prob": 0.56, "raw_prob": 0.62, "edge": 0.05,
             "confidence": 7.0, "grade": "B", "stake_units": 1.0,
             "recommended": True},
        ],
    }
    base.update(over)
    return base


def _store(tmp_path, entries):
    """Point the calibration store at a temp file holding `entries`."""
    import json
    p = tmp_path / "calibration.json"
    p.write_text(json.dumps(entries))
    cal.DEFAULT_PATH = p
    cal.reset_cache()
    return p


def _tmpdir():
    import pathlib
    import tempfile
    return pathlib.Path(tempfile.mkdtemp())


def _restore(orig):
    cal.DEFAULT_PATH = orig
    cal.reset_cache()


def test_journal_stores_the_raw_claim_and_the_live_correction():
    orig = cal.DEFAULT_PATH
    try:
        _store(_tmpdir(), {"mlb:total_bases": {"temperature": 1.6,
                                               "intercept": -0.2}})
        conn = ledger.connect(":memory:")
        ledger.log_recommendations(conn, _result())
        row = conn.execute(
            "SELECT hit_prob, raw_prob, cal_temp, cal_bias FROM bets").fetchone()
        assert row["hit_prob"] == 0.56          # unchanged: still the claim
        assert row["raw_prob"] == 0.62          # …before the market shrink
        assert row["cal_temp"] == 1.6
        assert row["cal_bias"] == -0.2
    finally:
        _restore(orig)


def test_journal_records_no_correction_for_an_unfitted_market():
    orig = cal.DEFAULT_PATH
    try:
        _store(_tmpdir(), {})
        conn = ledger.connect(":memory:")
        ledger.log_recommendations(conn, _result())
        row = conn.execute("SELECT cal_temp, cal_bias FROM bets").fetchone()
        # 1.0/0.0 is "nothing was applied", which inverts to identity —
        # NOT null, because null would be indistinguishable from a
        # pre-migration row whose correction is genuinely unknown.
        assert (row["cal_temp"], row["cal_bias"]) == (1.0, 0.0)
    finally:
        _restore(orig)


def test_journal_records_the_neutralised_correction_for_a_boundary_fit():
    # A boundary fit is never APPLIED (correction_for neutralises it), so
    # journaling the stored 6.0 would tell a later refit to un-correct
    # something that was priced straight.
    orig = cal.DEFAULT_PATH
    try:
        _store(_tmpdir(), {"mlb:total_bases": {"temperature": cal.GRID_MAX,
                                               "intercept": 0.0}})
        conn = ledger.connect(":memory:")
        ledger.log_recommendations(conn, _result())
        row = conn.execute("SELECT cal_temp FROM bets").fetchone()
        assert row["cal_temp"] == 1.0
    finally:
        _restore(orig)


def test_a_row_without_a_raw_claim_still_journals():
    orig = cal.DEFAULT_PATH
    try:
        _store(_tmpdir(), {})
        conn = ledger.connect(":memory:")
        rec = _result()
        rec["recommendations"][0].pop("raw_prob")
        assert ledger.log_recommendations(conn, rec) == 1
        assert conn.execute("SELECT raw_prob FROM bets").fetchone()[0] is None
    finally:
        _restore(orig)


def test_the_new_columns_migrate_onto_an_existing_ledger():
    import sqlite3
    d = _tmpdir()
    db = d / "old.db"
    conn = ledger.connect(db)
    conn.close()
    # Simulate a pre-migration file by dropping the three columns the way
    # SQLite allows, then reconnecting through the migration path.
    conn = sqlite3.connect(str(db))
    for col in ("raw_prob", "cal_temp", "cal_bias"):
        conn.execute(f"ALTER TABLE bets DROP COLUMN {col}")
    conn.commit()
    conn.close()
    conn = ledger.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
    assert {"raw_prob", "cal_temp", "cal_bias"} <= cols


# --- why the capture exists ------------------------------------------------
def _distorted_sample(k, n=6000, seed=11):
    """(stated, outcome) pairs from a model over-confident by temperature k."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        true_p = rnd.uniform(0.08, 0.92)
        # Stated odds are the true odds raised to k, so a k above 1 states
        # a MORE extreme probability than the outcomes support — and the
        # temperature that repairs it is k itself.
        odds = (true_p / (1 - true_p)) ** k
        out.append((odds / (1 + odds), 1 if rnd.random() < true_p else 0))
    return out


def test_refitting_on_corrected_claims_destroys_the_correction():
    """The reason a fitted market is frozen — measured, not asserted."""
    raw = _distorted_sample(1.7)
    first = cal.fit_temperature(raw, min_samples=200)
    assert 1.5 < first < 1.9, first          # recovers the real distortion

    # That correction ships. Every later pick states the CORRECTED number.
    after = [(cal.apply_temperature(p, first), o) for p, o in raw]
    naive = cal.fit_temperature(after, min_samples=200)
    # Those claims are already calibrated, so the fit says "no correction
    # needed" — and journalfit STORES, it does not compose, so storing this
    # would replace a working 1.7 with a 1.0 and undo the whole fit.
    assert abs(naive - 1.0) < 0.12, naive

    # Un-correct each row by the correction it was priced under, and the
    # same fitter lands back on the same answer. This is what the journal's
    # raw_prob + cal_temp + cal_bias columns make possible.
    undone = [(cal.undo_temperature(p, first), o) for p, o in after]
    honest = cal.fit_temperature(undone, min_samples=200)
    assert abs(honest - first) < 1e-6, (honest, first)


def test_nothing_unfroze_a_market():
    """journalfit still owns-and-skips. The capture changed no behaviour."""
    import inspect

    from engine import journalfit
    src = inspect.getsource(journalfit.fit_temperatures)
    assert "if key in stored:" in src
    assert 'out["owned"].append' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
