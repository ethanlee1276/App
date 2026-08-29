"""A fitted projection, measured against the blend we ship.

WHY THIS EXISTS. `engine.formcheck` established that the recency curve is
close to the ceiling of what reweighting a player's own past yards can
do: on the rows every candidate could price, the best curve orders
rush_yds at +0.658 and rec_yds at +0.550, and `engine.formbook` then
showed that none of that survives contact with a real closing line
(AUC 0.468 and 0.477). The dial is not the problem and the dial is not
the fix.

What the blend never gets to use is everything BESIDE the outcome's own
history — carries, targets, snap share, red-zone looks, air yards, xFP —
which the database has held all along for five seasons. The projection
consumes them only through `nflusage`'s volume bridge, as a single
hand-weighted product of "recent opportunities times season efficiency",
and measured in formcheck that decomposition lands mid-pack.

So this fits the weights instead of choosing them: ordinary least
squares over the standardised features, trained on earlier seasons and
scored on later ones. Not because linear regression is clever, but
because it is the honest floor — if a fitted linear combination of
everything we record cannot beat a hand-tuned average of one column,
then the information is not in these columns and no amount of
architecture rescues it. That is worth knowing before anything larger is
built.

NO ODDS ARE READ. This asks whether the projection is any good at
predicting the stat, which is prior to whether it can beat a price.

Standard library only.
"""

from __future__ import annotations

import math

#: Seasons that fit the weights, and seasons that judge them. Never
#: random, never overlapping — a model scored on a season it was fitted
#: on is scored on its own memory.
TRAIN_SEASONS = (2021, 2022, 2023)
TEST_SEASONS = (2024, 2025)

MARKETS = ("rush_yds", "rec_yds", "receptions", "pass_yds")

#: Per market: the opportunity column, then everything else worth a
#: coefficient. Named per market because air yards mean nothing to a
#: runner and carries nothing to a receiver.
COLUMNS = {
    "rush_yds": ("carries", "snap_pct", "rz_car", "i5_car", "xfp"),
    "rec_yds": ("targets", "air_yards", "snap_pct", "rz_tgt", "xfp"),
    "receptions": ("targets", "air_yards", "snap_pct", "rz_tgt", "xfp"),
    "pass_yds": ("pass_att",),
}

#: Prior games in the season before a row can be built.
MIN_HISTORY = 3

#: Recent opportunities per game a player needs before his row counts.
#:
#: THE POPULATION A PROP IS ACTUALLY OFFERED ON. Two thirds of the
#: rush_yds rows belong to receivers with no carries and no rushing
#: yards, where "his season average" predicts zero perfectly and any
#: extra column can only add noise. Measured across all rows the fitted
#: model therefore LOST to one column averaged (rank +0.727 against
#: +0.756) — a result about how many free zeros were in the sample, not
#: about the model. Books do not hang a rushing line on a slot receiver,
#: so neither does this.
MIN_OPPORTUNITY = {"rush_yds": 4.0, "rec_yds": 2.0,
                   "receptions": 2.0, "pass_yds": 10.0}


def _solve(a: list, b: list) -> list | None:
    """Gaussian elimination with partial pivoting. ``None`` if singular."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / m[col][col]
            for k in range(col, n + 1):
                m[r][k] -= f * m[col][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_least_squares(rows: list, ridge: float = 1e-6) -> list | None:
    """Coefficients for ``[1, x1..xk] -> y`` over ``[(xs, y)]``.

    A whisper of ridge on the diagonal, because two of these columns are
    nearly the same measurement — red-zone carries and inside-5 carries
    especially — and a singular normal matrix should degrade into a
    slightly biased answer rather than into None.
    """
    if not rows:
        return None
    k = len(rows[0][0]) + 1
    ata = [[0.0] * k for _ in range(k)]
    aty = [0.0] * k
    for xs, y in rows:
        v = [1.0] + list(xs)
        for i in range(k):
            aty[i] += v[i] * y
            for j in range(k):
                ata[i][j] += v[i] * v[j]
    for i in range(k):
        ata[i][i] += ridge * len(rows)
    return _solve(ata, aty)


def _mean(vals):
    got = [v for v in vals if v is not None]
    return sum(got) / len(got) if got else None


def _recent(vals, n):
    got = [v for v in vals[:n] if v is not None]
    return sum(got) / len(got) if got else None


def build_rows(conn, market: str, seasons) -> list:
    """``[(features, actual, season, week, player)]``, walk-forward.

    Every feature is computed from games BEFORE the one being predicted,
    which is what makes the fit honest and what a plain SQL join would
    quietly get wrong.
    """
    from .fantasy import _short_key
    from .formbook import _feature_logs

    cols = COLUMNS.get(market, ())
    fl = _feature_logs(conn, cols, seasons)
    sql = ("SELECT season, period, player, team, value "
           "FROM player_game_logs WHERE sport='nfl' AND market=? "
           "AND season IN (%s) ORDER BY season, period, player"
           % ",".join("?" * len(seasons)))
    seen: dict = {}
    career: dict = {}
    season_now = None
    out: list = []
    for r in conn.execute(sql, (market, *seasons)):
        try:
            week = int(r["period"])
        except (TypeError, ValueError):
            continue
        if r["value"] is None:
            continue
        season, player = int(r["season"]), r["player"]
        actual = float(r["value"])
        if season != season_now:
            for (p, _s), vals in seen.items():
                career.setdefault(p, []).extend(vals)
            seen, season_now = {}, season
        hist = seen.get((player, season)) or []
        if len(hist) >= MIN_HISTORY:
            skey = _short_key(player, r["team"] or "")
            feats = [
                _recent(hist, 3) or 0.0,
                _mean(hist) or 0.0,
                _mean(career.get(player, [])) or (_mean(hist) or 0.0),
                float(len(hist)),
            ]
            ok = True
            opp_now = None
            for c in cols:
                series = [fl.get((season, w, skey), {}).get(c)
                          for w in range(week - 1, 0, -1)]
                near, far = _recent(series, 4), _recent(series[4:], 12)
                if near is None:
                    ok = False
                    break
                feats.append(near)
                feats.append(near - far if far is not None else 0.0)
                if opp_now is None:
                    opp_now = near          # the first column is volume
            floor = MIN_OPPORTUNITY.get(market, 0.0)
            if ok and (opp_now is None or opp_now < floor):
                ok = False
            if ok:
                # The history rides along so `evaluate` can price the
                # SHIPPED blend on exactly these rows. Comparing a fitted
                # model to a season average answers the wrong question —
                # the board does not run a season average.
                out.append((feats, actual, season, week, player,
                            list(hist), list(career.get(player, []))))
        seen.setdefault((player, season), []).insert(0, actual)
    return out


def _standardise(rows: list):
    """Centre and scale, so a coefficient means the same thing on carries
    as on snap share and the normal matrix stays conditioned."""
    k = len(rows[0][0])
    mu = [sum(r[0][i] for r in rows) / len(rows) for i in range(k)]
    sd = []
    for i in range(k):
        var = sum((r[0][i] - mu[i]) ** 2 for r in rows) / max(1, len(rows) - 1)
        sd.append(math.sqrt(var) or 1.0)
    return mu, sd


def _apply(coef, xs, mu, sd) -> float:
    z = [(x - m) / s for x, m, s in zip(xs, mu, sd)]
    return coef[0] + sum(c * v for c, v in zip(coef[1:], z))


def evaluate(conn, market: str, train=TRAIN_SEASONS, test=TEST_SEASONS) -> dict:
    """Fit on ``train``, score on ``test``, beside the shipped blend."""
    from .form import compute_form, WINDOW_WEIGHTS
    from .models import GameLog

    tr = build_rows(conn, market, list(train))
    te = build_rows(conn, market, list(test))
    if len(tr) < 500 or len(te) < 200:
        return {"market": market, "skipped":
                f"{len(tr)} training and {len(te)} test rows"}
    mu, sd = _standardise(tr)
    coef = fit_least_squares([([(x - m) / s for x, m, s in zip(xs, mu, sd)], y)
                              for xs, y, *_k in tr])
    if coef is None:
        return {"market": market, "skipped": "normal matrix was singular"}

    from .formfit import weights_for
    weights = weights_for("nfl", market) or WINDOW_WEIGHTS
    err = {"fitted": [], "baseline": [], "shipped": []}
    rank = {"fitted": {}, "baseline": {}, "shipped": {}}
    for xs, y, season, week, _p, hist, career_vals in te:
        logs = [GameLog(week=0, opponent="", value=v) for v in hist]
        car = (sum(career_vals) / len(career_vals)) if career_vals else None
        shipped = compute_form(logs, car if car is not None else xs[1],
                               None, weights=weights).mean
        preds = {"fitted": _apply(coef, xs, mu, sd),
                 "baseline": xs[1],
                 "shipped": shipped}
        for k, v in preds.items():
            err[k].append(abs(v - y))
            rank[k].setdefault((season, week), []).append((v, y))
    out = {"market": market, "train_n": len(tr), "test_n": len(te),
           "coef": coef}
    for k in err:
        out[k] = {"mae": sum(err[k]) / len(err[k]), "rank": _mean_rank(rank[k])}
    return out


def _ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
    return out


def _spearman(xs, ys):
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else None


def _mean_rank(by_week: dict):
    got = []
    for rows in by_week.values():
        if len(rows) < 8:
            continue
        r = _spearman([a for a, _b in rows], [b for _a, b in rows])
        if r is not None:
            got.append(r)
    return sum(got) / len(got) if got else None


def report_lines(out: dict) -> list:
    if out.get("skipped"):
        return [f"  {out['market']}: skipped — {out['skipped']}"]
    lines = [f"  {out['market']}: fit on {out['train_n']:,}, "
             f"scored on {out['test_n']:,} held-out rows"]
    for k, label in (("fitted", "fitted (every column)"),
                     ("shipped", "shipped (the form blend)"),
                     ("baseline", "baseline (season mean)")):
        d = out[k]
        lines.append(f"      {label:<26} MAE {d['mae']:7.2f}   "
                     f"rank {d['rank']:+.3f}")
    # THE COMPARISON THAT DECIDES ANYTHING is against what the board
    # runs today, not against a season average the board never uses.
    gain = (out["fitted"]["rank"] or 0) - (out["shipped"]["rank"] or 0)
    if gain <= 0:
        lines.append(f"      ⚠️  fitting every column we record does not "
                     f"beat the blend already shipped ({gain:+.3f}) — the "
                     f"information is not in these columns")
    else:
        lines.append(f"      the fit orders {gain:+.3f} better than what the "
                     f"board ships, on seasons it never saw")
    return lines


__all__ = ["MARKETS", "COLUMNS", "TRAIN_SEASONS", "TEST_SEASONS",
           "build_rows", "fit_least_squares", "evaluate", "report_lines"]
