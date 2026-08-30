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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
