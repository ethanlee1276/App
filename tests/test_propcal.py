"""A calibration fitted against the wrong opponent.

`calibrate.py` fits every prop market through `engine.logwalk`, which
prices each game against a PROXY line — the player's trailing average,
shaded half a point down, at a synthetic -110. The correction it learns
is "how wrong is the model about a trailing average", and it is applied
live to decisions priced against a real book. Different questions.

Yardage is right-skewed, so a line near the recent MEAN sits above the
MEDIAN. Measured over 2,626 settled 2025 props with the model ignored:

    rec_yds     59.0% under        pass_yds    53.4% under
    rush_yds    57.4% under        receptions  36.9% under

And the curves fitted from it, read off the droplet:

    rec_yds     ceiling 0.470      pass_yds    no curve
    rush_yds    ceiling 0.402      receptions  ceiling 0.788

Rank for rank. The two whose ceiling fell below 0.5 are exactly the two
that skewed under hardest — and a correction that cannot exceed 0.470
can never call an over more likely than not, so those markets could only
ever be bet one way. That is the card Ethan found: UNDER 58.5 on a
player projected for 71.6.

`engine.propcal` fits the same markets on the BOOK-priced subset of the
walk-forward, which asks the question the live board asks.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import propcal
from engine.backtest import SettledProp


class _Report:
    def __init__(self, settled):
        self.settled, self.n = settled, len(settled)


def _prop(basis, market="rush_yds", raw=0.6, outcome=1, actual=None,
          line=58.5):
    s = SettledProp(player="P", market=market, line=line, odds=-110,
                    hit_prob=raw, projection=60.0,
                    actual=(70.0 if outcome else 40.0) if actual is None
                    else actual,
                    recommended=True, side="OVER", basis=basis)
    s.raw_prob = raw
    return s


# --- which pairs the fit is allowed to see -----------------------------------
def test_only_book_priced_props_are_learned_from():
    """The whole point. A proxy-priced pair teaches the model about a
    trailing average, which is not the opponent it faces."""
    rep = _Report([_prop("book"), _prop("naive"), _prop("book")])
    assert len(propcal.book_pairs(rep)) == 2


def test_the_market_filter_keeps_the_markets_apart():
    rep = _Report([_prop("book", market="rush_yds"),
                   _prop("book", market="rec_yds")])
    assert len(propcal.book_pairs(rep, "rush_yds")) == 1
    assert len(propcal.book_pairs(rep, "rec_yds")) == 1


def test_a_push_teaches_nothing_and_is_dropped():
    """A prop that landed exactly on the number decided nothing."""
    push = _prop("book", actual=58.5)
    assert push.outcome is None, "premise: landing on the line is a push"
    assert propcal.book_pairs(_Report([push])) == []


def test_the_raw_probability_is_what_is_learned_on():
    """Not the shrunk one. Fitting on an already-shrunk claim and then
    applying the result to a raw claim compounds the correction."""
    rep = _Report([_prop("book", raw=0.61)])
    assert propcal.book_pairs(rep)[0][0] == 0.61


def test_the_outcome_is_the_bit_that_actually_happened():
    rep = _Report([_prop("book", outcome=1), _prop("book", outcome=0)])
    assert sorted(p[1] for p in propcal.book_pairs(rep)) == [0, 1]


def test_a_report_with_no_settled_props_yields_nothing():
    assert propcal.book_pairs(_Report([])) == []


# --- what it refuses ---------------------------------------------------------
def test_a_thin_market_is_refused_rather_than_fitted_on_proxies():
    """A correction fitted on the wrong opponent is worse than none: the
    model runs uncorrected either way, and only one of the two also
    inverts sides."""
    assert propcal.MIN_BOOK_PAIRS > 200, (
        "the floor must be above calibrate.fit's own, since a fit here "
        "overrides one that is already live")


def test_a_database_with_no_harvested_closes_is_refused_by_name():
    from engine import db
    out = propcal.fit(db.connect(":memory:"), log=lambda *a: None)
    assert "no harvested NFL prop closes" in out["skipped"]
    assert propcal.report_lines(out)[0].startswith("prop calibration: skipped")


def test_the_touchdown_market_is_not_in_scope():
    """It has no line for a projection to be compared against, and
    `engine.tdbacktest` fits it through its own front door."""
    assert "anytime_td" not in propcal.MARKETS


# --- the report --------------------------------------------------------------
def test_a_refusal_says_which_market_and_why():
    out = {"season": 2025, "fitted": {},
           "refused": {"rush_yds": "12 book-priced pairs, needs 400 — ..."}}
    line = "\n".join(propcal.report_lines(out))
    assert "rush_yds" in line and "refused" in line


def test_an_adoption_reports_the_shape_it_chose():
    out = {"season": 2025, "refused": {}, "fitted": {"rush_yds": {
        "n": 900, "temperature": 1.1, "intercept": 0.02, "knots": 0,
        "brier_before": 0.24, "brier_after": 0.238}}}
    line = "\n".join(propcal.report_lines(out))
    assert "900 pairs" in line and "T=1.1" in line
    out["fitted"]["rush_yds"]["knots"] = 17
    assert "isotonic" in "\n".join(propcal.report_lines(out))


# --- the discipline ----------------------------------------------------------
def test_the_walk_runs_with_the_existing_calibration_disabled():
    """Fitting a correction on already-corrected input and then applying
    it to raw input compounds it on every re-run — the reason
    calibrate.py's own fit does the same."""
    import inspect
    src = inspect.getsource(propcal.fit)
    assert "with cal.disabled():" in src


def test_it_saves_only_when_something_was_fitted():
    import inspect
    src = inspect.getsource(propcal.fit)
    assert "if fitted:" in src, \
        "an empty refit must not rewrite the store"


# --- progress that can actually be seen --------------------------------------
def test_the_default_progress_channel_flushes():
    """A bare `print` is block-buffered whenever stdout is not a terminal,
    which is every backgrounded run. A walk that ticks once a minute then
    shows nothing until it exits, and reads as hung — Ethan sat eight
    minutes in front of a blank file. `run_tests.py` runs its children
    with `-u` and records the same lesson."""
    import inspect
    sig = inspect.signature(propcal.fit)
    assert sig.parameters["log"].default is propcal._tick
    assert "flush=True" in inspect.getsource(propcal._tick)


def test_the_tick_actually_writes_what_it_is_given():
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        propcal._tick("week 6 (1/12)")
    assert "week 6 (1/12)" in buf.getvalue()


# --- the nightly -------------------------------------------------------------
def test_the_nightly_runs_it_and_runs_it_last():
    """`calibrate.py` fits these same markets against a proxy line. The
    book-priced refit must be the LAST word on them, or the nightly
    would overwrite a correct fit with the one that caused this."""
    import inspect
    from engine import deepfit
    src = inspect.getsource(deepfit.run_all) if hasattr(deepfit, "run_all") \
        else inspect.getsource(deepfit)
    assert "refit_nfl_props(db)" in src
    body = src[src.index("refit_touchdowns(db)"):]
    assert "refit_nfl_props(db)" in body, \
        "it must come after the per-sport CLIs, not before"


def test_a_missing_database_is_not_a_failure():
    from engine import deepfit
    assert deepfit.refit_nfl_props("no/such/history.db") == []


def test_it_never_takes_the_nightly_down():
    """The settle pass must never fail because a fitter did."""
    import inspect
    from engine import deepfit
    src = inspect.getsource(deepfit.refit_nfl_props)
    assert "except Exception" in src and "skipped" in src


# --- a proxy fit must not outlive the evidence against it --------------------
def _store(tmp, entries):
    import json
    tmp.write_text(json.dumps(entries, indent=2))
    return tmp


def _cal_entry(basis, temperature=0.66):
    return {"temperature": temperature, "intercept": 0.0, "basis": basis,
            "curve": {}, "samples": 900}


def test_a_proxy_fit_may_not_overwrite_a_book_fit():
    """`deepfit.refit_all` runs the book fitter last and says it "must
    therefore be the last word". That is an ordering, and the whole class
    of bug this feature exists to fix is a rule stated in prose and
    enforced nowhere. So the store enforces it."""
    import tempfile, json, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:rush_yds": _cal_entry(cal.BASIS_BOOK, 2.8)})
        proxy = cal.Calibration(temperature=0.54, intercept=-0.98)
        proxy.basis = cal.BASIS_HISTORY
        cal.save({"nfl:rush_yds": proxy}, path)
        got = json.loads(path.read_text())["nfl:rush_yds"]
        assert got["temperature"] == 2.8, \
            "the proxy fitter overwrote the book fit"
        assert got["basis"] == cal.BASIS_BOOK


def test_a_book_fit_may_overwrite_a_proxy_fit():
    """The precedence runs one way only — otherwise the fix could never
    be installed over the thing it fixes."""
    import tempfile, json, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:rush_yds": _cal_entry(cal.BASIS_HISTORY, 0.54)})
        book = cal.Calibration(temperature=2.8, intercept=0.04)
        book.basis = cal.BASIS_BOOK
        cal.save({"nfl:rush_yds": book}, path)
        assert json.loads(path.read_text())["nfl:rush_yds"]["temperature"] == 2.8


def test_a_book_fit_may_be_refitted_by_a_later_book_fit():
    import tempfile, json, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:rush_yds": _cal_entry(cal.BASIS_BOOK, 2.8)})
        newer = cal.Calibration(temperature=3.4, intercept=0.0)
        newer.basis = cal.BASIS_BOOK
        cal.save({"nfl:rush_yds": newer}, path)
        assert json.loads(path.read_text())["nfl:rush_yds"]["temperature"] == 3.4


def test_the_guard_does_not_touch_markets_it_was_not_asked_about():
    import tempfile, json, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:rush_yds": _cal_entry(cal.BASIS_BOOK, 2.8),
                      "mlb:home_runs": _cal_entry(cal.BASIS_HISTORY, 1.4)})
        c = cal.Calibration(temperature=1.9, intercept=0.0)
        c.basis = cal.BASIS_HISTORY
        cal.save({"mlb:home_runs": c}, path)
        got = json.loads(path.read_text())
        assert got["mlb:home_runs"]["temperature"] == 1.9
        assert got["nfl:rush_yds"]["temperature"] == 2.8


def test_dropping_removes_the_entry_and_names_what_went():
    """Deleting and storing a neutral T=1.0 are different claims:
    `is_reliable` reads a stored entry as "somebody measured this"."""
    import tempfile, json, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:pass_yds": _cal_entry(cal.BASIS_HISTORY),
                      "nfl:receptions": _cal_entry(cal.BASIS_BOOK)})
        assert cal.drop(["nfl:pass_yds", "nfl:absent"], path) == ["nfl:pass_yds"]
        left = json.loads(path.read_text())
        assert "nfl:pass_yds" not in left and "nfl:receptions" in left


def test_dropping_nothing_leaves_the_file_alone():
    import tempfile, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:receptions": _cal_entry(cal.BASIS_BOOK)})
        before = path.read_text()
        assert cal.drop(["nfl:nothing_here"], path) == []
        assert path.read_text() == before
        assert cal.drop(["x"], _pl.Path(d) / "missing.json") == []


def test_a_refused_market_loses_a_proxy_correction_it_was_carrying():
    """The docstrings in propcal, deepfit and this file all said a
    refusal means the market runs uncorrected. The code kept the proxy
    fit in place. On the droplet that left nfl:pass_yds applying a
    correction fitted against a trailing average, with nothing to
    replace it and nothing saying so."""
    import inspect
    src = inspect.getsource(propcal.fit)
    assert "cal.drop(" in src
    assert "BASIS_BOOK" in src


def test_the_refusal_text_says_the_proxy_fit_was_dropped():
    out = {"season": 2025, "fitted": {}, "dropped": ["nfl:pass_yds"],
           "refused": {"pass_yds": "212 book-priced pairs, needs 400 — "
                                   "dropping the proxy-fitted correction"}}
    text = "\n".join(propcal.report_lines(out))
    assert "dropped nfl:pass_yds" in text and "proxy" in text


# --- a Brier arrow is not a verdict ------------------------------------------
def _fitted(brier_after, rate=0.5, **kw):
    d = {"n": 643, "temperature": 6.0, "intercept": -0.1, "knots": 0,
         "brier_before": 0.2847, "brier_after": brier_after,
         "base_rate": rate, "baseline": rate * (1.0 - rate),
         "at_boundary": False}
    d.update(kw)
    return {"season": 2025, "refused": {}, "fitted": {"rec_yds": d}}


def test_the_in_sample_margin_is_labelled_as_not_being_evidence():
    """It is still printed, because hiding it invites the next reader to
    recompute it and believe it. b(1-b) and not a flat 0.25: a market
    landing 57% has a no-skill floor of 0.2451, and reading that floor as
    0.2500 overstates the margin by more than double — which is the
    mistake this line exists to stop repeating."""
    out = _fitted(0.2422, rate=0.57)
    out["fitted"]["rec_yds"]["walk_forward"] = {
        "ran": True, "n": 205, "fitted": 0.2461,
        "constant": 0.2452, "margin": -0.0009}
    text = "\n".join(propcal.report_lines(out))
    assert "0.0029" in text, "the honest in-sample margin against 0.2451"
    assert "is not evidence" in text


def test_a_boundary_fit_reports_that_the_board_will_pass_it():
    text = "\n".join(propcal.report_lines(_fitted(0.2422, at_boundary=True)))
    assert "edge of the search grid" in text and "is_reliable" in text


def test_a_boundary_temperature_really_does_fail_is_reliable():
    """The claim the line above makes, checked against the function that
    has to honour it — rec_yds and rush_yds both fitted to exactly 6.0."""
    import tempfile, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:rec_yds": _cal_entry(cal.BASIS_BOOK, cal.GRID_MAX),
                      "nfl:receptions": _cal_entry(cal.BASIS_BOOK, 2.78)})
        cal.reset_cache()
        try:
            assert not cal.is_reliable("nfl", "rec_yds", path)
            assert cal.is_reliable("nfl", "receptions", path)
        finally:
            cal.reset_cache()


def test_an_older_fit_without_a_basis_is_not_treated_as_a_book_fit():
    """Every entry already on disk predates BASIS_BOOK, and guessing the
    other way would freeze the proxy fits in place permanently."""
    import tempfile, json, pathlib as _pl
    from engine import calibrate as cal
    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "calibration.json"
        _store(path, {"nfl:rush_yds": {"temperature": 0.54, "intercept": 0.0}})
        c = cal.Calibration(temperature=2.8, intercept=0.0)
        c.basis = cal.BASIS_HISTORY
        cal.save({"nfl:rush_yds": c}, path)
        assert json.loads(path.read_text())["nfl:rush_yds"]["temperature"] == 2.8


# --- scoring on pairs the fit has not seen -----------------------------------
def test_a_no_signal_model_does_not_earn_a_margin():
    """The test the in-sample comparison could not pass. Raw probability
    drawn independently of the outcome: a two-parameter fit will still
    beat a zero-parameter constant on the pairs it was fitted to."""
    import random
    rng = random.Random(7)
    pairs = [(rng.uniform(0.35, 0.75), int(rng.random() < 0.57))
             for _ in range(409)]
    assert propcal.walk_forward_brier(pairs)["margin"] <= 0


def test_a_real_signal_does_earn_one():
    """Outcomes generated FROM the claimed probability — a perfectly
    calibrated model, which must score well out of sample or the
    measurement is broken rather than the model."""
    import random
    rng = random.Random(11)
    pairs = [(p, int(rng.random() < p))
             for p in (rng.uniform(0.2, 0.8) for _ in range(409))]
    got = propcal.walk_forward_brier(pairs)
    assert got["margin"] > 0.02, got


def test_every_scored_block_is_later_than_its_training_pairs():
    """Expanding window, never random. The pairs arrive in week order and
    a random split puts the same week on both sides of the judge."""
    import inspect
    src = inspect.getsource(propcal.walk_forward_brier)
    assert "pairs[:lo]" in src and "pairs[lo:hi]" in src


def test_the_constant_is_the_training_base_rate_not_the_block_s():
    """A baseline that peeks is not a baseline: scoring against the base
    rate of the very block being scored hands it the answer."""
    import inspect
    src = inspect.getsource(propcal.walk_forward_brier)
    assert "for _p, o in train" in src, "the base rate must come from train"


def test_a_sample_too_small_to_score_says_so_rather_than_guessing():
    got = propcal.walk_forward_brier([(0.6, 1)] * 12)
    assert got["ran"] is False and "too few" in got["reason"]


def test_the_verdict_reads_the_walk_forward_and_not_the_stored_brier():
    """receptions on the droplet: in sample it beat a constant by 0.0029,
    at a size whose fitting artifact alone is about 0.0024."""
    out = _fitted(0.2422, rate=0.57)
    out["fitted"]["rec_yds"]["walk_forward"] = {
        "ran": True, "n": 205, "fitted": 0.2461, "constant": 0.2452,
        "margin": -0.0009}
    text = "\n".join(propcal.report_lines(out))
    assert "no skill out of sample" in text
    assert "is not evidence" in text, \
        "the in-sample margin must be shown as the artifact it is"


def test_an_out_of_sample_win_is_reported_as_one():
    out = _fitted(0.2422, rate=0.57)
    out["fitted"]["rec_yds"]["walk_forward"] = {
        "ran": True, "n": 205, "fitted": 0.2301, "constant": 0.2452,
        "margin": 0.0151}
    text = "\n".join(propcal.report_lines(out))
    assert "beats a constant by 0.0151 out of sample" in text
    assert "no skill" not in text


def test_an_unscoreable_market_says_so_instead_of_claiming_a_verdict():
    out = _fitted(0.2422, rate=0.57)
    out["fitted"]["rec_yds"]["walk_forward"] = {"ran": False,
                                                "reason": "too few"}
    text = "\n".join(propcal.report_lines(out))
    assert "no out-of-sample score" in text
    assert "beats a constant" not in text


def test_the_fit_records_a_walk_forward_score_for_every_market_it_adopts():
    import inspect
    src = inspect.getsource(propcal.fit)
    assert '"walk_forward": walk_forward_brier(pairs)' in src


def test_the_bake_off_could_not_have_judged_these_markets():
    """Why this exists at all. calibrate.bake_off needs MIN_HOLDOUT test
    rows and takes HOLDOUT_FRACTION of the sample; at 409, 490 and 643
    pairs it is skipped, so nothing out-of-sample ever ran."""
    from engine import calibrate as cal
    for n in (409, 490, 643):
        test_n = n - int(n * (1.0 - cal.HOLDOUT_FRACTION))
        assert test_n < cal.MIN_HOLDOUT, (
            f"{n} pairs now reaches the bake-off — propcal's own "
            f"walk-forward may be redundant, check before removing it")


# --- the walk's own counters -------------------------------------------------
def test_the_walk_names_both_denominators():
    """"2,626 props, 3,360 on real closes" reads as a counting bug. They
    are settled RECOMMENDATIONS and repriced SLATE props — different
    populations, and the larger one is not a subset of the smaller."""
    import inspect
    from engine import backtest
    src = inspect.getsource(backtest.backtest_from_stats)
    assert "settled recommendations" in src
    assert "of {props_seen:,} slate props" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
