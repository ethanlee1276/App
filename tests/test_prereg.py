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
    # NOT a hardcoded count. This asserted `== 3`, which is a fact about
    # how many tests happen to be registered rather than about the thing
    # under test, and it broke the next time one was added. What matters
    # is that the older tests survived the new field.
    ids = {t["id"] for t in store["tests"]}
    assert {prereg.B_MINUS["id"], prereg.A_BAND_NFL["id"]} <= ids
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


# --- superseding, without editing -------------------------------------

def _store():
    import tempfile, os
    return os.path.join(tempfile.mkdtemp(), "prereg.json")


def test_a_superseded_test_says_what_replaced_it_and_stops_collecting():
    path = _store()
    prereg.ensure_registered(path)
    v = next(x for x in prereg.report([], path)
             if x["id"] == "a-band-nfl-props-2026-08")
    assert v["status"] == "superseded"
    assert v["superseded_by"] == "a-receptions-nfl-2026-08"
    assert "STAKE_CAP_U" in v["reading"]


def test_superseding_does_not_edit_the_frozen_terms():
    """The hash is the whole protection. A supersession that voided the
    test would destroy the record of what was originally asked, which is
    the one thing a preregistration is for."""
    import json
    path = _store()
    prereg.ensure_registered(path)
    stored = json.load(open(path))
    t = next(x for x in stored["tests"] if x["id"] == "a-band-nfl-props-2026-08")
    assert t["hash"] == prereg._terms_hash(t)
    assert t["decides"] == prereg.A_BAND_NFL["decides"]


def test_an_edited_test_is_still_void_even_once_superseded():
    """Void outranks superseded: terms that moved report nothing at all,
    whatever else was recorded beside them."""
    import json
    path = _store()
    prereg.ensure_registered(path)
    stored = json.load(open(path))
    for t in stored["tests"]:
        if t["id"] == "a-band-nfl-props-2026-08":
            t["min_n"] = 3
    prereg.save(stored, path)
    v = next(x for x in prereg.report([], path)
             if x["id"] == "a-band-nfl-props-2026-08")
    assert v["status"] == "void"


def test_superseding_is_idempotent_and_refuses_an_unknown_id():
    path = _store()
    prereg.ensure_registered(path)
    prereg.supersede("a-band-nfl-props-2026-08", "a-receptions-nfl-2026-08",
                     "same reason", path)
    raised = False
    try:
        prereg.supersede("no-such-test", "x", "y", path)
    except KeyError:
        raised = True
    assert raised


# --- the touchdown board's registration (2026-08-28) ------------------------
def _td_test(tmp):
    """The LIVE touchdown test, whichever it currently is.

    `td-edge-nfl-2026-08` was superseded when engine/touchdowns began
    blending the share toward a player's xFP share of his offence — a
    preregistration asks about one model, and that model changed. These
    tests are about the category filter, which is a live concern for
    whichever test is collecting, so they follow the successor rather
    than pinning a retired id."""
    import json
    prereg.ensure_registered(tmp)
    by_id = {t["id"]: t for t in json.loads(open(tmp).read())["tests"]}
    live = [t for t in by_id.values()
            if t["id"].startswith("td-edge-nfl")
            and not t.get("superseded_by")]
    assert len(live) == 1, f"expected one live TD test, got {live}"
    return live[0]


def _td_rows(n, wins=0, grade="Lean", market="anytime_td",
             category="longshot"):
    """Scorer-board rows as the journal really writes them: the long-shot
    bucket, not the headline record."""
    return [{"date": "2026-12-01", "grade": grade, "sport": "nfl",
             "odds": 300, "market": market, "category": category,
             "status": "won" if i < wins else "lost"} for i in range(n)]


def test_the_touchdown_test_is_registered():
    import os, tempfile
    t = _td_test(os.path.join(tempfile.mkdtemp(), "p.json"))
    assert t["min_n"] == 120
    assert t["markets"] == ["anytime_td"]


def test_it_populates_from_the_longshot_ladder_not_the_prop_one():
    """`quality.letter` returns A+/A/B+ and `longshots._grade` returns
    Strong Play/Play/Lean. A test populated with the wrong ladder
    collects nothing forever while looking healthy."""
    import os, tempfile
    from engine.longshots import _grade
    t = _td_test(os.path.join(tempfile.mkdtemp(), "p.json"))
    assert set(t["population"]) == {"Strong Play", "Play", "Lean"}
    emitted = {_grade(c, e) for c in (4.6, 6.1, 7.6) for e in (0.02, 0.04, 0.06)}
    assert emitted - {"Pass"} <= set(t["population"])


def test_a_prop_graded_A_does_not_count_toward_it():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    assert prereg.verdict(t, _td_rows(200, 20, grade="A"))["n"] == 0


def test_another_market_does_not_count_toward_it():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    assert prereg.verdict(t, _td_rows(200, 20, market="rec_yds"))["n"] == 0


def test_with_no_comparison_band_it_is_a_test_against_break_even():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    assert t["compare_to"] == []
    v = prereg.verdict(t, _td_rows(120, 6))
    assert v["status"] == "decided" and v["supported"]
    assert "break-even" in v["reading"]


def test_a_profitable_sample_does_not_support_the_claim():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    v = prereg.verdict(t, _td_rows(120, 40))          # 40/120 at +300 profits
    assert v["roi"] > 0 and not v["supported"]


def test_it_says_nothing_before_the_sample_arrives():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    assert prereg.verdict(t, _td_rows(119, 6))["status"] == "collecting"


def test_zero_variance_is_not_reported_as_zero_evidence():
    """`se` is 0 only when every bet returned the same thing, and
    `z = 0.0` then reports the strongest possible result as the weakest.
    A one-sample test reaches that the moment a whole sample loses —
    which is the case it was registered to catch."""
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    v = prereg.verdict(t, _td_rows(120, 0))
    assert v["degenerate"] and v["supported"]
    assert "no spread" in v["reading"]


def test_the_touchdown_test_reads_the_bucket_it_is_journaled_in():
    """The scorer board journals to `category='longshot'` — a
    measurement-only bucket, deliberately never mixed into the headline
    record — and both prereg feeds selected main/paper only. The test
    would have sat at "0 of 120" forever while looking perfectly
    healthy: registered, and unable to collect."""
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    assert t["categories"] == ["longshot"]
    rows = _td_rows(120, 6)
    assert prereg.verdict(t, rows)["n"] == 120


def test_a_headline_bet_does_not_count_toward_the_touchdown_test():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    rows = [dict(r, category="main") for r in _td_rows(120, 6)]
    assert prereg.verdict(t, rows)["n"] == 0


def test_the_older_tests_still_read_the_headline_record_only():
    """Adding a per-test bucket must not change what an existing test
    sees, and `_terms_hash` keys only on fields a test carries, so their
    fingerprints are untouched."""
    import os, tempfile, json
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    prereg.ensure_registered(tmp)
    r = {t["id"]: t for t in
         json.loads(open(tmp).read())["tests"]}["a-receptions-nfl-2026-08"]
    assert "categories" not in prereg.RECEPTIONS_A_NFL
    main = [{"date": "2026-12-01", "grade": "A", "sport": "nfl", "odds": -110,
             "status": "lost", "market": "receptions", "category": "main"}
            for _ in range(90)]
    assert prereg.verdict(r, main)["n"] == 90
    assert prereg.verdict(
        r, [dict(x, category="longshot") for x in main])["n"] == 0
    for v in prereg.report([], tmp):
        assert v["status"] != "void", v


def test_a_row_with_no_category_is_treated_as_the_headline_record():
    """Older journal rows and hand-built fixtures carry no category."""
    import os, tempfile, json
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    prereg.ensure_registered(tmp)
    r = {t["id"]: t for t in
         json.loads(open(tmp).read())["tests"]}["a-receptions-nfl-2026-08"]
    rows = [{"date": "2026-12-01", "grade": "A", "sport": "nfl", "odds": -110,
             "status": "lost", "market": "receptions"} for _ in range(90)]
    assert prereg.verdict(r, rows)["n"] == 90


def test_one_query_shape_serves_both_callers():
    """`ledger.prereg_status` selected `market` and launch.py's report did
    not, so on the CLI path every market-scoped test filtered its entire
    population away and reported "0 of 80" forever."""
    import inspect, os
    from engine import ledger
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "launch.py"), encoding="utf-8") as fh:
        launch_src = fh.read()
    assert "prereg.rows_for(conn)" in launch_src
    assert "prereg.rows_for(conn)" in inspect.getsource(ledger._prereg_block)
    for col in ("market", "category", "grade", "odds", "status", "date"):
        assert col in prereg.ROW_SQL, col
    assert "longshot" in prereg.ROW_SQL,         "the scorer board's bucket must reach the tests scoped to it"


def test_a_sample_with_spread_still_uses_the_z():
    import os, tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "p.json")
    t = _td_test(tmp)
    v = prereg.verdict(t, _td_rows(120, 6))
    assert not v["degenerate"] and v["z"] < -2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
