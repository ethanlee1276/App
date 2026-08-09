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


def _run(path, orig, stores=None):
    """Run the check against a temp journal AND empty rung stores.

    The stores matter as much as the journal. The first version of this
    read the machine's REAL formfit/playerfit/hypotheses files, so it
    passed on a fresh clone and failed on the laptop that had actually
    learned something — the same mistake test_prose.py made when it
    reached for the live hypothesis store and fell through to a paid API
    call. A test whose verdict depends on how much the owner has bet is
    not testing the code.
    """
    from engine import losspatterns as lp, formfit, playerfit, hypotheses
    stores = stores or {}
    saved = (lp.load, formfit._load, playerfit._load, hypotheses.load)
    lp.load = lambda *a, **k: stores.get("miner", {})
    formfit._load = lambda *a, **k: stores.get("formfit", {})
    playerfit._load = lambda *a, **k: stores.get("playerfit", {})
    hypotheses.load = lambda *a, **k: stores.get("lab", {})
    ledger.connect = lambda *a, **k: orig(path)
    had = doctor.has_journal
    doctor.has_journal = lambda: True
    try:
        rep = doctor.Report()
        doctor.check_learning(rep)
        return rep.checks[0]
    finally:
        (lp.load, formfit._load, playerfit._load, hypotheses.load) = saved
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
    # `body_clock` is NOT in this list any more, and the omission is the
    # point — see the seasonal test below. The journal here is one `mlb`
    # bet, and body_clock is only ever computed for nfl/cfb.
    for dead in ("park_hr", "wind_out", "lineup_slot"):
        assert dead in row["fix"], dead
    # And the ones that ARE carrying data are not named as dead.
    for live in ("pen_own", "rest_days", "loss_cause"):
        assert live not in row["fix"], live


def test_a_football_only_dimension_is_not_a_fault_on_a_baseball_journal():
    """`betting.py` computes rest_days/body_clock under
    `if sport in ("nfl", "cfb")` — schedule fatigue is a football idea,
    and MLB's own spec parks it for want of a feed.

    On Ethan's journal, which is almost entirely baseball, the doctor
    reported "those pipelines are not journaling their dimension, so the
    miner can never convict on it". That reads as a broken pipeline and a
    task marked complete that was not. Neither was true: the sports that
    fill the column have barely bet yet.

    A warning implying a bug where there is none is how you learn to skip
    warnings."""
    path, orig = _journal(pen_own=12.0, pen_opp=9.0, park_hr=1.1,
                          wind_out=4.0, lineup_slot=3, lead_min=95.0,
                          loss_cause="blowout")
    row = _run(path, orig)
    assert row["status"] == doctor.OK, row
    assert "waits on NFL/CFB" in (row.get("detail") or "")
    assert "by season, not by fault" in (row.get("detail") or "")


def test_a_football_dimension_IS_a_fault_once_football_has_bet():
    """The exemption must be narrow. Once an nfl or cfb pick exists and
    the column is still empty, the pipeline really has stopped journaling
    it — which is the fault the original check was written to catch."""
    path, orig = _journal(pen_own=12.0, pen_opp=9.0, park_hr=1.1,
                          wind_out=4.0, lineup_slot=3, lead_min=95.0,
                          loss_cause="blowout")
    conn = orig(path)
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " hit_prob, stake_units, status, category) VALUES "
        "('t','nfl','2026-09-10','Y','rush_yds','OVER',40.5,-110,"
        "0.55,1.0,'lost','main')")
    conn.commit()
    conn.close()
    row = _run(path, orig)
    assert row["status"] == doctor.WARN, row
    assert "rest_days" in row["fix"] and "body_clock" in row["fix"]


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


def test_a_rung_that_has_learned_something_is_named():
    path, orig = _journal(**{d: (1.0 if d != "loss_cause" else "blowout")
                             for d in DIMS})
    row = _run(path, orig, stores={
        "miner": {"findings": [{"dim": "park_hr"}], "closed": [{"dim": "slot"}]},
        "formfit": {"mlb|hits": {"r": 0.4}, "nfl|rec_yds": {"r": 0.2}},
        "lab": {"hypotheses": [{"id": 1}], "watchlist": ["a", "b"]}})
    assert row["status"] == doctor.OK, row
    assert "miner: 1 open, 1 convicted" in row["detail"], row["detail"]
    assert "recency dial: 2 fitted" in row["detail"], row["detail"]
    assert "hypothesis lab: 1 live, 2 watched" in row["detail"], row["detail"]
    assert "no rung has convicted" not in row["detail"]


def test_a_store_that_cannot_be_read_is_reported_not_swallowed():
    """THE bug this check shipped with for one commit. It called `load` on
    every rung; formfit and playerfit expose `_load`, so the getattr
    raised, a bare except ate it, and the check announced "no rung has
    convicted anything yet" on a laptop where two rungs were full.

    Silence looking like health is the exact failure this check exists to
    catch, so it is not allowed to commit it."""
    from engine import formfit

    def boom(*a, **k):
        raise AttributeError("no such loader")

    path, orig = _journal(**{d: (1.0 if d != "loss_cause" else "blowout")
                             for d in DIMS})
    saved = formfit._load
    formfit._load = boom
    try:
        # _run re-patches, so break it from inside the stores instead.
        row = _run(path, orig)
        clean = row["status"]
    finally:
        formfit._load = saved
    assert clean == doctor.OK          # patched stores are readable
    # And with a genuinely broken loader the check must warn, not go quiet.
    rep = doctor.Report()
    ledger.connect = lambda *a, **k: orig(path)
    had, hl = doctor.has_journal, formfit._load
    doctor.has_journal = lambda: True
    formfit._load = boom
    try:
        doctor.check_learning(rep)
    finally:
        ledger.connect, doctor.has_journal, formfit._load = orig, had, hl
    row = rep.checks[0]
    assert row["status"] == doctor.WARN, row
    assert "could not read" in row["fix"], row["fix"]
    assert "recency dial" in row["fix"], row["fix"]


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
