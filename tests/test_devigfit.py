"""Deciding how the touchdown market shares its vig out.

`engine/devig` defaults to the power method on an argument. This module
is what turns the argument into a measurement, so its own honesty is what
matters: the split has to be by season, the fit has to be one parameter
each, and a tie has to read as a tie rather than as a winner.

The tests build synthetic markets whose true generating transform is
known, and check the fitter recovers it. Nothing here reads the database.

Run directly: `python3 tests/test_devigfit.py`
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.devigfit import (
    M_MIN, M_MAX, K_MIN, K_MAX, MIN_SPLIT, PIN_TOL, BANDS,
    log_loss, proportional, power, split, compare, band_lines, report_lines,
    _fit,
)


def _market(n, seasons=(2023, 2024, 2025), truth=None, seed=1):
    """Player-weeks whose scoring follows `truth(raw)` exactly."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        raw = rng.uniform(0.06, 0.60)
        p = truth(raw)
        rows.append({"season": seasons[i % len(seasons)],
                     "week": 1 + i % 18, "market": raw,
                     "scored": 1 if rng.random() < p else 0})
    return rows


# --- the loss -------------------------------------------------------------
def test_log_loss_prefers_the_truth():
    outcomes = [1] * 300 + [0] * 700
    honest = [0.30] * 1000
    over = [0.50] * 1000
    under = [0.10] * 1000
    assert log_loss(honest, outcomes) < log_loss(over, outcomes)
    assert log_loss(honest, outcomes) < log_loss(under, outcomes)


def test_log_loss_survives_a_certainty():
    """A probability of 0 on an event that happened is infinite surprise,
    and a fitter that returns inf cannot be compared to anything."""
    assert log_loss([0.0], [1]) < 20.0
    assert log_loss([1.0], [0]) < 20.0


# --- the fit --------------------------------------------------------------
def test_the_fitter_recovers_a_planted_multiplier():
    rows = _market(20000, truth=lambda r: r / 1.25, seed=7)
    m = _fit(rows, proportional, M_MIN, M_MAX)
    assert abs(m - 1.25) < 0.03, m


def test_the_fitter_recovers_a_planted_exponent():
    rows = _market(20000, truth=lambda r: r ** 1.30, seed=11)
    k = _fit(rows, power, K_MIN, K_MAX)
    assert abs(k - 1.30) < 0.04, k


def test_the_fitter_leaves_an_honest_book_alone():
    """A market with no vig must fit at the identity, not invent one."""
    rows = _market(20000, truth=lambda r: r, seed=13)
    assert abs(_fit(rows, proportional, M_MIN, M_MAX) - 1.0) < 0.03
    assert abs(_fit(rows, power, K_MIN, K_MAX) - 1.0) < 0.04


# --- the comparison -------------------------------------------------------
def test_a_power_market_is_called_for_power():
    got = compare(_market(20000, truth=lambda r: r ** 1.30, seed=3))
    assert not got["thin"]
    assert got["winner"] == "power"
    assert got["margin"] > 0.0005
    assert not got["k_pinned"]


def test_a_proportional_market_is_called_for_proportional():
    """The measurement has to be able to come back against the default,
    or it is not a measurement."""
    got = compare(_market(20000, truth=lambda r: r / 1.30, seed=5))
    assert not got["thin"]
    assert got["winner"] == "proportional"
    assert got["margin"] > 0.0005


def test_the_two_methods_tie_on_a_market_that_cannot_tell_them_apart():
    """They differ only in shape, so a book with almost no hold gives
    almost no shape to see — and the report must say so rather than
    crowning whichever fit was luckier."""
    got = compare(_market(20000, truth=lambda r: r * 0.99, seed=17))
    assert got["margin"] < 0.0005
    assert any("not a result" in ln for ln in report_lines(
        _market(20000, truth=lambda r: r * 0.99, seed=17)))


def test_a_boundary_fit_is_reported_as_a_failure_not_an_answer():
    """A parameter pinned at its bound means the search could not place
    the market, and printing it as a number invites someone to use it.

    The check needs a tolerance: a section search that runs all the way
    to the edge stops a hair inside it, so an exact `M_MIN < m` comparison
    never fires and every failed fit reads as a clean answer. This market
    is one a de-vig cannot describe — the book UNDERSTATES every price —
    and both fits should run to the floor and say so."""
    got = compare(_market(8000, truth=lambda r: min(0.99, r * 3.0), seed=19))
    assert got["m"] < M_MIN + PIN_TOL and got["k"] < K_MIN + PIN_TOL
    assert got["m_pinned"] and got["k_pinned"]
    assert any("AT THE BOUND" in ln for ln in
               report_lines(_market(8000, truth=lambda r: min(0.99, r * 3.0),
                                    seed=19)))


# --- the split ------------------------------------------------------------
def test_the_split_is_by_season_not_at_random():
    """Players in one game share a scoreboard. A random split leaves the
    same game in both halves, so the test set is partly memorised and the
    more flexible transform wins on that alone."""
    rows = _market(600, truth=lambda r: r)
    train, test = split(rows)
    assert train and test
    train_seasons = {r["season"] for r in train}
    test_seasons = {r["season"] for r in test}
    assert not (train_seasons & test_seasons)
    assert test_seasons == {max(r["season"] for r in rows)}


def test_one_season_cannot_be_split_and_says_so():
    rows = _market(600, seasons=(2025,), truth=lambda r: r)
    assert split(rows) == ([], [])
    got = compare(rows)
    assert got["thin"]
    assert any("too thin to split" in ln for ln in report_lines(rows))


def test_a_thin_join_refuses_to_report():
    rows = _market(MIN_SPLIT, truth=lambda r: r)
    got = compare(rows)
    assert got["thin"]


# --- the bands ------------------------------------------------------------
def test_the_bands_cover_every_price_exactly_once():
    assert BANDS[0][0] == 0.0 and BANDS[-1][1] > 1.0
    for (a_lo, a_hi), (b_lo, b_hi) in zip(BANDS, BANDS[1:]):
        assert a_hi == b_lo


def test_the_band_table_names_the_nearer_method_per_band():
    """Where the two disagree is the point, so the ends get checked
    separately — a method that wins overall while being wrong at the
    short end has not earned the short end."""
    rows = _market(20000, truth=lambda r: r ** 1.30, seed=23)
    lines = band_lines(rows, 1.25, 1.30)
    body = [ln for ln in lines[1:] if "thin" not in ln]
    assert body
    assert all(ln.split()[-1] in ("power", "prop", "tie") for ln in body)
    # The planted truth IS the power transform, so it should win the
    # bands it is measured on rather than only the summary number.
    assert sum(1 for ln in body if ln.endswith("power")) > len(body) / 2


def test_a_thin_band_is_marked_rather_than_averaged():
    rows = [{"season": 2024, "week": 1, "market": 0.5, "scored": 1}] * 5
    assert all("thin" in ln for ln in band_lines(rows, 1.2, 1.2)[1:])


# --- the module's own claim -----------------------------------------------
def test_it_asks_about_the_book_not_about_us():
    """The shape question is what the BOOK's number means. Letting the
    model's own probability into the join would make it a question about
    whether we beat the book, which `engine.tdbook` already answers and
    which cannot decide a de-vig."""
    import ast
    import inspect
    from engine import devigfit
    tree = ast.parse(inspect.getsource(devigfit))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "collected")
    keys = {n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "market" in keys and "scored" in keys
    assert "prob" not in keys, "the model's probability leaked into the join"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
