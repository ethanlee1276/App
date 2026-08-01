"""How wide is a college football game? Measure it, don't assert it.

Every number the pricing layer needs — scoring baseline, home field, the
spread of margins and totals around the projection — is a *fit* here, taken
from the games already ingested. Only when there isn't enough history does
the module fall back to a prior, and then it says so in a way that reaches
the board.

That distinction is the whole point. The NFL and MLB constants in
``engine.gamebets`` were fitted against results; inventing plausible-looking
college numbers next to them would make an uncalibrated model
indistinguishable from a calibrated one at a glance. So:

* with a real sample, ``fit_from_history`` returns measured values and
  ``fitted=True``;
* without one, the prior stands and ``fitted=False`` — which puts the whole
  CFB board on probation: journaled and graded, never staked.

The residual standard deviations are measured against the *ratings' own*
projection, so they answer the question the pricing actually asks ("how far
from our number do games land?") rather than the easier one ("how spread out
are scores?"). They are mildly optimistic because the ratings were fitted on
the same games; that is why ``MIN_GAMES`` is not small.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace

from .. import gamebets

# A fit needs a season's worth of games behind it. FBS plays ~800 a year, so
# this is a few weeks in — early enough to be useful, late enough that the
# residual spread isn't just noise.
MIN_GAMES = 400


@dataclass(frozen=True)
class CFBRatings:
    scoring_baseline: float   # points per team per game
    home_field: float         # points
    margin_sd: float          # SD of actual margin around the projection
    total_sd: float           # SD of actual total around the projection
    team_total_sd: float
    fitted: bool
    games: int
    note: str

    @property
    def probation(self) -> bool:
        """Un-fitted variance means the stake is a guess. Don't take it."""
        return not self.fitted


# Priors, used ONLY until a fit exists. Deliberately wide: college football's
# margin distribution is fatter than the NFL's, and a too-narrow SD turns
# every mispriced number into a confident bet.
PRIOR = CFBRatings(
    scoring_baseline=28.5, home_field=2.4, margin_sd=16.5, total_sd=15.5,
    team_total_sd=11.0, fitted=False, games=0,
    note=("Priced from a prior, not a fit — no measured CFB variance in the "
          "database yet, so this board is journaled and graded, not staked. "
          "Ingest a season of results and the numbers become measurements."),
)


def _neutral(extra: str | None) -> bool:
    try:
        return bool(json.loads(extra or "{}").get("neutral"))
    except (ValueError, TypeError):
        return False


def _sd(values: list[float]) -> float | None:
    """Sample standard deviation, or None when there is no sample.

    None rather than 0.0, and that distinction is load-bearing. The
    callers wrote ``_sd(res) or PRIOR.margin_sd``, which silently swapped
    in the prior whenever the computed value came out ZERO — and then
    reported ``fitted=True`` with a note claiming the number had been
    measured. "No sample" and "the residuals were tiny" are opposite
    findings and must not share a return value.
    """
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def fit_from_history(conn, ratings: dict, seasons: list[int] | None = None,
                     min_games: int = MIN_GAMES) -> CFBRatings:
    """Measure the CFB constants from finished games in the database.

    ``ratings`` is the ``{team: TeamRating}`` map from
    :func:`engine.teamrates.compute_team_ratings`, needed because the
    standard deviations are residuals around ITS projection.
    """
    q = ("SELECT home, away, home_score, away_score, extra FROM games "
         "WHERE sport='cfb' AND home_score IS NOT NULL AND away_score IS NOT NULL")
    args: list = []
    if seasons:
        q += " AND season IN (%s)" % ",".join("?" * len(seasons))
        args = list(seasons)
    rows = conn.execute(q, args).fetchall()
    if len(rows) < min_games:
        return replace(PRIOR, games=len(rows), note=(
            f"{len(rows)} CFB games in the database, {min_games} needed to fit "
            f"the variance. {PRIOR.note}"))

    points, margins, home_edge = [], [], []
    for r in rows:
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        points += [hs, as_]
        margins.append(hs - as_)
        if not _neutral(r["extra"]):
            home_edge.append(hs - as_)

    baseline = sum(points) / len(points)
    hfa = (sum(home_edge) / len(home_edge)) if home_edge else PRIOR.home_field

    # Residuals around what the ratings would have projected.
    margin_res, total_res, team_res = [], [], []
    for r in rows:
        hr, ar = ratings.get(r["home"]), ratings.get(r["away"])
        if not hr or not ar:
            continue
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        proj_margin = (hr.net - ar.net) + (0.0 if _neutral(r["extra"]) else hfa)
        proj_home = baseline + hr.off + ar.def_
        proj_away = baseline + ar.off + hr.def_
        margin_res.append((hs - as_) - proj_margin)
        total_res.append((hs + as_) - (proj_home + proj_away))
        team_res += [hs - proj_home, as_ - proj_away]

    # A None here means the residual list was too short to measure, which
    # is the ONLY case that should fall back to the prior. A measured
    # value is used as measured, however small — see `_sd`.
    m, t, tt = _sd(margin_res), _sd(total_res), _sd(team_res)
    borrowed = [name for name, v in (("margin", m), ("total", t),
                                     ("team total", tt)) if v is None]
    margin_sd = m if m is not None else PRIOR.margin_sd
    total_sd = t if t is not None else PRIOR.total_sd
    team_sd = tt if tt is not None else PRIOR.team_total_sd
    note = (f"Fitted on {len(rows)} CFB games: margins land {margin_sd:.1f} "
            f"points from the projection, totals {total_sd:.1f}, and home "
            f"field is worth {hfa:+.1f}.")
    if borrowed:
        # Say so. A prior wearing a fitted label is the one number on the
        # board nobody would think to check.
        note += (" NOT fitted: " + ", ".join(borrowed) + " had too few "
                 "residuals to measure and kept the prior value.")
    return CFBRatings(
        scoring_baseline=round(baseline, 2), home_field=round(hfa, 2),
        margin_sd=round(margin_sd, 2), total_sd=round(total_sd, 2),
        team_total_sd=round(team_sd, 2), fitted=not borrowed,
        games=len(rows), note=note,
    )


def install(r: CFBRatings) -> None:
    """Register these numbers as the 'cfb' sport in :mod:`engine.gamebets`.

    gamebets looks its constants up per sport, and CFB's are the only ones
    that change from build to build — so they live here, with the code that
    measures them, and are pushed in rather than hard-coded there.
    """
    gamebets.SCORING_BASELINE["cfb"] = r.scoring_baseline
    gamebets.HOME_FIELD["cfb"] = r.home_field
    gamebets.MARGIN_SD["cfb"] = r.margin_sd
    gamebets.TOTAL_SD["cfb"] = r.total_sd
    gamebets.TEAM_TOTAL_SD["cfb"] = r.team_total_sd


def win_prob(margin: float, r: CFBRatings) -> float:
    """Home win probability from a projected margin.

    A normal CDF over the fitted margin spread — the same shape the NFL
    moneyline uses, with college football's own width.
    """
    from ..statmath import normal_cdf, clamp
    return clamp(normal_cdf(margin / max(r.margin_sd, 1e-6)), 0.02, 0.98)


# The prior is in force until a build measures something better.
install(PRIOR)
