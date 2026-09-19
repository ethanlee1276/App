"""A stopping rule is only a stopping rule if it predates the data.

NFL prices through the gate MLB does — MARKET_TIER is entirely NFL markets,
and TIER_MIN_EDGE and TIER_SHRINK are shared — so it inherits MLB's failure
mode exactly. MLB's took 247 settled bets to become visible, and NFL will
not produce 247 until December.

So nflguard looks after every week and fires on a boundary fixed in August,
before a single NFL bet has settled. What is pinned here is everything that
would quietly turn that back into a fixed-n test, or into a rule chosen
after seeing a season:

  * the boundary and the minimum look are module constants,
  * looks are per DATE, not per bet — more looks than the boundary was
    calibrated for raises the false-alarm rate silently,
  * the first crossing wins; a later look dipping back under does not
    un-fire it,
  * it reports and never disables anything,
  * a quiet season is reported as "not catastrophic", never as "honest".

Run directly: `python3 tests/test_nflguard.py`
"""

import datetime as dt
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nflguard as ng                                           # noqa: E402
from engine import ledger                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _season(gap, weeks=10, per_week=15, seed=4, sport="nfl"):
    conn = ledger.connect(":memory:")
    rng = random.Random(seed)
    start, k = dt.date(2026, 9, 13), 0
    for wk in range(weeks):
        d = (start + dt.timedelta(days=7 * wk)).isoformat()
        for _ in range(per_week):
            p = min(max(rng.gauss(0.55, 0.06), 0.35), 0.80)
            k += 1
            conn.execute(
                "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
                "odds,hit_prob,edge,status,category) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d + "T12:00:00", sport, d, f"P{k}", "rec_yds", "OVER", 40.5,
                 "dk", -110, round(p, 4), 0.04,
                 "won" if rng.random() < (p - gap) else "lost", "main"))
    conn.commit()
    return conn


# --- the rule is fixed, and fixed in the right units -------------------------
def test_the_boundary_and_the_minimum_look_are_constants():
    """A threshold living where a diff shows it moving is the only thing
    separating a pre-registered rule from one chosen in December."""
    src = open(os.path.join(ROOT, "nflguard.py"), encoding="utf-8").read()
    body = src[src.index("def verdict("):src.index("def report(")]
    assert "BOUNDARY" in body and "2.5" not in body
    assert ng.BOUNDARY == 2.5 and ng.MIN_LOOK == 25


def test_the_boundary_carries_its_false_alarm_table():
    """z 2.5 is not a single-look significance level, and a reader who
    assumes it is will think this is far stricter than it is. The measured
    rate over repeated weekly looks has to travel with it."""
    assert "not a single-look z" in ng.__doc__.lower() \
        or "NOT a single-look z" in ng.__doc__
    for cell in ("8.9%", "3.2%", "z 2.50"):
        assert cell in ng.__doc__, cell


def test_the_measured_detection_speed_is_recorded():
    """The whole justification: it catches MLB's failure mode around 100
    bets rather than 247. And the limits are recorded beside it."""
    assert "105 bets" in ng.__doc__ and "247" in ng.__doc__
    # Collapse whitespace before matching: the phrase wraps across a line,
    # and an assertion that names the exact spelling goes red on a reflow
    # that changed nothing. Third time today.
    flat = " ".join(ng.__doc__.split())
    assert "5-point over-claim will probably run all year undetected" in flat
    assert "Silence here is not proof the board is honest" in flat


# --- looks are per date ------------------------------------------------------
def test_a_look_happens_once_per_date_not_once_per_bet():
    """More looks than the boundary was calibrated for raises the
    false-alarm rate, and does it silently."""
    conn = _season(0.0, weeks=10, per_week=15)
    looks = ng.path(ng.load(conn, "nfl"))
    assert len(looks) <= 10
    assert len({x["date"] for x in looks}) == len(looks)


def test_no_look_happens_before_the_minimum():
    conn = _season(0.0, weeks=10, per_week=15)
    looks = ng.path(ng.load(conn, "nfl"))
    assert all(x["n"] >= ng.MIN_LOOK for x in looks)
    # …and a season too short to reach it produces none at all
    assert ng.path(ng.load(_season(0.0, weeks=1, per_week=10), "nfl")) == []


def test_the_running_statistic_is_cumulative_not_per_week():
    """A weekly z would throw away the evidence that makes a sequential
    test worth running at all."""
    looks = ng.path(ng.load(_season(0.0, weeks=8), "nfl"))
    assert [x["n"] for x in looks] == sorted(x["n"] for x in looks)
    assert looks[-1]["n"] > looks[0]["n"]


# --- what it decides ---------------------------------------------------------
def test_an_honest_season_does_not_fire():
    state, _ = ng.verdict(ng.path(ng.load(_season(0.0), "nfl")))
    assert state == "WATCHING"


def test_mlbs_failure_mode_fires_well_before_247_bets():
    """The reason this exists. MLB's +12 took 247 settled bets to see."""
    looks = ng.path(ng.load(_season(0.12), "nfl"))
    state, lk = ng.verdict(looks)
    assert state == "FIRED"
    assert lk["n"] < 200, lk
    assert lk["gap"] > 0.05


def test_the_first_crossing_wins():
    """Sequential means the decision is made at the crossing. A later look
    dipping back under is not evidence the board recovered — it is the same
    bets plus noise, and re-opening on it would make the boundary a
    suggestion."""
    looks = [{"date": "a", "n": 40, "z": 1.0, "gap": 0.01,
              "claimed": 0.55, "landed": 0.54},
             {"date": "b", "n": 60, "z": 2.9, "gap": 0.12,
              "claimed": 0.55, "landed": 0.43},
             {"date": "c", "n": 90, "z": 0.4, "gap": 0.01,
              "claimed": 0.55, "landed": 0.54}]
    state, lk = ng.verdict(looks)
    assert state == "FIRED" and lk["date"] == "b"


def test_an_empty_board_is_too_early_not_all_clear():
    state, lk = ng.verdict(ng.path(ng.load(ledger.connect(":memory:"), "nfl")))
    assert state == "TOO EARLY" and lk is None


# --- what it must not do -----------------------------------------------------
def test_it_disables_nothing():
    src = open(os.path.join(ROOT, "nflguard.py"), encoding="utf-8").read()
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "commit()",
                      "write_text", "recommended"):
        assert forbidden not in src, forbidden
    assert "NOTHING HAS BEEN DISABLED" in src


def test_a_quiet_season_is_not_reported_as_an_honest_one():
    """The limit that matters most. A 5-point gap is missed roughly seven
    times in ten and is already enough to invert the edge window, so
    silence cannot be allowed to read as a clean bill of health."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ng.report(_season(0.0), "nfl")
    out = buf.getvalue()
    assert "Quiet means not catastrophically dishonest" in out
    assert "It does not mean" in out


def test_it_points_at_barcheck_when_it_fires():
    """Firing is the start of a decision, not the end. If the gap clears
    2.5 points the question stops being how to tune the gate."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ng.report(_season(0.12), "nfl")
    assert "barcheck.py" in buf.getvalue()


def test_cfb_runs_through_the_same_guard():
    """CFB shares the gate and the calendar, so it inherits the same risk."""
    state, _ = ng.verdict(ng.path(ng.load(_season(0.12, sport="cfb"), "cfb")))
    assert state == "FIRED"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
