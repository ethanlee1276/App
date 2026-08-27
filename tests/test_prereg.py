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


# --- the NFL A-band registration ---------------------------------------------
def test_the_nfl_a_band_claim_is_registered():
    """Found 2026-08-27: the elite prop band landed worse than the band
    below it in all four ingested seasons. Registered rather than acted
    on — see the next test for why that is not timidity."""
    from engine import prereg
    import tempfile
    store = prereg.ensure_registered(
        os.path.join(tempfile.mkdtemp(), "prereg.json"))
    ids = {t["id"] for t in store["tests"]}
    assert "a-band-nfl-props-2026-08" in ids
    assert "bplus-props-2026-08" in ids, "registering one must not drop the other"


def test_the_new_claim_did_not_get_an_easier_bar_than_the_old_one():
    """B_MINUS was registered forward at z = 2.1 because 2.1 was not
    enough to convict a bucket chosen after looking. The NFL finding
    reads 1.89. Acting on the weaker one would be applying a lower
    standard to a finding because it is mine."""
    from engine.prereg import A_BAND_NFL, B_MINUS
    assert A_BAND_NFL["min_n"] >= B_MINUS["min_n"]
    assert "1.89" in A_BAND_NFL["why_now"]
    assert "2.1" in A_BAND_NFL["why_now"]


def test_the_claim_names_what_it_would_change():
    """A registration that decides nothing is a note. This one moves a
    stake cap, which is money."""
    from engine.prereg import A_BAND_NFL
    assert "STAKE_CAP_U" in A_BAND_NFL["decides"]


def test_the_two_registrations_point_opposite_ways_on_purpose():
    """B+ is the bad bucket in MLB and the good one in NFL. Two sports
    disagreeing argues against a universal law about grade bands — and
    for measuring each sport on its own record."""
    from engine.prereg import A_BAND_NFL, B_MINUS
    assert B_MINUS["population"] == ["B+"] and "B+" in A_BAND_NFL["compare_to"]
    assert A_BAND_NFL["population"] == ["A"]
    assert A_BAND_NFL["sport"] != B_MINUS["sport"]


# --- a test scoped to one market --------------------------------------
#
# "Why does B+ beat A" turned out to be one cell: A-graded RECEPTIONS at
# 40.7% over 86 bets, against B+ receptions at 60.3% over 199. Take that
# cell out and the A band lands 54.7% — no finding at all. A test about
# one market has to be able to say so.

def test_a_market_scoped_test_only_counts_that_market():
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "prereg.json")
    prereg.register(prereg.RECEPTIONS_A_NFL, path)
    rows = [{"date": "2099-01-01", "sport": "nfl", "grade": "A",
             "market": m, "odds": -110, "status": "lost"}
            for m in ("receptions",) * 3 + ("rush_yds",) * 40]
    v = next(x for x in prereg.report(rows, path)
             if x["id"] == "a-receptions-nfl-2026-08")
    assert v["n"] == 3, v


def test_the_market_filter_applies_to_the_reference_too():
    """Comparing A-receptions against every B+ prop would dilute the
    comparison with three markets the finding is not about."""
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "prereg.json")
    prereg.register(prereg.RECEPTIONS_A_NFL, path)
    rows = [{"date": "2099-01-01", "sport": "nfl", "grade": "B+",
             "market": m, "odds": -110, "status": "won"}
            for m in ("receptions",) * 5 + ("rec_yds",) * 50]
    v = next(x for x in prereg.report(rows, path)
             if x["id"] == "a-receptions-nfl-2026-08")
    assert v["n_reference"] == 5, v


def test_adding_the_market_field_did_not_void_the_older_tests():
    """`_terms_hash` keys only on the fields a test actually carries, so
    a filter no existing test uses cannot change their fingerprints. A
    voided preregistration reports nothing, which would have quietly
    thrown away both standing tests."""
    for test in (prereg.B_MINUS, prereg.A_BAND_NFL):
        assert "markets" not in test
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "prereg.json")
    store = prereg.ensure_registered(path)
    assert len(store["tests"]) == 3
    for v in prereg.report([], path):
        assert v["status"] != "void", v


def test_the_receptions_remedy_names_a_lever_that_moves():
    """A preregistration whose remedy points at a retired constant fires
    and changes nothing. This one names the 40-point edge component of
    the quality score, which is what decides the grade."""
    from engine import quality
    import inspect
    decides = prereg.RECEPTIONS_A_NFL["decides"]
    assert "edge_pts" in decides and "TIER_MIN_EDGE" not in decides
    source = inspect.getsource(quality.quality_score)
    assert "edge_pts" in source
    assert "TIER_MIN_EDGE[tier]" in source


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
