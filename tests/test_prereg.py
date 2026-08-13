"""Preregistered tests: the terms are frozen and the sample is honest.

Ethan, 2026-08-13, after `gradecheck` declined to convict the B+ bucket:
"yeah do that, wire it into the lab."

WHY THIS EXISTS AT ALL. B+ props read -24.4% over 95 settled bets while
A+ and A were statistically identical to each other. `gradecheck` would
not convict it — testing six buckets and picking the worst needs about
|z| > 2.6 and this was 2.1. Registering it forward is how that evidence
gets earned instead of assumed.

Every test here pins a property that, if it broke, would silently turn
this back into the thing it was built to replace: a number somebody
watched until it said what they wanted.
"""

import datetime
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import prereg                                   # noqa: E402


def _t(**kw):
    t = dict(prereg.B_MINUS, registered="2026-08-13", z_threshold=1.96)
    t.update(kw)
    t["hash"] = prereg._terms_hash(t)
    return t


def _rows(n_pop, pop_wins, n_ref, ref_wins, date="2026-09-01", grade="B+"):
    out = [{"date": date, "sport": "mlb", "grade": grade, "odds": -110,
            "status": "won" if i < pop_wins else "lost"} for i in range(n_pop)]
    out += [{"date": date, "sport": "mlb", "grade": "A", "odds": -110,
             "status": "won" if i < ref_wins else "lost"} for i in range(n_ref)]
    return out


def test_the_bets_that_suggested_the_idea_cannot_test_it():
    """THE property. B+ was chosen BECAUSE 95 settled bets read -24.4%.
    Scoring those same 95 would be asking one sample twice and calling
    the second answer confirmation. Only bets dated strictly after the
    registration count."""
    old = _rows(200, 20, 200, 140, date="2026-08-01")      # before it
    v = prereg.verdict(_t(), old)
    assert v["n"] == 0, "pre-registration bets leaked into the test"
    assert v["status"] == "collecting"
    # Same day as registration is also excluded: those bets existed when
    # the idea did.
    same = _rows(200, 20, 200, 140, date="2026-08-13")
    assert prereg.verdict(_t(), same)["n"] == 0


def test_it_reports_progress_not_a_running_result():
    """Watching a total and calling it the moment it crosses a line is
    sequential testing, and it finds significance in pure noise given
    enough looks. Before min_n the only honest output is how far along
    it is — and crucially, NO verdict field to misread."""
    v = prereg.verdict(_t(), _rows(60, 5, 60, 40))
    assert v["status"] == "collecting"
    assert "supported" not in v, "a collecting test must not carry a verdict"
    assert "roi" not in v, "a collecting test must not publish a number"
    assert "60 of 100" in v["reading"]


def test_at_the_named_sample_it_decides_both_ways():
    big_gap = prereg.verdict(_t(), _rows(120, 30, 120, 70))
    assert big_gap["status"] == "decided" and big_gap["supported"] is True
    assert big_gap["z"] < -1.96
    none = prereg.verdict(_t(), _rows(120, 55, 120, 57))
    assert none["status"] == "decided" and none["supported"] is False
    assert "nothing changes and the bucket stays" in none["reading"]


def test_moving_the_goalposts_voids_the_test():
    """The failure mode preregistration exists to prevent, made
    mechanical. Lowering min_n after seeing the data would otherwise
    turn a null into a finding, silently."""
    moved = dict(_t(), min_n=10)          # hash now stale
    v = prereg.verdict(moved, _rows(120, 30, 120, 70))
    assert v["status"] == "void"
    assert "terms changed" in v["reading"]
    assert "supported" not in v


def test_registering_again_cannot_overwrite_the_original():
    """The first registration is the one that counts. A silent overwrite
    would erase the very record being protected."""
    path = os.path.join(tempfile.mkdtemp(), "p.json")
    prereg.register(dict(prereg.B_MINUS, registered="2026-08-13"), path)
    prereg.register(dict(prereg.B_MINUS, registered="2030-01-01", min_n=5), path)
    tests = prereg.load(path)["tests"]
    assert len(tests) == 1
    assert tests[0]["registered"] == "2026-08-13" and tests[0]["min_n"] == 100


def test_the_metric_is_flat_staked_so_sizing_cannot_confound_it():
    """The question is which BUCKET wins. Leaving stake size in would let
    a sizing policy answer it — the same reason gradecheck flat-stakes."""
    assert prereg._flat_profit({"status": "won", "odds": 180}) == 1.8
    assert prereg._flat_profit({"status": "lost", "odds": 180}) == -1.0
    assert abs(prereg._flat_profit({"status": "won", "odds": -110})
               - 100 / 110) < 1e-9


def test_the_registration_records_why_it_was_not_acted_on_immediately():
    """A preregistration whose reasoning is lost is a note. The stored
    terms have to carry the number that was NOT enough."""
    assert "2.1" in prereg.B_MINUS["why_now"] or "z=2.1" in prereg.B_MINUS["why_now"]
    assert prereg.B_MINUS["decides"], "a test with no decision is an observation"
    assert prereg.B_MINUS["min_n"] >= 100


def test_the_lab_page_shows_progress_without_a_number():
    """The page must not let a collecting test look like a finding —
    that is the whole point, and it is a rendering decision as much as a
    statistical one."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    fn = app[app.index("function recPrereg("):app.index("function recHypothesisLab(")]
    assert 'status === "collecting"' in fn
    assert "pr-prog" in fn and "t.min_n" in fn
    # A collecting branch that printed roi would defeat it.
    coll = fn[fn.index('status === "collecting"'):fn.index("const tone")]
    assert "roi" not in coll and "%" not in coll.replace("${pct}%", "")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
