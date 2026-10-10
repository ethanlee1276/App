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

THE VERDICT, 2026-08-30: MEASURED, AND NOT WIRED IN.

Run against the droplet's real closes — walked forward, split by week,
both parameters fitted on the earlier weeks, bets priced against the
book's own two sides so the vig is paid:

    market       model      |claimed-real|   bets    hit      ROI
    rec_yds      SHIPPED           0.1137     344   49.7%    -6.9%
    rec_yds      mixture           0.0709     360   48.9%    -7.9%
    receptions   SHIPPED           0.0610     304   55.6%    +4.5%
    receptions   mixture           0.0285     332   56.6%    +4.2%

The mixture is a better PROBABILITY and not a better BOARD. It halves the
calibration miss in both markets — that part is real, large, and held
out — and it does not make money that the normal was not already making.
On receptions it takes 28 more bets and lifts the hit rate a point while
the ROI does not move.

AND AT THIS SAMPLE SIZE THE ROI COLUMN CANNOT SEPARATE THEM ANYWAY. At
300-360 flat stakes the standard error on any of those numbers is about
five points:

    receptions mixture   +4.2%   95% CI roughly [-2%, +18%]
    rec_yds    mixture   -7.9%   95% CI roughly [-17%, +3%]

Neither market's ROI is distinguishable from zero, let alone from the
other model's. So the honest reading is not "the mixture lost" — it is
"the mixture is better calibrated and the board did not care, and we
cannot yet measure whether it would."

That is enough to decline the change. Rewriting every yardage probability
on a live board — receptions is the market with the measured edge — buys
a better-looking number and no demonstrated gain, and the live path is
not where you find out.

AND THE GATE THAT REFUSES THESE MARKETS COSTS NOTHING, measured on the
live NFL board 2026-09-03. `calibrate.is_reliable` shuts rush_yds and
rec_yds outright, which reads on the page as a door with picks behind
it. Ethan asked whether that was the reason the board recommended none:

    "NFL's 169 props dying at calibration — the rushing/receiving fits
     are at their search boundary. That's the single biggest reason NFL
     shows zero picks."

277 props built, 124 carrying a real book price, 153 never quoted by
anybody — books post lines for a subset of the skill players we project,
and 277 - 124 is exactly the 153. Of the 124 priced, 80 sat in the two
shut markets. Replaying every OTHER gate on those 80 from the published
row — credibility, the tier bar, break-even plus the favourite
surcharge, the quality floor, and every rule check but the grade:

    56   model disagrees with the book by more than 10 points
    24   edge under the tier bar
     0   would have been a pick

Not one reached the price gate, let alone the quality floor or the
rules. The calibration gate refused eighty props and every one of them
dies one gate later on its own merits. So the refusal is honest AND
free: reopening these markets — by widening the search grid, by wiring
the mixture below, by any route — buys zero picks on this board.

That 56 is the rest of this module seen from the live path instead of
the harness — but only three quarters of it is. The same replay across
ALL 124 priced props, not just the eighty in the shut markets:

    market        over 10 points off      95% CI        P(zero)
    rush_yds           27/32    84%     [68%, 93%]       29.0%
    rec_yds            29/48    60%     [46%, 73%]       21.2%
    pass_yds           16/25    64%     [45%, 80%]        2.3%
    receptions          4/19    21%     [ 9%, 43%]       12.4%
    -----------------------------------------------------------
    all                76/124   61%     [53%, 69%]

Three of the four fall in the order the zero rates predict — rushing
worst, receiving next, receptions best, against 29.0 > 21.2 > 12.4.
That is this module's argument confirmed on a live board against real
book prices rather than in a harness.

PASSING YARDS REFUTES IT. 2.3% zeroes, by far the most normal-shaped of
the four, and it misses the market by more than ten points on two thirds
of the props books quote — indistinguishable from receiving yards and
clearly worse than receptions, whose intervals do not overlap it. A
spike at zero cannot explain a market that has no spike at zero. There
is a SECOND defect in the football prop chain and this module does not
know what it is.

Which matters more than the yardage finding, because pass_yds is NOT
shut. rush_yds and rec_yds are refused wholesale and cost nothing;
passing yards is open, priced, and on the board.

And 61% of the whole priced board failing is a statement about the model
rather than about 76 separate bad quotes. `MAX_CREDIBLE_EDGE`'s own
comment calls a gap this size "a data error, not alpha". When three
props in five trip a bad-data detector, the data being detected is ours.

WHAT IS NOT KNOWN, and has to be before anyone acts on the table above:
whether the gap is the model's number or the market's. `fair` comes out
of the two-way de-vig, and task #66 — verify the NFL de-vig once Week 1
prop menus post — is open for exactly this reason. This board IS Week 1:
every projection is built on last season's logs across a summer of
roster churn, which is the widest this model will ever be. A signed,
side-normalised gap per market separates a biased model from a merely
wide one from a broken de-vig, and none of that is measured yet.

WHAT WOULD CHANGE THE ANSWER, in order:
  * More closes. rush_yds (838 joined) and pass_yds (266) are still too
    thin to ask, and rush_yds is one of the two shut markets this was
    meant to reopen. The harvest covers 14 weeks of one season and about
    58% of it joins; roughly three times the closes would take every
    market past the noise floor.
  * A reason to care about calibration for its own sake. The displayed
    model %, the EV on the card and the stake all read the probability,
    and being twice as close is worth something there even when the
    bet/no-bet decision does not move. That is a product argument, not a
    betting one, and it should be made as one.

Standard library only. The synthetic-line half needs `player_game_logs`
and runs anywhere; `--real` needs `odds_history` and only runs on the box
that bought the closes.

    python3 -m engine.yardagefit [market ...]
    python3 -m engine.yardagefit --real [market ...]
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
                    "actual": max(weeks[period], 0.0),
                    # IDENTITY TRAVELS, so a row can be joined to the
                    # price a book actually hung on it. Without this the
                    # only lines available are synthetic ones placed at
                    # round numbers, which is a weaker question.
                    "player": key[1], "team": key[2], "period": period})
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


def fit_sigma_on_over(train, beta, lines, weight: float = 0.0,
                      typical: float = 0.0) -> float:
    """Fitted on the question the board actually asks."""
    best = None
    for sigma in SIGMA_GRID:
        err = over_error(train, lines,
                         lambda d, L, s=sigma: mixture_over(
                             d, L, beta, s * _width_of(d, weight, typical)))
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


# --- against the prices a book actually hung ------------------------------
#
# Everything above is scored at SYNTHETIC lines placed at round numbers,
# on rows selected by projection. That is a weaker question than the one
# the board answers, and it is the reason none of this is wired in: a
# book hangs its line at its own number, which is sharper than a fixed
# grid, so better calibration against 25.5 does not prove a better board.
#
# This half needs `odds_history`, which only the box that bought the
# closes has. It is the same join `engine.tdbook` makes for touchdowns —
# walk the model forward, then meet it with the price.

#: A close further from the model's projection than this is a different
#: player — a name collision, or a line for a market we mis-keyed.
MAX_LINE_GAP = 4.0

#: Bet only when the model disagrees with the price by at least this
#: much. The board's own bar is higher; this is deliberately loose,
#: because the question here is whether the DISAGREEMENT is informative
#: at all, not whether it clears a threshold.
MIN_EDGE = 0.03

#: Share of the harvested WEEKS that train; the rest score.
TRAIN_SHARE = 0.7

#: Rows either side of that cut before the comparison means anything.
MIN_SPLIT = 250


def _order(period):
    """Sort a period that may be a week number or a date, numerically.

    '10' before '9' is a silently wrong timeline, and a wrong timeline
    means the split leaks the future into training.
    """
    try:
        return (0, int(str(period).lstrip("0") or 0), "")
    except (TypeError, ValueError):
        return (1, 0, str(period))


def split_by_week(rows) -> tuple[list, list]:
    """Earlier weeks train, later weeks score.

    BY WEEK, NOT BY SEASON, and that is a correction this codebase has
    already made once. `engine.devigfit` split on season first, reasoning
    that a season boundary certainly separates games — it does, but a
    PURCHASED HARVEST COVERS A STRETCH OF ONE SEASON. Leave-one-season-out
    over 1,808 joined receiving rows returns nothing at all and reports
    the data as too thin, when the data is fine and the split is wrong.

    Split by time rather than at random for the usual reason: players in
    one game share a scoreboard, so a random split leaves the same game
    in both halves and the more flexible model wins on memory.
    """
    keys = sorted({(r["season"], _order(r["period"])) for r in rows})
    if len(keys) < 2:
        return [], []
    cut = max(1, min(len(keys) - 1, round(len(keys) * TRAIN_SHARE)))
    train_keys = set(keys[:cut])
    train, test = [], []
    for r in rows:
        k = (r["season"], _order(r["period"]))
        (train if k in train_keys else test).append(r)
    return train, test


def _norm(name: str) -> str:
    """The join key, shared rather than copied.

    A second normaliser that drifts from the first is the same bug this
    codebase keeps paying for — two spellings, two people. `backtest`
    owns this one and six other join sites use it.
    """
    from .backtest import _norm as shared
    return shared(name)


def real_lines(conn, market: str, sport: str = "nfl") -> dict:
    """``{(normalised player, YYYY-MM-DD): close}`` from the harvest."""
    from .db import closing_odds_by_date
    out = {}
    for (player, date), row in closing_odds_by_date(conn, sport, market).items():
        out[(_norm(player), date)] = row
    return out


def dated(rows, seasons=None) -> int:
    """Stamp each row with its game's date, in place. Returns how many.

    The logs key a game by (season, period); the harvest keys a price by
    (player, date). `formbook.game_dates` is the bridge both sides of
    this codebase already use.
    """
    from .formbook import game_dates
    dates = game_dates(seasons)
    hit = 0
    for r in rows:
        try:
            week = int(str(r["period"]).lstrip("0") or 0)
        except (TypeError, ValueError):
            continue
        date = dates.get((r["season"], week, r["team"]))
        if date:
            r["date"] = date
            hit += 1
    return hit


def matched(rows, closes) -> tuple[list, dict]:
    """``(joined rows, why the rest did not)``.

    A join that quietly drops 40% of a purchased harvest and reports the
    remainder as the answer is how a thin result gets read as a thin
    market. The counts say which it is.
    """
    out = []
    why = {"no date": 0, "no close": 0, "line far from projection": 0}
    for r in rows:
        if not r.get("date"):
            why["no date"] += 1
            continue
        close = closes.get((_norm(r["player"]), r["date"]))
        if not close or close.get("line") is None:
            why["no close"] += 1
            continue
        line = float(close["line"])
        # A LINE NOWHERE NEAR THE PROJECTION IS A DIFFERENT PLAYER. Two
        # men share a name every season, and joining them silently is how
        # a backtest reports an edge it never had. Scaled by the square
        # root of the projection, because four yards means something very
        # different at 8 than at 80.
        if line <= 0 or abs(line - r["mu"]) > MAX_LINE_GAP * max(
                1.0, r["mu"] ** 0.5):
            why["line far from projection"] += 1
            continue
        got = dict(r)
        got["line"] = line
        got["over_odds"] = close.get("over_odds")
        got["under_odds"] = close.get("under_odds")
        got["book"] = close.get("book", "")
        out.append(got)
    return out, why


def _american_prob(odds) -> float | None:
    if odds is None:
        return None
    o = float(odds)
    return (100.0 / (o + 100.0)) if o > 0 else ((-o) / (-o + 100.0))


def _payout(odds) -> float:
    o = float(odds)
    return (o / 100.0) if o > 0 else (100.0 / -o)


def bet_record(rows, prob, min_edge: float = MIN_EDGE) -> dict:
    """Flat-stake ROI from betting whichever side the model prefers.

    THE ONLY SCORE THAT SETTLES THIS. A better-calibrated probability
    that never disagrees with the price profitably is a nicer number and
    the same board. Priced against the book's own two sides, so the vig
    is paid exactly as it would be.
    """
    bets = wins = 0
    pnl = 0.0
    for r in rows:
        p_over = prob(r, r["line"])
        over_p = _american_prob(r["over_odds"])
        under_p = _american_prob(r["under_odds"])
        if over_p is None or under_p is None:
            continue
        hit = r["actual"] > r["line"]
        if p_over - over_p >= min_edge:
            bets += 1
            wins += 1 if hit else 0
            pnl += _payout(r["over_odds"]) if hit else -1.0
        elif (1.0 - p_over) - under_p >= min_edge:
            bets += 1
            wins += 0 if hit else 1
            pnl += -1.0 if hit else _payout(r["under_odds"])
    return {"bets": bets, "wins": wins, "pnl": pnl,
            "roi": (pnl / bets) if bets else None,
            "hit_rate": (wins / bets) if bets else None}


def ranked_record(rows, prob, by: str = "edge", take: float = 0.25,
                  min_edge: float = MIN_EDGE) -> dict:
    """Bet the TOP SLICE of a board, ordered either way, and settle it.

    THE QUESTION ETHAN ASKED, 2026-08-30: "we need to figure out if we are
    gonna put real money on these bets" — i.e. should the likelihood board
    feed the money path, or only the edge board?

    Ranking and pricing are different abilities and the site is now good
    at one of them. But a board ordered by LIKELIHOOD is not automatically
    a board worth betting: a -260 near-lock can be correctly ranked first
    and still lose money, because being right 70% of the time at a price
    that needs 72% is a losing bet made confidently.

    So this settles it empirically rather than by argument. Both orderings
    bet the same NUMBER of rows off the same qualifying pool — every row
    where the model disagrees with the price by `min_edge`, so neither
    ordering is allowed to bet something the other would refuse outright.
    The only difference is WHICH of the qualifying rows get the money.

    `by="prob"` takes the most likely; `by="edge"` takes the biggest
    disagreement. Same stake, same prices, same vig.
    """
    pool = []
    for r in rows:
        p_over = prob(r, r["line"])
        over_p = _american_prob(r["over_odds"])
        under_p = _american_prob(r["under_odds"])
        if over_p is None or under_p is None:
            continue
        if p_over - over_p >= min_edge:
            pool.append((r, True, p_over, p_over - over_p))
        elif (1.0 - p_over) - under_p >= min_edge:
            pool.append((r, False, 1.0 - p_over, (1.0 - p_over) - under_p))
    if not pool:
        return {"bets": 0, "roi": None, "hit_rate": None}
    key = (lambda t: -t[2]) if by == "prob" else (lambda t: -t[3])
    pool.sort(key=key)
    n = max(1, int(round(len(pool) * take)))
    wins = 0
    pnl = 0.0
    for r, is_over, _p, _e in pool[:n]:
        hit = r["actual"] > r["line"]
        won = hit if is_over else not hit
        odds = r["over_odds"] if is_over else r["under_odds"]
        wins += 1 if won else 0
        pnl += _payout(odds) if won else -1.0
    return {"bets": n, "wins": wins, "pnl": pnl, "roi": pnl / n,
            "hit_rate": wins / n, "pool": len(pool)}


def report_real(market: str, conn=None, db_path=None) -> list:
    """The same candidates, judged at the prices books really hung."""
    import sqlite3 as _sq
    close_it = conn is None
    conn = conn or _sq.connect(str(db_path or DEFAULT_DB))
    conn.row_factory = _sq.Row
    try:
        data = rows(conn, market)
        closes = real_lines(conn, market)
        out = [f"=== nfl:{market} against REAL closes"]
        if not closes:
            return out + ["  no harvested closing lines for this market — "
                          "this needs the box that bought them"]
        stamped = dated(data, sorted({d["season"] for d in data}))
        joined, why = matched(data, closes)
        out.append(f"  {len(data):,} walked-forward rows, {stamped:,} dated, "
                   f"{len(closes):,} harvested closes, "
                   f"{len(joined):,} joined")
        out.append("  unjoined: " + ", ".join(
            f"{k} {v:,}" for k, v in why.items() if v))

        lines = MARKETS.get(market, ())
        train, test = split_by_week(joined)
        weeks = len({(r["season"], _order(r["period"])) for r in joined})
        out.append(f"  harvest spans {weeks} week(s) over "
                   f"{len({r['season'] for r in joined})} season(s) — "
                   f"split {len(train):,} train / {len(test):,} score")
        if len(train) < MIN_SPLIT or len(test) < MIN_SPLIT:
            return out + [
                f"  too thin to judge: needs {MIN_SPLIT} either side of the "
                f"cut. This is a harvest size problem, not a verdict — "
                f"buy more closes for this market and re-run"]

        beta = fit_zero(train)
        s_over = fit_sigma_on_over(train, beta, lines)
        cands = {
            "SHIPPED normal": lambda r, L: shipped_over(r, L, market),
            "mixture": (lambda r, L, b=beta, sg=s_over:
                        mixture_over(r, L, b, sg)),
        }
        out.append(f"  {'model':<18}{'|claimed-real|':>15}{'bets':>7}"
                   f"{'hit':>8}{'ROI':>9}")
        actual = sum(1 for r in test if r["actual"] > r["line"]) / len(test)
        for label, prob in cands.items():
            claimed = sum(prob(r, r["line"]) for r in test) / len(test)
            got = bet_record(test, prob)
            row = f"  {label:<18}{abs(claimed - actual):>15.4f}" \
                  f"{got['bets']:>7}"
            row += (f"{got['hit_rate']:>8.1%}{got['roi']:>9.1%}"
                    if got["bets"] else f"{'-':>8}{'-':>9}")
            out.append(row)
        out.append(f"  overs actually landed {actual:.1%} of the time on "
                   f"the scored weeks")
        out.append("  a better number that never bets differently is a "
                   "nicer model and the same board — the ROI column is "
                   "the one that decides whether to wire this in")

        # DOES THE LIKELIHOOD BOARD DESERVE MONEY? Same qualifying pool,
        # same stake, same prices — only the ORDER in which the money is
        # spent differs. If likelihood wins here, the main board earns a
        # place in the journal; if edge wins, the likelihood page stays
        # insight and the edge board keeps the bankroll.
        out.append(f"  {'top quarter picked by':<24}{'bets':>7}{'hit':>8}"
                   f"{'ROI':>9}")
        ship = lambda r, L: shipped_over(r, L, market)     # noqa: E731
        for by, label in (("prob", "likelihood"), ("edge", "edge")):
            got = ranked_record(test, ship, by=by)
            if not got["bets"]:
                continue
            out.append(f"  {label:<24}{got['bets']:>7}"
                       f"{got['hit_rate']:>8.1%}{got['roi']:>9.1%}")
        return out
    finally:
        if close_it:
            conn.close()


# --- the fitted mixture, stored for the likelihood board -----------------
#
# DECLINED FOR BETTING, ADOPTED FOR DISPLAY, and those are not in tension.
# Against real closes the mixture does not make money the normal was not
# already making, so it has no business changing which bets get placed.
# But the likelihood board's whole job is to state HOW LIKELY something
# is, and there the mixture is measurably closer: it halves the miss
# between what we claim and what lands (rec_yds 0.1137 -> 0.0709,
# receptions 0.0610 -> 0.0285).
#
# The page needed it badly. `calibrate.correction_for` DISCARDS a
# boundary fit rather than applying it — correctly, since a capped
# temperature is the search failing — so rush_yds and rec_yds, the two
# markets whose fits ran to the cap, were being displayed with NO
# correction at all. The likelihood page was quoting the raw number from
# the two markets measured most overconfident.
#
# pass_yds is excluded on the same evidence that adopted the others: it
# is 2.3% zeroes, the normal fits it nearly perfectly, and the mixture
# measured WORSE there (0.0389 against 0.0324).
MIXTURE_MARKETS = ("rush_yds", "rec_yds", "receptions")

#: HOW MUCH OF THE PLAYER'S OWN VOLATILITY GOES INTO HIS WIDTH, per
#: market. 0.0 is one league-wide sigma for everybody; 1.0 scales it by
#: how volatile this player has been against the market's typical; 0.5 is
#: the shrunk middle, which is what a per-player estimate off four games
#: deserves when nobody quite believes it.
#:
#: MEASURED 2026-08-30, walking the train/score cut across five points of
#: the season, scored on mean absolute miss between claimed and realised
#: P(over):
#:
#:     market      typical CV   winner                 flat -> adopted
#:     rush_yds        0.98     scaled, 5 of 5 cuts    0.0275 -> 0.0137
#:     rec_yds         0.86     per-player, 5 of 5     0.0181 -> 0.0161
#:     receptions      0.61     flat holds             0.0037 (late cuts)
#:
#: The ordering is the finding and it is not a coincidence: the more
#: dispersed the market, the more a player's own spread is worth knowing.
#: In a stable market a four-game CV is mostly noise, and receptions —
#: the tightest of the three — is where scaling never once won.
#:
#: So each market takes its own answer, the same way the mixture itself
#: was adopted for three markets and refused for pass_yds. rec_yds takes
#: the blended form rather than the full one because the later cuts, which
#: carry the most training data and are the closest thing here to live
#: conditions, preferred it.
WIDTH_WEIGHT = {"rush_yds": 1.0, "rec_yds": 0.5, "receptions": 0.0}

#: A width may not double or halve on the strength of four games.
WIDTH_CLAMP = (0.6, 1.6)

#: Where the fitted mixture lives, beside the calibration store and
#: per-box for the same reason: it is fitted from this box's history.
STORE_NAME = "yardage.json"


def store_path(models_dir=None):
    import os
    from pathlib import Path
    base = models_dir or os.environ.get("QB_MODELS_DIR") or (
        Path(__file__).resolve().parents[1] / "data" / "models")
    return Path(base) / STORE_NAME


def fit_market(conn, market: str) -> dict | None:
    """``{"zero": [b0, b1], "sigma": s, "rows": n}`` fitted on all history."""
    data = rows(conn, market)
    lines = MARKETS.get(market, ())
    if len(data) < MIN_TRAIN or not lines:
        return None
    beta = fit_zero(data)
    weight = WIDTH_WEIGHT.get(market, 0.0)
    typical = _typical_cv(data)
    # Fitted WITH the width rule in force, so sigma and the scaling are
    # chosen together rather than one being bolted onto the other.
    sigma = fit_sigma_on_over(data, beta, lines,
                              weight=weight, typical=typical)
    return {"zero": [round(beta[0], 5), round(beta[1], 5)],
            "sigma": round(sigma, 4), "rows": len(data),
            "width_weight": weight, "typical_cv": round(typical, 4),
            "market": market}


def _typical_cv(rows) -> float:
    """The market's median coefficient of variation — what a player's own
    spread is compared AGAINST, so the scaling is relative rather than
    absolute."""
    cvs = sorted((r["form_sd"] / r["mu"]) for r in rows
                 if r["mu"] > 0 and r["form_sd"] > 0)
    return cvs[len(cvs) // 2] if cvs else 0.0


def _width_of(row, weight: float, typical: float) -> float:
    """The multiplier on sigma for one row — 1.0 when the market takes no
    per-player width, or the clamped ratio scaled by what it earned."""
    if not weight or typical <= 0:
        return 1.0
    cv = (row["form_sd"] / row["mu"]) if row["mu"] > 0 else 0.0
    if cv <= 0:
        return 1.0
    ratio = min(max(cv / typical, WIDTH_CLAMP[0]), WIDTH_CLAMP[1])
    return 1.0 + weight * (ratio - 1.0)


def save_fits(conn, models_dir=None) -> dict:
    """Fit every adopted market and write the store. Returns what it wrote."""
    import json
    out = {}
    for market in MIXTURE_MARKETS:
        got = fit_market(conn, market)
        if got:
            out[market] = got
    path = store_path(models_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    return out


def load_fits(models_dir=None) -> dict:
    import json
    path = store_path(models_dir)
    try:
        got = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def display_prob(market: str, projection, line, recent_values,
                 fits=None) -> float | None:
    """P(over) under the fitted mixture, for DISPLAY. None when it cannot.

    Returns None rather than a guess whenever anything is missing — the
    caller then keeps the number it already had, which is the honest
    fallback. A likelihood page that silently swapped in a worse number
    would be the opposite of the point.
    """
    fits = load_fits() if fits is None else fits
    got = fits.get(market)
    if not got or projection is None or line is None:
        return None
    try:
        mu = float(projection)
        ln = float(line)
    except (TypeError, ValueError):
        return None
    if mu <= MIN_PROJECTION or ln <= 0:
        return None
    vals = [v for v in (recent_values or []) if v is not None]
    if len(vals) < 3:
        return None
    row = {"mu": mu, "form_sd": 0.0,
           "zero_rate": sum(1 for v in vals if float(v) <= 0) / len(vals)}
    beta = got.get("zero") or [0.0, 0.0]
    sigma = float(got.get("sigma") or 0.6)
    # THE PLAYER'S OWN VOLATILITY, as much of it as this market earned.
    # See WIDTH_WEIGHT: measured per market, and only rushing takes it in
    # full. Needs the spread of his own recent games and the market's
    # typical, both of which the store carries.
    weight = float(got.get("width_weight", 0.0) or 0.0)
    typical = float(got.get("typical_cv", 0.0) or 0.0)
    if weight and typical > 0 and len(vals) > 1:
        mean = sum(float(v) for v in vals) / len(vals)
        var = sum((float(v) - mean) ** 2 for v in vals) / (len(vals) - 1)
        cv = (math.sqrt(var) / mu) if mu > 0 else 0.0
        if cv > 0:
            ratio = min(max(cv / typical, WIDTH_CLAMP[0]), WIDTH_CLAMP[1])
            sigma *= 1.0 + weight * (ratio - 1.0)
    return mixture_over(row, ln, beta, sigma)


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--fit" in args:
        import sqlite3 as _sq
        conn = _sq.connect(str(DEFAULT_DB))
        try:
            wrote = save_fits(conn)
        finally:
            conn.close()
        for market, got in sorted(wrote.items()):
            print(f"{market:<12} sigma {got['sigma']:.3f}  "
                  f"P(zero) = sigmoid({got['zero'][0]:+.2f} "
                  f"{got['zero'][1]:+.2f} x logit(prior blank rate))  "
                  f"({got['rows']:,} rows)")
        if not wrote:
            print("nothing fitted — needs player_game_logs")
        return 0
    real = "--real" in args
    args = [a for a in args if a not in ("--real", "--fit")]
    fn = report_real if real else report
    for i, market in enumerate(args or list(MARKETS)):
        if i:
            print()
        for line in fn(market):
            print(line)
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
