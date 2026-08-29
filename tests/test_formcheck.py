"""Is the base projection better than the average it is built from?

`propcal` measured the NFL prop markets against real closes and found
rush_yds at AUC 0.479 and rec_yds at 0.468 — no ordering at a book's
number. A temperature cannot fix an ordering, so the work goes back to
the projection.

`engine.formcheck` asks the prior question, which needs no odds: does
`engine.form.compute_form` — the base every multiplier is applied to —
predict the actual stat better than a plain trailing average? Measured
over 22,355 player-weeks across 2021-2025:

    market      form rank   best baseline     AUC vs book
    rush_yds      +0.732    last5   +0.744       0.479
    rec_yds       +0.691    season  +0.700       0.468
    receptions    +0.727    (form wins)          0.557

The two markets whose form blend loses to a plain season average are the
two that failed against a book, and the one that wins is the one with a
measured edge. Their fitted curves say the same thing: receptions and
pass_yds carry gentle, season-weighted weights and beat their baselines;
rush_yds is fitted to last1 .25 / last3 .35 / season .05 and loses, and
rec_yds was never adopted at all so it runs the hard-coded default, which
is just as recency-heavy.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import formcheck


# --- the ranking measure -----------------------------------------------------
def test_a_perfect_ordering_scores_one():
    assert abs(formcheck._spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9


def test_a_reversed_ordering_scores_minus_one():
    assert abs(formcheck._spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-9


def test_ties_are_averaged_rather_than_ordered_by_accident():
    assert formcheck._ranks([5, 5, 5]) == [2.0, 2.0, 2.0]
    assert formcheck._ranks([1, 3, 2]) == [1.0, 3.0, 2.0]


def test_a_constant_prediction_has_no_ordering_at_all():
    """The reason ordering is scored apart from MAE: a predictor that
    shades everyone toward the league mean wins on average error while
    ranking nobody, and ranking is the whole job of a prop pick."""
    assert formcheck._spearman([7, 7, 7, 7], [1, 2, 3, 4]) is None


def test_a_week_too_thin_to_rank_is_skipped_not_scored_as_zero():
    thin = {(2025, 1): [({"form": 1.0}, 5.0), ({"form": 2.0}, 6.0)]}
    assert formcheck._mean_week_rank(thin, "form") is None


# --- what each candidate is allowed to see -----------------------------------
def test_every_candidate_sees_only_games_already_played():
    """History is most-recent-first and holds prior games only; the row
    being predicted is appended after it is scored."""
    import inspect
    src = inspect.getsource(formcheck.run)
    assert "seen.setdefault((player, season), []).insert(0, actual)" in src
    i_score = src.index("preds = predictors(")
    i_append = src.index("seen.setdefault((player, season), []).insert")
    assert i_score < i_append, "the actual was recorded before it was predicted"


def test_the_career_anchor_cannot_contain_the_game_being_predicted():
    """It is folded in on the season boundary, so it holds only seasons
    that have finished."""
    import inspect
    src = inspect.getsource(formcheck.run)
    assert "if season != season_now:" in src
    assert "career.setdefault(p, []).extend(vals)" in src


def test_a_thin_log_is_not_scored():
    assert formcheck.MIN_HISTORY >= 3


def test_the_baselines_are_what_they_claim():
    got = formcheck.predictors([10.0, 20.0, 30.0, 40.0, 50.0], [], [], None)
    assert got["last1"] == 10.0
    assert got["last3"] == 20.0
    assert got["season"] == 30.0
    assert got["last5"] == 30.0


def test_the_form_candidate_is_the_engine_s_own_blend():
    import inspect
    src = inspect.getsource(formcheck.predictors)
    assert "from .form import compute_form" in src
    assert 'out["form"] = form.mean' in src


def test_the_gentle_control_is_a_long_window_curve():
    """It exists to isolate the recency curve from everything else, so it
    has to actually be gentle."""
    g = formcheck.GENTLE
    assert abs(sum(g.values()) - 1.0) < 1e-9
    assert g["season"] + g["last10"] > g["last1"] + g["last3"]


def test_no_odds_are_read_anywhere():
    """The point of this harness. A measurement priced against a proxy
    line is the bug the whole line of work exists to undo."""
    import pathlib
    src = pathlib.Path(formcheck.__file__).read_text()
    for word in ("odds_history", "over_odds", "under_odds", "closing",
                 "SportsbookLine", "real_lines", "_naive_line"):
        assert word not in src, \
            f"formcheck reads '{word}' — it must measure the stat, not a price"
    # And it reads the game logs directly rather than through the replay,
    # which is what needs a schedule feed and eight minutes per season.
    assert "player_game_logs" in src
    assert "backtest_from_stats" not in src


# --- the report --------------------------------------------------------------
def test_a_market_whose_baseline_wins_is_called_out():
    out = {"market": "rec_yds", "n": 100, "candidates": {
        "form": {"n": 100, "mae": 16.0, "rmse": 24.0, "rank": 0.691},
        "season": {"n": 100, "mae": 15.6, "rmse": 23.8, "rank": 0.700}}}
    text = "\n".join(formcheck.report_lines(out))
    assert "orders this market better" in text and "season" in text


def test_a_market_our_blend_wins_is_not():
    out = {"market": "receptions", "n": 100, "candidates": {
        "form": {"n": 100, "mae": 1.18, "rmse": 1.70, "rank": 0.727},
        "season": {"n": 100, "mae": 1.19, "rmse": 1.72, "rank": 0.723}}}
    assert "orders this market better" not in \
        "\n".join(formcheck.report_lines(out))


def test_an_empty_market_says_so_rather_than_dividing_by_zero():
    class _C:
        def execute(self, *a):
            return []
    out = formcheck.run(_C(), "rush_yds")
    assert out["n"] == 0 and "no game logs" in out["skipped"]


# --- the decomposition that did not work --------------------------------------
def test_volume_needs_a_real_denominator():
    """An efficiency measured over three touches is one screen pass
    wearing a trend costume."""
    assert formcheck.volume_predictor([50.0, 40.0], [2.0, 1.0]) is None


def test_volume_is_recent_role_times_long_run_efficiency():
    hist = [60.0, 60.0, 60.0, 60.0, 60.0, 60.0]
    opps = [15.0, 15.0, 15.0, 15.0, 15.0, 15.0]
    assert abs(formcheck.volume_predictor(hist, opps) - 60.0) < 1e-9


def test_a_role_change_moves_the_volume_estimate_but_not_the_rate():
    """The point of splitting them: 4 carries a game at the same 4.0
    yards is a different projection, and the rate should not move."""
    hist = [16.0, 16.0, 16.0, 16.0, 80.0, 80.0, 80.0, 80.0]
    opps = [4.0, 4.0, 4.0, 4.0, 20.0, 20.0, 20.0, 20.0]
    got = formcheck.volume_predictor(hist, opps)
    assert abs(got - 16.0) < 1e-9, got


def test_a_missing_opportunity_log_yields_no_estimate():
    assert formcheck.volume_predictor([50.0], []) is None
    assert formcheck.volume_predictor([50.0, 40.0], [None, None]) is None


# --- candidates are only comparable on rows they all priced -------------------
def test_candidates_are_scored_on_the_same_rows():
    """THE MEASUREMENT BUG THIS HARNESS HAD. `volume` returns None below
    MIN_OPPORTUNITIES, so on rush_yds it priced only real ball-carriers
    while every other candidate was also scored on thousands of receivers
    whose rushing yards are zero — where predicting zero is free. Read
    off their own rows, volume showed MAE 19.89 against gentle's 7.34,
    a gap that describes which rows each was handed and nothing else."""
    import inspect
    src = inspect.getsource(formcheck.run)
    assert "all(r[2].get(n) is not None for n in names)" in src
    assert 'out["candidates"][name] = {' in src
    i = src.index("usable = [r for r in rows_kept")
    j = src.index('out["candidates"][name]')
    assert i < j, "the common subset must be taken before anything is scored"


def test_every_candidate_reports_the_same_n():
    out = {"market": "rush_yds", "n": 22355, "compared_on": 7236,
           "candidates": {
               "form": {"n": 7236, "mae": 20.19, "rmse": 28.36, "rank": 0.649},
               "gentle": {"n": 7236, "mae": 19.52, "rmse": 27.40, "rank": 0.658}}}
    assert len({d["n"] for d in out["candidates"].values()}) == 1
    assert "7,236 carrying every candidate" in \
        "\n".join(formcheck.report_lines(out))


def test_the_report_says_what_the_numbers_compare_on():
    """22,355 player-weeks and 7,236 comparable rows are different facts
    and a reader who conflates them draws the wrong conclusion."""
    out = {"market": "rush_yds", "n": 22355, "compared_on": 7236,
           "candidates": {"form": {"n": 7236, "mae": 20.0, "rmse": 28.0,
                                   "rank": 0.649}}}
    head = formcheck.report_lines(out)[0]
    assert "22,355" in head and "7,236" in head


# --- the default curve is the measured one now -------------------------------
def test_the_shipped_default_is_the_curve_that_won():
    """It used to be transcribed from docs/NFL_MODEL.md §5 and never
    checked against an outcome. Held out on 2024-2025 the long-window
    curve beat it on rush_yds (+0.663 vs +0.645) and rec_yds (+0.541 vs
    +0.521), the two markets currently shut for AUC 0.47."""
    from engine.form import WINDOW_WEIGHTS
    assert WINDOW_WEIGHTS == formcheck.GENTLE
    assert abs(sum(WINDOW_WEIGHTS.values()) - 1.0) < 1e-9


def test_the_default_leans_long_rather_than_hot():
    from engine.form import WINDOW_WEIGHTS as w
    recent = w["last1"] + w["last3"] + w["last5"]
    longrun = w["last10"] + w["season"] + w["career"] + w["vs_opp"]
    assert longrun > recent, \
        "the spec curve put ~75% on the recent windows; that lost"


def test_the_baseball_curve_is_untouched():
    """MLB passes its own weights and none of this was measured there."""
    from engine.form import MLB_WINDOW_WEIGHTS
    assert MLB_WINDOW_WEIGHTS != formcheck.GENTLE


def test_a_hot_curve_must_now_beat_the_measured_baseline_to_be_adopted():
    """formfit compares a fitted curve against the DEFAULT, so raising
    the baseline re-examines the rush_yds curve on disk rather than
    anyone editing a stored file by hand."""
    import inspect
    from engine import formfit
    src = inspect.getsource(formfit)
    assert "brier_default - brier_fitted >= MIN_GAIN" in src


def test_head_to_head_history_is_inert_and_says_so():
    """MEASURED, not assumed: filled from a player's real history across
    9,097 held-out 2024-2025 player-weeks, the vs-opponent window moves
    the blend's ordering by 0.0001 on all three markets. A player meets a
    given opponent once a season, so it is a one-game sample carrying 7%
    of a weight. Kept because weighted_mean renormalises over absent
    windows and the sample slate exercises the path; documented so the
    next reader does not spend a morning wiring it up."""
    import pathlib as _pl
    src = _pl.Path("engine/form.py").read_text()
    i = src.index("WINDOW_WEIGHTS = {")
    note = src[max(0, i - 1200):i]
    assert "inert in production" in note.lower()
    assert "0.0001" in note
    from engine.form import WINDOW_WEIGHTS
    assert WINDOW_WEIGHTS.get("vs_opp", 0) > 0, \
        "the window was removed — the sample slate still supplies it"


def test_an_absent_window_is_renormalised_rather_than_counted_as_zero():
    """Why keeping an unfilled window costs nothing. If it were treated
    as a zero the blend would be dragged down by every window nobody
    supplies."""
    from engine.form import compute_form
    from engine.models import GameLog
    logs = [GameLog(week=0, opponent="", value=50.0) for _ in range(6)]
    got = compute_form(logs, 50.0, None)
    assert abs(got.mean - 50.0) < 1e-9, got.mean


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
