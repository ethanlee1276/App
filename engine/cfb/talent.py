"""The preseason prior — what high-school recruiting is actually worth.

§5 of the college spec says the preseason prior carries ~25% of an
early-season projection and decays toward ~5% by November, and §6 says the
prior IS returning production × talent composite × coaching change. This
module is that sentence, made arithmetic.

**Why it matters more here than in any other sport in this repo.** A
12-game season with 25% annual roster turnover means a team's Week-3 net
rating is built on two games against opponents nobody has measured either.
Shrinking that toward the league average — which is what every
results-only rating does — quietly asserts that an unproven Alabama and an
unproven Kent State are both average. They are not, and the market knows
it, so a model without a prior is not neutral in September: it is wrong in
a direction the market will take money for.

**Where the number comes from, and what happens when it can't be fitted.**
The map from a talent composite to expected net points is FITTED against
completed seasons in our own database — regress each team's realised net
margin on its talent z-score, get points per standard deviation. Until
there are enough completed team-seasons to fit, a documented prior slope
stands in and ``fitted`` is False, which keeps the college board on
probation exactly as an unfitted variance does.

**Two guards against double counting.** The blue-chip ratio is not a
second additive term — it is the same high-school ratings the composite
already contains, so it only adjusts confidence in the composite. And
returning production scales how fast the prior gives way to results, not
the prior's size: a talented team returning nobody should be trusted less
early, not rated lower forever.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# §5 — the prior's share of the projection: ~25% early, ~5% by November.
# November is roughly game 10 in a 12-game season, and the decay is linear
# in games played because that is how the evidence actually accumulates.
PRIOR_START = 0.25
PRIOR_FLOOR = 0.05
PRIOR_DECAY_PER_GAME = 0.02

# Points of net margin per standard deviation of talent composite, used
# only until a fit exists. Deliberately conservative: understating the
# prior costs a little accuracy, overstating it manufactures edges against
# a market that prices recruiting well.
PRIOR_POINTS_PER_SD = 6.0
MIN_TEAM_SEASONS = 60          # before the slope is a measurement


@dataclass(frozen=True)
class TalentFit:
    points_per_sd: float
    fitted: bool
    samples: int
    r: float
    note: str


PRIOR_FIT = TalentFit(
    points_per_sd=PRIOR_POINTS_PER_SD, fitted=False, samples=0, r=0.0,
    note=("Talent-to-points slope is a documented prior, not a fit — not "
          "enough completed team-seasons in the database yet. Backfill more "
          "seasons and it becomes a measurement."))


def prior_weight(games_played: int, returning: float | None = None) -> float:
    """How much of the rating should still be the preseason prior.

    ``returning`` is the share of last year's production back. A team that
    returns almost nothing has a *less* informative prior about this year's
    version of itself, so its prior decays faster; a team with everyone
    back keeps its prior longer. Both directions are small — this adjusts
    the schedule, it does not replace it.
    """
    n = max(0, int(games_played or 0))
    if n == 0:
        return 1.0                      # nothing has happened yet
    w = max(PRIOR_FLOOR, PRIOR_START - PRIOR_DECAY_PER_GAME * n)
    if returning is not None:
        # 0.5 returning production is the league-typical figure; ±0.3
        # around it moves the prior's staying power by ±20% relative.
        w *= max(0.7, min(1.3, 1.0 + (float(returning) - 0.5) * 0.7))
    return round(min(1.0, w), 4)


def _z_scores(values: dict[str, float]) -> dict[str, float]:
    vals = [v for v in values.values() if v is not None]
    if len(vals) < 3:
        return {k: 0.0 for k in values}
    mean = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) or 1.0
    return {k: round((v - mean) / sd, 4) for k, v in values.items()
            if v is not None}


def talent_prior(talent: dict[str, float], fit: TalentFit = PRIOR_FIT,
                 blue_chip: dict | None = None) -> dict[str, float]:
    """``{team: prior net points/game}`` from the talent composite.

    The blue-chip ratio does NOT add points — it is the same high-school
    star ratings the composite is built from, and adding it again would
    count one fact twice. It shades the prior toward zero when the two
    disagree, which is the honest use of a second view on the same
    evidence.
    """
    z = _z_scores(talent)
    bc_z = _z_scores({k: v.get("ratio", 0.0)
                      for k, v in (blue_chip or {}).items()}) if blue_chip else {}
    out: dict[str, float] = {}
    for team, zt in z.items():
        points = zt * fit.points_per_sd
        zb = bc_z.get(team)
        if zb is not None and zt * zb < 0:
            # The composite and the blue-chip ratio disagree about whether
            # this roster is above or below average. Halve the claim.
            points *= 0.5
        out[team] = round(points, 3)
    return out


def blend_rating(results_net: float, prior_net: float, games_played: int,
                 returning: float | None = None) -> float:
    """The rating actually used to price a game."""
    w = prior_weight(games_played, returning)
    return round(w * prior_net + (1.0 - w) * results_net, 3)


def fit_points_per_sd(team_seasons: list[tuple[float, float]],
                      min_samples: int = MIN_TEAM_SEASONS) -> TalentFit:
    """Measure the talent→points slope from completed team-seasons.

    ``team_seasons`` is [(talent_z, realised net points/game), …]. Ordinary
    least squares through the origin: a zero talent z-score is a
    league-average roster, which should predict a zero net margin, and
    fitting an intercept would let the model claim the average team is
    above average.
    """
    pairs = [(float(z), float(net)) for z, net in team_seasons
             if z is not None and net is not None]
    if len(pairs) < min_samples:
        return TalentFit(PRIOR_POINTS_PER_SD, False, len(pairs), 0.0,
                         f"{len(pairs)} team-seasons, {min_samples} needed to "
                         f"fit the talent slope. {PRIOR_FIT.note}")
    sxy = sum(z * net for z, net in pairs)
    sxx = sum(z * z for z, net in pairs)
    if sxx <= 0:
        return PRIOR_FIT
    slope = sxy / sxx
    # Correlation, so the note can say how much this actually explains.
    mz = sum(z for z, _ in pairs) / len(pairs)
    mn = sum(n for _, n in pairs) / len(pairs)
    cov = sum((z - mz) * (n - mn) for z, n in pairs)
    vz = sum((z - mz) ** 2 for z, _ in pairs)
    vn = sum((n - mn) ** 2 for _, n in pairs)
    r = cov / math.sqrt(vz * vn) if vz > 0 and vn > 0 else 0.0
    return TalentFit(
        points_per_sd=round(slope, 3), fitted=True, samples=len(pairs),
        r=round(r, 3),
        note=(f"Fitted on {len(pairs)} team-seasons: one standard deviation "
              f"of recruiting talent is worth {slope:+.1f} net points a game "
              f"(r={r:.2f})."))


# The transfer portal, in star-equivalents. A roster is not the roster its
# recruiting class describes once a dozen starters have walked out of it,
# and the portal is the only place that shows up before a snap is played.
# The scale is deliberately small: net portal stars is a noisy, incomplete
# count (not every move is graded, and a player's stars say little about
# what he became in three years of college), so it NUDGES the prior rather
# than steering it. Clamped so no team's prior can be halved or doubled by
# a transfer list.
PORTAL_POINTS_PER_STAR = 0.12
PORTAL_CLAMP = 2.5                  # points of net rating, either way


def portal_shift(entry: dict | None) -> float:
    """Points of net rating this team's portal traffic is worth."""
    if not entry:
        return 0.0
    try:
        net = float(entry.get("net_stars") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return round(max(-PORTAL_CLAMP,
                     min(PORTAL_CLAMP, net * PORTAL_POINTS_PER_STAR)), 3)


def apply_prior(ratings: dict, prior: dict[str, float],
                returning: dict[str, dict] | None = None,
                portal: dict[str, dict] | None = None) -> tuple[dict, dict]:
    """Blend the talent prior into results-based ratings.

    Only the NET rating is blended. Offense/defense — which is what the
    totals model reads — has no talent analogue here: a recruiting
    composite says a roster is good, not that it scores 34 a game, and
    inventing a split would put a fabricated number straight into every
    total on the board. Totals stay results-only, and the report says so.

    ``portal`` adjusts the PRIOR, not the rating. A team that gutted its
    roster in the portal has a recruiting composite describing players who
    left; a team that raided it has one describing players it does not yet
    include. Both corrections belong to the preseason number and decay
    with it, which is why they are applied here rather than to the blend.
    """
    from dataclasses import replace as _replace

    blended, report = {}, {"teams": 0, "prior_only": 0, "results_only": 0,
                           "portal_teams": 0}
    for team, r in ratings.items():
        p = prior.get(team)
        if p is None:
            report["results_only"] += 1
            blended[team] = r
            continue
        shift = portal_shift((portal or {}).get(team))
        if shift:
            p += shift
            report["portal_teams"] += 1
        ret = (returning or {}).get(team, {}).get("overall")
        net = blend_rating(r.net, p, r.games, ret)
        blended[team] = _replace(r, net=net)
        report["teams"] += 1
    # TEAMS WITH A PRIOR BUT NO GAMES YET ARE THE WHOLE REASON THE PRIOR
    # IS HERE — and until 2026-08-19 this loop counted them and threw them
    # away. `blended` is keyed off the RESULTS ratings, so on the opening
    # Saturday, when no team has played and `ratings` is empty, every
    # team's prior was computed, reported, and dropped: zero ratings
    # attached, and a board that priced nothing on the one weekend the
    # prior exists to cover.
    #
    # Found by dress-rehearsing the opener ten days out, the same way the
    # NFL Week-1 gap was found. The bug is invisible in November because
    # by then every team has results and this loop matches nothing.
    #
    # ONLY THE NET RATING COMES FROM THE PRIOR. Offense and defense stay
    # at league average, for the reason the docstring above gives: a
    # recruiting composite says a roster is good, not that it scores 34 a
    # game. `games=0` is the honest count and is what every downstream
    # weight reads to know how little is behind this number.
    from ..teamrates import TeamRating

    for team, p in prior.items():
        if team in blended:
            continue
        report["prior_only"] += 1
        shift = portal_shift((portal or {}).get(team))
        if shift:
            report["portal_teams"] += 1
        blended[team] = TeamRating(net=round(p + shift, 3), off=0.0,
                                   def_=0.0, games=0)
    return blended, report


def team_seasons_from_db(conn, talent_by_year: dict[int, dict[str, float]],
                         min_games: int = 8) -> list[tuple[float, float]]:
    """Build the fit's input from ingested results + talent by season."""
    rows = conn.execute(
        "SELECT season, home, away, home_score, away_score FROM games "
        "WHERE sport='cfb' AND home_score IS NOT NULL").fetchall()
    agg: dict = {}
    for r in rows:
        season = int(r["season"] or 0)
        margin = float(r["home_score"]) - float(r["away_score"])
        for team, m in ((r["home"], margin), (r["away"], -margin)):
            slot = agg.setdefault((season, team), [0.0, 0])
            slot[0] += m
            slot[1] += 1
    out: list[tuple[float, float]] = []
    for season, table in talent_by_year.items():
        z = _z_scores(table)
        for (s, team), (total, n) in agg.items():
            if s != season or n < min_games:
                continue
            zt = z.get(team)
            if zt is not None:
                out.append((zt, total / n))
    return out
