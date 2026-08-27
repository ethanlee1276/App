"""Grading the touchdown model — the picks that had never been measured.

`engine.touchdowns` is behind every anytime-TD pick and every longshot
on both football boards, and on 2026-08-27 nothing had ever graded it.
`backtest.py` walks the yardage and reception markets; `anytime_td`
appears nowhere in it. The board shipped, settled itself against
results, and no one had asked whether its probabilities were true.

They have to be true in a specific place. A longshot lives in the TAIL —
a +450 price asks whether an 18% shot is really 18% — so a model
beautifully calibrated at 40% and quietly overconfident at 15% looks
healthy in aggregate while losing money on every longshot it publishes.

Measured over four seasons and 17,785 player-weeks it was the opposite
of what a longshot board wants: too CONSERVATIVE at the bottom, claiming
4.9% where 9.2% actually scored. It was passing over the very picks it
exists to find.

Run directly: `python3 tests/test_tdbacktest.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tdbacktest as T
from engine.longshots import NFL_TD_ODDS, CFB_TD_ODDS, in_odds_window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- the implied-total arithmetic --------------------------------------------
def test_the_home_team_gets_the_favoured_half():
    """`spread` is the HOME number (negative = home favoured), the
    convention engine.ingest stores. A home team laying 7 in a 47 game is
    implied for 27 — getting this backwards would hand the underdog the
    favourite's touchdowns on every row."""
    assert T.implied_total(47.0, -7.0, True) == 27.0
    assert T.implied_total(47.0, -7.0, False) == 20.0


def test_a_pickem_splits_the_total():
    assert T.implied_total(44.0, 0.0, True) == 22.0
    assert T.implied_total(44.0, 0.0, False) == 22.0


def test_a_missing_or_zero_total_is_refused_not_defaulted():
    assert T.implied_total(None, -3.0, True) is None
    assert T.implied_total(0.0, -3.0, True) is None
    assert T.implied_total("", -3.0, True) is None


# --- the report ---------------------------------------------------------------
def _report(rows):
    r = T.TDBacktest()
    for prob, scored in rows:
        r.add(prob, scored)
    return r.finish()


def test_a_band_reports_claimed_against_landed():
    r = _report([(0.20, 1)] * 30 + [(0.20, 0)] * 70)
    b = r.bands[(0.18, 0.28)]
    assert b["n"] == 100
    assert abs(b["claimed"] - 0.20) < 1e-9
    assert abs(b["landed"] - 0.30) < 1e-9
    assert abs(b["gap"] - 0.10) < 1e-9


def test_the_bands_are_finer_at_the_bottom_where_longshots_live():
    """A few points of overconfidence is the whole margin on a +450, and
    nothing on a -200."""
    widths = [hi - lo for lo, hi in T.BANDS]
    assert widths[0] <= widths[-1]
    assert T.BANDS[0][0] == 0.0 and T.BANDS[-1][1] > 1.0


def test_an_overconfident_band_is_flagged():
    r = _report([(0.50, 1)] * 35 + [(0.50, 0)] * 65)
    assert "overconfident" in r.summary(min_band_n=10)


def test_a_conservative_band_is_named_but_not_alarmed():
    r = _report([(0.05, 1)] * 12 + [(0.05, 0)] * 88)
    text = r.summary(min_band_n=10)
    assert "conservative" in text and "overconfident" not in text


def test_a_thin_band_is_not_reported():
    r = _report([(0.05, 1)] * 3)
    assert "0%-10%" not in r.summary(min_band_n=40)


def test_an_empty_run_says_what_it_needs():
    assert "anytime_td" in T.TDBacktest().finish().summary()


def test_the_pairs_are_the_shape_the_calibrator_takes():
    """The whole reason this exists: a touchdown has no LINE, so
    `calibrate.fit_market` can never fit it, and (nfl, anytime_td) sat on
    a neutral correction while calibrated_prob applied it to every pick.
    These pairs are the missing input."""
    r = _report([(0.2, 1), (0.4, 0)])
    assert r.pairs == [(0.2, 1), (0.4, 0)]
    from engine.calibrate import fit
    assert fit(r.pairs, sport="nfl", market="anytime_td") is not None


# --- the walk-forward promise -------------------------------------------------
def _seeded(conn, weeks=10):
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, "
                 "period TEXT, game_id TEXT, player TEXT, team TEXT, "
                 "opponent TEXT, position TEXT, home INT, market TEXT, "
                 "value REAL)")
    conn.execute("CREATE TABLE games (sport TEXT, season INT, period TEXT, "
                 "home TEXT, away TEXT, spread REAL, total REAL)")
    rows = []
    for w in range(1, weeks + 1):
        wk = f"{w:03d}"
        for market, value in (("anytime_td", 1.0), ("targets", 8.0),
                              ("carries", 3.0), ("rz_tgt", 2.0),
                              ("i5_car", 1.0)):
            rows.append(("nfl", 2025, wk, f"g{w}", "A Back", "KC", "BUF",
                         "RB", 1, market, value))
        conn.execute("INSERT INTO games VALUES ('nfl',2025,?,'KC','BUF',-6.0,47.0)",
                     (wk,))
    conn.executemany("INSERT INTO player_game_logs VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def test_a_players_first_weeks_are_never_graded():
    """His probability would be built from the very games being graded."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seeded(conn, weeks=10)
    r = T.run(conn, "nfl")
    assert r.n == 10 - T.MIN_PRIOR_WEEKS


def test_a_week_with_no_game_row_is_skipped_rather_than_guessed():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seeded(conn, weeks=10)
    conn.execute("DELETE FROM games")
    conn.commit()
    assert T.run(conn, "nfl").n == 0


def test_a_thin_sample_is_not_fitted():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seeded(conn, weeks=10)
    fit, report = T.fit_calibration(conn)
    assert fit is None, "a handful of weeks must not move a live correction"
    assert report.n < T.MIN_FIT_PAIRS


# --- the odds window ----------------------------------------------------------
def test_the_longshot_ceilings_moved_on_measured_evidence():
    """The old +450 held because "our proxy-fed model cannot separate a
    sub-18% event from noise". The model is no longer proxy-fed, and
    inside that region the top quintile out-scores the bottom by 7.4
    points at z = 7.6 — measured separation, exactly where the ceiling
    said there was none."""
    assert NFL_TD_ODDS[1] > 450
    assert CFB_TD_ODDS[1] > 600
    assert in_odds_window(600, NFL_TD_ODDS)
    assert in_odds_window(800, CFB_TD_ODDS)


def test_the_ceilings_still_stop_somewhere():
    """Widening is not removing. Past the measured region the bands thin
    and the model has nothing to stand on."""
    assert not in_odds_window(2000, NFL_TD_ODDS)
    assert not in_odds_window(2000, CFB_TD_ODDS)


def test_the_window_records_the_measurement_that_moved_it():
    src = open(os.path.join(ROOT, "engine", "longshots.py"),
               encoding="utf-8").read()
    assert "z = 7.6" in src and "17,785" in src


# --- the stale note that told a reader to rebuild what exists -----------------
def test_the_model_no_longer_claims_it_cannot_see_red_zone_usage():
    """It said play-by-play "lives in data this project doesn't ingest"
    long after the ingest landed. A stale "we cannot see X" is worse than
    no note: it sends a reader to build something that already exists."""
    src = open(os.path.join(ROOT, "engine", "touchdowns.py"),
               encoding="utf-8").read()
    head = src[:src.index('"""', src.index('"""') + 3)]
    assert "doesn't ingest" not in head or "used to sit here" in head
    assert "engine.nflusage" in head


def test_the_weekly_refit_reaches_the_touchdown_market():
    src = open(os.path.join(ROOT, "engine", "deepfit.py"),
               encoding="utf-8").read()
    assert "def refit_touchdowns(" in src
    assert "refit_touchdowns(db)" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
