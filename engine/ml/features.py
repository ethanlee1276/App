"""Feature extraction shared by training and inference.

Given the same game context the hand-tuned modules see, produce the feature
vector the learned multiplier is a function of. Keeping this in one place
guarantees training and inference stay in lockstep.

The features mirror the levers the hand-tuned engine pulls, so the learned
coefficients are directly interpretable — e.g. a negative ``wind`` weight for
passing yards means wind suppresses the passing game, learned rather than
assumed.
"""

from __future__ import annotations

from ..matchup import _defense_factor
from ..models import DefenseProfile, Game, Prop

# Order matters: it defines the coefficient layout in the serialized model.
FEATURE_ORDER = ["intercept", "def", "spread", "total", "wind", "dome", "cold"]


def _team_spread(prop: Prop, game: Game) -> float:
    """Point spread from the prop team's perspective (negative = favored)."""
    is_home = prop.team == game.home
    return game.spread if is_home else -game.spread


def extract_features(prop: Prop, game: Game, defense: DefenseProfile) -> dict:
    factor, _ = _defense_factor(defense, prop)     # box-score matchup strength
    ts = _team_spread(prop, game)
    w = game.weather
    return {
        "intercept": 1.0,
        "def": factor - 1.0,                       # >0 = generous matchup
        "spread": -ts / 10.0,                      # >0 = team favored
        "total": (game.total - 44.0) / 10.0,       # centered game total
        "wind": 0.0 if w.dome else w.wind_mph / 10.0,
        "dome": 1.0 if w.dome else 0.0,
        "cold": 1.0 if (not w.dome and w.temp_f <= 32) else 0.0,
    }


def vectorize(feat: dict) -> list[float]:
    return [feat[k] for k in FEATURE_ORDER]
