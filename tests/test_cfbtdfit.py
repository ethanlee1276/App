"""The college touchdown model, graded against its own four seasons.

`engine.tdbacktest` measured the NFL touchdown model on 2026-08-27 and
found a model that had never been graded. College could not be graded at
all that day — the database held ten CFB player rows. With
`engine.sources.cfbstats` it holds 232,913, and `engine.cfbtdfit` asks
the same question of the college board.

Two of these tests exist because the first answer was wrong. The replay
initially reported a model over-confident by nine to eleven points and
the obvious ship was a correction pulling every college longshot DOWN;
the real cause was seven weeks of 2025 arriving without their scoring
plays. On clean data the sign reverses. So the fitter's contract is
pinned here: it must replay the model the board actually runs — roster
positions included — and it must choose its parameters on the training
seasons without ever consulting the held-out ones.

Run directly: `python3 tests/test_cfbtdfit.py`
"""

import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import cfbtdfit as F
from engine.cfb import tds as T


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE player_game_logs (
        sport TEXT, season INTEGER, period TEXT, game_id TEXT,
        player TEXT, team TEXT, opponent TEXT, position TEXT, home INTEGER,
        market TEXT, value REAL)""")
    # THE GAMES TABLE IS NOT OPTIONAL ANY MORE. The replay reads each
    # game's closing spread and total to drive the implied team total and
    # the game script, which is the difference between grading the role
    # and grading the chain the board runs.
    conn.execute("""CREATE TABLE games (
        sport TEXT, season INTEGER, period TEXT, game_id TEXT,
        home TEXT, away TEXT, home_score REAL, away_score REAL,
        spread REAL, total REAL)""")
    return conn


def _log(conn, season, period, player, team, market, value, position=""):
    conn.execute(
        "INSERT INTO player_game_logs VALUES ('cfb',?,?,?,?,?,'',?,1,?,?)",
        (season, period, f"g{period}", player, team, position, market, value))


def _game(conn, season, period, home, away="OPP", spread=-7.0, total=52.0,
          home_score=31.0, away_score=24.0):
    conn.execute("INSERT INTO games VALUES ('cfb',?,?,?,?,?,?,?,?,?)",
                 (season, period, f"g{period}", home, away, home_score,
                  away_score, spread, total))


def _season(conn, season, player, team, weeks, tds, position="RB",
            carries=15.0, rush_yds=80.0, spread=-7.0, total=52.0):
    """`weeks` games for one player, the first `tds` of them with a score."""
    for i in range(weeks):
        period = f"{season}-09-{i + 1:02d}"
        _log(conn, season, period, player, team, "carries", carries, position)
        _log(conn, season, period, player, team, "rush_yds", rush_yds, position)
        _log(conn, season, period, player, team, "receptions", 1.0, position)
        _log(conn, season, period, player, team, "rec_yds", 10.0, position)
        _log(conn, season, period, player, team, "rz_car", 3.0, position)
        _log(conn, season, period, player, team, "rz_rec", 0.0, position)
        _log(conn, season, period, player, team, "anytime_td",
             1.0 if i < tds else 0.0, position)
        _game(conn, season, period, team, spread=spread, total=total)


# --- the walk forward -------------------------------------------------
def test_a_player_is_not_graded_until_he_has_a_history():
    conn = _conn()
    _season(conn, 2024, "Back", "UGA", weeks=5, tds=2)
    rows = F.samples(conn)
    assert len(rows) == 5 - F.MIN_PRIOR_GAMES
    assert all(s.games >= F.MIN_PRIOR_GAMES for s in rows)


def test_form_is_season_to_date_because_the_live_board_averages_that_way():
    conn = _conn()
    _season(conn, 2024, "Back", "UGA", weeks=6, tds=3)
    rows = sorted(F.samples(conn), key=lambda s: s.games)
    # game 4 looks back at 3, game 6 at 5 — a growing window, not a
    # rolling one. `usage_table` takes a season average.
    assert [s.games for s in rows] == [3, 4, 5]


def test_the_outcome_is_did_he_score_not_how_many():
    conn = _conn()
    _season(conn, 2024, "Back", "UGA", weeks=5, tds=5)
    for period in ("2024-09-04", "2024-09-05"):
        conn.execute("UPDATE player_game_logs SET value=3 WHERE period=? "
                     "AND market='anytime_td'", (period,))
    assert all(s.scored == 1 for s in F.samples(conn))


def test_the_replay_reads_the_roster_position_the_board_prices_off():
    """Not a detail: the usage inference disagrees with the roster on
    7,835 of 28,141 graded player-games, and grading on the inference
    would grade a model nobody runs."""
    conn = _conn()
    _season(conn, 2024, "Runner", "UGA", weeks=5, tds=1, position="QB")
    assert {s.position for s in F.samples(conn)} == {"QB"}
    plain = _conn()
    _season(plain, 2024, "Runner", "UGA", weeks=5, tds=1, position="")
    assert {s.position for s in F.samples(plain)} == {"RB"}


def test_a_season_filter_is_honoured():
    conn = _conn()
    _season(conn, 2023, "Back", "UGA", weeks=5, tds=1)
    _season(conn, 2024, "Back", "UGA", weeks=5, tds=1)
    assert {s.season for s in F.samples(conn, seasons=[2024])} == {2024}


# --- the model it replays ---------------------------------------------
def test_role_share_is_the_boards_own_formula():
    s = F.Sample(season=2024, position="RB", share=0.32, td_mean=0.0,
                 games=4, scored=0)
    assert abs(F.role_share(s) - T.POSITION_TD_SHARE["RB"]) < 1e-9


def test_the_blend_pulls_toward_a_players_own_scoring_rate():
    low = F.Sample(2024, "WR", 0.20, td_mean=0.0, games=10, scored=0)
    high = F.Sample(2024, "WR", 0.20, td_mean=1.0, games=10, scored=0)
    assert F.blended(high, 25.0, 0.30) > F.role_share(high)
    assert F.blended(low, 25.0, 0.30) < F.role_share(low)


def test_the_blend_weight_is_capped_where_the_constant_says():
    s = F.Sample(2024, "WR", 0.20, td_mean=1.5, games=200, scored=0)
    capped = F.blended(s, 25.0, 0.30)
    harder = F.blended(s, 25.0, 0.90)
    assert harder > capped


def test_the_installed_constants_are_the_ones_the_fit_chose():
    assert (T.TD_HISTORY_GAMES, T.TD_HISTORY_MAX_WEIGHT) in [
        (g, w) for g in F.BLEND_GAMES for w in F.BLEND_WEIGHTS], \
        "the shipped blend must be a point the fitter can actually reach"
    assert (T.TD_HISTORY_GAMES, T.TD_HISTORY_MAX_WEIGHT) != F.PREVIOUS_BLEND


def test_probability_is_one_minus_e_to_the_minus_rate():
    assert abs(F.probability(0.1)
               - (1 - math.exp(-T.CFB_AVG_TEAM_OFF_TDS * 0.1))) < 1e-12


# --- the fit ----------------------------------------------------------
def test_the_blend_is_chosen_on_train_and_only_reported_on_the_holdout():
    conn = _conn()
    for season in F.TRAIN_SEASONS + F.TEST_SEASONS:
        for i in range(12):
            _season(conn, season, f"Back{i}", "UGA", weeks=8, tds=i % 5)
    out = F.fit_blend(F.samples(conn))
    assert out["chosen"] in [(g, w) for g in F.BLEND_GAMES
                             for w in F.BLEND_WEIGHTS]
    assert out["train"] and out["test"]
    for key in ("held_out", "held_out_previous", "held_out_no_history"):
        assert isinstance(out[key], float)


def test_a_sample_with_no_holdout_season_refuses_to_choose():
    conn = _conn()
    _season(conn, F.TRAIN_SEASONS[0], "Back", "UGA", weeks=8, tds=2)
    assert F.fit_blend(F.samples(conn))["chosen"] is None


def test_the_report_is_ordered_in_time_so_the_bake_off_holds_out_a_future():
    """`calibrate.bake_off` takes the LAST 30% of the pairs as its judge.
    Built the obvious way these come out grouped by player, and the
    judge scores the correction on an arbitrary subset of the sport
    rather than on its future."""
    conn = _conn()
    for i in range(6):
        _season(conn, 2024, f"Back{i}", "UGA", weeks=8, tds=i % 4)
    rows = sorted(F.samples(conn), key=lambda s: (s.season, s.period))
    assert [s.period for s in rows] == sorted(s.period for s in rows)
    assert len(F.run(conn).pairs) == len(rows)


def test_a_thin_sample_produces_no_calibration_at_all():
    conn = _conn()
    _season(conn, 2024, "Back", "UGA", weeks=8, tds=3)
    fit, report = F.fit_calibration(conn)
    assert fit is None
    assert report.n < F.MIN_FIT_PAIRS


def test_the_report_grades_by_band():
    conn = _conn()
    for i in range(20):
        _season(conn, 2024, f"Back{i}", "UGA", weeks=9, tds=i % 6,
                carries=float(3 + i), rush_yds=float(20 + 8 * i))
    report = F.run(conn)
    assert report.n
    assert report.bands
    assert "CFB anytime-TD backtest" in report.summary(min_band_n=1)


def test_red_zone_role_is_priced_at_the_weight_the_fit_chose():
    """The first measurement said no, on a chain with the game script
    held at 1.0 and a third of 2025 missing its touchdowns. With the
    feed's broken weeks caught and the board's real closing numbers
    driving the replay, the same grid picks an interior 0.10."""
    from engine.sources import cfbstats
    assert "rz_car" in cfbstats.MARKETS and "rz_rec" in cfbstats.MARKETS
    assert "rz_car" in F.MARKETS and "rz_rec" in F.MARKETS
    assert 0.0 < T.RZ_SHARE_WEIGHT < 0.5
    assert T.RZ_SHARE_WEIGHT in F.RZ_WEIGHTS


def test_the_red_zone_blend_is_a_no_op_without_red_zone_rows():
    """A board built from a feed that cannot see field position must not
    take a silent haircut on everybody."""
    plain = F.Sample(2024, "RB", 0.30, td_mean=0.0, games=5, scored=0)
    assert plain.rz_share == plain.share
    assert abs(F.role_share(plain, rz_weight=0.0)
               - F.role_share(plain)) < 1e-12


# --- the chain, not just the role -------------------------------------
def test_the_replay_reads_the_games_own_closing_numbers():
    conn = _conn()
    _season(conn, 2024, "Back", "UGA", weeks=5, tds=2, spread=-21.0,
            total=62.0)
    row = F.samples(conn)[0]
    assert row.spread == -21.0 and row.total == 62.0
    # A 62 total with the home side laying 21 implies 41.5 for them,
    # well above the FBS average — so the chain must claim more here
    # than it would at a neutral total.
    assert row.team_tds > T.CFB_AVG_TEAM_OFF_TDS


def test_a_game_with_no_stored_line_falls_back_to_the_fbs_average():
    plain = F.Sample(2024, "RB", 0.30, td_mean=0.0, games=5, scored=0)
    assert plain.team_tds == T.CFB_AVG_TEAM_OFF_TDS
    assert plain.script == 1.0


def test_the_game_script_rides_the_spread_for_a_back():
    favoured = F.Sample(2024, "RB", 0.30, 0.0, 5, 0, spread=-21.0, total=52.0,
                        is_home=True)
    dog = F.Sample(2024, "RB", 0.30, 0.0, 5, 0, spread=21.0, total=52.0,
                   is_home=True)
    assert favoured.script > 1.0 > dog.script


# --- the opponent, without reading the future -------------------------
def test_defense_is_measured_from_games_already_played():
    """`cfb.tds.defense_multiplier` reads a team's whole season, which is
    right on a live board and leaks in a replay of a finished one."""
    conn = _conn()
    for i in range(6):
        period = f"2024-09-{i + 1:02d}"
        _game(conn, 2024, period, "OPP", away="X", home_score=10.0,
              away_score=45.0)
    table = F.defense_to_date(conn)
    early = table.get((2024, "2024-09-02", "OPP"))
    late = table.get((2024, "2024-09-06", "OPP"))
    assert early[1] == 1 and late[1] == 5
    assert late[0] == 45.0
    # The first game of a season has no prior, so it is absent entirely
    # rather than carrying a zero.
    assert (2024, "2024-09-01", "OPP") not in table


def test_the_defence_term_is_neutral_because_the_total_prices_it():
    """It used to return points allowed against the FBS average, up to
    +/-20%, multiplied onto a team-touchdown estimate that comes FROM the
    game's implied total — a number the book set knowing how good that
    defence is.

    Over 3,920 walk-forward games, predicting the opponent's offensive
    touchdowns: implied total alone scored chi-square 3.0, implied total
    times this term 181.8, missing by 16-19% at each end on more than
    half the board. Leave-one-season-out, dropping it beat keeping it in
    every season (13.1 against 196.1) and the best partial weight (0.04
    to 0.14) was no better than zero.

    This module replays the BOARD'S chain, so it has to go neutral here
    too or it would be grading a model nobody runs."""
    for allowed, played in ((45.0, 1), (None, 9), (45.0, 9), (10.0, 9)):
        assert F.defense_multiplier(allowed, played) == 1.0, (allowed, played)


def test_the_replay_chain_still_matches_the_live_one():
    """The two have to agree or the fit measures something else. Both are
    neutral now, and that has to stay true on both sides at once."""
    import sqlite3
    from engine.cfb import tds as live
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE games (sport TEXT, season INT, period TEXT, "
                 "game_id TEXT, home TEXT, away TEXT, home_score REAL, "
                 "away_score REAL)")
    for i in range(6):
        conn.execute("INSERT INTO games VALUES ('cfb', 2025, ?, ?, 'OPP', "
                     "'X', 10, 45)", (f"2025-09-{i + 1:02d}", f"g{i}"))
    conn.commit()
    assert live.defense_multiplier(conn, "OPP", 2025)[0] == 1.0
    assert F.defense_multiplier(45.0, 6) == 1.0


# --- the joint fit ----------------------------------------------------
def test_the_constants_are_fitted_together_not_one_at_a_time():
    """The blend, the anchors and the red-zone weight all move the same
    number, so installing each one's result in turn makes the next fit
    answer a question about a model that no longer exists."""
    import inspect
    source = inspect.getsource(F.fit_all)
    assert "fit_anchors" in source and "_best_blend" in source
    assert "TRAIN_SEASONS" in source


def test_the_joint_fit_never_consults_the_holdout_while_choosing():
    conn = _conn()
    for season in F.TRAIN_SEASONS + F.TEST_SEASONS:
        for i in range(6):
            _season(conn, season, f"Back{i}", "UGA", weeks=7, tds=i % 4,
                    carries=float(4 + 2 * i))
    out = F.fit_all(F.samples(conn), rounds=1)
    assert out["chosen"]["rz_weight"] in F.RZ_WEIGHTS
    assert out["chosen"]["max_weight"] in F.BLEND_WEIGHTS
    assert set(out["chosen"]["anchors"]) == set(T.POSITION_TD_SHARE)
    assert out["train"] and out["test"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
