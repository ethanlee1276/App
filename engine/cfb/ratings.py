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


# Priors, used ONLY until a fit exists on THIS box's database.
#
# These were invented — plausible-looking numbers next to the NFL's fitted
# ones — until 2026-08-27, when `engine.sources.cfbfastr` made four real
# seasons reachable and 3,132 FBS-vs-FBS games could be measured. Three of
# the five guesses were good and two were not:
#
#     scoring baseline   28.5 guessed    26.70 measured   (totals 3.6 high)
#     home field          2.4 guessed     2.71 measured
#     margin SD          16.5 guessed    16.50 measured
#     total SD           15.5 guessed    15.73 measured
#     team total SD      11.0 guessed    11.55 measured
#
# So the numbers below are now the measured ones, and `fitted` is still
# False — deliberately. A constant measured on somebody else's seasons is
# a much better prior than a guess and it is still not a fit on the games
# this board is pricing, which is what the probation rule is about. Run
# `ingest_cfb_history` and the fit takes over, honestly.
PRIOR = CFBRatings(
    scoring_baseline=26.70, home_field=2.71, margin_sd=16.50, total_sd=15.73,
    team_total_sd=11.55, fitted=False, games=0,
    note=("Priced from four past seasons, not from a fit on this database — "
          "so this board is journaled and graded, not staked. The numbers "
          "are measured (3,132 FBS games, 2022–2025); what is missing is a "
          "measurement on the games being priced. Ingest a season of "
          "results and they become a fit."),
)


def _neutral(extra: str | None) -> bool:
    try:
        return bool(json.loads(extra or "{}").get("neutral"))
    except (ValueError, TypeError):
        return False


#: The alternating fit below stops when no team's strength moves more
#: than this, or after this many passes. It converged in 80 on four
#: seasons; the ceiling exists so a degenerate schedule cannot hang a
#: build, not because convergence is in doubt.
HFA_TOL = 1e-7
HFA_MAX_ITER = 300

#: Home-and-home pairs needed before the paired cross-check is quoted.
HFA_MIN_PAIRS = 50


def home_field(games: list[tuple]) -> float | None:
    """Home-field advantage, solved JOINTLY with team strength.

    THE BUG THIS REPLACES, measured 2026-08-27 on 3,132 real FBS games:
    this module estimated home field as the plain mean home margin over
    non-neutral games, and that number came out **+4.73 points**. It is
    not the home-field advantage. It is the home-field advantage plus
    the fact that in college football good teams host bad ones far more
    often than the reverse — the non-conference buy game is an entire
    industry. Two estimators that control for who was playing agree it
    is about +2.7:

        joint least squares, all 3,132 games      +2.71
        home-and-home pairs only, 739 pairs       +2.62 ± 0.38
        plain mean home margin (what shipped)     +4.73

    The direction matters. Installing 4.73 would have pushed every
    projected margin two points toward the home side on every college
    game on the board — most of a key number, applied universally, and
    wearing the word "fitted". The invented prior it would have replaced
    (2.4) was closer to the truth than the measurement.

    ``games`` is ``[(home, away, home_margin, counts_as_home)]``. Returns
    None when there is nothing to solve.

    The estimator alternates: given a home-field number, each team's
    strength is the average of what its games imply; given strengths,
    home field is the average of what the margins have left over. That
    is coordinate descent on the least-squares problem

        margin = strength(home) - strength(away) + H · at_home

    and it lands on the same answer as solving the normal equations
    directly, without a matrix library this project does not have.
    """
    sited = [g for g in games if g[3]]
    if not sited or not games:
        return None
    teams = {t for g in games for t in (g[0], g[1])}
    if len(teams) < 2:
        return None
    strength = {t: 0.0 for t in teams}
    hfa = 0.0
    for _ in range(HFA_MAX_ITER):
        hfa = sum(m - (strength[h] - strength[a])
                  for h, a, m, _s in sited) / len(sited)
        acc = {t: [0.0, 0] for t in teams}
        for h, a, m, at_home in games:
            edge = m - (hfa if at_home else 0.0)
            acc[h][0] += edge + strength[a]
            acc[h][1] += 1
            acc[a][0] += strength[h] - edge
            acc[a][1] += 1
        fresh = {t: (v[0] / v[1] if v[1] else 0.0) for t, v in acc.items()}
        # Strengths are only identified up to a constant — centre them,
        # or the whole scale drifts and the home-field term absorbs it.
        mean = sum(fresh.values()) / len(fresh)
        fresh = {t: v - mean for t, v in fresh.items()}
        moved = max(abs(fresh[t] - strength[t]) for t in teams)
        strength = fresh
        if moved < HFA_TOL:
            break
    return hfa


def paired_home_field(games: list[tuple]) -> tuple[float, int] | None:
    """The same number from home-and-home pairs alone — a cross-check.

    Where two teams played at both venues, strength cancels exactly:
    one margin is ``S_h - S_a + H`` and the other ``S_a - S_h + H``, so
    their mean IS the home-field advantage with no model in between. It
    uses a quarter of the games, which is why it checks the joint fit
    rather than replacing it.
    """
    pairs: dict = {}
    for home, away, margin, at_home in games:
        if not at_home:
            continue
        pairs.setdefault(tuple(sorted((home, away))), {}).setdefault(
            home, []).append(margin)
    both = []
    for (x, y), byhost in pairs.items():
        if x in byhost and y in byhost:
            mx = sum(byhost[x]) / len(byhost[x])
            my = sum(byhost[y]) / len(byhost[y])
            both.append((mx + my) / 2.0)
    if len(both) < HFA_MIN_PAIRS:
        return None
    return sum(both) / len(both), len(both)


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

    points, margins = [], []
    for r in rows:
        hs, as_ = float(r["home_score"]), float(r["away_score"])
        points += [hs, as_]
        margins.append(hs - as_)

    baseline = sum(points) / len(points)
    # NOT the mean home margin — see `home_field` for the two-point bias
    # that estimator carries in this sport, and the measurement that
    # caught it.
    shape = [(r["home"], r["away"],
              float(r["home_score"]) - float(r["away_score"]),
              not _neutral(r["extra"])) for r in rows]
    solved = home_field(shape)
    hfa = solved if solved is not None else PRIOR.home_field

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

    # HOW WIDE SHOULD THIS BE, AND HOW WE KNOW. Fitting these residuals
    # against ONE rating per team pooled over every ingested season gives
    # margins 16.5 points wide; fitting each season against its own
    # ratings gives 15.1, and the temptation is to take the tighter
    # number — a narrower spread is a more confident model and a bigger
    # stake.
    #
    # It is in-sample. A season's ratings are fitted on the same twelve
    # games the residuals are then measured from, so of course they hug.
    # The check that settles it arrived with `engine.sources.cfblines`:
    # over the same 3,126 graded games the CLOSING SPREAD's own residual
    # is 15.2 points, and the closing total's is 15.7. A model that
    # `engine.gamecal` measures at NO edge over the college spread
    # (slope -0.037, its side beating the close 48.4% of the time)
    # cannot also be sharper than the number it is losing to. So 16.5 is
    # the honest width and 15.1 was optimism — while the total's fitted
    # 15.7 landing on the market's 15.7 is what a matched estimate looks
    # like, and is exactly the market gamecal DOES find a sliver of edge
    # against.
    #
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
    check = paired_home_field(shape)
    if check:
        # The independent read, quoted alongside. Home-and-home pairs
        # need no model at all, so a joint fit that has drifted away from
        # them is visible on the board rather than only in a test.
        note += (f" Home field cross-checks at {check[0]:+.1f} on "
                 f"{check[1]} home-and-home pairs.")
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
