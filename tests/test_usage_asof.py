"""The replay measured a model the live board does not run.

`engine/projection.build_projection` takes a `usage` bridge — the
player's recent opportunities times season efficiency — and blends it
against observed form by sample size. At `USAGE_PRIOR_GAMES` games of log
the two weigh equally, so early in a season the bridge supplies half the
projection's base.

`nfl_build` passes it. `engine/backtest.py` passed nothing, and the
reason was sound: `nflusage.volume_roles` read every week of the season,
so replaying week 7 with 22 weeks on disk would have handed the model its
own answers. Measured on 2024, one player's bridge read 4.75 targets per
game at 5.55 yards a target across the full season and 2.5 at 3.08 as of
week 7 — a factor of three on what it contributes.

So the walk avoided the leak by switching the layer off, and every
calibration fitted through it, plus every AUC read off it, described a
different model from the one taking bets. That is the proxy-line mistake
one level up: fit against one opponent, apply against another.

`volume_roles` takes a week cutoff now, and the replay passes it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import nflusage


def _conn():
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, "
              "period TEXT, game_id TEXT, player TEXT, team TEXT, "
              "opponent TEXT, position TEXT, home INTEGER, market TEXT, "
              "value REAL)")
    return c


def _log(c, week, market, value, player="A.Back", team="LV"):
    c.execute("INSERT INTO player_game_logs (sport, season, period, player, "
              "team, market, value) VALUES ('nfl', 2024, ?, ?, ?, ?, ?)",
              ("%03d" % week, player, team, market, value))


def _busy(c, weeks, carries=25.0, yards=100.0):
    for w in weeks:
        _log(c, w, "carries", carries)
        _log(c, w, "rush_yds", yards)


# --- the cutoff keeps out what had not happened -------------------------------
def test_a_cutoff_excludes_the_week_being_predicted():
    """Strictly before: week 7's own game is the thing being forecast."""
    c = _conn()
    _busy(c, range(1, 8))
    role = nflusage.volume_roles(c, 2024, upto_week=7)[("a", "back", "LV")]
    assert role["rush_yds"]["n_weeks"] == 6


def test_a_cutoff_excludes_every_later_week_too():
    c = _conn()
    _busy(c, range(1, 5))                      # the real past
    _busy(c, range(5, 19), carries=1.0, yards=2.0)   # the unknown future
    role = nflusage.volume_roles(c, 2024, upto_week=5)[("a", "back", "LV")]
    assert role["rush_yds"]["opp_per_game"] == 25.0, \
        "a later collapse in usage leaked backwards into week 5"
    assert role["rush_yds"]["eff"] == 4.0


def test_without_a_cutoff_the_whole_season_still_comes_back():
    """Live callers pass no cutoff and must keep the behaviour they had —
    their database only holds games that have been played."""
    c = _conn()
    _busy(c, range(1, 19))
    role = nflusage.volume_roles(c, 2024)[("a", "back", "LV")]
    assert role["rush_yds"]["n_weeks"] == 18


def test_the_week_filter_compares_numbers_not_strings():
    """`period` is TEXT and the cutoff is an int, and SQLite orders every
    integer below every string — so an uncast `period < 10` matches
    nothing at all, silently turning the bridge off for the whole replay
    instead of raising."""
    c = _conn()
    _busy(c, [1, 2, 3, 9, 10, 11, 12])
    role = nflusage.volume_roles(c, 2024, upto_week=10)[("a", "back", "LV")]
    assert role["rush_yds"]["n_weeks"] == 4          # weeks 1, 2, 3, 9

    # And the failure it prevents runs the WRONG way, which is why the
    # CAST is load-bearing rather than tidy. SQLite gives the integer 10
    # the column's TEXT affinity and compares lexicographically, where
    # '010' < '10' because '0' < '1' — so every row matches and the
    # cutoff silently passes the whole season through. A filter that
    # returned nothing would have been caught the first time it ran.
    rows = 7 * 2                                    # carries + rush_yds
    naive = c.execute("SELECT COUNT(*) FROM player_game_logs "
                      "WHERE period < 10").fetchone()[0]
    assert naive == rows, (
        "SQLite's affinity rules changed; re-check that volume_roles' "
        "CAST is still what stops the cutoff leaking the whole season")
    cast = c.execute("SELECT COUNT(*) FROM player_game_logs "
                     "WHERE CAST(period AS INTEGER) < 10").fetchone()[0]
    assert cast == 4 * 2


def test_a_cutoff_before_any_game_yields_no_role_rather_than_a_junk_one():
    c = _conn()
    _busy(c, range(1, 19))
    assert nflusage.volume_roles(c, 2024, upto_week=1) == {}


def test_the_recent_window_still_takes_the_latest_weeks_under_the_cutoff():
    c = _conn()
    _busy(c, range(1, 5), carries=2.0, yards=8.0)
    _busy(c, range(5, 9), carries=20.0, yards=80.0)
    role = nflusage.volume_roles(c, 2024, upto_week=9)[("a", "back", "LV")]
    assert role["rush_yds"]["opp_per_game"] == 20.0, \
        f"VOL_WEEKS={nflusage.VOL_WEEKS} should cover weeks 5-8 only"


# --- and the maps carry it through -------------------------------------------
def test_build_usage_maps_passes_the_cutoff_down():
    c = _conn()
    _busy(c, range(1, 19))
    maps = nflusage.build_usage_maps(c, 2024, upto_week=5)
    assert maps["volume"][("a", "back", "LV")]["rush_yds"]["n_weeks"] == 4


def test_build_usage_maps_still_works_with_no_arguments():
    c = _conn()
    _busy(c, range(1, 19))
    assert nflusage.build_usage_maps(c)["volume"]


# --- the replay actually runs the layer now ----------------------------------
def test_the_replay_builds_the_bridge_as_of_the_week_it_is_replaying():
    import inspect
    from engine import backtest
    src = inspect.getsource(backtest.backtest_from_stats)
    assert "build_usage_maps(usage_conn, season, upto_week=w)" in src
    assert "nfl_usage=usage" in src


def test_the_calibration_fitter_asks_for_it():
    """propcal fits the corrections the live board applies, so its replay
    is the one that most has to be the live model."""
    import inspect
    from engine import propcal
    assert "usage_conn=conn" in inspect.getsource(propcal.fit)


def test_a_replay_without_a_connection_is_unchanged():
    """Opt-in: callers that pass no connection keep exactly the behaviour
    they had, so this cannot quietly move a number nobody re-measured."""
    import inspect
    from engine import backtest
    src = inspect.getsource(backtest.backtest_from_stats)
    assert "usage = None" in src and "if usage_conn is not None:" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
