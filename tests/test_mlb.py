"""Tests for the MLB engine (offline; runs on the bundled sample slate)."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.parks import get_park, evaluate_park
from engine.mlb.weather import evaluate_weather
from engine.mlb.matchup import evaluate_matchup
from engine.mlb.betting import _poisson_over
from engine.mlb.models import (
    MLBWeather, MLBGame, MLBProp, MLBGameLog, Pitcher,
    TOTAL_BASES, HOME_RUNS, STRIKEOUTS,
)
from engine.mlb.pipeline import run_mlb_slate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLATE = os.path.join(ROOT, "data", "mlb_sample_slate.json")


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


# --- park engine ------------------------------------------------------------
def test_coors_boosts_offense():
    eff = evaluate_park(get_park("coors"))
    assert eff.multipliers[HOME_RUNS] > 1.1
    assert eff.multipliers[TOTAL_BASES] > 1.05
    assert any("Altitude" in r for r in eff.reasons)


def test_pitcher_park_suppresses():
    eff = evaluate_park(get_park("oracle"))
    assert eff.multipliers[HOME_RUNS] < 1.0


# --- weather engine ---------------------------------------------------------
def test_wind_out_boosts_hr():
    eff = evaluate_weather(MLBWeather(wind_mph=18, wind_dir_rel="out", temp_f=80))
    assert eff.multipliers[HOME_RUNS] > 1.08


def test_wind_in_suppresses_hr():
    eff = evaluate_weather(MLBWeather(wind_mph=18, wind_dir_rel="in", temp_f=80))
    assert eff.multipliers[HOME_RUNS] < 0.95


def test_roof_closed_is_neutral():
    eff = evaluate_weather(MLBWeather(roof_closed=True, wind_mph=25, wind_dir_rel="out"))
    assert all(approx(m, 1.0) for m in eff.multipliers.values())


def test_rain_risk_warns():
    eff = evaluate_weather(MLBWeather(precip_chance=0.7))
    assert eff.warnings


# --- matchup ----------------------------------------------------------------
def _game(**kw):
    base = dict(home="CHC", away="PHI", park="wrigley",
                pitchers={"CHC": Pitcher("RHP Guy", "R", 0.52, 0.40, 0.19),
                          "PHI": Pitcher("Ace", "R", 0.34, 0.33, 0.29)},
                bullpen_rank={"CHC": 27, "PHI": 5},
                team_k_rate={"CHC": 0.27, "PHI": 0.20})
    base.update(kw)
    return MLBGame(**base)


def _hitter(bats="L", spot=2, market=TOTAL_BASES):
    return MLBProp("Hitter", "PHI", "CHC", "1B", market,
                   [MLBGameLog(i, "X", 2) for i in range(1, 8)], 1.8, None, [],
                   bats=bats, lineup_spot=spot)


def test_platoon_and_weak_pitcher_boost():
    eff = evaluate_matchup(_hitter(bats="L"), _game())
    assert eff.multiplier > 1.05
    assert any("Platoon" in r for r in eff.reasons)


def test_pitcher_k_matchup():
    prop = MLBProp("Ace", "PHI", "CHC", "SP", STRIKEOUTS,
                   [MLBGameLog(i, "X", 7) for i in range(1, 8)], 6.5, None, [],
                   throws="R", lineup_spot=1)
    eff = evaluate_matchup(prop, _game())
    assert eff.multiplier > 1.05
    assert any("strikes out" in r for r in eff.reasons)


# --- Poisson HR pricing -----------------------------------------------------
def test_poisson_over_half():
    lam = 0.25
    assert approx(_poisson_over(0.5, lam), 1 - math.exp(-lam), 1e-9)


def test_poisson_over_one_and_half():
    lam = 0.25
    expected = 1 - math.exp(-lam) * (1 + lam)
    assert approx(_poisson_over(1.5, lam), expected, 1e-9)


# --- park-relative wind geometry --------------------------------------------
def test_relative_wind_out_in_cross():
    from engine.mlb.sources.mlbstats import relative_wind
    # Wrigley CF bearing ~30° (NNE). Air travels toward from_deg+180.
    assert relative_wind(210, 30) == "out"    # blows toward CF (30°)
    assert relative_wind(30, 30) == "in"      # blows back toward the plate
    assert relative_wind(120, 30) == "cross"  # perpendicular


def test_relative_wind_threshold_and_wraparound():
    from engine.mlb.sources.mlbstats import relative_wind, _ang_diff
    # Exactly 45° off center still counts as out (inclusive threshold).
    assert relative_wind(225, 0) == "out"     # blow_to 45, delta 45
    # Wraparound across 0/360 handled.
    assert relative_wind(190, 10) == "out"    # blow_to 10, delta 0
    assert _ang_diff(350, 10) == 20
    assert _ang_diff(10, 350) == 20


def test_relative_wind_covers_all_parks():
    from engine.mlb.sources.mlbstats import PARK_ORIENTATION, PARK_COORDS
    # Every park we fetch weather for has an orientation so wind can be
    # classified (no silent fallback to neutral for a mapped park).
    for key in PARK_COORDS:
        assert key in PARK_ORIENTATION


# --- pipeline ---------------------------------------------------------------
def test_pipeline_runs_and_holds_lineup():
    result = run_mlb_slate(SLATE)
    assert result["sport"] == "mlb"
    recs = result["recommendations"]
    assert result["counts"]["props_analyzed"] == len(recs)
    # NFL-compatible shape for the shared frontend.
    for key in ("headline", "hit_prob", "edge", "confidence", "logs", "form",
                "all_lines", "grade"):
        assert key in recs[0]
    # Betts is not in a confirmed lineup -> held despite a positive edge.
    betts = next(r for r in recs if r["player"] == "Mookie Betts")
    assert betts["recommended"] is False
    assert any("lineup" in w.lower() for w in betts["warnings"])
    # Games carry park context for the ballpark art.
    assert result["games"][0]["park_name"]
    assert "factors" in result["games"][0]


def test_longshot_diag_counts_the_funnel():
    """An empty HR board must explain itself: the diag counts survivors at
    each gate (props → 0.5-line quote → real book → plus-money window)."""
    result = run_mlb_slate(SLATE)
    dg = result["longshot_diag"]
    assert set(dg) == {"hr_props", "posted_half", "real_priced", "plus_money"}
    # The funnel only narrows.
    assert (dg["hr_props"] >= dg["posted_half"] >= dg["real_priced"]
            >= dg["plus_money"] >= 0)
    # The sample slate carries real plus-money HR quotes, so the far end of
    # the funnel is populated and the board renders.
    assert dg["plus_money"] > 0
    assert result["long_shots"] or result["longshot_watch"]


def test_hr_props_feature_top_three_on_recommended():
    """Home runs live on the Long Shots page; the Recommended page features
    only the top three — and both pages agree on which three."""
    result = run_mlb_slate(SLATE)
    hr = [r for r in result["recommendations"] if r["market"] == "home_runs"]
    # Every HR rec carries the stamp, and at most three are featured.
    assert all("hr_featured" in r for r in hr)
    featured = [r["player"] for r in hr if r["hr_featured"]]
    assert len(featured) <= 3
    # The featured names are exactly the head of the Long Shots page: value
    # picks first, topped up from the watchlist ranking.
    board = [d["player"] for d in result["long_shots"]]
    for w in result["longshot_watch"]:
        if len(board) >= 3:
            break
        if w["player"] not in board:
            board.append(w["player"])
    assert set(featured) == set(board[:3]) & {r["player"] for r in hr}
    # Non-HR markets are never stamped.
    assert all("hr_featured" not in r for r in result["recommendations"]
               if r["market"] != "home_runs")


def test_pipeline_edges_are_sane():
    result = run_mlb_slate(SLATE)
    for r in result["recommendations"]:
        assert 0.0 <= r["hit_prob"] <= 1.0
        assert abs(r["edge"]) < 0.35   # no runaway edges


def test_home_run_projection_ignores_when_the_homers_happened():
    """Regression: recency blending on a rare 0/1 event turned WHEN a
    hitter homered into a ~43x projection swing (0.344 HR/game if it was
    yesterday, 0.008 if eleven games ago — same 2-in-15 hitter). That
    manufactured the 20%+ 'edges' on plus-money home-run props, and no
    calibration temperature can fix it because the error is dispersion,
    not level."""
    from engine.mlb.backtest import _neutral_game
    from engine.mlb.projection import build_mlb_projection
    from engine.mlb.models import MLBGameLog, MLBProp, HOME_RUNS

    game = _neutral_game()

    def mean_for(prior, career=0.13):
        logs = [MLBGameLog(game=len(prior) - j, opponent="", value=float(v))
                for j, v in enumerate(prior)]
        prop = MLBProp(player="X", team="H", opponent="A", position="",
                       market=HOME_RUNS, logs=logs, career_avg=career,
                       vs_pitcher_avg=None, lines=[], lineup_spot=3)
        return build_mlb_projection(prop, game).mean

    same_rate = [
        [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],   # homered yesterday
        [0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],   # five games ago
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1],   # eleven games ago
    ]
    means = [mean_for(p) for p in same_rate]
    # Identical underlying rate → identical projection, whatever the order.
    assert max(means) / min(means) < 1.05, means
    # And it lands near the hitter's real rate, not multiples of it.
    assert 0.10 < means[0] < 0.20, means[0]

    # Skill must still come through: a genuine slugger projects far higher.
    slugger = mean_for([1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0],
                       career=0.40)
    assert slugger > 2.5 * means[0], (slugger, means[0])

    # A hitter with no homers at all sits below the 2-in-15 hitter.
    assert mean_for([0] * 15) < means[0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
