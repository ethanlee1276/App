"""Fitting the weights instead of choosing them.

`formcheck` showed the recency curve is near the ceiling of what
reweighting a player's own past yards can do, and `formbook` showed none
of it survives a real closing line — rush_yds at AUC 0.468, rec_yds at
0.477. The dial is neither the problem nor the fix.

What the blend never sees is everything beside the outcome's own
history: carries, targets, snap share, red-zone looks, air yards, xFP,
five seasons of it. So `engine.nflfit` fits weights over those instead of
hand-picking one recency curve — ordinary least squares, trained on
2021-2023 and scored on 2024-2025. Not because regression is clever, but
because it is the honest floor: if a fitted combination of everything we
record cannot beat a hand-tuned average of one column, the information is
not in these columns and no larger architecture rescues it.

Measured on the population a prop is actually offered on, against what
the board ships:

    rush_yds    +0.553 vs +0.535    MAE 23.66 vs 24.95
    rec_yds     +0.536 vs +0.521    MAE 20.91 vs 21.53
    receptions  +0.544 vs +0.537    MAE  1.54 vs  1.57
    pass_yds    +0.202 vs +0.219    MAE 63.05 vs 65.43
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import nflfit


# --- the solver ---------------------------------------------------------------
def test_it_solves_a_system_it_should():
    assert nflfit._solve([[2.0, 1.0], [1.0, 3.0]], [5.0, 10.0]) == [1.0, 3.0]


def test_a_singular_system_returns_nothing_rather_than_nonsense():
    assert nflfit._solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]) is None


def test_least_squares_recovers_a_known_line():
    rows = [([x, 2.0 * x], 3.0 + 5.0 * x) for x in range(1, 40)]
    coef = nflfit.fit_least_squares(rows)
    # x and 2x are collinear, so the ridge decides how the slope is split
    # between them; the PREDICTION is what has to be right.
    for x in (2.0, 7.0, 19.0):
        pred = coef[0] + coef[1] * x + coef[2] * 2.0 * x
        assert abs(pred - (3.0 + 5.0 * x)) < 0.05, (x, pred)


def test_collinear_columns_degrade_rather_than_crash():
    """Red-zone carries and inside-5 carries are nearly the same
    measurement, so the normal matrix is nearly singular by design."""
    rows = [([x, x], float(x)) for x in range(1, 60)]
    assert nflfit.fit_least_squares(rows) is not None


def test_no_rows_is_not_a_crash():
    assert nflfit.fit_least_squares([]) is None


# --- the discipline -----------------------------------------------------------
def test_training_and_scoring_seasons_never_overlap():
    assert not (set(nflfit.TRAIN_SEASONS) & set(nflfit.TEST_SEASONS))
    assert max(nflfit.TRAIN_SEASONS) < min(nflfit.TEST_SEASONS), \
        "a model scored on a season before the one it learned from"


def test_features_come_only_from_earlier_weeks():
    import inspect
    src = inspect.getsource(nflfit.build_rows)
    assert "for w in range(week - 1, 0, -1)" in src
    i_use = src.index("out.append((feats")
    i_add = src.index("seen.setdefault((player, season), []).insert(0, actual)")
    assert i_use < i_add, "the actual was recorded before it was predicted"


def test_the_career_anchor_closes_on_the_season_boundary():
    import inspect
    src = inspect.getsource(nflfit.build_rows)
    assert "if season != season_now:" in src


def test_standardising_uses_the_training_rows_only():
    """Scaling with the test set's own mean leaks its distribution."""
    import inspect
    src = inspect.getsource(nflfit.evaluate)
    assert "mu, sd = _standardise(tr)" in src
    assert "_standardise(te)" not in src


# --- the population -----------------------------------------------------------
def test_players_without_the_ball_are_excluded():
    """Two thirds of the rush_yds rows are receivers with no carries and
    no rushing yards, where a season average predicts zero perfectly.
    Measured across all rows the fitted model LOST (+0.727 to +0.756) —
    a fact about how many free zeros were in the sample. Books do not
    hang a rushing line on a slot receiver."""
    assert nflfit.MIN_OPPORTUNITY["rush_yds"] > 0
    assert nflfit.MIN_OPPORTUNITY["pass_yds"] >= 10


def test_the_floor_reads_the_volume_column_not_an_arbitrary_one():
    import inspect
    src = inspect.getsource(nflfit.build_rows)
    assert "opp_now = near" in src and "the first column is volume" in src
    for market, cols in nflfit.COLUMNS.items():
        assert cols[0] in ("carries", "targets", "pass_att"), (market, cols)


# --- the comparison -----------------------------------------------------------
def test_the_fit_is_judged_against_what_the_board_ships():
    """Beating a season average answers the wrong question: the board
    does not run a season average."""
    import inspect
    src = inspect.getsource(nflfit.evaluate)
    assert "compute_form(" in src and 'weights_for("nfl", market)' in src
    assert '"shipped"' in src


def test_a_loss_against_the_shipped_blend_is_reported_as_one():
    out = {"market": "pass_yds", "train_n": 1290, "test_n": 883,
           "fitted": {"mae": 63.05, "rank": 0.202},
           "shipped": {"mae": 65.43, "rank": 0.219},
           "baseline": {"mae": 65.67, "rank": 0.205}}
    text = "\n".join(nflfit.report_lines(out))
    assert "does not beat the blend already shipped" in text
    assert "-0.017" in text


def test_a_win_names_the_margin_and_the_holdout():
    out = {"market": "rush_yds", "train_n": 2733, "test_n": 1839,
           "fitted": {"mae": 23.66, "rank": 0.553},
           "shipped": {"mae": 24.95, "rank": 0.535},
           "baseline": {"mae": 23.83, "rank": 0.558}}
    text = "\n".join(nflfit.report_lines(out))
    assert "+0.018" in text or "+0.019" in text
    assert "never saw" in text


def test_all_three_comparators_are_printed():
    """The season mean stays visible: on rush_yds it still orders best of
    the three, and hiding it would oversell the fit."""
    out = {"market": "rush_yds", "train_n": 2733, "test_n": 1839,
           "fitted": {"mae": 23.66, "rank": 0.553},
           "shipped": {"mae": 24.95, "rank": 0.535},
           "baseline": {"mae": 23.83, "rank": 0.558}}
    text = "\n".join(nflfit.report_lines(out))
    for label in ("fitted", "shipped", "baseline"):
        assert label in text


def test_a_thin_market_is_refused_rather_than_fitted():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
              "period TEXT, player TEXT, team TEXT, market TEXT, value REAL)")
    out = nflfit.evaluate(c, "rush_yds")
    assert "skipped" in out


def test_it_reads_no_odds():
    """Whether the projection predicts the stat is prior to whether it
    beats a price, and this container has no prices at all."""
    import pathlib
    src = pathlib.Path(nflfit.__file__).read_text()
    for word in ("odds_history", "over_odds", "closing_odds_by_date"):
        assert word not in src


# --- the touchdown market -----------------------------------------------------
def test_the_touchdown_target_is_binary():
    """The market is "scored at least one", not a count. Settling a
    probability against a count of 2 would make every calibration bin
    describe nothing."""
    import inspect
    src = inspect.getsource(nflfit.td_rows)
    assert "1 if float(r[\"value\"]) > 0 else 0" in src


def test_red_zone_columns_lead_the_touchdown_feature_list():
    assert nflfit.TD_COLUMNS[0].startswith("rz")
    assert "xfp" in nflfit.TD_COLUMNS


def test_the_auc_handles_ties_and_one_sided_samples():
    assert nflfit._auc([(0.5, 1), (0.5, 0)] * 20) == 0.5
    assert nflfit._auc([(0.1, 0), (0.9, 1)]) == 1.0
    assert nflfit._auc([(0.4, 1)] * 10) is None


def test_a_thin_touchdown_sample_is_refused():
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
              "period TEXT, player TEXT, team TEXT, market TEXT, value REAL)")
    assert "skipped" in nflfit.evaluate_td(c)


def test_expected_fantasy_points_is_still_absent_from_the_touchdown_model():
    """MEASURED ON HELD-OUT SEASONS: xfp orders a touchdown at AUC 0.696,
    ahead of the player's own TD rate at 0.672 — which is what
    engine/touchdowns actually leans on — and ahead of red-zone carries
    at 0.576, which it treats as the signal worth a multiplier. xfp is
    ingested for five seasons and read by engine/fantasy for the waiver
    board. This test fails the day somebody wires it into the touchdown
    model, and that is the point: the claim in this file's docstring
    stops being true then and should be rewritten."""
    import pathlib as _pl
    src = _pl.Path("engine/touchdowns.py").read_text()
    assert "xfp" not in src, \
        "xfp now reaches the touchdown model — update the finding above"


def test_the_red_zone_nudge_is_still_capped_where_it_was():
    """rz_car measured AUC 0.576 against xfp's 0.696, so the cap is not
    obviously wrong — but it should not move without a measurement."""
    import pathlib as _pl
    src = _pl.Path("engine/touchdowns.py").read_text()
    assert "0.85, 1.15" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
