"""Learned coefficients for the MLB projection engine.

Same idea as the NFL ML phase, reusing the shared pure-Python ridge model
(`engine.ml.model`): replace the hand-tuned park / weather / matchup / Statcast
*magnitudes* with coefficients fit on history, keeping the multiplicative
structure so a learned model is a drop-in for the clamp in
``build_mlb_projection``:

    predicted_mean = form.mean × exp(w · features)

The features are the raw levers the hand-tuned modules pull (park factors,
signed wind, platoon, pitcher SLG-allowed, bullpen, lineup slot, opponent K
rate, and the Statcast xSLG-gap / barrel / CSW signals), so the learned
coefficients read like the assumptions they replace. Assembling training rows
from historical game context is the historical-database phase; ``build_examples``
and ``fit`` are pure and unit-tested, and recover known coefficients.
"""

from __future__ import annotations

import math

from ..ml.model import MultiplierModel, ridge_fit
from .models import (
    MLBProp, MLBGame, HITTER_MARKETS, TOTAL_BASES, HOME_RUNS, HITS, STRIKEOUTS,
)
from .parks import get_park
from .matchup import LINEUP_SPOT_PA

FEATURE_ORDER = [
    "intercept", "park_hr", "park_run", "park_k", "wind", "temp",
    "platoon", "pit_slg", "bullpen", "lineup", "opp_k", "xslg_gap", "barrel", "csw",
]


def extract_features(prop: MLBProp, game: MLBGame) -> dict:
    park = get_park(game.park)
    w = game.weather
    f = {k: 0.0 for k in FEATURE_ORDER}
    f["intercept"] = 1.0

    f["park_hr"] = park.hr_factor - 1.0
    f["park_run"] = park.run_factor - 1.0
    f["park_k"] = park.k_factor - 1.0

    if not w.roof_closed:
        if w.wind_mph >= 10 and w.wind_dir_rel == "out":
            f["wind"] = w.wind_mph / 10.0
        elif w.wind_mph >= 10 and w.wind_dir_rel == "in":
            f["wind"] = -w.wind_mph / 10.0
        f["temp"] = (w.temp_f - 72.0) / 20.0

    if prop.market in HITTER_MARKETS:
        starter = game.pitchers.get(prop.opponent)
        if starter:
            adv = (prop.bats == "S") or (prop.bats != starter.throws)
            f["platoon"] = 1.0 if adv else 0.0
            side_slg = (starter.slg_allowed_vs_l if prop.bats in ("L", "S")
                        else starter.slg_allowed_vs_r)
            f["pit_slg"] = side_slg - 0.400
        pen = game.bullpen_rank.get(prop.opponent)
        if pen:
            f["bullpen"] = (pen - 15) / 15.0          # >0 = worse pen = more offense
        if prop.lineup_spot:
            f["lineup"] = LINEUP_SPOT_PA.get(prop.lineup_spot, 1.0) - 1.0
        if prop.statcast:
            sc = prop.statcast
            if sc.xslg is not None and sc.slg is not None:
                f["xslg_gap"] = sc.xslg - sc.slg
            if sc.barrel_pct is not None:
                f["barrel"] = sc.barrel_pct - 0.08

    elif prop.market == STRIKEOUTS:
        f["opp_k"] = game.team_k_rate.get(prop.opponent, 0.22) - 0.22
        if prop.statcast and prop.statcast.csw_pct is not None:
            f["csw"] = prop.statcast.csw_pct - 0.28

    return f


def vectorize(feat: dict) -> list[float]:
    return [feat[k] for k in FEATURE_ORDER]


# --- training ---------------------------------------------------------------
def build_examples(rows: list[dict]) -> dict[str, tuple[list, list]]:
    """``rows`` = [{"prop": MLBProp, "game": MLBGame, "baseline": float,
    "actual": float}]. Target is log((actual+.5)/(baseline+.5))."""
    data: dict[str, tuple[list, list]] = {}
    for r in rows:
        baseline = r["baseline"]
        if baseline <= 0:
            continue
        feat = vectorize(extract_features(r["prop"], r["game"]))
        y = math.log((r["actual"] + 0.5) / (baseline + 0.5))
        X, Y = data.setdefault(r["prop"].market, ([], []))
        X.append(feat)
        Y.append(y)
    return data


def fit(data: dict[str, tuple[list, list]], l2: float = 1.0,
        min_examples: int = 30) -> tuple[MultiplierModel, dict]:
    coefs: dict[str, list[float]] = {}
    report: dict = {}
    for market, (X, Y) in data.items():
        if len(X) < min_examples:
            continue
        w = ridge_fit(X, Y, l2=l2)
        preds = [sum(wi * xi for wi, xi in zip(w, row)) for row in X]
        rmse = math.sqrt(sum((p - y) ** 2 for p, y in zip(preds, Y)) / len(Y))
        coefs[market] = w
        report[market] = {"n": len(X), "rmse_log": rmse, "coefs": w}
    model = MultiplierModel(feature_order=FEATURE_ORDER, coefs=coefs,
                            clamp_lo=0.78, clamp_hi=1.28,
                            meta={"sport": "mlb", "l2": l2})
    return model, report


def report_summary(report: dict) -> str:
    out = ["Trained MLB learned multiplier model"]
    for market, info in sorted(report.items()):
        out.append(f"  {market:12} n={info['n']:<5} "
                   f"in-sample RMSE(log)={info['rmse_log']:.4f}")
        for name, w in zip(FEATURE_ORDER, info["coefs"]):
            if name == "intercept" or abs(w) < 0.005:
                continue
            out.append(f"      {name:9} {w:+.3f}")
    return "\n".join(out)
