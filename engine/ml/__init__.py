"""Learned adjustments for the projection engine.

Replaces the hand-tuned weather/matchup *magnitudes* with coefficients fit on
historical data, while the rule modules still generate the human-readable
reasons. The structure is deliberately the same as the hand-tuned engine — a
multiplicative adjustment on the recent-form baseline — so a learned model is a
drop-in for the clamp in ``projection.build_projection``:

    predicted_mean = form.mean * exp(w · features)

Everything is pure Python (a small ridge regression solved by Gaussian
elimination), so there is no numpy/sklearn dependency and models serialize to
plain JSON.
"""

from .model import MultiplierModel, ridge_fit
from .features import extract_features, vectorize, FEATURE_ORDER

__all__ = ["MultiplierModel", "ridge_fit", "extract_features", "vectorize", "FEATURE_ORDER"]
