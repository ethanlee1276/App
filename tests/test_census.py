"""The gate census — where tonight's picks died, on every board.

"878 analyzed → 1 recommended" is a number a reader has to trust. The
same line with a funnel under it is a number they can check, and the
difference is the whole trust question: an empty board and a broken
board look identical without one. MLB and the hoops boards had this;
NFL and CFB did not, which with a football season opening meant a quiet
Sunday would have said "nothing qualified" and offered nothing to check.

What this file pins:

  * THE FIRST FAILURE, NOT EVERY FAILURE. A prop that misses three gates
    is one death. Counting it three times makes the census sum past the
    props analyzed and read as a rendering fault.
  * THE FUNNEL IS DERIVED FROM THE DECISION, not recomputed beside it. A
    funnel that disagrees with the ruling it explains is worse than none.
  * AN UNNAMED GATE STILL SHOWS. A new rule appears in the funnel the day
    it is added rather than being silently swallowed.

Run directly: `python3 tests/test_census.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.census import (census, census_from_reasons,        # noqa: E402
                           reason_key, GATE_WORDS)
from engine.rules import condition                             # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _row(**kw):
    base = {"recommended": False, "checks": []}
    base.update(kw)
    return base


def _checks(**flags):
    return [condition(k, k, v, "", "") for k, v in flags.items()]


def test_only_the_first_failing_gate_is_counted():
    got = census([_row(checks=_checks(grade=True, edge=False, juice=False))])
    assert got.get("edge") == 1 and "juice" not in got, \
        "one prop died three times — the census will sum past the board"


def test_the_census_never_sums_past_the_board():
    rows = [_row(recommended=True),
            _row(checks=_checks(grade=False)),
            _row(checks=_checks(grade=True, edge=False)),
            _row(has_market=False, market_label="Receiving Yards")]
    got = census(rows)
    counted = sum(v for k, v in got.items() if isinstance(v, int))
    assert counted == len(rows), (counted, got)


def test_an_unpriced_prop_never_reaches_a_gate_and_names_its_market():
    got = census([_row(has_market=False, market_label="Anytime TD"),
                  _row(has_market=False, market_label="Anytime TD"),
                  _row(has_market=False, market_label="Receiving Yards")])
    assert got["no_real_price"] == 3
    assert got["no_price_markets"] == {"Anytime TD": 2, "Receiving Yards": 1}, \
        "a big unpriced count is usually the books' menu — unnamed it " \
        "reads as a broken join"


def test_a_row_with_no_failing_check_is_held_not_invented():
    got = census([_row(checks=_checks(grade=True, edge=True))])
    assert got.get("held_by_rules") == 1


def test_a_skip_predicate_keeps_another_boards_deaths_out():
    rows = [_row(market="anytime_td", checks=_checks(grade=False)),
            _row(market="rec_yds", checks=_checks(grade=False))]
    got = census(rows, skip=lambda r: r.get("market") == "anytime_td")
    assert got.get("grade") == 1, \
        "the long-shot board's working-as-intended deaths counted here"


def test_an_unnamed_gate_still_appears():
    got = census([_row(checks=_checks(brand_new_rule=False))])
    assert got.get("brand_new_rule") == 1, \
        "a gate with no display name vanished from the funnel"
    assert "brand_new_rule" not in GATE_WORDS


def test_reason_bucketing_drops_the_figures_and_keeps_the_sentence():
    a = reason_key("edge -1.7% < required 4.5% over break-even 52.4%")
    b = reason_key("edge -0.9% < required 3.1% over break-even 51.0%")
    assert a == b, "every pick became its own census row"
    assert "edge" in a and "%" not in a


def test_the_reason_shape_counts_published_passed_and_held():
    got = census_from_reasons(
        [{"p": 1}, {"p": 2}],
        [{"why": "edge -1.7% < required 4.5%"},
         {"why": "edge -0.9% < required 3.1%"},
         {"why": "grade 58 below the 62 bar"}],
        held=[{"h": 1}])
    assert got["recommended"] == 2 and got["held_by_rules"] == 1
    assert sum(v for k, v in got.items()
               if k not in ("recommended", "held_by_rules")) == 3


# --- the boards that publish it ---------------------------------------------

def test_the_football_boards_publish_a_census():
    nfl = _read("engine", "pipeline.py")
    assert '"gate_census": _census(results' in nfl, \
        "the NFL board went back to a bare count"
    # And it asks for the sport, which is what turns on the calibration
    # bucket. Without it the gate that closed rush_yds and rec_yds
    # wholesale on 2026-08-29 was counted under "held by rules", where a
    # closed market is indistinguishable from a quiet slate.
    assert 'sport="nfl"' in nfl, \
        "the funnel cannot name a market its own calibration closed"
    cfb = _read("cfb_build.py")
    assert 'out["gate_census"] = census_from_reasons(' in cfb, \
        "a quiet Saturday explains nothing again"


def test_the_hoops_board_shares_the_bucketing_instead_of_copying_it():
    nba = _read("engine", "nba", "pipeline.py")
    i = nba.index("def _reason_key")
    body = nba[i:nba.index("\ndef ", i)]
    assert "from ..census import reason_key" in body, \
        "a second copy of the bucketing came back — it will drift"


def test_the_page_can_name_every_gate_the_rules_can_fail():
    """Each key the football rules can fail has words on the board. A
    missing one renders as its raw key, which is honest but ugly.

    Read from CENSUS_GATE_NAMES rather than from inside the funnel: the
    map used to live in the funnel and a two-entry copy of it fed the
    headline sentence, so "every gate has words" was true of the table
    and false of the one line above it."""
    app = _read("web", "js", "app.js")
    i = app.index("const CENSUS_GATE_NAMES = {")
    body = app[i:app.index("function censusBuckets()", i)]
    for key in ("grade", "pregame", "confidence", "edge", "juice", "health",
                "calibration", "no_real_price", "no_history"):
        assert f"{key}:" in body, f"the funnel cannot name {key}"


def test_the_headline_and_the_table_read_the_same_names():
    """THE SECOND MAP. `biggestCensusBucket` carried its own two-entry
    copy — no_real_price and no_history — and it feeds the ONE sentence a
    reader gets before the table on an empty board. Every other gate
    printed as its raw key there while the full English sat in the
    funnel's map a few lines below.

    NFL on the droplet, 2026-09-03: 64 unpriced, 169 closed by
    calibration, 44 graded Pass. The largest bucket was `calibration`, so
    the sentence read "The largest reason is calibration (169)"."""
    app = _read("web", "js", "app.js")
    for fn in ("biggestCensusBucket", "censusFunnelHTML"):
        i = app.index(f"function {fn}()")
        body = app[i:i + 1500]
        assert "CENSUS_GATE_NAMES" in body, f"{fn} does not read the shared map"
        assert 'no_real_price: "' not in body, \
            f"{fn} carries its own copy of the gate names again"


def test_the_unpriced_note_uses_the_right_sports_noun():
    """It read "every hitter in the lineup" on every board — the wrong
    sport's noun in the one panel whose whole job is explaining an empty
    board honestly. Caught on a real NFL Week-1 rehearsal, by looking."""
    app = _read("web", "js", "app.js")
    i = app.index("const whoWeProject")
    body = app[i:i + 400]
    assert 'state.sport === "mlb"' in body
    assert "skill player on the card" in body
    # The TEMPLATE must interpolate, not hardcode. Counting the phrase
    # across the file would also count the comment that explains the fix,
    # which is prose about the bug rather than the bug.
    j = app.index("const noPrice = npmRows")
    tmpl = app[j:j + 700]
    assert "${whoWeProject}" in tmpl
    assert "every hitter in the lineup" not in tmpl


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
