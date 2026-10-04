"""Tests for the learned-multiplier ML layer (pure, no network)."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ml.model import solve_linear, ridge_fit, MultiplierModel
from engine.ml.features import extract_features, vectorize, FEATURE_ORDER
from engine.ml.train import build_examples, fit
from engine.models import (
    Team, DefenseProfile, Weather, Game, Prop, GameLog, PASS_YDS,
)


def approx(a, b, tol=1e-6):
    return abs(a - b) < tol


# --- linear algebra ---------------------------------------------------------
def test_solve_linear():
    # 2x + y = 5 ; x + 3y = 10  ->  x=1, y=3
    x = solve_linear([[2, 1], [1, 3]], [5, 10])
    assert approx(x[0], 1.0, 1e-6) and approx(x[1], 3.0, 1e-6)


def test_ridge_recovers_known_coefficients():
    true_w = [2.0, -1.0, 0.5]
    X, y = [], []
    for i in range(60):
        a, b = (i % 7) - 3, (i % 5) - 2
        row = [1.0, float(a), float(b)]
        X.append(row)
        y.append(true_w[0] + true_w[1] * a + true_w[2] * b)
    w = ridge_fit(X, y, l2=0.0)
    assert all(approx(w[i], true_w[i], 1e-6) for i in range(3))


def test_ridge_intercept_unregularized():
    # Constant target -> intercept absorbs it even with heavy L2 on slopes.
    X = [[1.0, float(i)] for i in range(20)]
    y = [5.0 for _ in range(20)]
    w = ridge_fit(X, y, l2=100.0)
    assert approx(w[0], 5.0, 1e-3) and abs(w[1]) < 1e-2


# --- model ------------------------------------------------------------------
def test_predict_and_clamp():
    m = MultiplierModel(FEATURE_ORDER, {PASS_YDS: [0.1, 0, 0, 0, 0, 0, 0]})
    feat = [1, 0, 0, 0, 0, 0, 0]
    assert approx(m.predict_multiplier(feat, PASS_YDS), math.exp(0.1), 1e-9)
    # huge coefficient is clamped
    m2 = MultiplierModel(FEATURE_ORDER, {PASS_YDS: [5.0, 0, 0, 0, 0, 0, 0]})
    assert approx(m2.predict_multiplier(feat, PASS_YDS), 1.40)


def test_model_serialization_roundtrip(tmp_path=None):
    m = MultiplierModel(FEATURE_ORDER, {PASS_YDS: [0.05, -0.2, 0.1, 0, -0.3, 0, -0.05]},
                        meta={"season": 2024})
    d = m.to_dict()
    back = MultiplierModel.from_dict(d)
    assert back.coefs[PASS_YDS] == m.coefs[PASS_YDS]
    assert back.feature_order == FEATURE_ORDER


# --- features ---------------------------------------------------------------
def _prop(team="BUF", opp="KC", market=PASS_YDS, role="starter"):
    return Prop("QB", team, opp, "QB", market, [], 0.0, None, [], role)


def test_feature_signs():
    game = Game(home="KC", away="BUF", weather=Weather(dome=False, temp_f=20, wind_mph=25),
                spread=-3.0, total=52.0)  # home KC favored by 3; BUF is +3 dog
    d = DefenseProfile("KC", vs_qb=1.10)
    f = extract_features(_prop(team="BUF"), game, d)
    assert approx(f["def"], 0.10)          # generous pass D
    assert f["spread"] < 0                  # BUF is an underdog
    assert approx(f["total"], 0.8)          # (52-44)/10
    assert approx(f["wind"], 2.5)           # 25/10
    assert f["cold"] == 1.0                 # 20F
    # dome zeroes wind
    fd = extract_features(_prop(), Game("KC", "BUF", Weather(dome=True), total=44), DefenseProfile("KC"))
    assert fd["dome"] == 1.0 and fd["wind"] == 0.0


# --- training assembly ------------------------------------------------------
def _srow(name, team, opp, week, pass_yds):
    return {"player_display_name": name, "position": "QB", "recent_team": team,
            "opponent_team": opp, "week": str(week), "season": "2024", "season_type": "REG",
            "passing_yards": str(pass_yds), "rushing_yards": "0", "receiving_yards": "0",
            "receptions": "0", "attempts": "30", "carries": "0", "targets": "0"}


def test_build_examples_walkforward():
    stats = [_srow("Q", "AAA", "ZZZ", w, 250) for w in (1, 2, 3, 4)]
    stats.append(_srow("Q", "AAA", "BBB", 5, 300))  # target week
    games = {5: [Game(home="AAA", away="BBB",
                      weather=Weather(dome=False, temp_f=60, wind_mph=10),
                      spread=0.0, total=44.0)]}
    data = build_examples(stats, games, [5], min_history=4)
    assert PASS_YDS in data
    X, Y = data[PASS_YDS]
    assert len(X) == 1
    row = X[0]
    # wind 10 -> 1.0, spread 0, total centered 0, not dome/cold
    assert approx(row[FEATURE_ORDER.index("wind")], 1.0)
    assert approx(row[FEATURE_ORDER.index("total")], 0.0)
    # target = log((300+.5)/(250+.5))
    assert approx(Y[0], math.log(300.5 / 250.5), 1e-9)
    # min_history gate: needs >=5 prior -> nothing
    assert build_examples(stats, games, [5], min_history=5) == {}


def test_fit_learns_wind_sign():
    # Synthetic: passing falls as wind rises. The learner should give wind < 0.
    X, Y = [], []
    for wind in range(0, 30):
        feat = [1.0, 0.0, 0.0, 0.0, wind / 10.0, 0.0, 0.0]
        X.append(feat)
        Y.append(-0.3 * (wind / 10.0))
    model, report = fit({PASS_YDS: (X, Y)}, l2=0.01, min_examples=10)
    w_wind = model.coefs[PASS_YDS][FEATURE_ORDER.index("wind")]
    assert w_wind < -0.1


# --- integration with the projection engine ---------------------------------
def test_projection_uses_learned_multiplier():
    logs = [GameLog(w, "X", 250) for w in range(1, 6)]
    prop = Prop("QB", "BUF", "KC", "QB", PASS_YDS, logs, 250, None, [], "starter")
    game = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-3, total=44)
    opp = Team("KC", "KC", DefenseProfile("KC"))

    from engine.projection import build_projection
    base = build_projection(prop, game, opp, model=None)
    # Model forces a +22% multiplier via the intercept, regardless of features.
    m = MultiplierModel(FEATURE_ORDER, {PASS_YDS: [0.2, 0, 0, 0, 0, 0, 0]})
    learned = build_projection(prop, game, opp, model=m)
    assert approx(learned.mean, 250 * math.exp(0.2), 1e-6)
    assert learned.mean != base.mean
    assert any("Learned model" in r for r in learned.reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
