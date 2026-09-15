"""A met bar has to actually lift the gate.

Three modules publish a promotion bar and none of them could reach it.
`engine.parlayledger` computes all four of §13's conditions — a hundred
graded tickets, positive flat-stake ROI, aggregate leg CLV at or above
zero, z of at least two — and `launch.py` prints them PASS by PASS,
while the same dict returns ``"probation": True`` as a literal.
`engine.hoops.LeagueTuning.calibrated` was a literal too, so the
coverage page's "grades accumulate automatically; the bar lifts itself"
was never true.

Same disease as the stake gate found the same week, running the other
way: that one DID something it said it would not, and this REFUSED to do
something it said it would. A model that has earned its promotion and
cannot receive it is a learning loop with the last link missing.

What it deliberately is not is automatic. Every other fitter here adopts
on its own because the worst case is a slightly wrong price; the worst
case here is money at risk that was not at risk before.

Run directly: `python3 tests/test_promotion.py`
"""

import contextlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import promotion as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MET = {"tickets": True, "roi": True, "clv": True, "z": True}
SHORT = {"tickets": True, "roi": False, "clv": True, "z": False}


@contextlib.contextmanager
def sandbox():
    keep, keep_cache = P.STATE_PATH, dict(P._cache)
    P.STATE_PATH = os.path.join(tempfile.mkdtemp(), "promotion.json")
    P._cache.clear()
    try:
        yield P.STATE_PATH
    finally:
        P.STATE_PATH = keep
        P._cache.clear()
        P._cache.update(keep_cache)


# --- the bar ------------------------------------------------------------------
def test_every_condition_must_hold():
    assert P.bar_met(MET) is True
    assert P.bar_met(SHORT) is False


def test_an_empty_set_of_conditions_is_not_a_met_bar():
    """A promotion with no conditions behind it is the thing this module
    exists to stop."""
    assert P.bar_met({}) is False
    assert P.bar_met(None) is False


def test_a_bar_says_which_test_failed():
    assert P.failing(SHORT) == ["roi", "z"]
    assert P.failing(MET) == []


# --- promoting ----------------------------------------------------------------
def test_promotion_is_refused_until_the_bar_is_met():
    with sandbox():
        try:
            P.promote("wnba", conditions=SHORT)
        except ValueError as exc:
            assert "roi" in str(exc) and "z" in str(exc)
        else:
            raise AssertionError("promoted a model that had not earned it")
        assert P.promoted("wnba") is False


def test_a_met_bar_can_be_promoted_and_the_evidence_is_kept():
    with sandbox():
        P.promote("wnba", conditions=MET, evidence={"graded": 140})
        assert P.promoted("wnba") is True
        rec = P.record("wnba")
        assert rec["evidence"]["graded"] == 140
        assert rec["conditions"] == MET
        assert rec["at"] > 0
        assert rec["forced"] is False


def test_a_forced_promotion_is_recorded_as_forced():
    """A promotion nobody can audit is the same as one nobody measured."""
    with sandbox():
        P.promote("wnba", conditions=SHORT, force=True)
        assert P.promoted("wnba") is True
        assert P.record("wnba")["forced"] is True


def test_a_promotion_with_no_conditions_offered_is_not_second_guessed():
    """Some gates have no computable bar. Passing none is a caller saying
    so, and is recorded — it is not silently treated as a met bar."""
    with sandbox():
        P.promote("ufc", evidence={"why": "reviewed by hand"})
        assert P.promoted("ufc") is True
        assert P.record("ufc")["conditions"] == {}


# --- demoting -----------------------------------------------------------------
def test_demotion_needs_no_bar():
    """Withdrawing risk must never be harder than taking it."""
    with sandbox():
        P.promote("wnba", conditions=MET)
        P.demote("wnba", "the sample was one hot month")
        assert P.promoted("wnba") is False
        assert P.record("wnba")["why"] == "the sample was one hot month"


def test_a_demotion_remembers_when_the_promotion_was():
    with sandbox():
        P.promote("wnba", conditions=MET)
        was = P.record("wnba")["at"]
        P.demote("wnba")
        assert P.record("wnba")["was"] == was


# --- the safe direction -------------------------------------------------------
def test_an_unreadable_state_withholds_risk_rather_than_taking_it():
    with sandbox() as path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        P._cache.clear()
        assert P.promoted("wnba") is False


def test_a_corrupt_entry_is_not_a_promotion():
    with sandbox():
        P._write({"wnba": "yes please"})
        P._cache.clear()
        assert P.promoted("wnba") is False


def test_an_unknown_key_is_never_promoted():
    with sandbox():
        assert P.promoted("quidditch") is False


# --- the gate reads the record ------------------------------------------------
def test_the_hoops_gate_reads_the_record_not_the_literal():
    from engine.hoops import WNBA
    with sandbox():
        assert WNBA.probation is True
        P.promote("wnba", conditions=MET)
        assert WNBA.probation is False
        P.demote("wnba", "withdrawn")
        assert WNBA.probation is True


def test_a_source_calibrated_league_is_the_floor():
    """NBA's numbers were fitted against its own results before any of
    this existed; a missing record must not put it back on probation."""
    from engine.hoops import NBA
    with sandbox():
        assert NBA.calibrated is True
        assert NBA.probation is False


def test_the_gate_survives_a_broken_promotion_module():
    from engine import hoops
    from engine.hoops import WNBA
    keep = P.promoted
    P.promoted = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    try:
        assert WNBA.probation is True      # withholds, does not take
    finally:
        P.promoted = keep


# --- what the reader is told ---------------------------------------------------
def test_a_met_but_unpromoted_bar_says_it_is_waiting_on_a_person():
    """The state that must never sit quietly: nothing is stopping it and
    the only reason it is still on probation is that no one looked."""
    with sandbox():
        note = P.note("parlays", MET)
        assert "waiting on a person" in note
        st = P.status("parlays", MET)
        assert st["awaiting"] is True and st["promoted"] is False


def test_a_promoted_model_says_so():
    with sandbox():
        P.promote("parlays", conditions=MET)
        assert "promoted" in P.note("parlays", MET)
        assert P.status("parlays", MET)["awaiting"] is False


def test_a_short_bar_names_what_is_missing():
    with sandbox():
        assert "roi" in P.note("parlays", SHORT)


def test_the_health_check_watches_for_a_met_unacted_bar():
    src = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()
    assert 'promotion.status("parlays"' in src
    assert 'st["awaiting"]' in src


def test_the_coverage_page_no_longer_claims_the_bar_lifts_itself():
    src = open(os.path.join(ROOT, "engine", "coverage.py"),
               encoding="utf-8").read()
    # Comments stripped: the module's own note QUOTES the old wording to
    # record what was wrong with it, which is the opposite of shipping it.
    shipped = "\n".join(l for l in src.splitlines()
                        if not l.lstrip().startswith("#"))
    assert "the bar lifts itself" not in shipped
    assert "engine/promotion" in shipped


# --- the command a person actually runs ----------------------------------------
def test_the_bar_is_recomputed_from_the_record_not_taken_on_trust():
    """The CLI refuses on LIVE evidence rather than on whatever a caller
    hands it — otherwise "promote" would be a way to skip the bar."""
    src = open(os.path.join(ROOT, "engine", "promotion.py"),
               encoding="utf-8").read()
    assert "def conditions_for(" in src
    block = src[src.index('if argv and argv[0] == "promote"'):]
    assert "conditions_for(key)" in block[:400]


def test_an_unmeasurable_bar_is_not_a_met_bar():
    """A box with no journal cannot answer the question, and "I could not
    measure it" must never read as "the bar is met"."""
    assert P.conditions_for("quidditch") is None
    assert P.bar_met(P.conditions_for("quidditch") or {}) is False


def test_the_parlay_conditions_map_to_the_ledgers_own_report():
    """If these keys drift from parlayledger's, the bar silently reads
    missing conditions as failing forever."""
    src = open(os.path.join(ROOT, "engine", "parlayledger.py"),
               encoding="utf-8").read()
    for field in ("tickets_have", "tickets_required", "roi_positive",
                  "clv_non_negative", "z_clears"):
        assert f'"{field}"' in src, field


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
