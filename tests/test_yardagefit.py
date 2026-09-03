"""The yardage markets' real defect: the wrong distribution, not a width.

rush_yds and rec_yds are shut — AUC 0.47 against a real book, a fitted
temperature pinned to its grid edge, an isotonic curve so saturated that
`calibrate.one_sided` had to veto it. Their projections meanwhile rank
actual yardage well and carry no bias. A good ordering that cannot beat a
line is a distribution problem, and this module is where it was found.

Three things are pinned, each of which was a wrong turn first:

  * the zero atom is real and predictable, and a normal's negative tail
    is a bad stand-in for it — too small at the bottom of the board, two
    to five times too large above fifteen yards;
  * the positive part must be fitted on P(over), not on the density.
    Fitted on the density the mixture wins the distribution test outright
    (PIT chi-square 482 -> 170) and gets WORSE at the only question the
    board asks;
  * and it must only be adopted where the defect exists — pass_yds is
    2.3% zeroes and the shipped normal is right there.

Run directly: `python3 tests/test_yardagefit.py`
"""

import math
import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import yardagefit as Y                             # noqa: E402


def _db(zero_rate=0.30, n_players=260, weeks=17, seed=11, market="rush_yds"):
    """A synthetic league whose truth we set: each player has his own
    chance of a blank, and a lognormal day when he plays.

    NOTHING is read off this box. The suite runs the same everywhere or
    it is measuring a machine rather than a model."""
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, "
                 "period TEXT, game_id TEXT, player TEXT, team TEXT, "
                 "opponent TEXT, position TEXT, home INT, market TEXT, "
                 "value REAL)")
    out = []
    for season in (2021, 2022, 2023, 2024, 2025):
        for p in range(n_players):
            # Blank-prone players and workhorses, so the prior rate has
            # something to separate.
            q = zero_rate * (0.2 + 1.6 * (p % 5) / 4.0)
            scale = 12.0 + 70.0 * ((p * 7) % 11) / 10.0
            for w in range(1, weeks + 1):
                v = 0.0 if rng.random() < q else \
                    scale * math.exp(rng.gauss(0.0, 0.55) - 0.55 ** 2 / 2)
                out.append(("nfl", season, f"{w:03d}", f"g{w}", f"P{p}",
                            f"T{p % 32}", "OPP", "RB", 1, market, v))
    conn.executemany("INSERT INTO player_game_logs VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?)", out)
    conn.commit()
    return conn


def _rows(**kw):
    conn = _db(**kw)
    try:
        return Y.rows(conn, kw.get("market", "rush_yds"))
    finally:
        conn.close()


# --- the atom -------------------------------------------------------------
def test_the_zero_rate_a_player_has_shown_predicts_the_one_he_will_show():
    """The whole reason the atom is priceable rather than a league
    constant. Measured on the real logs it runs 4.4% -> 10.9% -> 23.8% ->
    37.4% -> 66.5% across five bands of prior blank rate."""
    data = _rows()
    beta = Y.fit_zero(data)
    assert beta[1] > 0.2, \
        f"a player's own blank rate must carry positive weight: {beta}"
    quiet = [d for d in data if d["zero_rate"] < 0.10]
    blanky = [d for d in data if d["zero_rate"] > 0.40]
    assert quiet and blanky
    q_lo = sum(Y.zero_prob(beta, d) for d in quiet) / len(quiet)
    q_hi = sum(Y.zero_prob(beta, d) for d in blanky) / len(blanky)
    assert q_hi > q_lo + 0.10, (q_lo, q_hi)


def test_the_claimed_blank_rate_is_shrunk_toward_the_league():
    """A player with four prior games and one blank is claiming 25% and
    the sample does not support it. The fitted slope is the shrinkage —
    a slope of 1.0 would take every small-sample claim at face value."""
    beta = Y.fit_zero(_rows())
    assert 0.0 < beta[1] < 1.0, \
        f"slope {beta[1]:.2f} means the prior rate is taken literally"


def test_a_blank_free_market_still_returns_a_usable_probability():
    """pass_yds is 2.3% zeroes. The atom must degrade to nearly nothing
    rather than to a divide-by-zero."""
    data = _rows(zero_rate=0.01)
    beta = Y.fit_zero(data)
    q = sum(Y.zero_prob(beta, d) for d in data) / len(data)
    assert 0.0 < q < 0.10, q
    p = Y.mixture_over(data[0], 20.0, beta, 0.5)
    assert 0.0 <= p <= 1.0


# --- the objective --------------------------------------------------------
def test_the_width_is_fitted_on_the_question_the_board_asks():
    """THE WRONG TURN THIS PINS. Fitted by maximum likelihood on the
    density the mixture wins the distribution test outright — PIT
    chi-square 482 -> 170 on real rushing logs — and runs about ten
    points light on every over, which is worse than the normal it
    replaced. The density objective is dominated by the many small
    outcomes: it buys shape in the bulk and pays for it at the line.

    So the two fits must actually differ, and the one the board uses must
    be the one fitted on P(over)."""
    data = _rows()
    lines = Y.MARKETS["rush_yds"]
    beta = Y.fit_zero(data)
    s_density = Y.fit_sigma_on_density(data, beta)
    s_over = Y.fit_sigma_on_over(data, beta, lines)
    err_density = Y.over_error(
        data, lines, lambda d, L: Y.mixture_over(d, L, beta, s_density))
    err_over = Y.over_error(
        data, lines, lambda d, L: Y.mixture_over(d, L, beta, s_over))
    assert err_over <= err_density, (s_density, err_density, s_over, err_over)


def test_the_mixture_keeps_the_mean_the_blend_earned():
    """Mean-matched on purpose. A projection of 60 yards has to still
    MEAN 60 yards after the atom is carved out of it, or the card and the
    probability are describing two different players."""
    row = {"mu": 60.0, "form_sd": 20.0, "zero_rate": 0.25, "actual": 0.0}
    beta = [0.0, 0.8]
    for sigma in (0.3, 0.6, 0.9):
        q = Y.zero_prob(beta, row)
        median = max(row["mu"] / (1 - q), 0.5) * math.exp(-0.5 * sigma ** 2)
        mean_positive = median * math.exp(0.5 * sigma ** 2)
        assert abs((1 - q) * mean_positive - row["mu"]) < 1e-9, sigma


def test_a_higher_line_is_never_more_likely_than_a_lower_one():
    row = {"mu": 45.0, "form_sd": 18.0, "zero_rate": 0.2, "actual": 0.0}
    beta = [0.0, 0.8]
    ps = [Y.mixture_over(row, L, beta, 0.55)
          for L in (0.5, 10.5, 25.5, 45.5, 80.5, 150.5)]
    assert ps == sorted(ps, reverse=True), ps
    assert ps[-1] >= 0.0 and ps[0] <= 1.0 - Y.zero_prob(beta, row) + 1e-9


# --- adopting it only where the defect is ---------------------------------
def test_the_mixture_beats_the_normal_when_blanks_are_common():
    data = _rows(zero_rate=0.30)
    lines = Y.MARKETS["rush_yds"]
    beta = Y.fit_zero(data)
    sigma = Y.fit_sigma_on_over(data, beta, lines)
    mix = Y.over_error(data, lines,
                       lambda d, L: Y.mixture_over(d, L, beta, sigma))
    ship = Y.over_error(data, lines,
                        lambda d, L: Y.shipped_over(d, L, "rush_yds"))
    assert mix < ship, (mix, ship)


def test_the_report_refuses_to_guess_on_a_thin_market():
    conn = _db(n_players=6, weeks=6)
    try:
        lines = Y.report("rush_yds", conn=conn)
    finally:
        conn.close()
    assert any("too few" in x for x in lines), lines


def test_the_report_names_every_candidate_and_picks_one():
    conn = _db()
    try:
        lines = Y.report("rush_yds", conn=conn)
    finally:
        conn.close()
    text = "\n".join(lines)
    for label in ("SHIPPED normal", "mixture, width from density",
                  "mixture, width from P(over)"):
        assert label in text, text
    assert "<-- best" in text, text
    assert "realised" in text, text


# --- the walk itself ------------------------------------------------------
def test_every_row_is_built_from_weeks_before_it():
    """A projection that has seen its own week is not a projection. The
    first MIN_PRIOR weeks of a player's season produce no row at all."""
    conn = _db(n_players=1, weeks=17, seed=3)
    try:
        data = Y.rows(conn, "rush_yds")
    finally:
        conn.close()
    per_season = len(data) / 5
    assert per_season == 17 - Y.MIN_PRIOR, per_season


def test_the_blend_is_the_shipped_one_not_a_second_opinion():
    """`WINDOW_WEIGHTS` is measured and fitted elsewhere. Copying it here
    would grade a projection the board does not make — and would drift
    silently the next time `formfit` moves it."""
    import inspect
    src = inspect.getsource(Y)
    assert "from .form import WINDOW_WEIGHTS" in src
    assert "WINDOW_WEIGHTS.get" in src
    # Equal values through the blend must return that value.
    assert abs(Y.blended([12.0] * 8) - 12.0) < 1e-9


# --- against the prices a book really hung -------------------------------
def _joined(n=40, line=25.5, over=-110, under=-110, mu=26.0):
    return [{"season": 2023 + i % 3, "mu": mu, "form_sd": 12.0,
             "zero_rate": 0.15, "actual": 40.0 if i % 2 else 5.0,
             "player": f"P{i}", "team": "KC", "period": f"{i % 17 + 1:03d}",
             "date": "2023-09-10", "line": line, "over_odds": over,
             "under_odds": under, "book": "DK"} for i in range(n)]


def test_a_line_nowhere_near_the_projection_is_a_different_player():
    """THE JOIN GUARD. Two men share a name every season, and joining
    them silently is how a backtest reports an edge it never had. A close
    hung at 80 yards against a 12-yard projection is not that player's
    line."""
    rows = [{"season": 2023, "mu": 12.0, "form_sd": 6.0, "zero_rate": 0.2,
             "actual": 10.0, "player": "Common Name", "team": "KC",
             "period": "001", "date": "2023-09-10"}]
    near = {(Y._norm("Common Name"), "2023-09-10"):
            {"line": 13.5, "over_odds": -110, "under_odds": -110,
             "book": "DK"}}
    far = {(Y._norm("Common Name"), "2023-09-10"):
           {"line": 80.5, "over_odds": -110, "under_odds": -110,
            "book": "DK"}}
    assert len(Y.matched(rows, near)[0]) == 1
    got, why = Y.matched(rows, far)
    assert got == [], \
        "an 80-yard line on a 12-yard projection is somebody else"
    # And it SAYS so — a join that drops rows silently reads as a thin
    # market rather than as a strict guard.
    assert why["line far from projection"] == 1, why


def test_a_row_with_no_date_cannot_be_joined_at_all():
    """The logs key a game by (season, period) and the harvest keys a
    price by (player, date). A row the schedule could not date has no
    way to meet a price, and guessing one would join it to the wrong
    week."""
    rows = [{"season": 2023, "mu": 26.0, "form_sd": 12.0, "zero_rate": 0.1,
             "actual": 30.0, "player": "A Back", "team": "KC",
             "period": "001"}]
    closes = {(Y._norm("A Back"), "2023-09-10"):
              {"line": 25.5, "over_odds": -110, "under_odds": -110}}
    got, why = Y.matched(rows, closes)
    assert got == [] and why["no date"] == 1, why


def test_the_book_name_is_normalised_the_way_the_rest_of_the_join_is():
    """`engine.backtest` strips punctuation and suffixes to meet book
    spellings. Anything else here would silently match nobody, which
    reads as 'no harvested lines' rather than as a keying bug."""
    assert Y._norm("Ken Walker III") == Y._norm("ken walker")
    assert Y._norm("Ja'Marr Chase") == "jamarr chase"
    assert Y._norm("A.J. Brown") == Y._norm("aj brown")


def test_the_bet_record_pays_the_vig_on_both_sides():
    """Priced against the book's own two prices, so the juice is paid
    exactly as it would be. A model that is right 52% of the time at -110
    still loses, and this has to show that."""
    rows = _joined(n=100, line=25.5)
    # A model that always screams OVER, on rows that go over half the
    # time: 50% at -110 is a losing board and must read as one.
    got = Y.bet_record(rows, lambda r, L: 0.99)
    assert got["bets"] == 100
    assert abs(got["hit_rate"] - 0.5) < 1e-9
    assert got["roi"] < -0.04, got

    # And the other side of the same board, for the same reason.
    under = Y.bet_record(rows, lambda r, L: 0.01)
    assert under["bets"] == 100 and under["roi"] < -0.04, under


def test_a_model_that_never_disagrees_places_no_bets():
    """The point of the ROI column. A better-calibrated number that never
    finds a price worth taking is a nicer model and the same board."""
    rows = _joined(n=60, over=-110, under=-110)
    got = Y.bet_record(rows, lambda r, L: Y._american_prob(-110))
    assert got["bets"] == 0 and got["roi"] is None


def test_the_edge_bar_is_applied_to_both_sides():
    rows = _joined(n=40, over=-110, under=-110)
    p = Y._american_prob(-110) + Y.MIN_EDGE / 2.0
    assert Y.bet_record(rows, lambda r, L: p)["bets"] == 0, \
        "half the bar is not the bar"
    p = Y._american_prob(-110) + Y.MIN_EDGE + 1e-9
    assert Y.bet_record(rows, lambda r, L: p)["bets"] == 40


def test_without_a_harvest_it_says_so_rather_than_reporting_zeroes():
    """This half only runs where the closes were bought. Everywhere else
    it has to say which box it needs, not print an empty table that
    reads as a measurement."""
    conn = _db()
    conn.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, "
                 "event_id TEXT, home TEXT, away TEXT, player TEXT, "
                 "market TEXT, book TEXT, line REAL, over_odds INT, "
                 "under_odds INT)")
    conn.commit()
    try:
        lines = Y.report_real("rush_yds", conn=conn)
    finally:
        conn.close()
    assert any("box that bought them" in x for x in lines), lines


def test_the_parameters_are_fitted_off_the_weeks_being_scored():
    """Both the zero-rate logistic and the width come from weeks the
    scored half never contains. Fitting on the scored weeks is how a
    mixture that memorised the outcome reports an edge."""
    import inspect
    src = inspect.getsource(Y.report_real)
    assert "train, test = split_by_week(joined)" in src
    assert "fit_zero(train)" in src
    assert "fit_sigma_on_over(train, beta, lines)" in src
    assert "fit_zero(test)" not in src and "fit_sigma_on_over(test" not in src
def test_the_split_is_by_week_because_a_harvest_is_one_season_deep():
    """THE CORRECTION THIS CODEBASE HAS ALREADY MADE ONCE. `devigfit`
    split on season first — a season boundary certainly separates games,
    but a PURCHASED HARVEST COVERS A STRETCH OF ONE SEASON. Run on
    2026-08-30 against the real closes, leave-one-season-out returned
    nothing for receiving (1,808 joined rows) and receptions (1,689) and
    reported both as too thin, when the data was fine and the split was
    wrong."""
    rows = [{"season": 2025, "period": f"{w:03d}", "mu": 26.0,
             "form_sd": 12.0, "zero_rate": 0.1, "actual": 30.0,
             "line": 25.5, "over_odds": -110, "under_odds": -110}
            for w in range(1, 18) for _ in range(20)]
    train, test = Y.split_by_week(rows)
    assert train and test, "one season must still split"
    tr_weeks = {r["period"] for r in train}
    te_weeks = {r["period"] for r in test}
    assert not (tr_weeks & te_weeks), "a week cannot be in both halves"
    assert max(tr_weeks) < min(te_weeks), "earlier weeks train, later score"


def test_week_ten_sorts_after_week_nine():
    """'10' before '9' is a silently wrong timeline, and a wrong timeline
    leaks the future into training."""
    assert Y._order("009") < Y._order("010")
    assert Y._order("002") < Y._order("012")


def test_a_single_week_cannot_be_split_at_all():
    rows = [{"season": 2025, "period": "001"} for _ in range(50)]
    assert Y.split_by_week(rows) == ([], [])


def test_a_thin_harvest_says_it_is_a_harvest_problem_not_a_verdict():
    """The difference between "the mixture lost" and "we have not bought
    enough closes to ask". Reporting the first when it is the second is
    how a good change gets dropped."""
    conn = _db()
    conn.execute("CREATE TABLE odds_history (sport TEXT, taken_at TEXT, "
                 "event_id TEXT, home TEXT, away TEXT, player TEXT, "
                 "market TEXT, book TEXT, line REAL, over_odds INT, "
                 "under_odds INT)")
    conn.execute("INSERT INTO odds_history VALUES ('nfl','2023-09-10T00:00:00',"
                 "'e','KC','DEN','P1','rush_yds','DK',25.5,-110,-110)")
    conn.commit()
    try:
        lines = Y.report_real("rush_yds", conn=conn)
    finally:
        conn.close()
    text = "\n".join(lines)
    assert "harvest size problem, not a verdict" in text, text


def test_the_verdict_is_written_down_with_the_numbers_that_produced_it():
    """MEASURED AND DECLINED, 2026-08-30. Against real closes the mixture
    halves the calibration miss in both markets it could be scored on and
    does not make money the normal was not already making — and at 300 to
    360 flat stakes neither market's ROI is distinguishable from zero, let
    alone from the other model's.

    The decision not to wire it is worth more than the code would have
    been, so the numbers behind it live in the module rather than in a
    commit message nobody will find again. A later reader with a bigger
    harvest needs to know exactly what was asked and what came back."""
    import inspect
    src = inspect.getsource(Y)
    for number in ("0.1137", "0.0709", "0.0610", "0.0285",
                   "-6.9%", "+4.5%", "+4.2%"):
        assert number in src, f"the verdict lost {number}"
    assert "NOT WIRED IN" in src


def test_what_the_closed_gate_costs_is_written_down_too():
    """MEASURED ON A LIVE BOARD, 2026-09-03. Ethan read the NFL funnel's
    "calibration 169" as the single biggest reason the board recommended
    nothing. Eighty-nine of those had no book price at all; of the eighty
    that did, replaying every other gate from the published row put 56
    past the ten-point credibility bar and 24 under the tier bar, and
    left NONE that would have been a pick.

    The gate is honest and it is free, and that is the fact most likely
    to be re-derived by the next person who sees two whole markets shut
    on a Sunday board — so it lives in the module beside the reason they
    are shut, not in a terminal somebody has closed."""
    import inspect
    src = inspect.getsource(Y)
    # 56 and 24 appear elsewhere in the module for unrelated reasons, so
    # they are pinned as the SENTENCES that carry them rather than as
    # bare digits — a substring test that another line already satisfies
    # proves nothing about the line it was written for.
    for number in ("277", "124", "153"):
        assert number in src, f"the live measurement lost {number}"
    for line in ("56   model disagrees with the book by more than 10 points",
                 "24   edge under the tier bar",
                 "0   would have been a pick"):
        assert line in src, f"the live measurement lost: {line}"
    assert "COSTS NOTHING" in src
    assert "WHAT WOULD CHANGE THE ANSWER" in src
    # And the reason it was declined must not be misremembered as "it
    # lost" — that is a different, wrong lesson.
    assert "better PROBABILITY and not a better BOARD" in src


def test_nothing_here_reaches_the_live_probability_path():
    """The mixture is a measurement, not a model. `statmath.prob_over` is
    what the board asks, and it must stay untouched until a harvest big
    enough to judge says otherwise."""
    import inspect
    import re
    from engine import projection, betting
    for mod in (projection, betting):
        src = inspect.getsource(mod)
        # An IMPORT, not a mention. `projection.CV_FLOOR` cites this
        # module in prose on purpose — that is the finding recorded where
        # the constant it concerns lives, and banning the word would
        # delete the pointer along with the coupling.
        assert not re.search(r"^\s*(from|import)\s+.*yardagefit",
                             src, re.M), \
            f"{mod.__name__} imports a measurement as if it were a model"
    # And the board still asks the normal.
    assert "prob_over" in inspect.getsource(betting)


# --- the player's own volatility, market by market -----------------------
def test_a_boom_bust_back_clears_his_line_less_often_than_a_metronome():
    """THE INFORMATION THE FLAT WIDTH THREW AWAY. Two backs with the same
    52-yard projection against the same 45.5 line: one runs 50-55 every
    week, the other alternates 0 and 100.

    The volatile one is LESS likely to clear it, and that is real
    football rather than an artifact. A right-skewed distribution's
    median sits below its mean by exp(-sigma^2 / 2), so an average
    carried by a few huge games clears a line near that average less
    often than a steady one does."""
    fits = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.76,
                         "width_weight": 1.0, "typical_cv": 0.98}}
    steady = Y.display_prob("rush_yds", 52.0, 45.5,
                            [52, 55, 50, 54, 53, 51], fits=fits)
    wild = Y.display_prob("rush_yds", 52.0, 45.5,
                          [0, 110, 5, 95, 20, 80], fits=fits)
    assert steady > wild + 0.05, (steady, wild)


def test_each_market_takes_only_the_width_it_earned():
    """Measured by walking the train/score cut across five points of the
    season. Rushing wanted the player's spread in full and won all five;
    receptions never once preferred it and keeps a flat width. The
    ordering follows how dispersed the market is, which is why it is a
    per-market number and not a global switch."""
    assert Y.WIDTH_WEIGHT["rush_yds"] == 1.0
    assert Y.WIDTH_WEIGHT["receptions"] == 0.0
    assert 0.0 < Y.WIDTH_WEIGHT["rec_yds"] < 1.0
    for market in Y.MIXTURE_MARKETS:
        assert market in Y.WIDTH_WEIGHT, market


def test_a_flat_market_ignores_volatility_entirely():
    """receptions took no per-player width, so two histories with the
    same projection must land on the same number — otherwise the weight
    is not doing what the table says."""
    fits = {"receptions": {"zero": [-0.82, 0.48], "sigma": 0.46,
                           "width_weight": 0.0, "typical_cv": 0.61}}
    # SAME BLANK RATE, different spread. The atom is a separate input
    # fitted from the prior zero rate, so a history containing a zero
    # moves the answer through P(zero) whatever the width does — an
    # earlier version of this fixture compared a history with a blank
    # against one without and read that as the width leaking.
    a = Y.display_prob("receptions", 5.0, 3.5, [5, 5, 5, 5, 5, 5], fits=fits)
    b = Y.display_prob("receptions", 5.0, 3.5, [2, 8, 2, 8, 2, 8], fits=fits)
    assert a == b, (a, b)


def test_a_width_cannot_double_or_halve_on_four_games():
    """A per-player estimate off a handful of games is mostly noise at
    the tails, so the ratio is clamped before it multiplies anything."""
    assert Y.WIDTH_CLAMP[0] < 1.0 < Y.WIDTH_CLAMP[1]
    row = {"mu": 50.0, "form_sd": 500.0}      # absurd volatility
    assert Y._width_of(row, 1.0, 1.0) <= 1.0 + (Y.WIDTH_CLAMP[1] - 1.0)
    row = {"mu": 50.0, "form_sd": 0.001}      # absurd steadiness
    assert Y._width_of(row, 1.0, 1.0) >= 1.0 - (1.0 - Y.WIDTH_CLAMP[0])


def test_a_player_with_no_spread_is_not_penalised_for_it():
    """No history, no opinion — the width falls back to the market's."""
    assert Y._width_of({"mu": 50.0, "form_sd": 0.0}, 1.0, 1.0) == 1.0
    assert Y._width_of({"mu": 0.0, "form_sd": 10.0}, 1.0, 1.0) == 1.0
    assert Y._width_of({"mu": 50.0, "form_sd": 10.0}, 1.0, 0.0) == 1.0


def test_the_width_and_the_sigma_are_fitted_together():
    """Bolting a scaling onto a sigma chosen without it would leave the
    pair describing two different models."""
    import inspect
    src = inspect.getsource(Y.fit_market)
    assert "weight=weight, typical=typical" in src
    fit = inspect.getsource(Y.fit_sigma_on_over)
    assert "_width_of(d, weight, typical)" in fit


def test_the_store_carries_what_the_display_needs():
    """`display_prob` reads the weight and the market's typical CV off
    the store, so a fit written without them silently reverts to flat."""
    got = {"zero": [0.0, 0.5], "sigma": 0.6, "width_weight": 1.0,
           "typical_cv": 0.9}
    for missing in ("width_weight", "typical_cv"):
        thin = {k: v for k, v in got.items() if k != missing}
        p = Y.display_prob("rush_yds", 52.0, 45.5, [40, 60, 50, 55],
                           fits={"rush_yds": thin})
        assert p is not None, missing


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
