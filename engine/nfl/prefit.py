"""Does preseason starter usage move a preseason result? Measure, then decide.

Ethan, 2026-08-14, on the preseason board: "i wanna show props for the pre
season … i dont care" which market — and then, to the offer to fit it
first rather than price it on a hunch, "yes do this now too".

THE CLAIM BEING TESTED, WRITTEN DOWN BEFORE IT IS TESTED.

`prestarters` measures one thing: how long a team's first string was on
the field, read off the starting quarterback's attempts. The claim that
would justify pricing August is that this moves the scoreboard — that two
teams playing their starters produce a different game from two teams
playing fourth-string quarterbacks, in a direction and by an amount you
could bet.

It is a plausible claim and it is not obviously true. Starters are better,
so they score more; starters also play clean, conservative football with a
vanilla playbook, and backups throw interceptions that become short fields.
Those push opposite ways. Nobody here knows the sign, which is the whole
reason to measure instead of asserting.

TWO QUESTIONS, IN ORDER, AND THE FIRST ONE CAN KILL THE SECOND.

  A. MECHANISM. Does OBSERVED usage — what actually happened, known only
     after the game — track the final? If knowing the answer in advance
     does not help, nothing built on a forecast of it can.

  B. FORECAST. At bet time nobody knows the attempts. What exists is the
     team's HABIT in previous Augusts, which is what `prestarters.tendency`
     reports. So B fits prior-seasons-only tendency against the result and
     scores it OUT OF SAMPLE, season by season forward. This is the only
     version that was ever bettable, and it is strictly weaker than A.

THE BAR IS SET IN THIS FILE, ABOVE THE ANSWER, ON PURPOSE. `MIN_ROWS`,
`MAX_P` and `MIN_SIGNAL_POINTS` are declared as constants before any
result exists, so the verdict cannot be talked into place afterwards. Two
predictors are tested against two outcomes — attempts SUM against the
TOTAL, attempts GAP against the MARGIN — and that pairing is fixed here
rather than chosen from whatever came back best. p is required at 0.01
rather than 0.05 for exactly that reason: with a handful of tests, one
result at 0.05 is what luck looks like.

AND CONVICTION HERE IS STILL NOT PERMISSION TO PRICE.

Even a clean fit only proves the effect exists — not that the market has
missed it. Which teams are resting starters is the single most-reported
fact about a preseason game; it is in every beat writer's Thursday column
and the number moves on it. A signal we can measure from five-year-old
habits is a stale copy of what the book already has.

So `prices_allowed()` is a separate gate and it is CLOSED, and stays shut
until the residual has been measured against posted lines we are only now
starting to record. `verdict()` answering "measured" moves the question
from "is there anything here" to "is there anything here the book missed",
which is progress and is not a price.

Read-only. Ordinary SQL and arithmetic; no third-party stats package.
"""

from __future__ import annotations

import math
import random

from . import prestarters as ps

#: Games needed before any of this means anything. A preseason is ~49
#: fixtures, and a walk-forward needs at least one season to fit on and one
#: to be scored against, so this is deliberately more than one August.
MIN_ROWS = 60
#: Two-sided permutation p a correlation must clear. 0.01, not 0.05,
#: because four (predictor, outcome) pairs are examined across the two
#: questions and one of them landing under 0.05 is the null hypothesis
#: behaving normally.
MAX_P = 0.01
#: How many POINTS of real adjustment the model has to be making, out of
#: sample, off the league mean.
#:
#: Where 1.0 comes from: a total bet at -110 needs 52.4%, and against a
#: preseason spread of finals (SD in the region of ten points) that is a
#: shift of 0.06 SD, about 0.6 points. Requiring 1.0 leaves room for the
#: fact that some of any real effect is already inside the posted number —
#: a model whose entire edge is 0.6 points has none left after the book
#: has had the same thought.
MIN_SIGNAL_POINTS = 1.0
#: Permutation resamples. Enough to resolve a p of 0.01 without the run
#: taking longer than the ingest that feeds it.
RESAMPLES = 4000
#: Fixed so two runs on the same data give the same verdict. A p-value
#: that wobbles between launches is one somebody re-rolls until it passes.
SEED = 20260814

#: The pairs that get tested, fixed here rather than chosen from results.
#: Sum of both starting quarterbacks' attempts against the game's total;
#: the gap between them against the margin.
PAIRS = (("att_sum", "total"), ("att_gap", "margin"))


# --- the joined sample ------------------------------------------------------
def finals(conn, seasons=None) -> list[dict]:
    """Played preseason games, earliest first. ``[]`` if none are stored."""
    q = ("SELECT season, week, game_id, date, home, away, home_score, "
         "away_score FROM preseason_games WHERE sport='nfl' "
         "AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = []
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = [int(s) for s in seasons]
    try:
        rows = conn.execute(q + " ORDER BY date, game_id", args).fetchall()
    except Exception:                                         # noqa: BLE001
        return []                        # table absent = nothing ingested yet
    return [dict(r) for r in rows]


def sample(conn, seasons=None) -> list[dict]:
    """One row per played game with both sides' usage attached.

    A game is DROPPED when either side's usage is missing rather than
    filled with a zero — zero attempts is a coach resting his starter, an
    absent box score is a game we did not ingest, and averaging the second
    into the first would manufacture rests that never happened.

    ``exp_*`` are the forecast-time versions: each side's tendency computed
    from seasons STRICTLY BEFORE this one, which is all a bettor could have
    had. They are None for the earliest season in the sample, and rows
    carrying None are excluded from question B rather than imputed.
    """
    games = finals(conn, seasons)
    if not games:
        return []
    years = sorted({int(g["season"]) for g in games})
    out: list[dict] = []
    for g in games:
        season, week = int(g["season"]), int(g["week"] or 0)
        h = ps.usage(conn, g["home"], season, week)
        a = ps.usage(conn, g["away"], season, week)
        if not h or not a or not h.get("qb") or not a.get("qb"):
            continue
        prior = [y for y in years if y < season]
        eh = _expected(conn, g["home"], prior, week)
        ea = _expected(conn, g["away"], prior, week)
        hs, as_ = float(g["home_score"]), float(g["away_score"])
        out.append({
            "season": season, "week": week, "game_id": g["game_id"],
            "date": g["date"], "home": g["home"], "away": g["away"],
            "total": hs + as_, "margin": hs - as_,
            "home_att": h["qb_att"], "away_att": a["qb_att"],
            "att_sum": h["qb_att"] + a["qb_att"],
            "att_gap": h["qb_att"] - a["qb_att"],
            "exp_home": eh, "exp_away": ea,
            "exp_sum": None if eh is None or ea is None else eh + ea,
            "exp_gap": None if eh is None or ea is None else eh - ea,
        })
    return out


def _expected(conn, team: str, prior_seasons: list[int], week: int):
    """A team's attempt habit from earlier Augusts only, or None."""
    if not prior_seasons:
        return None
    t = ps.tendency(conn, team, prior_seasons, week=week)
    if t.get("n"):
        return t["mean_att"]
    t = ps.tendency(conn, team, prior_seasons)      # any week, if not this one
    return t["mean_att"] if t.get("n") else None


# --- arithmetic -------------------------------------------------------------
def pearson(xs, ys) -> float | None:
    """Correlation, or None when either side has no spread to correlate."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def ols(xs, ys):
    """``(slope, intercept)`` or None. Least squares, by hand."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def permutation_p(xs, ys, resamples: int = RESAMPLES,
                  seed: int = SEED) -> float | None:
    """Two-sided p for the correlation, by shuffling one column.

    A permutation rather than a t-test because it assumes nothing about
    the shape of either variable, and attempt counts are visibly not
    normal — they pile up at zero and again around a first-half workload.
    """
    r = pearson(xs, ys)
    if r is None:
        return None
    rng = random.Random(seed)
    shuffled = list(ys)
    hits = 0
    for _ in range(resamples):
        rng.shuffle(shuffled)
        rr = pearson(xs, shuffled)
        if rr is not None and abs(rr) >= abs(r):
            hits += 1
    # +1 on both sides: a p of exactly zero claims more resolution than
    # `resamples` draws can supply.
    return (hits + 1) / (resamples + 1)


def rmse(errors) -> float | None:
    e = [float(x) for x in errors]
    return math.sqrt(sum(x * x for x in e) / len(e)) if e else None


def signal_points(base_rmse: float | None, model_rmse: float | None):
    """POINTS of adjustment the model actually made pay, off the mean.

    With ``y = mean + correction + noise`` and the correction uncorrelated
    with the noise, ``base_mse - model_mse`` is the variance of the
    correction, so its root is the typical size of the adjustment in the
    units of the outcome. That is directly comparable to the ~0.6 points a
    -110 total needs, which is why the bar is stated in points rather than
    in a correlation nobody can price.

    Negative when the model is worse than the mean, and returned negative
    rather than clamped — a model that hurts should read as one.
    """
    if base_rmse is None or model_rmse is None:
        return None
    d = base_rmse ** 2 - model_rmse ** 2
    return math.copysign(math.sqrt(abs(d)), d)


# --- question A: is the mechanism there at all ------------------------------
def mechanism(rows: list[dict]) -> dict:
    """In-sample fit of what ACTUALLY happened against the final.

    Deliberately generous — it uses information no bettor has — because
    its job is to FALSIFY. If knowing the attempts in advance does not
    move the scoreboard, nothing built on guessing them can.
    """
    out: dict = {"n": len(rows), "pairs": {}}
    for x, y in PAIRS:
        pair = [(r[x], r[y]) for r in rows
                if r.get(x) is not None and r.get(y) is not None]
        xs = [p[0] for p in pair]
        ys = [p[1] for p in pair]
        r = pearson(xs, ys)
        fit = ols(xs, ys) if len(xs) >= 2 else None
        out["pairs"][f"{x}~{y}"] = {
            "n": len(xs), "r": None if r is None else round(r, 4),
            "slope": None if not fit else round(fit[0], 4),
            "p": permutation_p(xs, ys) if len(xs) >= MIN_ROWS else None,
        }
    return out


# --- question B: could it have been forecast --------------------------------
def walk_forward(rows: list[dict], x: str, y: str) -> dict:
    """Fit on earlier seasons, predict the next one, never the reverse.

    Scored against the only baseline that costs nothing to run: the mean
    outcome of the seasons already seen. A model that cannot beat "assume
    this August looks like the last ones" has found nothing.
    """
    usable = [r for r in rows if r.get(x) is not None and r.get(y) is not None]
    seasons = sorted({r["season"] for r in usable})
    model_err: list[float] = []
    base_err: list[float] = []
    scored: list[int] = []
    tested = 0
    for season in seasons:
        past = [r for r in usable if r["season"] < season]
        now = [r for r in usable if r["season"] == season]
        if len(past) < MIN_ROWS // 2 or not now:
            continue
        fit = ols([r[x] for r in past], [r[y] for r in past])
        if not fit:
            continue
        b, a = fit
        mean = sum(r[y] for r in past) / len(past)
        for r in now:
            model_err.append(r[y] - (a + b * r[x]))
            base_err.append(r[y] - mean)
        tested += len(now)
        scored.append(season)
    m, base = rmse(model_err), rmse(base_err)
    return {
        "x": x, "y": y, "n": tested,
        "seasons_scored": scored,
        "model_rmse": None if m is None else round(m, 3),
        "base_rmse": None if base is None else round(base, 3),
        "signal_points": None if m is None else round(signal_points(base, m), 3),
    }


def forecast(rows: list[dict]) -> dict:
    """Question B across both declared pairs, using the forecast-time inputs."""
    out: dict = {"pairs": {}}
    for x, y in PAIRS:
        fx = {"att_sum": "exp_sum", "att_gap": "exp_gap"}[x]
        wf = walk_forward(rows, fx, y)
        usable = [r for r in rows if r.get(fx) is not None]
        wf["p"] = (permutation_p([r[fx] for r in usable], [r[y] for r in usable])
                   if len(usable) >= MIN_ROWS else None)
        out["pairs"][f"{fx}~{y}"] = wf
    return out


# --- the verdict ------------------------------------------------------------
def verdict(report: dict) -> str:
    """"insufficient" / "no" / "measured", against the bar set above.

    "measured" is the strongest thing this file can say and it is not
    "tradeable" — see `prices_allowed`.
    """
    if int(report.get("n", 0)) < MIN_ROWS:
        return "insufficient"
    mech = report.get("mechanism", {}).get("pairs", {})
    if not any(v.get("p") is not None and v["p"] <= MAX_P for v in mech.values()):
        return "no"
    for v in report.get("forecast", {}).get("pairs", {}).values():
        sp = v.get("signal_points")
        p = v.get("p")
        if (sp is not None and sp >= MIN_SIGNAL_POINTS
                and p is not None and p <= MAX_P):
            return "measured"
    return "no"


def prices_allowed(report: dict | None = None) -> bool:
    """Whether the board may put a NUMBER on a preseason game. It may not.

    Hard False, and the constant is the point rather than an oversight.
    Conviction in `verdict` establishes that the effect exists; pricing
    needs the further fact that the POSTED LINE has missed it, and that
    comparison needs preseason closing lines we only began recording on
    2026-08-14. One August of them is not a measurement.

    When that sample exists this becomes a real function with a real bar,
    and the change will show up in a diff as its own decision — which is
    exactly what a switch from "showing the schedule" to "taking a
    position" should have to do.
    """
    return False


def fit(conn, seasons=None) -> dict:
    """The whole measurement, as one dict. Safe to call with an empty DB."""
    rows = sample(conn, seasons)
    report: dict = {
        "n": len(rows),
        "seasons": sorted({r["season"] for r in rows}),
        "bar": {"min_rows": MIN_ROWS, "max_p": MAX_P,
                "min_signal_points": MIN_SIGNAL_POINTS},
        "mechanism": mechanism(rows) if rows else {"n": 0, "pairs": {}},
        "forecast": forecast(rows) if rows else {"pairs": {}},
    }
    report["verdict"] = verdict(report)
    report["prices_allowed"] = prices_allowed(report)
    return report


def explain(report: dict) -> str:
    """One paragraph a human can read, matched to the verdict."""
    v = report.get("verdict")
    n = report.get("n", 0)
    if v == "insufficient":
        return (f"{n} joined game(s); the bar is {MIN_ROWS}. Run "
                f"`python3 ingest.py nflpre --seasons 2021-2026` and ask "
                f"again — nothing can be concluded from this yet.")
    if v == "no":
        return (f"{n} game(s) across {len(report.get('seasons', []))} "
                f"season(s): starter usage does not predict the preseason "
                f"result by enough to bet. The board keeps showing the scan "
                f"and the market's number as information, and prices "
                f"nothing.")
    return (f"{n} game(s): the effect is real and large enough to be worth "
            f"pricing against a line. It is NOT priced yet — that needs the "
            f"posted preseason numbers, which we started recording "
            f"2026-08-14.")
