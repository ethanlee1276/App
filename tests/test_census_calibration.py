"""A board that recommends nothing has to say why.

2026-08-29, the live NFL build: "Analyzed 285 props → 0 recommended",
and nothing under it. rush_yds and rec_yds had both been refused
wholesale — their calibrations fitted to the top of the search grid, so
`betting.evaluate_prop` closes the market outright — but the printout
could not distinguish that from a quiet slate, a broken join, or a model
that had stopped working.

`engine/census.py` was written for exactly this. Its docstring: "NFL and
CFB never emitted one, which is why this module exists ... with the
football season opening, a quiet Sunday board would have said 'nothing
qualified' and offered nothing to check." The pipeline had been
publishing `gate_census` into recommendations.json the whole time. No
caller printed it, and the shared counter had no bucket for the gate that
was actually doing the killing — MLB's private copy did.
"""

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import calibrate
from engine.census import census


def _store(entries):
    d = pathlib.Path(tempfile.mkdtemp()) / "calibration.json"
    d.write_text(json.dumps(entries))
    calibrate.DEFAULT_PATH = d
    calibrate.reset_cache()
    return d


def _boundary_store():
    return _store({
        "nfl:rush_yds": {"temperature": calibrate.GRID_MAX,
                         "intercept": -0.18, "basis": "book"},
        "nfl:rec_yds": {"temperature": calibrate.GRID_MAX,
                        "intercept": -0.10, "basis": "book"},
        "nfl:receptions": {"temperature": 2.78, "intercept": 0.04,
                           "basis": "book"}})


_ORIGINAL = calibrate.DEFAULT_PATH


def _restore():
    calibrate.DEFAULT_PATH = _ORIGINAL
    calibrate.reset_cache()


def _rows():
    return [
        {"recommended": True, "market": "receptions"},
        {"recommended": False, "market": "rush_yds",
         "market_label": "Rushing Yards"},
        {"recommended": False, "market": "rec_yds",
         "market_label": "Receiving Yards"},
        {"recommended": False, "market": "receptions",
         "checks": [{"key": "edge", "passed": False}]},
    ]


# --- the bucket ---------------------------------------------------------------
def test_a_market_closed_by_its_calibration_is_counted_as_that():
    _boundary_store()
    try:
        got = census(_rows(), sport="nfl")
        assert got["calibration"] == 2
        assert got.get("edge") == 1, "the live market still dies its own death"
    finally:
        _restore()


def test_the_closed_markets_are_named_not_just_totalled():
    """"calibration 172" is a mystery; the names are something to act on."""
    _boundary_store()
    try:
        got = census(_rows(), sport="nfl")
        assert got["calibration_markets"] == ["Receiving Yards",
                                              "Rushing Yards"]
    finally:
        _restore()


def test_a_recommended_prop_is_never_counted_as_closed():
    """Order matters: recommended is checked first, so a market that is
    open cannot be reported shut."""
    _boundary_store()
    try:
        rows = [{"recommended": True, "market": "rush_yds"}]
        got = census(rows, sport="nfl")
        assert got["recommended"] == 1 and "calibration" not in got
    finally:
        _restore()


def test_a_healthy_store_produces_no_calibration_bucket_at_all():
    _store({"nfl:rush_yds": {"temperature": 1.4, "intercept": 0.0}})
    try:
        got = census(_rows(), sport="nfl")
        assert "calibration" not in got and "calibration_markets" not in got
    finally:
        _restore()


def test_without_a_sport_the_counter_behaves_exactly_as_before():
    """Opt-in, so no existing caller's funnel shifts under it."""
    _boundary_store()
    try:
        got = census(_rows())
        assert "calibration" not in got
        assert got["held_by_rules"] == 2      # the two closed rows, as before
    finally:
        _restore()


def test_the_buckets_still_sum_to_the_rows_analyzed():
    """A prop that misses three gates is one death, not three, or the
    funnel reads as a rendering fault."""
    _boundary_store()
    try:
        got = census(_rows(), sport="nfl")
        total = sum(v for k, v in got.items()
                    if isinstance(v, int) and k != "no_real_price")
        total += got["no_real_price"]
        assert total == len(_rows())
    finally:
        _restore()


# --- and it reaches a human --------------------------------------------------
def test_the_nfl_pipeline_asks_for_the_sport_aware_census():
    import inspect
    from engine import pipeline
    src = inspect.getsource(pipeline.run_slate)
    assert '_census(results, sport="nfl")' in src


def test_the_nfl_build_actually_prints_the_funnel():
    """It was published to JSON and never shown, which is why a board
    recommending 0 of 285 looked like a quiet night."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "nfl_build.py"), encoding="utf-8").read()
    i = src.index("props → ")
    block = src[i:i + 1400]
    assert "Gate census" in block
    assert "calibration_markets" in block


def test_both_boards_word_the_closed_market_line_the_same_way():
    """A reader who learns the phrase on one board should not have to
    learn it again on the other."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    phrase = "Markets closed by calibration (fit at search boundary)"
    for name in ("nfl_build.py", "mlb_build.py"):
        src = open(os.path.join(root, name), encoding="utf-8").read()
        assert phrase in src, f"{name} words it differently"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
