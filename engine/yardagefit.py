"""Why the yardage markets cannot rank a hit above a miss.

WHAT WAS KNOWN. `nfl:rush_yds` and `nfl:rec_yds` are shut: they measured
AUC 0.47 against a real book, their fitted temperature came out pinned to
the edge of its grid, and their isotonic curve saturated so hard that
`calibrate.one_sided` had to veto it — every rushing pick on the board
was an UNDER by construction. Meanwhile the same projections rank actual
yardage well (+0.663 and +0.541 by rank correlation, `engine.formcheck`),
and they are unbiased: the residual mean is -0.06 yards on a 25.2-yard
projection.

A good ordering, no bias, and no ability to beat a line is not a ranking
failure. It is the DISTRIBUTION.

WHAT IS WRONG WITH IT. The board answers "over this line?" with
`statmath.prob_over`, which is Normal(mean, std). Rushing yards are not
normal — they are a spike at zero with a long right tail. On the walked-
forward population the board would actually price:

    projection    P(zero)   normal's mass below zero
      1-8          61.9%          36.0%
      8-15         28.1%          25.7%
     15-30         11.9%          18.4%
     30-50          3.5%           9.1%
     50-75          0.9%           3.8%

The normal's negative tail is standing in for the goose egg, and it is
wrong in BOTH directions — far too little at the bottom, two to five
times too much everywhere above fifteen yards. Mass wrongly placed below
zero comes straight off the over, so the model misprices every over by an
amount that changes sign across the board. That is what an AUC of 0.47
looks like from the inside, and it is why a temperature cannot rescue it:
a monotone squeeze cannot move mass from one end of a distribution to the
other. The fitter ran to the boundary because it was asked to fix a shape
error with a width knob.

THE FAMILY THAT FITS. A real probability of zero plus a lognormal for the
rest. The player's own prior zero rate predicts the atom cleanly (4.4% ->
10.9% -> 23.8% -> 37.4% -> 66.5% across five bands), so it is priceable
rather than a constant.

AND THE PART THAT IS EASY TO GET WRONG. Fit that lognormal by maximum
likelihood on the density and it wins the distribution test outright —
PIT chi-square 482 -> 170 — while getting WORSE at the only question the
product asks, running about ten points light on every over. The density
objective is dominated by the many small outcomes; it buys shape in the
bulk and pays for it around the line. Fitted instead on P(over) itself
the same family lands where it should. The scores, leave-one-season-out,
mean absolute miss in claimed-against-realised P(over):

                                    rush_yds   rec_yds
    SHIPPED normal                    0.0418    0.0528
    mixture, width from the density   0.0945    0.0587
    mixture, width from P(over)       0.0265    0.0161

Standard library only. Needs `player_game_logs`; no odds history, so it
runs anywhere.

    python3 -m engine.yardagefit [market ...]
"""

from __future__ import annotations

import math
import sqlite3
import sys
from collections import defaultdict

from .db import DEFAULT_DB
from .form import WINDOW_WEIGHTS
from .projection import CV_FLOOR

#: The markets this asks about, and the lines to score P(over) at. Real
#: books hang these near a player's own projection, so the bands below
#: select the rows a book would plausibly have quoted at that number.
MARKETS = {
    "rush_yds": (15.5, 25.5, 40.5, 60.5),
    "rec_yds": (15.5, 25.5, 40.5, 60.5),
    "receptions": (2.5, 3.5, 4.5, 5.5),
    "pass_yds": (200.5, 235.5, 265.5),
}

#: Windows the shipped blend averages over — `engine.form.WINDOW_WEIGHTS`
#: supplies the weights, so a re-fit there moves this too.
WINDOWS = (("last1", 1), ("last3", 3), ("last5", 5), ("last10", 10))

#: Prior games before a player is projected at all, matching the live
#: usage maps rather than inventing a second window.
MIN_PRIOR = 4

#: A projection below this is not a prop anybody prices.
MIN_PROJECTION = 1.0

#: Rows a book would plausibly quote at a given line: within this
#: multiple of the projection, either side.
LINE_LO, LINE_HI = 0.4, 3.0

#: A band thinner than this is noise wearing a percentage.
MIN_BAND = 300
MIN_TRAIN, MIN_TEST = 800, 200

#: Widths searched for the positive part.
SIGMA_GRID = tuple(s / 100.0 for s in range(10, 161, 2))

DECILES = 10


def blended(vals) -> float:
    """The shipped window blend over a player's prior games."""
    pairs = []
    for name, n in WINDOWS:
        weight = WINDOW_WEIGHTS.get(name, 0.0)
        if weight:
            sub = vals[-n:]
            pairs.append((sum(sub) / len(sub), weight))
    season = WINDOW_WEIGHTS.get("season", 0.0)
    if season:
        pairs.append((sum(vals) / len(vals), season))
    total = sum(w for _v, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else 0.0


def rows(conn, market: str, sport: str = "nfl") -> list:
    """One row per player-week, from weeks STRICTLY BEFORE it."""
    by: dict = defaultdict(dict)
    for (season, period, player, team, value) in conn.execute(
            "SELECT season, period, player, team, value FROM player_game_logs "
            "WHERE sport=? AND market=?", (sport, market)):
        by[(season, player, team)][period] = float(value or 0.0)
    out = []
    for key, weeks in by.items():
        vals: list = []
        for period in sorted(weeks):
            if len(vals) >= MIN_PRIOR:
                mean = sum(vals) / len(vals)
                sd = math.sqrt(sum((v - mean) ** 2 for v in vals)
                               / (len(vals) - 1)) if len(vals) > 1 else 0.0
                out.append({
                    "season": key[0], "mu": blended(vals), "form_sd": sd,
                    "zero_rate": sum(1 for v in vals if v <= 0) / len(vals),
                    "actual": max(weeks[period], 0.0)})
            vals.append(weeks[period])
    return [d for d in out if d["mu"] > MIN_PROJECTION]


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def fit_zero(train) -> list:
    """P(zero) from the player's OWN prior rate, shrunk toward the league.

    A logistic on the rate, not the rate itself. A player with four prior
    games and one blank is claiming 25% and the sample does not support
    it; the fitted slope is what shrinks that claim.
    """
    xs = [[1.0, logit(min(max(d["zero_rate"], 0.02), 0.98))] for d in train]
    ys = [1 if d["actual"] <= 0 else 0 for d in train]
    beta = [0.0, 0.0]
    for _ in range(40):
        grad = [0.0, 0.0]
        hess = [[1e-6, 0.0], [0.0, 1e-6]]
        for x, y in zip(xs, ys):
            p = sigmoid(beta[0] * x[0] + beta[1] * x[1])
            w = max(p * (1.0 - p), 1e-9)
            for i in range(2):
                grad[i] += x[i] * (y - p)
                for j in range(2):
                    hess[i][j] += w * x[i] * x[j]
        det = hess[0][0] * hess[1][1] - hess[0][1] * hess[1][0]
        if abs(det) < 1e-12:
            break
        s0 = (grad[0] * hess[1][1] - hess[0][1] * grad[1]) / det
        s1 = (hess[0][0] * grad[1] - grad[0] * hess[1][0]) / det
        beta = [beta[0] + s0, beta[1] + s1]
        if abs(s0) < 1e-10 and abs(s1) < 1e-10:
            break
    return beta


def zero_prob(beta, row) -> float:
    return min(max(sigmoid(beta[0] + beta[1]
                           * logit(min(max(row["zero_rate"], 0.02), 0.98))),
                   0.001), 0.95)


def mixture_over(row, line: float, beta, sigma: float) -> float:
    """P(X > line) under (atom at zero) + (lognormal for the rest).

    MEAN-MATCHED, so the mixture still projects the mean the blend
    earned: E[X | X > 0] is mu / (1 - q), and the lognormal's median is
    set below that by exp(-sigma^2 / 2) to make its mean land there.
    """
    q = zero_prob(beta, row)
    if line <= 0:
        return 1.0 - q
    median = max(row["mu"] / (1.0 - q), 0.5) * math.exp(-0.5 * sigma * sigma)
    return (1.0 - q) * (1.0 - phi((math.log(line) - math.log(median)) / sigma))


def shipped_over(row, line: float, market: str) -> float:
    """What the board says today: Normal(mean, max(form sd, CV x mean))."""
    cv = CV_FLOOR.get(market, 0.35)
    sd = max(row["form_sd"], cv * max(row["mu"], 1.0))
    return 1.0 - phi((line - row["mu"]) / max(sd, 1e-6))


def over_error(data, lines, prob) -> float | None:
    """Mean absolute miss between claimed and realised P(over)."""
    total, used = 0.0, 0
    for line in lines:
        sel = [d for d in data if LINE_LO * line < d["mu"] < LINE_HI * line]
        if len(sel) < MIN_BAND:
            continue
        claimed = sum(prob(d, line) for d in sel) / len(sel)
        actual = sum(1 for d in sel if d["actual"] > line) / len(sel)
        total += abs(claimed - actual)
        used += 1
    return (total / used) if used else None


def fit_sigma_on_density(train, beta) -> float:
    """Maximum likelihood on the positive part — the WRONG objective for
    this product, kept because the comparison is the finding."""
    pos = [d for d in train if d["actual"] > 0]
    best = None
    for sigma in SIGMA_GRID:
        total = 0.0
        for d in pos:
            q = zero_prob(beta, d)
            median = max(d["mu"] / (1.0 - q), 0.5) * math.exp(-0.5 * sigma ** 2)
            z = (math.log(d["actual"]) - math.log(median)) / sigma
            total += -0.5 * z * z - math.log(sigma) - math.log(d["actual"])
        if best is None or total > best[0]:
            best = (total, sigma)
    return best[1]


def fit_sigma_on_over(train, beta, lines) -> float:
    """Fitted on the question the board actually asks."""
    best = None
    for sigma in SIGMA_GRID:
        err = over_error(train, lines,
                         lambda d, L, s=sigma: mixture_over(d, L, beta, s))
        if err is None:
            continue
        if best is None or err < best[0]:
            best = (err, sigma)
    return best[1] if best else 1.0


def pit_chi(data, cdf) -> float:
    """Uniformity of the probability integral transform, by decile."""
    counts = [0] * DECILES
    for d in data:
        u = min(max(cdf(d), 0.0), 0.999999)
        counts[int(u * DECILES)] += 1
    expected = len(data) / DECILES
    return sum((c - expected) ** 2 / expected for c in counts)


def report(market: str, conn=None, db_path=None) -> list:
    close = conn is None
    conn = conn or sqlite3.connect(str(db_path or DEFAULT_DB))
    try:
        data = rows(conn, market)
    finally:
        if close:
            conn.close()
    lines = MARKETS.get(market, ())
    out = [f"=== nfl:{market} — {len(data):,} walked-forward player-weeks"]
    if len(data) < MIN_TRAIN + MIN_TEST or not lines:
        return out + ["  too few player-weeks to measure"]
    zeroes = sum(1 for d in data if d["actual"] <= 0) / len(data)
    out.append(f"  {zeroes:.1%} of outcomes are exactly zero — the shape "
               f"no density has")

    seasons = sorted({d["season"] for d in data})
    totals = defaultdict(float)
    n = 0
    kept = None
    for season in seasons:
        train = [d for d in data if d["season"] != season]
        test = [d for d in data if d["season"] == season]
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            continue
        beta = fit_zero(train)
        s_density = fit_sigma_on_density(train, beta)
        s_over = fit_sigma_on_over(train, beta, lines)
        kept = (beta, s_density, s_over)
        for label, prob in (
                ("SHIPPED normal", lambda d, L: shipped_over(d, L, market)),
                ("mixture, width from density",
                 lambda d, L, b=beta, s=s_density: mixture_over(d, L, b, s)),
                ("mixture, width from P(over)",
                 lambda d, L, b=beta, s=s_over: mixture_over(d, L, b, s))):
            err = over_error(test, lines, prob)
            if err is not None:
                totals[label] += err * len(test)
        n += len(test)
    if not n or kept is None:
        return out + ["  not enough seasons to hold one out"]
    beta, s_density, s_over = kept
    out.append(f"  P(zero) = sigmoid({beta[0]:+.2f} {beta[1]:+.2f} x "
               f"logit(prior zero rate));  lognormal width "
               f"{s_density:.2f} by density, {s_over:.2f} by P(over)")
    out.append("  held-out mean |claimed - realised| P(over):")
    best = min(totals, key=totals.get)
    for label, value in totals.items():
        mark = "   <-- best" if label == best else ""
        out.append(f"    {label:<30}{value / n:>8.4f}{mark}")
    out.append(f"  {'line':>8}{'rows':>7}   shipped / mixture / realised")
    for line in lines:
        sel = [d for d in data if LINE_LO * line < d["mu"] < LINE_HI * line]
        if len(sel) < MIN_BAND:
            continue
        ship = sum(shipped_over(d, line, market) for d in sel) / len(sel)
        mix = sum(mixture_over(d, line, beta, s_over) for d in sel) / len(sel)
        real = sum(1 for d in sel if d["actual"] > line) / len(sel)
        out.append(f"  {line:>8.1f}{len(sel):>7}   {ship:>7.1%}"
                   f"{mix:>9.1%}{real:>10.1%}")
    return out


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    for i, market in enumerate(args or list(MARKETS)):
        if i:
            print()
        for line in report(market):
            print(line)
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
