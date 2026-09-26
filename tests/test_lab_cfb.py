"""The Lab page stops telling subscribers the college TD board is unmeasured.

`engine.cfbtdfit` has been a walk-forward prop harness since it was
written — 29,047 graded player-weeks, and its pairs are what fitted the
live `cfb:anytime_td` calibration — while the Lab page's coverage row
still said "no walk-forward prop harness yet — game lines only". The
Lab is the site's trust furniture; a measured board described as
unmeasured is the same failure as an unmeasured one described as
measured, pointing the other way.

The new entry carries a THIRD basis, "outcomes": no price exists
anywhere in the replay, so it claims predictive skill and nothing else,
and the card must not dress it in the market-relative chip.

Run directly: `python3 tests/test_lab_cfb.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.lab import cfb_props, NO_PROP_HARNESS
from engine.tdbacktest import TDBacktest


def _report(pairs):
    rep = TDBacktest(label="CFB")
    for p, scored in pairs:
        rep.add(p, scored)
    return rep.finish()


def _filled():
    # 200 rows, ~27% base rate, probabilities spread across the bands.
    pairs = []
    for i in range(200):
        p = 0.05 + (i % 10) * 0.06
        pairs.append((p, 1 if (i * 7) % 100 < 27 else 0))
    return _report(pairs)


def test_the_entry_exists_with_the_outcomes_basis():
    got = cfb_props(runner=_filled)
    m = got["markets"][0]
    assert m["market"] == "anytime_td"
    assert m["basis"] == "outcomes"
    assert "not an edge over a book" in m["basis_note"]


def test_skill_is_scored_against_the_base_rate():
    got = cfb_props(runner=_filled)
    sk = got["markets"][0]["skill"]
    assert sk is not None
    assert abs(sk["base_rate"] - 0.27) < 0.02
    assert sk["base_brier"] > 0


def test_the_bands_travel_as_bins_the_page_can_draw():
    got = cfb_props(runner=_filled)
    bins = got["markets"][0]["bins"]
    assert bins and all("mean_pred" in b and "hit_rate" in b and b["n"]
                        for b in bins)
    los = [b["lo"] for b in bins]
    assert los == sorted(los), "bins must arrive in band order"


def test_no_roi_columns_pretend_to_be_a_record():
    m = cfb_props(runner=_filled)["markets"][0]
    assert m["n_bets"] == 0 and m["roi"] is None and m["win_rate"] is None


def test_an_empty_replay_is_an_honest_gap_not_a_crash():
    got = cfb_props(runner=lambda: _report([]))
    assert "unavailable" in got
    assert "college" in got["unavailable"]


def test_a_failed_replay_reports_itself():
    def boom():
        raise RuntimeError("db locked")
    got = cfb_props(runner=boom)
    assert "db locked" in got["unavailable"]


def test_cfb_left_the_no_harness_dict():
    assert "cfb" not in NO_PROP_HARNESS


def test_the_build_calls_the_college_harness():
    with open(os.path.join(ROOT, "engine", "lab.py"), encoding="utf-8") as f:
        src = f.read()
    assert 'sports["cfb"] = {"props": cfb_props(' in src


def test_the_card_does_not_dress_outcomes_as_real_closes():
    """The chip ternary defaulted everything non-naive, non-mixed to the
    green "real closes" — the exact market-relative claim an
    outcomes-basis entry cannot make."""
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    assert 'outcomes ? "outcomes only"' in js
    assert 'outcomes ? "never priced — nothing here is a bet"' in js


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
