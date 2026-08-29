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
def test_the_market_being_right_is_named():
    """The longshot tail, as the record already suggests: the model says
    30%, the book says 20%, and 20% is what happens."""
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.20)))
    assert "the MARKET was nearer" in text


def test_the_model_being_right_is_named():
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.30)))
    assert "the MODEL was nearer" in text


def test_a_tie_is_not_awarded_to_either():
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.25)))
    assert "too close to separate" in text


def test_each_band_gets_its_own_verdict():
    """The finding is that the answer differs by band — the model is
    under the market on favourites and over it on longshots — so one
    verdict for the whole sample would average the two away."""
    rows = _rows(200, 0.30, 0.20, 0.20) + _rows(200, 0.50, 0.62, 0.62)
    text = "\n".join(tdbook.report_lines(rows))
    assert text.count("the MARKET was nearer") == 2


def test_the_vig_is_disclosed_rather_than_removed():
    """Implied probability from one side carries the hold, so every
    market column reads high. Saying so beats a de-vig that needs the
    other side and would quietly drop every one-sided quote."""
    text = "\n".join(tdbook.report_lines(_rows(200, 0.30, 0.20, 0.20)))
    assert "includes the vig" in text


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
