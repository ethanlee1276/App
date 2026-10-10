"""The drive sim's reconciliation (drivesimrecon.py) — fixture-driven.

The history arm ran the night it was built: five seasons, 1,378
gradable finals, and the verdict was NO EDGE — the sim's cover×over
joint does not beat independence at the closing line, so independence
keeps the seat. That verdict is the system WORKING: the bar exists so
a challenger that only ties never ships its complexity. What is pinned
here is the arithmetic that produced it:

  * outcome classification honors pushes on either leg,
  * the nflverse sign convention flips exactly once,
  * the paired tally and the two-standard-error verdict thresholds,
  * joint_cells sums to one, rebuilds independence from its own
    marginals, and drops pushes from the effective count.

Run directly: `python3 tests/test_drivesimrecon.py`
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drivesimrecon as dr
from engine import drivesim


def test_outcome_cell_honors_pushes_on_either_leg():
    g = {"margin": 3, "spread": -3.0, "total": 44.0, "points": 47}
    assert dr.outcome_cell(g) is None, "a spread push grades nothing"
    g = {"margin": 4, "spread": -3.0, "total": 44.0, "points": 44}
    assert dr.outcome_cell(g) is None, "a total push grades nothing"
    g = {"margin": 4, "spread": -3.0, "total": 44.0, "points": 47}
    assert dr.outcome_cell(g) == (True, True)
    g = {"margin": -10, "spread": -3.0, "total": 44.0, "points": 30}
    assert dr.outcome_cell(g) == (False, False)


def test_settled_games_flips_the_sign_once():
    rows = [{"season": "2025", "week": "1", "home_team": "PHI",
             "away_team": "DAL", "home_score": "24", "away_score": "20",
             "spread_line": "8.5", "total_line": "47.5"},
            {"season": "2025", "week": "2", "home_team": "KC",
             "away_team": "DEN", "home_score": "", "away_score": "",
             "spread_line": "3.0", "total_line": "42.5"}]
    with mock.patch("engine.sources.nflverse.load_schedules",
                    lambda: rows):
        got = dr.settled_games([2025])
    assert len(got) == 1, "an unplayed game cannot be graded"
    g = got[0]
    # nflverse says home favored by 8.5; the sim speaks home-negative.
    assert g["spread"] == -8.5 and g["margin"] == 4 and g["points"] == 44


def test_the_tally_and_the_two_se_bar():
    t = dr.Tally()
    for _ in range(400):
        t.add(0.50, 0.52)          # sim better by 0.02, every game
    assert t.n == 400 and abs(t.mean + 0.02) < 1e-12
    assert "EARNS CONSIDERATION" in dr.verdict(t)
    worse = dr.Tally()
    for _ in range(400):
        worse.add(0.52, 0.50)
    assert "INDEPENDENCE KEEPS THE SEAT" in dr.verdict(worse)
    # Noise around zero: the challenger loses the tie.
    tie = dr.Tally()
    for i in range(400):
        tie.add(0.5 + (0.01 if i % 2 else -0.01), 0.5)
    assert "NO EDGE" in dr.verdict(tie)
    thin = dr.Tally()
    for _ in range(50):
        thin.add(0.4, 0.6)
    assert "NO CALL" in dr.verdict(thin), \
        "fifty games is a hot streak, not a sample"


def test_joint_cells_is_a_distribution_and_indep_is_its_own_marginals():
    card = drivesim.simulate("nfl", -3.0, 44.0, trials=4000)
    jc = card.joint_cells()
    assert jc["n"] > 0
    assert abs(sum(jc["cells"].values()) - 1.0) < 1e-9
    assert abs(sum(jc["indep"].values()) - 1.0) < 1e-9
    pc = jc["cells"][(True, True)] + jc["cells"][(True, False)]
    po = jc["cells"][(True, True)] + jc["cells"][(False, True)]
    assert abs(jc["indep"][(True, True)] - pc * po) < 1e-12
    # Pushes exist at integer lines and are OUT of the effective count.
    assert jc["n"] < card.trials


def test_grade_caches_by_line_and_counts_pushes():
    games = [
        {"season": "2025", "week": "1", "home": "A", "away": "B",
         "spread": -3.0, "total": 44.5, "margin": 7, "points": 47},
        {"season": "2025", "week": "1", "home": "C", "away": "D",
         "spread": -3.0, "total": 44.5, "margin": -4, "points": 40},
        {"season": "2025", "week": "2", "home": "E", "away": "F",
         "spread": -3.0, "total": 44.5, "margin": 3, "points": 41},
    ]
    r = dr.grade(games, trials=800)
    assert r["cards"] == 1, "one line pair, one simulation"
    assert r["pushes"] == 1 and r["tally"].n == 2
    assert r["realized_margin_sd"] > 0


def test_the_forward_arm_reads_the_journal_shape():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "drivesimrecon.py"),
        encoding="utf-8").read()
    assert "drivesim.LOG_PATH" in src, \
        "the forward arm must grade the SAME file the build journals"
    assert "last write per" in src.lower() or "Last write per" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
