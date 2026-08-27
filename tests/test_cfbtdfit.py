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
    return conn


def _log(conn, season, period, player, team, market, value, position=""):
    conn.execute(
        "INSERT INTO player_game_logs VALUES ('cfb',?,?,?,?,?,'',?,1,?,?)",
        (season, period, f"g{period}", player, team, position, market, value))


def _season(conn, season, player, team, weeks, tds, position="RB",
            carries=15.0, rush_yds=80.0):
    """`weeks` games for one player, the first `tds` of them with a score."""
    for i in range(weeks):
        period = f"{season}-09-{i + 1:02d}"
        _log(conn, season, period, player, team, "carries", carries, position)
        _log(conn, season, period, player, team, "rush_yds", rush_yds, position)
        _log(conn, season, period, player, team, "receptions", 1.0, position)
        _log(conn, season, period, player, team, "rec_yds", 10.0, position)
        _log(conn, season, period, player, team, "anytime_td",
             1.0 if i < tds else 0.0, position)


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


def test_red_zone_role_is_ingested_and_deliberately_not_priced():
    assert "rz_car" not in F.MARKETS and "rz_rec" not in F.MARKETS
    from engine.sources import cfbstats
    assert "rz_car" in cfbstats.MARKETS and "rz_rec" in cfbstats.MARKETS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
