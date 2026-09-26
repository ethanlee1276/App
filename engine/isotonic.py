"""A calibrator with more than one knob, because the error has more than
one sign.

WHY THIS EXISTS. `calibrate.py` corrects a model with temperature scaling:
one parameter, applied in log-odds space, that squeezes every probability
toward 50% (T > 1) or pushes it away (T < 1). It is the right tool for a
model that is uniformly over- or under-confident, and it is a strictly
monotone map with 50% as its fixed point — which means the correction it
applies always has the SAME SIGN on the same side of 50%.

Ethan's own Record page, MLB hits, 295,456 settled props:

    said 19%  →  actual 14%   (over-claimed by 5)
    said 30%  →  actual 26%   (over-claimed by 4)
    said 54%  →  actual 58%   (UNDER-claimed by 4)
    said 66%  →  actual 87%   (UNDER-claimed by 21)
    said 83%  →  actual 81%   (over-claimed by 2)

That curve crosses the diagonal twice. Above 50% it needs to be pushed UP
at 66% and DOWN at 83%; no value of T does both, because T's correction
above 50% is one-signed by construction. The site's own copy already says
this out loud — "a line that crosses is two different problems wearing one
average" — and then the fitter averages them anyway. It lands on whatever
the biggest bucket wants (40–60% holds 92% of the samples) and leaves the
tails as they were.

WHAT THIS DOES INSTEAD. Isotonic regression: the least-squares fit to the
outcomes subject only to "never decreasing". No functional form, so it can
bend where the data bends and cross the diagonal as many times as the data
does. Fitted by the pool-adjacent-violators algorithm, which is exact,
linear-time and about thirty lines of arithmetic — no dependency, and
nothing to tune.

WHAT IT COSTS, AND THE GUARD. Flexibility overfits. A curve with enough
knots reproduces its training set perfectly and predicts nothing, which is
the failure mode temperature scaling was chosen to avoid in the first
place. Two restraints, and the second is the one that matters:

  * :data:`MIN_BIN` — no knot may rest on fewer than this many samples, so
    a single lucky pocket cannot become a step in the curve;
  * the fit is never adopted on its own say-so. `calibrate.fit` runs it
    against plain temperature scaling on a HELD-OUT slice and keeps
    whichever actually wins there, or neither. See that function; this
    module only produces candidates.

Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Fewest samples allowed under one knot. Below this a step in the curve
#: is a coincidence with a shape.
MIN_BIN = 250


def pava(pairs: list[tuple[float, int]]) -> list[tuple[float, float, int]]:
    """Pool adjacent violators: the monotone least-squares fit.

    Returns ``[(x_max_of_block, mean_outcome, n_in_block), ...]`` in
    increasing x. Exact: sort by the predicted probability, then merge any
    adjacent pair whose means run downhill, which is provably the
    least-squares solution under the monotone constraint.

    THE COUNT IS RETURNED, not reconstructed afterwards. The first cut of
    this walked the sorted points back over the block edges to count them,
    which is wrong whenever two blocks share an x_max — ties at the same
    predicted probability are common and every point lands in the first
    block, leaving the second with zero and dividing by it. The algorithm
    already knows the size of every block it merged; asking it is both
    correct and shorter.
    """
    if not pairs:
        return []
    pts = sorted(pairs, key=lambda t: t[0])
    # Each block: [sum of outcomes, count, largest x in the block]
    blocks: list[list[float]] = []
    for x, y in pts:
        blocks.append([float(y), 1.0, float(x)])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
            s, n, _ = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
            blocks[-1][2] = max(blocks[-1][2], x)
    return [(b[2], b[0] / b[1], int(b[1])) for b in blocks]


def _merge_small(blocks: list[tuple[float, float, int]],
                 min_bin: int) -> list[tuple[float, float, int]]:
    """Fold blocks under ``min_bin`` into their neighbour, keeping order.

    Merging is by weighted mean, so the result is still the monotone fit
    of the pooled data — folding a thin block into its neighbour cannot
    break monotonicity, because the merged mean lies between the two.
    """
    xs = [[float(x), float(y), int(n)] for x, y, n in blocks]
    i = 0
    while len(xs) > 1 and i < len(xs):
        if xs[i][2] >= min_bin:
            i += 1
            continue
        j = i + 1 if i + 1 < len(xs) else i - 1
        tot = xs[i][2] + xs[j][2]
        if tot <= 0:
            xs.pop(i)
            continue
        xs[j][1] = (xs[i][1] * xs[i][2] + xs[j][1] * xs[j][2]) / tot
        xs[j][0] = max(xs[i][0], xs[j][0])
        xs[j][2] = tot
        xs.pop(i)
        i = max(0, i - 1)
    return [(x, y, n) for x, y, n in xs]


@dataclass
class Curve:
    """A fitted monotone mapping from claimed probability to corrected one.

    ``knots`` are ``(x, y)`` in increasing x, where x is the largest
    claimed probability in a pooled block and y is what actually happened
    in it. Between knots the curve interpolates linearly, so the result is
    continuous — a step function would make two nearly identical claims
    land on visibly different corrected numbers, which reads as a bug on a
    board even when the arithmetic is right.
    """

    knots: list[tuple[float, float]] = field(default_factory=list)
    samples: int = 0

    def apply(self, p: float) -> float:
        if not self.knots:
            return float(p)
        p = float(p)
        ks = self.knots
        if p <= ks[0][0]:
            return _clip(ks[0][1])
        if p >= ks[-1][0]:
            return _clip(ks[-1][1])
        for (x0, y0), (x1, y1) in zip(ks, ks[1:]):
            if x0 <= p <= x1:
                if x1 == x0:
                    return _clip(y1)
                w = (p - x0) / (x1 - x0)
                return _clip(y0 + w * (y1 - y0))
        return _clip(ks[-1][1])

    def to_dict(self) -> dict:
        return {"knots": [[round(x, 5), round(y, 5)] for x, y in self.knots],
                "samples": self.samples}

    @staticmethod
    def from_dict(d) -> "Curve":
        if not isinstance(d, dict):
            return Curve()
        ks = []
        for pair in d.get("knots") or []:
            try:
                ks.append((float(pair[0]), float(pair[1])))
            except (TypeError, ValueError, IndexError):
                return Curve()
        return Curve(knots=ks, samples=int(d.get("samples") or 0))

    def __bool__(self) -> bool:
        return len(self.knots) > 1


def _clip(y: float) -> float:
    return min(max(float(y), 1e-4), 1.0 - 1e-4)


def fit(pairs: list[tuple[float, int]], min_bin: int = MIN_BIN) -> Curve:
    """Fit a monotone calibration curve, or an empty one if it cannot.

    An empty Curve is falsey and applies nothing, which is the honest
    output when the sample is too small to place even two knots — a curve
    of one knot is a constant, and a model that answers the same number to
    every question is not calibrated, it is switched off.
    """
    if len(pairs) < min_bin * 2:
        return Curve()
    blocks = _merge_small(pava(pairs), min_bin)
    if len(blocks) < 2:
        return Curve()
    return Curve(knots=[(float(x), float(y)) for x, y, _n in blocks],
                 samples=len(pairs))


def brier(pairs: list[tuple[float, int]], curve: Curve | None = None) -> float:
    if not pairs:
        return 0.0
    if curve is None or not curve:
        return sum((p - o) ** 2 for p, o in pairs) / len(pairs)
    return sum((curve.apply(p) - o) ** 2 for p, o in pairs) / len(pairs)
