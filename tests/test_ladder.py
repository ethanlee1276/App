"""The conviction ladder, measured and then actually said out loud.

`engine.backtest` has computed this per grade since 2026-08-27 and
printed it at the bottom of a terminal report. Pooled over four ingested
NFL seasons the reading is not marginal:

    A   123/248 = 49.6% against a claimed 54.2%
    B+  432/765 = 56.5% against a claimed 53.8%

The board went on presenting A above B+ regardless, because the ladder's
order is hard-coded and nothing on the pricing path had ever seen the
record. Same failure this codebase keeps finding in itself: measured in
one place, enforced nowhere.

Run directly: `python3 tests/test_ladder.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ladder


def _bands(a_landed=0.4958, b_landed=0.5647, a_n=248, b_n=765):
    return {"A": {"n": a_n, "claimed": 0.5417, "landed": a_landed},
            "B+": {"n": b_n, "claimed": 0.538, "landed": b_landed}}


# --- pooling ----------------------------------------------------------
def test_seasons_pool_by_weight_not_by_average():
    """One season of a band is not the sample the question needs, and a
    218-bet season must not count the same as a 59-bet one."""
    pooled = ladder.pooled([
        {"B+": {"n": 100, "claimed": 0.5, "landed": 0.60}},
        {"B+": {"n": 900, "claimed": 0.5, "landed": 0.50}},
    ])
    assert pooled["B+"]["n"] == 1000
    assert abs(pooled["B+"]["landed"] - 0.51) < 1e-9


def test_pooling_reproduces_the_four_season_nfl_reading():
    pooled = ladder.pooled([
        {"A": {"n": 59, "claimed": .542, "landed": .576},
         "B+": {"n": 218, "claimed": .538, "landed": .578}},
        {"A": {"n": 69, "claimed": .541, "landed": .464},
         "B+": {"n": 177, "claimed": .538, "landed": .508}},
        {"A": {"n": 59, "claimed": .542, "landed": .491},
         "B+": {"n": 185, "claimed": .538, "landed": .557}},
        {"A": {"n": 61, "claimed": .542, "landed": .459},
         "B+": {"n": 185, "claimed": .538, "landed": .611}},
    ])
    assert pooled["A"]["n"] == 248 and pooled["B+"]["n"] == 765
    assert abs(pooled["A"]["landed"] - 0.496) < 0.001
    assert abs(pooled["B+"]["landed"] - 0.565) < 0.001


def test_an_empty_band_is_dropped_rather_than_dividing_by_zero():
    assert ladder.pooled([{"A": {"n": 0, "claimed": 0.5, "landed": 0.5}}]) == {}
    assert ladder.pooled([]) == {}


# --- the inversion ----------------------------------------------------
def test_an_out_of_order_ladder_is_found():
    bad = ladder.inversion(_bands())
    assert bad["upper"] == "A" and bad["lower"] == "B+"
    assert abs(bad["gap"] - 0.0689) < 1e-4


def test_an_ordered_ladder_reports_nothing():
    assert ladder.inversion(_bands(a_landed=0.60, b_landed=0.52)) is None


def test_two_bands_within_a_couple_of_points_are_not_an_inversion():
    """Below MIN_GAP they are the same band twice, and a warning that
    fires on noise trains a reader to ignore warnings."""
    assert ladder.inversion(_bands(a_landed=0.55, b_landed=0.56)) is None


def test_a_thin_band_is_not_compared_at_all():
    assert ladder.inversion(_bands(a_n=40)) is None
    assert ladder.inversion(_bands(b_n=40)) is None


def test_the_worst_pair_wins_when_several_are_out_of_order():
    bands = {"A+": {"n": 200, "claimed": .60, "landed": .45},
             "A": {"n": 200, "claimed": .55, "landed": .50},
             "B+": {"n": 200, "claimed": .53, "landed": .58}}
    bad = ladder.inversion(bands)
    assert (bad["upper"], bad["lower"]) == ("A+", "B+")


# --- the note ---------------------------------------------------------
def _saved(bands):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "ladder.json")
    ladder.save("nfl", bands, path)
    return path


def test_the_note_quotes_the_record_rather_than_asserting_it():
    note = ladder.note_for("nfl", _saved(_bands()))
    assert note and "49.6%" in note and "56.5%" in note and "765" in note


def test_an_ordered_ladder_puts_no_note_on_the_board():
    """A note that only ever appears is not information."""
    assert ladder.note_for("nfl", _saved(_bands(a_landed=.60, b_landed=.52))) \
        is None


def test_an_unmeasured_sport_says_nothing():
    assert ladder.note_for("cfb", _saved(_bands())) is None
    assert ladder.note_for("nfl", "/nonexistent/ladder.json") is None


def test_an_unreadable_store_costs_the_note_not_the_board():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "ladder.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert ladder.load(path) == {}
    assert ladder.note_for("nfl", path) is None


def test_saving_one_sport_does_not_erase_another():
    path = _saved(_bands())
    ladder.save("mlb", {"A": {"n": 150, "claimed": .55, "landed": .40},
                        "B+": {"n": 150, "claimed": .53, "landed": .52}}, path)
    stored = ladder.load(path)
    assert set(stored) == {"nfl", "mlb"}
    assert stored["nfl"]["A"]["n"] == 248


# --- it reaches the card ----------------------------------------------
def test_the_pricing_path_reads_the_ladder():
    import inspect
    from engine import betting
    source = inspect.getsource(betting)
    assert "from .ladder import note_for" in source


def test_only_the_upper_bands_carry_the_warning():
    """It is a warning ABOUT the top of the ladder. Printing it on a B+
    card — the band that is doing the out-landing — would read as a
    caution against the pick that earned its place."""
    import inspect
    from engine import betting
    source = inspect.getsource(betting)
    assert 'grade in ("A+", "A")' in source


def test_the_deep_refit_re_measures_it():
    import inspect
    from engine import deepfit
    assert "ladder" in inspect.getsource(deepfit.refit_all)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
