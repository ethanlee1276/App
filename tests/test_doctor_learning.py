"""Is the learning ladder recording, and has it learned anything?

Four rungs run off the journal — the blind-spot miner, the recency dial,
the per-player memory and the hypothesis lab — and every one is silent
when it has nothing to say. Silence is indistinguishable from "never wired
up", which is the failure worth catching: a ladder that quietly stopped
being fed looks exactly like a ladder with no findings yet.

So the check reports the two halves separately. INPUT is whether the
journal carries the circumstance dimensions the rungs band; a pick logged
without them can never be convicted of anything. OUTPUT is whether any
rung has fitted a number or convicted a pocket. Input without output is
normal and early. Input going to zero after it was non-zero is a broken
pipeline, and that is what this exists to surface.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import doctor                                              # noqa: E402
from engine import ledger                                  # noqa: E402

DIMS = ("lead_min", "park_hr", "wind_out", "lineup_slot", "rest_days",
        "body_clock", "pen_own", "pen_opp", "loss_cause")


def _journal(**cols):
    """A one-pick journal with the named dimensions filled in."""
    path = os.path.join(tempfile.mkdtemp(), "l.db")
    orig = ledger.connect
    conn = orig(path)
    keys = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        f" hit_prob, stake_units, status, category{', ' + keys if cols else ''})"
        " VALUES ('t','mlb','2026-08-01','X','outs','OVER',16.5,-110,"
        f"0.56,1.0,'lost','main'{', ' + marks if cols else ''})",
        tuple(cols.values()))
    conn.commit()
    return path, orig


def _run(path, orig):
    ledger.connect = lambda *a, **k: orig(path)
    had = doctor.has_journal
    doctor.has_journal = lambda: True
    try:
        rep = doctor.Report()
        doctor.check_learning(rep)
        return rep.checks[0]
    finally:
        ledger.connect = orig
        doctor.has_journal = had


def test_a_dimension_that_is_always_null_is_reported_not_averaged_away():
    """The failure mode: one pipeline stops journaling its dimension, the
    overall count still looks healthy, and the miner silently loses a
    column it can never convict on again."""
    path, orig = _journal(pen_own=12.0, rest_days=6, loss_cause="blowout")
    row = _run(path, orig)
    assert row["status"] == doctor.WARN, row
    assert "always-NULL" in row["fix"]
    for dead in ("park_hr", "wind_out", "lineup_slot", "body_clock"):
        assert dead in row["fix"], dead
    # And the ones that ARE carrying data are not named as dead.
    for live in ("pen_own", "rest_days", "loss_cause"):
        assert live not in row["fix"], live


def test_a_fully_journaled_pick_is_green():
    path, orig = _journal(**{d: (1.0 if d != "loss_cause" else "blowout")
                             for d in DIMS})
    row = _run(path, orig)
    assert row["status"] == doctor.OK, row
    assert "9/9 mineable dimensions" in row["detail"], row["detail"]


def test_it_separates_recording_from_having_learned():
    """Both halves get said out loud. A ladder that is recording but has
    convicted nothing is early, not broken — and reporting only the second
    half would make a healthy young journal look dead."""
    path, orig = _journal(**{d: (1.0 if d != "loss_cause" else "blowout")
                             for d in DIMS})
    row = _run(path, orig)
    assert "journaled picks" in row["detail"]
    assert "no rung has convicted anything yet" in row["detail"], row["detail"]


def test_an_empty_journal_is_not_a_failure():
    path = os.path.join(tempfile.mkdtemp(), "l.db")
    orig = ledger.connect
    orig(path)                       # creates the schema, inserts nothing
    row = _run(path, orig)
    assert row["status"] == doctor.OK
    assert "nothing to learn from yet" in row["detail"]


def test_the_check_is_registered_and_marked_as_needing_the_laptop():
    """It reads the journal, so on CI or a fresh clone it must say "not my
    machine" rather than going red."""
    assert doctor.check_learning in doctor.CHECKS
    assert doctor.check_learning in doctor.DATA_CHECKS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
