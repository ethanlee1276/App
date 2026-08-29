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
    M_MIN, M_MAX, K_MIN, K_MAX, MIN_SPLIT, PIN_TOL, BANDS, TRAIN_SHARE,
    log_loss, proportional, power, split, compare, band_lines, report_lines,
    haircut_lines, _fit,
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
def test_the_split_keeps_whole_games_on_one_side():
    """Players in one game share a scoreboard. A random split leaves the
    same game in both halves, so the test set is partly memorised and the
    more flexible transform wins on that alone."""
    rows = _market(600, truth=lambda r: r)
    train, test = split(rows)
    assert train and test
    train_keys = {(r["season"], r["week"]) for r in train}
    test_keys = {(r["season"], r["week"]) for r in test}
    assert not (train_keys & test_keys)
    # And the held-out side is the LATER one — training on the future to
    # predict the past is not a held-out test of anything.
    assert min(test_keys) > max(train_keys)


def test_one_season_of_harvested_closes_can_still_be_split():
    """The bug the first live run found. The split used to cut on SEASON,
    reasoning that a season boundary certainly separates games. It does —
    but a purchased harvest covers a stretch of ONE season, so on 3,890
    joined NFL player-weeks it produced 0 train and 0 test and reported
    the data as too thin when the data was fine.

    A week boundary separates games just as completely and works inside a
    season, which is the only shape this data comes in."""
    rows = _market(4000, seasons=(2025,), truth=lambda r: r ** 1.3)
    train, test = split(rows)
    assert train and test
    assert len({r["season"] for r in rows}) == 1
    got = compare(rows)
    assert not got["thin"], got
    # It fits and reports rather than refusing. NOT that power wins: at
    # 4,000 rows the planted exponent is recovered (k near 1.3) but the
    # two methods land 0.0002 apart, inside this module's own "not a
    # result" band. That is the honest answer at this sample size and it
    # is worth knowing — the live NFL harvest is 3,890 rows.
    assert abs(got["k"] - 1.3) < 0.1, got["k"]
    assert got["margin"] < 0.0005


def test_the_split_orders_weeks_as_numbers_not_as_text():
    """Week 10 comes after week 9. Sorted as text it does not, and a
    wrong timeline leaks the future into training silently."""
    rows = [{"season": 2025, "week": w, "market": 0.3, "scored": 0}
            for w in ("1", "2", "3", "9", "10")]
    train, test = split(rows)
    assert {r["week"] for r in test} == {"10"}


def test_a_college_period_is_a_date_and_still_orders():
    """An NFL log's period is a week number; a college log's is a date.
    Both have to sort, and neither may crash the other."""
    rows = [{"season": 2026, "week": d, "market": 0.3, "scored": 0}
            for d in ("2026-08-29", "2026-09-05", "2026-09-12", "2026-09-19")]
    train, test = split(rows)
    assert {r["week"] for r in test} == {"2026-09-19"}
    mixed = rows + [{"season": 2025, "week": "17", "market": 0.3, "scored": 0}]
    assert split(mixed)[0]                       # does not raise


def test_most_of_the_timeline_trains():
    assert 0.5 < TRAIN_SHARE < 0.9
    rows = _market(1000, seasons=(2025,), truth=lambda r: r)
    train, test = split(rows)
    assert len(train) > len(test)


def test_a_single_week_cannot_be_split_and_says_so():
    """One week of closes has no later week to score on, and that has to
    read as "not enough data" rather than as a verdict."""
    rows = [{"season": 2025, "week": "1", "market": 0.3, "scored": 0}
            for _ in range(600)]
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


def test_the_band_table_scores_both_methods_in_every_band():
    """Where the two disagree is the point, so the ends get checked
    separately — a method that wins overall while being wrong at one end
    has not earned that end. Replaced a "nearer" column, which called a
    rounding error a win and hid how badly the loser lost."""
    rows = _market(20000, truth=lambda r: r ** 1.30, seed=23)
    lines = band_lines(rows, 1.25, 1.30)
    body = [ln for ln in lines[1:] if ln.strip().startswith("0.")
            and "thin" not in ln]
    assert body
    for ln in body:
        float(ln.split()[-1])              # power z parses
        float(ln.split()[-2])              # prop z parses
    # The planted truth IS the power transform, so its total miss should
    # be the smaller one rather than merely winning more bands.
    chi = [ln for ln in lines if "chi-square" in ln][0]
    prop_chi = float(chi.split("proportional")[1].split()[0])
    power_chi = float(chi.split("power")[1].split()[0])
    assert power_chi < prop_chi


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


# --- reading the bands ----------------------------------------------------
def _at(band_rates, n=900):
    """Rows whose realised rate is set exactly, band by band."""
    rows = []
    for (lo, hi), (raw, act) in zip(BANDS, band_rates):
        hits = int(round(act * n))
        for i in range(n):
            # Spread across weeks so `split` has a timeline to cut on —
            # a helper that parks every row in one week makes every
            # caller look "too thin" for reasons of its own making.
            rows.append({"season": 2025, "week": str(1 + i % 6),
                         "market": raw, "scored": 1 if i < hits else 0})
    return rows


def test_the_bands_carry_error_bars():
    """Without them the table misleads. The first live run showed power
    "nearer" in two bands and proportional in three, which reads as a coin
    flip — scored against each band's standard error, proportional matched
    four bands almost exactly and missed one by 3.1 sigma while power was
    mediocre in all five. Same numbers, completely different diagnosis."""
    rows = _at([(0.058, 0.050), (0.135, 0.088), (0.226, 0.193),
                (0.352, 0.321), (0.547, 0.465)])
    lines = band_lines(rows, 1.1606, 1.1236)
    assert "prop z" in lines[0] and "power z" in lines[0]
    assert any("chi-square" in ln for ln in lines)


def test_a_band_the_shape_misses_shows_up_as_a_big_z():
    """The whole point: one band at 3 sigma is where the shape is wrong,
    whatever the summary log loss says."""
    rows = _at([(0.058, 0.050), (0.135, 0.088), (0.226, 0.193),
                (0.352, 0.321), (0.547, 0.465)])
    lines = band_lines(rows, 1.1606, 1.1236)
    body = [ln for ln in lines[1:] if ln.strip().startswith("0.")]
    zs = [float(ln.split()[-2]) for ln in body]
    assert max(abs(z) for z in zs) > 2.5
    # and it is the 0.10-0.18 band, not a random one
    assert abs(zs[1]) == max(abs(z) for z in zs)


def test_the_haircut_column_shows_the_shape_without_either_method():
    """Both transforms are attempts to predict what the market charged.
    Seeing that column directly says whether either shape is the right
    family at all — and on the live data it was not: four bands near 14%
    and one at 35% is flat-plus-a-spike, not a smooth curve."""
    rows = _at([(0.058, 0.050), (0.135, 0.088), (0.226, 0.193),
                (0.352, 0.321), (0.547, 0.465)])
    lines = haircut_lines(rows)
    cuts = [float(ln.split()[-1].rstrip("%")) for ln in lines[2:]]
    assert len(cuts) == 5
    flat = [cuts[0], cuts[2], cuts[3], cuts[4]]
    assert max(flat) - min(flat) < 10        # four bands cluster
    assert cuts[1] > max(flat) + 15          # one spikes well clear


def test_the_report_says_what_the_data_did_and_did_not_settle():
    """Both methods beating the raw price IS a result and must be stated;
    the choice between them was not, and must not be dressed up as one."""
    rows = _at([(0.058, 0.050), (0.135, 0.088), (0.226, 0.193),
                (0.352, 0.321), (0.547, 0.465)], n=400)
    text = "\n".join(report_lines(rows, min_split=1))
    assert "not settled" in text
    assert "beat the raw price" in text


# --- both sports ----------------------------------------------------------
def test_the_join_reads_outcomes_from_the_logs_not_from_a_replay():
    """The shape question is about the BOOK's number, so the model plays
    no part — and running a replay to learn who scored would drag a
    model into a measurement that does not involve it. The touchdown
    outcome is a column in the logs."""
    import ast
    import inspect
    from engine import devigfit
    fn = next(n for n in ast.walk(ast.parse(inspect.getsource(devigfit)))
              if isinstance(n, ast.FunctionDef) and n.name == "collected")
    names = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "run" not in names, "collected is replaying a model again"
    sql = " ".join(n.value for n in ast.walk(fn)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str))
    assert "player_game_logs" in sql
    assert "anytime_td" in sql


def test_college_is_wired_through_the_same_fitter():
    """One module, both sports. The only real difference is the bridge to
    a date — an NFL log's period is a week number and the schedule
    supplies the date, while a college log's period IS the date — and
    that difference has to be visible in the code rather than left for
    college to silently join nothing."""
    import ast
    import inspect
    from engine import devigfit
    src = inspect.getsource(devigfit)
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "collected")
    consts = {n.value for n in ast.walk(fn)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "nfl" in consts, "collected does not branch on sport at all"
    assert "sport" in inspect.signature(devigfit.collected).parameters


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
