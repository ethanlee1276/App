"""The hoops boards dropped most of their props in silence.

Ethan's diagnosis run answered the question I had got wrong twice:

    Props buildable     430
    ✓ The history is fine.

430 props built from stored logs, and a blank WNBA board. The props were
never the problem — they were being built and then thrown away, and the page
said this about it:

    "No props clear the current thresholds. Loosen the sliders or enable
     show non-recommended."

Which is advice that cannot work. A slider filters what ARRIVES, and on that
night almost nothing arrived: nba_build's pricing loop dropped every prop
without a two-way book price with a bare `continue`, no counter, no report.
Most props most nights have no price, so the common case was invisible and
indistinguishable from the model rejecting everything.

MLB has had a gate census for a long while — "Where tonight's props died".
The hoops boards never got one, so this adds it at both layers that discard
props: the build's own drops (no price, no history) and the pipeline's
(thin sample, volatile minutes, edge under the bar, grade under the bar).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.hoops import WNBA, NBA
from engine.nba.pipeline import run_nba_slate, _census, _reason_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()


def _prop(player, **kw):
    base = {"player": player, "team": "LV", "opponent": "CHI", "market": "pts",
            "line": 15.5, "over_odds": -110, "under_odds": -110,
            "book": "FanDuel", "minutes": [30, 29, 31, 28, 30],
            "values": [16, 14, 18, 12, 15], "is_starter": True,
            "spread": -3.0, "is_favorite": True, "rest": "1day",
            "freshness": 0.5}
    base.update(kw)
    return base


# --- the tally --------------------------------------------------------------
def test_the_pipeline_reports_why_each_prop_died():
    props = [_prop(f"P{i}") for i in range(8)]
    props.append(_prop("Thin", minutes=[22], values=[9], is_starter=False))
    r = run_nba_slate(props, tune=WNBA)
    assert r["gate_census"], "the reasons are computed and then discarded"
    assert sum(r["gate_census"].values()) + r["counts"]["picks"] \
        == r["counts"]["props_analyzed"], \
        "the census does not account for every prop analyzed"


def test_a_prop_failing_three_gates_is_counted_once():
    """Otherwise the census sums to more than the props analyzed and every
    number on it is inflated."""
    src = open(os.path.join(ROOT, "engine", "nba", "pipeline.py"),
               encoding="utf-8").read()
    fn = src[src.index("def _census("):]
    assert "fails[0]" in fn


def test_reason_keys_are_categories_rather_than_one_row_per_prop():
    """Reasons are written for a card and carry that prop's own figures:
    "edge -1.7% < required 4.5% over break-even 52.4%". Tallied verbatim
    every prop becomes its own row and the census turns into a list of
    two hundred 1s."""
    a = _reason_key("edge -1.7% < required 4.5% over break-even 52.4%")
    b = _reason_key("edge -3.2% < required 6.0% over break-even 55.1%")
    assert a == b and a, (a, b)
    assert not any(c.isdigit() for c in a)
    # …but genuinely different reasons must stay apart.
    assert _reason_key("thin sample — under 3 usable games") != a


def test_the_categories_read_as_english():
    for raw, want in (
            ("thin sample — under 3 usable games", "thin sample"),
            ("grade 61 below the 70 bar — no bet, no leans",
             "grade below the bar")):
        assert _reason_key(raw) == want


def test_an_empty_slate_produces_an_empty_census_not_a_crash():
    r = run_nba_slate([], tune=NBA)
    assert r["gate_census"] == {}


# --- the build's own drops --------------------------------------------------
def test_the_build_counts_the_props_it_drops_before_the_model():
    """The bare `continue` that started all this."""
    i = BUILD.index("census = {\"no_real_price\": 0, \"no_history\": 0}")
    block = BUILD[i:i + 700]
    assert 'census["no_history"] += 1' in block
    assert 'census["no_real_price"] += 1' in block


def test_both_layers_end_up_in_one_table():
    assert 'out["gate_census"] = {**census' in BUILD
    assert 'out["counts"]["props_built"] = len(slate.props)' in BUILD, \
        "nothing records how many props existed before pricing"


# --- the page ---------------------------------------------------------------
def test_the_page_stops_recommending_a_slider_that_cannot_help():
    i = JS.index("No props reached the board")
    block = JS[i - 700:i + 700]
    assert "censusTotal() > 0" in block
    assert "cannot\n        help here" in block or "cannot help here" in block


def test_the_empty_message_names_the_biggest_actual_cause():
    i = JS.index("No props reached the board")
    assert "biggestCensusBucket()" in JS[i - 400:i + 400]


def test_the_funnel_is_shown_under_every_empty_message():
    """"Why is this blank" is the same question whichever branch answers
    it, so the breakdown should not be conditional on the wording."""
    i = JS.index('host.innerHTML = `<p class="loading">${msg}</p>')
    assert "censusFunnelHTML()" in JS[i:i + 120]


def test_a_total_is_never_reported_as_a_reason():
    """props_built is how many existed, not a cause of death. Ranking it
    would make the largest bucket the total, every time."""
    fn = JS[JS.index("function censusBuckets()"):]
    fn = fn[:fn.index("\n}\n")]
    for key in ("props_built", "recommended", "no_price_markets"):
        assert key in fn, f"{key} is not excluded from the buckets"


def test_the_build_side_keys_have_readable_names():
    assert "no_history:" in JS
    fn = JS[JS.index("function biggestCensusBucket()"):]
    assert "no real book price yet" in fn[:600]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
