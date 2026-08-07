"""The correction has to be allowed to lose.

selfit fits the selection shrink and then tries to break it on data it has
never seen. Everything worth pinning here is about the ways that test could
be rigged in the correction's favour without anyone noticing:

  * a bar chosen after seeing the answer,
  * a bar on the SIGNED gap, so over-shooting counts as success,
  * a split that leaks — the same night on both sides,
  * an UNDER restated with the wrong sign, so half the board is corrected
    backwards,
  * grading its own homework and reporting the in-sample gain as evidence.

Run directly: `python3 tests/test_selfit.py`
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import selfit as sf                                             # noqa: E402
from engine import calibrate as cal                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rows(n, gap, dates, seed=5, side="OVER"):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        p = round(rng.uniform(0.50, 0.70), 3)
        out.append({"sport": "mlb", "market": "tb", "side": side,
                    "hit_prob": p, "date": dates[i % len(dates)],
                    "ts": dates[i % len(dates)] + "T12:00:00",
                    "status": "won" if rng.random() < (p - gap) else "lost"})
    return out


# --- the bar cannot be gamed -------------------------------------------------
def test_over_correction_is_a_failure_not_a_success():
    """The first cut of verdict() compared a SIGNED gap against a positive
    threshold, so shrinking a claim far below what landed counted as
    passing. An under-claim is the same miscalibration with the sign
    flipped: it kills good bets instead of taking bad ones."""
    assert sf.verdict(-0.011, -0.182)[0] == "FAIL"
    assert sf.verdict(0.120, -0.140)[0] == "FAIL"      # overshot the target
    # and the reading has to say WHY, not just fail
    assert "WORSE" in sf.verdict(0.120, -0.140)[1]


def test_a_journal_with_nothing_to_correct_says_so():
    """An honest held-out half cannot demonstrate a correction works. It
    must not be scored as a pass just because the number is small."""
    v, why = sf.verdict(0.02, 0.01)
    assert v == "NOTHING TO CORRECT"
    assert "cannot demonstrate" in why


def test_a_pass_needs_both_conditions():
    # small enough, but barely moved -> not a pass
    assert sf.verdict(0.055, 0.049)[0] == "INCONCLUSIVE"
    # moved a lot, still far from honest -> not a pass
    assert sf.verdict(0.300, 0.085)[0] == "FAIL"
    # both -> pass
    assert sf.verdict(0.120, 0.030)[0] == "PASS"


def test_the_bars_are_module_constants_not_inline_numbers():
    """A threshold written down where a diff shows it moving is the only
    thing separating a pre-registered bar from a rationalised one."""
    src = open(os.path.join(ROOT, "selfit.py"), encoding="utf-8").read()
    body = src[src.index("def verdict("):src.index("def report(")]
    for name in ("PASS_GAP", "FAIL_GAP", "HALVED"):
        assert name in body, name
    # no bare decimal thresholds smuggled into the comparison
    assert "0.05" not in body and "0.08" not in body


# --- the split cannot leak ---------------------------------------------------
def test_the_split_never_cuts_a_date_in_half():
    """One night is one pitcher, one park, one weather. Splitting on the
    row index would put the same night on both sides and leak the thing
    being held out."""
    dates = [f"2026-07-{d:02d}" for d in range(10, 26)]
    early, late = sf.split(_rows(300, 0.12, dates))
    assert early and late
    assert max(r["date"] for r in early) < min(r["date"] for r in late)


def test_the_split_lands_near_the_middle():
    dates = [f"2026-07-{d:02d}" for d in range(10, 26)]
    early, late = sf.split(_rows(320, 0.12, dates))
    assert abs(len(early) - len(late)) <= len(dates) * 3


def test_a_single_date_cannot_be_split():
    rows = _rows(50, 0.12, ["2026-07-10"])
    early, late = sf.split(rows)
    assert late == [] and len(early) == 50


# --- the correction is applied in the right direction ------------------------
def test_an_under_is_corrected_through_the_mirror_not_directly():
    """The fit lives in P(over). A bet on the UNDER claims 1-p there, and
    applying the shrink to its own number instead would push half the board
    the wrong way."""
    over = {"hit_prob": 0.70, "side": "OVER"}
    under = {"hit_prob": 0.70, "side": "UNDER"}
    T, c = 2.0, 0.0
    # A pure temperature pulls any claim toward 50% — both sides, same way.
    assert sf.corrected(over, T, c) < 0.70
    assert sf.corrected(under, T, c) < 0.70
    # …and the UNDER's answer is the mirror of the over-claim it implies.
    assert abs(sf.corrected(under, T, c)
               - (1.0 - cal.apply_temperature(0.30, T, c))) < 1e-12


def test_an_identity_correction_changes_nothing():
    rows = _rows(80, 0.12, ["2026-07-10", "2026-07-11"])
    assert abs(sf.measure(rows)["gap"]
               - sf.measure(rows, 1.0, 0.0)["gap"]) < 1e-12


def test_the_measured_gap_matches_a_hand_count():
    rows = [{"hit_prob": 0.60, "side": "OVER", "status": "won"},
            {"hit_prob": 0.60, "side": "OVER", "status": "lost"},
            {"hit_prob": 0.60, "side": "OVER", "status": "lost"},
            {"hit_prob": 0.60, "side": "OVER", "status": "lost"}]
    m = sf.measure(rows)
    assert abs(m["claimed"] - 0.60) < 1e-12
    assert abs(m["landed"] - 0.25) < 1e-12
    assert abs(m["gap"] - 0.35) < 1e-12


# --- it never ships anything -------------------------------------------------
def test_it_writes_no_store_at_all():
    """Steps 2 and 3 of §10. Applying is step 4 and a separate decision,
    because §8 says it may empty the board."""
    src = open(os.path.join(ROOT, "selfit.py"), encoding="utf-8").read()
    for forbidden in ("write_text", "json.dump", "conn.commit",
                      "UPDATE ", "INSERT "):
        assert forbidden not in src, forbidden


def test_only_the_selected_side_is_training_data():
    """`loose` is the control. Fitting on it would train the correction on
    the population it is supposed to be measured against."""
    import inspect
    src = inspect.getsource(sf.load)
    assert 'category: str = "main"' in inspect.signature(sf.load).__str__() \
        or 'category="main"' in src or "category: str = \"main\"" in src
    assert "loose" in src and "never as a fit input" in src


def test_the_report_marks_the_in_sample_line_as_not_evidence():
    src = open(os.path.join(ROOT, "selfit.py"), encoding="utf-8").read()
    assert "grading its own homework" in src
    assert "Only the second line is evidence" in src


def test_a_boundary_fit_is_called_out():
    """Simulation put the fitted temperature's 95th percentile ON the grid
    ceiling. A fit that ran to the edge did not converge, and shipping one
    would be shipping the search bound rather than a parameter."""
    src = open(os.path.join(ROOT, "selfit.py"), encoding="utf-8").read()
    assert "at_boundary" in src
    assert "failure to converge" in src


def test_the_measured_power_is_recorded_in_the_module():
    """A verdict from a test that finds a real effect half the time has to
    arrive with that number attached, or it will be read as certainty."""
    assert "55%" in sf.__doc__ and "6%" in sf.__doc__
    assert "only about half the time" in sf.__doc__


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
