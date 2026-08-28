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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
