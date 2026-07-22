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


def test_pipeline_edges_are_sane():
    result = run_mlb_slate(SLATE)
    for r in result["recommendations"]:
        assert 0.0 <= r["hit_prob"] <= 1.0
        assert abs(r["edge"]) < 0.35   # no runaway edges


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
