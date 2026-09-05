"""Where the touchdown model disagrees with the market, by price.

The Week 1 board showed a shape. Every value pick sat ABOVE the book by
about four points at +300 to +650, while the watchlist sat six to eleven
points BELOW it on favourites at -150 to -265:

    Jahmyr Gibbs     model 0.576   book 0.685
    Jonathan Taylor  model 0.502   book 0.587
    Jauan Jennings   model 0.283   book 0.236
    Greg Dortch      model 0.165   book 0.126

A model flatter than the market at both ends — and the board only bets
one of those ends. `engine.tdbacktest` grades against outcomes and
cannot see it: a model can be well calibrated on average and wrong in
exactly the band it chooses to bet, which is what 51 book-priced bets at
30.5% claimed and 11.8% delivered already suggested.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tdbook


def _rows(n, model, market, hit_rate):
    hits = int(round(n * hit_rate))
    return [(model, market, 1 if i < hits else 0) for i in range(n)]


# --- the arithmetic -----------------------------------------------------------
def test_a_price_becomes_its_implied_probability():
    assert abs(tdbook._prob(-110) - 110 / 210) < 1e-9
    assert abs(tdbook._prob(300) - 0.25) < 1e-9
    assert tdbook._prob(0) is None
    assert tdbook._prob(None) is None


def test_rows_land_in_the_band_their_MARKET_price_names():
    """Bucketed by the market, not by the model. Bucketing by our own
    number would sort the picks by how wrong we were and hide it."""
    rows = _rows(50, 0.30, 0.20, 0.2) + _rows(50, 0.30, 0.50, 0.5)
    got = {(b["lo"], b["hi"]): b["n"] for b in tdbook.bands(rows, min_band=1)}
    assert got[(0.15, 0.25)] == 50
    assert got[(0.40, 0.60)] == 50


def test_a_thin_band_says_so_instead_of_reporting_a_rate():
    got = tdbook.bands(_rows(5, 0.30, 0.20, 0.2), min_band=40)
    assert all(b["thin"] for b in got if b["n"] < 40)
    assert "too few to read" in "\n".join(tdbook.report_lines(
        _rows(5, 0.30, 0.20, 0.2)))


# --- the verdict --------------------------------------------------------------
def test_the_model_is_graded_against_reality_not_against_the_book():
    """anytime_td is Yes-only, so the implied probability keeps its whole
    hold and reads high by construction. The first version of this report
    scored the market against the outcome too and named a winner, which
    convicted the book of its own vig."""
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.20)))
    assert "model +50% vs reality" in text
    assert "was nearer" not in text


def test_a_model_that_matches_reality_says_so_without_a_sign():
    """A hair either side of zero printed "-0%", which reads as a
    direction it does not have."""
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.30)))
    assert "matches reality" in text
    assert "-0%" not in text and "+0%" not in text


def test_under_estimating_reads_negative():
    text = "\n".join(tdbook.report_lines(_rows(200, 0.12, 0.20, 0.17)))
    assert "model -29% vs reality" in text


def test_each_band_is_graded_on_its_own():
    """The finding is that the error changes sign by band: measured, the
    model runs +24% in the 0-15% band and -29% in the two above it. One
    number for the whole sample averages that away."""
    rows = _rows(200, 0.063, 0.087, 0.051) + _rows(200, 0.205, 0.317, 0.290)
    text = "\n".join(tdbook.report_lines(rows))
    # +26 not +24 because 200 rows cannot hold a rate of exactly 0.051;
    # on the real 2,691 player-weeks the two bands read +24% and -29%.
    assert "model +26% vs reality" in text
    assert "model -29% vs reality" in text


def test_the_vig_is_disclosed_rather_than_removed():
    """Implied probability from one side carries the hold, so every
    market column reads high. Saying so beats a de-vig that needs the
    other side and would quietly drop every one-sided quote."""
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.20)))
    assert "keeps its whole hold" in text
    assert "context, not a competitor" in text


def test_no_closes_is_said_plainly():
    assert "no player-week joined" in "\n".join(tdbook.report_lines([]))


# --- the replay it reads from -------------------------------------------------
def test_the_replay_prices_the_model_the_board_runs():
    """engine/touchdowns blends its share toward the xFP share. A replay
    that leaves that out fits a calibration for a model nobody runs — the
    fault engine/backtest had with the usage bridge, and the reason
    nflusage.xfp_roles exists."""
    import inspect
    from engine import tdbacktest
    src = inspect.getsource(tdbacktest.run)
    assert "xfp=xfp" in src
    assert 'team_week.get((season, w, team), {}).get("xfp"' in src


def test_the_replay_reads_xfp_from_earlier_weeks_only():
    import inspect
    from engine import tdbacktest
    src = inspect.getsource(tdbacktest.run)
    assert '_prior_form(weeks, prior, "xfp")' in src


def test_the_replay_can_hand_out_the_identity_it_does_not_grade_on():
    """Without the player there is nothing to join a price to."""
    import inspect
    from engine import tdbacktest
    src = inspect.getsource(tdbacktest.run)
    assert 'collect({"season"' in src and '"player": display.get' in src


def test_collecting_is_optional_and_off_by_default():
    import inspect
    from engine import tdbacktest
    assert "collect=None" in inspect.getsource(tdbacktest.run)
    assert "if collect is not None:" in inspect.getsource(tdbacktest.run)


def test_the_join_uses_the_player_and_his_own_game_date():
    """A week holds a Thursday, a Sunday and a Monday, and those are
    three different closes."""
    import inspect
    src = inspect.getsource(tdbook.joined)
    assert 'dates.get((r["season"], int(r["week"]), r["team"]))' in src
    assert "_norm(r[\"player\"])" in src


# --- fitting on the population that gets bet ---------------------------------
def test_the_fit_needs_a_real_book_priced_population():
    """Above calibrate.fit's own floor, for propcal's reason: a
    correction fitted here replaces one that is already live."""
    import inspect
    assert tdbook.MIN_FIT >= 800
    src = inspect.getsource(tdbook.fit)
    assert "if len(rows) < min_fit:" in src
    assert "joined(conn" in src, "it must fit on the joined subset"
    assert "BASIS_BOOK" in src, "so a proxy-population fit cannot overwrite it"


def test_a_thin_sample_is_refused_by_name():
    assert "needs" in "\n".join(tdbook.fit_lines(None, [1] * 10))


def test_the_report_shows_what_the_fit_does_to_every_band():
    """Adopting on the Brier line alone is how this went wrong the first
    time: T=1.12 bias=+0.20 improved average Brier from 0.1458 to 0.1435
    and took the 0-15% band from +24% to +94% against reality."""
    from engine.calibrate import Calibration
    got = Calibration(temperature=1.12, intercept=0.20, samples=2691,
                      brier_before=0.1458, brier_after=0.1435)
    rows = _rows(995, 0.063, 0.087, 0.051) + _rows(659, 0.205, 0.317, 0.290)
    text = "\n".join(tdbook.fit_lines(got, rows))
    assert "BOOK-PRICED" in text
    assert "0.063 → 0.099" in text, text
    assert "+23% → +93%" in text, text


def test_a_squared_objective_prices_the_longshot_band_at_nothing():
    """Not a fitter defect — the reason any Brier-minimising correction
    sells the tail to buy the top. Three points wrong at p=0.05 costs a
    sixteenth of what twelve points wrong at p=0.6 does."""
    cheap = (0.08 - 0.05) ** 2
    dear = (0.60 - 0.48) ** 2
    assert dear / cheap > 15


def test_the_docstring_records_that_narrowing_alone_did_not_fix_it():
    import inspect
    src = inspect.getsource(tdbook.fit)
    assert "IT IS NOT ENOUGH" in src
    assert "stays with a person" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
