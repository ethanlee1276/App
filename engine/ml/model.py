"""Pure-Python ridge regression and the serialized multiplier model.

The feature dimension is tiny (a handful of matchup/weather terms), so the
normal equations (XᵀX + λR) w = Xᵀy are solved directly by Gaussian elimination
with partial pivoting — no linear-algebra dependency required.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from ..statmath import clamp


def _matmul_AtA(X: list[list[float]]) -> list[list[float]]:
    n = len(X[0])
    A = [[0.0] * n for _ in range(n)]
    for row in X:
        for i in range(n):
            xi = row[i]
            if xi == 0.0:
                continue
            Ai = A[i]
            for j in range(n):
                Ai[j] += xi * row[j]
    return A


def _matvec_Atb(X: list[list[float]], y: list[float]) -> list[float]:
    n = len(X[0])
    b = [0.0] * n
    for row, yi in zip(X, y):
        for i in range(n):
            b[i] += row[i] * yi
    return b


def solve_linear(A: list[list[float]], b: list[float]) -> list[float]:
    """Solve A x = b via Gaussian elimination with partial pivoting."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        # partial pivot
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            M[piv][col] += 1e-9  # nudge a singular pivot
        M[col], M[piv] = M[piv], M[col]
        pivot = M[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = M[r][col] / pivot
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                M[r][c] -= factor * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def ridge_fit(X: list[list[float]], y: list[float], l2: float = 1.0,
              reg_mask: list[int] | None = None) -> list[float]:
    """Ridge-regression weights. ``reg_mask`` (1=regularize, 0=don't) defaults to
    regularizing everything except the first column (the intercept)."""
    if not X:
        return []
    n = len(X[0])
    if reg_mask is None:
        reg_mask = [0] + [1] * (n - 1)
    A = _matmul_AtA(X)
    for i in range(n):
        A[i][i] += l2 * reg_mask[i]
    b = _matvec_Atb(X, y)
    return solve_linear(A, b)


@dataclass
class MultiplierModel:
    """Per-market learned multipliers on the recent-form baseline."""

    feature_order: list[str]
    coefs: dict[str, list[float]]           # market -> weights
    clamp_lo: float = 0.70
    clamp_hi: float = 1.40
    meta: dict | None = None

    def has(self, market: str) -> bool:
        return market in self.coefs

    def predict_log(self, feat_vec: list[float], market: str) -> float:
        return sum(w * f for w, f in zip(self.coefs[market], feat_vec))

    def predict_multiplier(self, feat_vec: list[float], market: str) -> float:
        return clamp(math.exp(self.predict_log(feat_vec, market)),
                     self.clamp_lo, self.clamp_hi)

    # --- serialization ---
    def to_dict(self) -> dict:
        return {
            "feature_order": self.feature_order,
            "coefs": self.coefs,
            "clamp_lo": self.clamp_lo,
            "clamp_hi": self.clamp_hi,
            "meta": self.meta or {},
        }

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_dict(cls, d: dict) -> "MultiplierModel":
        return cls(
            feature_order=d["feature_order"],
            coefs={k: list(map(float, v)) for k, v in d["coefs"].items()},
            clamp_lo=d.get("clamp_lo", 0.70),
            clamp_hi=d.get("clamp_hi", 1.40),
            meta=d.get("meta", {}),
        )

    @classmethod
    def load(cls, path: str | Path) -> "MultiplierModel":
        return cls.from_dict(json.loads(Path(path).read_text()))
