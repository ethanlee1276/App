"""Recent-form weighting.

Season averages hide streaks. This module blends several look-back windows
(last game, last 3, last 5, last 10, full season) plus career and
opponent-history baselines into a single form-adjusted mean, and reports a
trend so the explanation can say "heating up" or "cooling off".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import GameLog
from .statmath import weighted_mean, sample_std, clamp

# How much each look-back window contributes. Re-fit to the spec's recency
# rule (docs/NFL_MODEL.md §5: last 2 ≈ 45%, last 4 ≈ 35%, season ≈ 20%):
# season averages blend September's team with December's — recent games
# describe the team that will actually play Sunday. Mapped onto our window
# structure, the recent windows (1/3/5) now carry ~75% and the long anchors
# (10/season/career/opponent) ~25%.
WINDOW_WEIGHTS = {
    "last1": 0.22,
    "last3": 0.33,
    "last5": 0.20,
    "last10": 0.10,
    "season": 0.09,
    "career": 0.03,
    "vs_opp": 0.03,
}

# MLB runs a GENTLER recency curve (docs/MLB_MODEL.md §6: last 7 ≈ 40% ·
# last 15 ≈ 30% · season 20% · vs-pitcher 10%): baseball's nightly variance
# is so large that a hot week means far less than a hot fortnight in the
# NFL, and batter-vs-pitcher history stays a small input because most of
# it is noise. Mapped onto the same window structure.
MLB_WINDOW_WEIGHTS = {
    "last1": 0.08,
    "last3": 0.17,
    "last5": 0.15,
    "last10": 0.30,
    "season": 0.20,
    "career": 0.00,
    "vs_opp": 0.10,
}


#: Games at which a hitter's recent window and his season rate get equal
#: say — the k in ``w = n / (n + k)``.
#:
#: The textbook value is not this one, and the gap is deliberate. For a
#: mean estimated from n games the empirical-Bayes weight is exactly
#: n/(n+k) with k = (a player's game-to-game variance) / (the real variance
#: BETWEEN players). Per-game hits are roughly Binomial(3.8 at-bats, .250),
#: a within-player variance near 0.71; the spread of TRUE per-game rates
#: across everyone who bats has a standard deviation near 0.13, a between
#: variance near 0.017. That puts k around 40 — which is the well-known
#: fact that batting rates stabilise slowly, and it is probably right.
#:
#: It is also not what is being asked for here. The log window is capped at
#: fifteen games, so k=40 would leave every MLB hitter at roughly a quarter
#: his own recent form and three quarters his season line — replacing the
#: recency model docs/MLB_MODEL.md §6 specifies, on the strength of an
#: argument nobody has run against this book's own record. The defect
#: found on the live slate is narrower than that: projections with no floor
#: under them at all, hitters priced at batting averages of .014 and .030
#: because a short log went quiet.
#:
#: 8 is half a form window, and it is scoped to that defect. A three-game
#: log keeps about a quarter of its own number instead of all of it; a full
#: fifteen keeps two thirds. And for the hitter this is least likely to
#: harm — a regular whose recent games look like his season — it changes
#: nothing at all, because the two numbers agree.
#:
#: Not fitted against this book's data, which is why it is conservative:
#: the history DB in the build container carries NFL logs only. Recomputing
#: it from real MLB logs is a measurement worth taking before it moves.
CAREER_PRIOR_GAMES = 8.0


@dataclass
class FormResult:
    mean: float
    std: float
    trend: str            # "up", "down", or "flat"
    trend_delta: float    # last-3 avg minus prior-season avg, in stat units
    sample_games: int
    trend_mult: float = 1.0   # shade the projection toward recent form
    #: The longer-run rate the blend was pulled toward, or None when no
    #: usable one was supplied. Reported so the card can say so and the
    #: journal can band it — a shrunk projection is a different animal from
    #: one the player's own games earned.
    shrunk_to: float | None = None


def _avg(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def compute_form(
    logs: list[GameLog],
    career_avg: float,
    vs_opponent_avg: Optional[float],
    weights: dict | None = None,
    prior: float | None = None,
    prior_n: int = 0,
    prior_games: float = 0.0,
) -> FormResult:
    """Blend look-back windows into a form-adjusted mean and a variance
    estimate. ``logs`` are ordered most-recent first. ``weights`` selects the
    sport's recency curve (default: the NFL spec's; MLB passes its own).

    ``prior``/``prior_n``/``prior_games`` shrink the blend toward a
    longer-run rate when the log is thin, and are off unless a caller asks
    for them. ``prior`` is that rate, ``prior_n`` is how many games it was
    measured over, and ``prior_games`` is the k in ``w = n/(n+k)``.

    The blend alone has no floor under it. Every window above is an average
    of the SAME games, so weighting them differently cannot rescue a short
    log — a hitter with three quiet games comes out at three quiet games,
    and the live sim gate found several projected under a .100 batting
    average, one at .014. Those are the numbers the board prices from.
    """
    weights = weights or WINDOW_WEIGHTS
    vals = [g.value for g in logs]

    windows = {
        "last1": _avg(vals[:1]),
        "last3": _avg(vals[:3]),
        "last5": _avg(vals[:5]),
        "last10": _avg(vals[:10]),
        "season": _avg(vals),
        "career": career_avg,
        "vs_opp": vs_opponent_avg,
    }

    pairs = [
        (v, weights[k])
        for k, v in windows.items()
        if v is not None and weights.get(k, 0) > 0
    ]
    mean = weighted_mean(pairs)

    # Shrink toward the longer-run rate by how thin the window above is.
    #
    # n/(n+k), and n is the games the BLEND was computed from — not the
    # ones the prior spans. Getting that backwards weights a three-game
    # estimate as though it were sixty: measured, a hitless three-game log
    # against a 60-game season average of 0.95 came out at 0.38 instead of
    # 0.88, because the 0 was given the 60 games' worth of confidence that
    # belonged to the number it was being shrunk toward.
    #
    # A prior measured over almost nothing is not a prior. When prior_n is
    # missing or no larger than the log itself, the anchor carries nothing
    # the blend does not already have — which is exactly the state this
    # used to ship in, MLB's career_avg being the mean of the same fifteen
    # logs — so the shrink stands down rather than pretending.
    shrunk_to = None
    n = len(vals)
    if (prior_games > 0 and prior is not None and prior > 0
            and prior_n > max(n, 1)):
        w = n / (n + prior_games)
        mean = w * mean + (1.0 - w) * prior
        shrunk_to = prior

    # Variance from the observed game log; fall back to a position-agnostic
    # coefficient of variation if we have too few games.
    std = sample_std(vals[:10])
    if std <= 0 and mean > 0:
        std = 0.35 * mean

    # Trend: recent 3 games versus the rest of the season.
    recent = _avg(vals[:3])
    prior = _avg(vals[3:]) if len(vals) > 3 else career_avg
    trend_delta = 0.0
    trend = "flat"
    trend_mult = 1.0
    if recent is not None and prior:
        trend_delta = recent - prior
        rel = trend_delta / prior if prior else 0.0
        if rel > 0.10:
            trend = "up"
        elif rel < -0.10:
            trend = "down"
        # Downward-only recency shade: a sustained cool-off pulls the projection
        # toward recent form (to -10%), so the model stops leaning on stale
        # early-season numbers for a player who's stopped producing. We do NOT
        # inflate hot streaks — books price recent heat fast and chasing it is a
        # classic bettor trap — so a hot bat instead earns a small *confidence*
        # bonus (see betting._trend_alignment), not a bigger projected number.
        trend_mult = clamp(1.0 + 0.30 * clamp(rel, -0.5, 0.0), 0.90, 1.0)

    return FormResult(
        mean=mean,
        std=std,
        trend=trend,
        trend_delta=trend_delta,
        sample_games=len(vals),
        trend_mult=trend_mult,
        shrunk_to=shrunk_to,
    )
