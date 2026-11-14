"""Tests for the MLB learned-multiplier ML layer (pure, no network)."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.ml import (
    extract_features, vectorize, build_examples, fit, FEATURE_ORDER,
)
from engine.mlb.models import (
    MLBProp, MLBGame, MLBWeather, Pitcher, StatcastProfile,
    TOTAL_BASES, STRIKEOUTS,
)


def _idx(name):
    return FEATURE_ORDER.index(name)


# --- feature extraction -----------------------------------------------------
def test_features_park_and_wind():
    game = MLBGame(home="COL", away="A", park="coors",
                   weather=MLBWeather(wind_mph=16, wind_dir_rel="out", temp_f=90))
    prop = MLBProp("H", "A", "COL", "1B", TOTAL_BASES, [], 1.8, None, [], bats="R")
    f = extract_features(prop, game)
    assert f["park_hr"] > 0.15          # Coors
    assert f["wind"] > 1.0              # blowing out, 16mph
    assert f["temp"] > 0.8              # hot
    # wind in flips the sign
    game.weather.wind_dir_rel = "in"
    assert extract_features(prop, game)["wind"] < 0


def test_features_platoon_and_statcast():
    game = MLBGame(home="H", away="A", park="generic",
                   pitchers={"A": Pitcher("SP", "R", slg_allowed_vs_l=0.52)},
                   bullpen_rank={"A": 27})
    prop = MLBProp("H", "H", "A", "1B", TOTAL_BASES, [], 1.8, None, [],
                   bats="L", lineup_spot=2,
                   statcast=StatcastProfile(xslg=0.56, slg=0.50, barrel_pct=0.15))
    f = extract_features(prop, game)
    assert f["platoon"] == 1.0                 # L vs R
    assert abs(f["pit_slg"] - 0.12) < 1e-9     # .520 - .400
    assert f["bullpen"] > 0                     # bad pen (27)
    assert f["lineup"] > 0                      # top of order
    assert abs(f["xslg_gap"] - 0.06) < 1e-9
    assert abs(f["barrel"] - 0.07) < 1e-9


def test_features_pitcher_market():
    game = MLBGame(home="H", away="A", park="generic",
                   team_k_rate={"A": 0.27})
    prop = MLBProp("SP", "H", "A", "SP", STRIKEOUTS, [], 6.5, None, [],
                   throws="R", statcast=StatcastProfile(csw_pct=0.32))
    f = extract_features(prop, game)
    assert abs(f["opp_k"] - 0.05) < 1e-9
    assert abs(f["csw"] - 0.04) < 1e-9
    assert f["platoon"] == 0.0                  # hitter-only feature stays 0


# --- training ---------------------------------------------------------------
def _rows_driven_by(feature_name, market, weight, n=200, seed=1):
    import random
    rng = random.Random(seed)
    rows = []
    baseline = 6.5 if market == STRIKEOUTS else 1.8
    for _ in range(n):
        if market == STRIKEOUTS:
            csw = rng.uniform(0.24, 0.34)
            prop = MLBProp("SP", "H", "A", "SP", market, [], baseline, None, [],
                           statcast=StatcastProfile(csw_pct=csw))
            game = MLBGame("H", "A", "generic", team_k_rate={"A": 0.22})
        else:
            prop = MLBProp("H", "H", "A", "1B", market, [], baseline, None, [],
                           bats="R", lineup_spot=5,
                           statcast=StatcastProfile(xslg=rng.uniform(0.35, 0.6),
                                                    slg=0.45))
            game = MLBGame("H", "A", rng.choice(["coors", "oracle", "generic"]))
        feat = extract_features(prop, game)
        y = weight * feat[feature_name]
        prop_actual = baseline * math.exp(y)
        rows.append({"prop": prop, "game": game, "baseline": baseline,
                     "actual": prop_actual})
    return rows


def test_fit_recovers_csw_sign():
    rows = _rows_driven_by("csw", STRIKEOUTS, 1.5)
    model, report = fit(build_examples(rows), l2=0.05, min_examples=20)
    assert model.has(STRIKEOUTS)
    assert model.coefs[STRIKEOUTS][_idx("csw")] > 0.5


def test_fit_recovers_park_hr_sign():
    rows = _rows_driven_by("park_hr", TOTAL_BASES, 0.8)
    model, _ = fit(build_examples(rows), l2=0.05, min_examples=20)
    assert model.coefs[TOTAL_BASES][_idx("park_hr")] > 0.2


def test_build_examples_shape_and_market_split():
    rows = _rows_driven_by("csw", STRIKEOUTS, 1.0, n=5) + \
           _rows_driven_by("park_hr", TOTAL_BASES, 1.0, n=7)
    data = build_examples(rows)
    assert len(data[STRIKEOUTS][0]) == 5 and len(data[TOTAL_BASES][0]) == 7
    assert len(data[STRIKEOUTS][0][0]) == len(FEATURE_ORDER)


# --- projection integration -------------------------------------------------
def test_projection_uses_model():
    from engine.mlb.projection import build_mlb_projection
    from engine.ml.model import MultiplierModel
    logs = [__import__("engine.mlb.models", fromlist=["MLBGameLog"]).MLBGameLog(i, "X", 2)
            for i in range(1, 11)]
    prop = MLBProp("H", "A", "H", "1B", TOTAL_BASES, logs, 1.8, None, [], bats="R")
    game = MLBGame("H", "A", "generic")
    base = build_mlb_projection(prop, game, model=None)
    # +20% intercept model regardless of features
    coefs = {TOTAL_BASES: [0.0] * len(FEATURE_ORDER)}
    coefs[TOTAL_BASES][0] = 0.2
    m = MultiplierModel(FEATURE_ORDER, coefs, clamp_lo=0.78, clamp_hi=1.28)
    learned = build_mlb_projection(prop, game, model=m)
    assert abs(learned.mean - base.form.mean * math.exp(0.2)) < 1e-6
    assert any("Learned model" in r for r in learned.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
