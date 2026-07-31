"""League tuning for the basketball engine — one model, two leagues.

The Scalpy pipeline (minutes → distribution → clamp → gate) is not
NBA-specific. What is NBA-specific is a handful of numbers baked into it,
and shipping a WNBA page meant separating the two.

Two kinds of constant live here, and the difference matters more than any
individual value:

**Structural facts.** A WNBA game is 40 minutes, not 48; rosters are 12,
not 15; the season is 44 games, not 82. These are not opinions, and
anything denominated in minutes has to be scaled or it is simply wrong —
a vacancy cap of "8 minutes over his recent high" means something
different in a game that is a sixth shorter.

**Tuning.** MARGIN_SD, the blowout curves, the shot-distribution CVs, the
gate thresholds. Every one of these was fitted against NBA results. I have
no WNBA sample to fit them against, so WNBA inherits them — and says so.
``calibrated=False`` is not decoration: the pipeline routes an uncalibrated
league's picks into a probation bucket that grades but does not bet, on
the same promotion bar the long-shot watchlist and the Polymarket flow
model already use. A model that has never been graded against a league
does not get to bet that league on the strength of borrowed numbers.

Guessing at "WNBA-ish" values would have been worse than inheriting: it
would look tailored while being invented, and nothing downstream could
tell the difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class LeagueTuning:
    key: str
    name: str
    # --- structural: facts about the sport ---------------------------------
    game_minutes: int = 48
    roster_size: int = 15
    season_games: int = 82
    personal_fouls: int = 6
    # --- tuning: fitted numbers ---------------------------------------------
    margin_sd: float = 11.5
    blowout_margin: float = 18.0
    blowout_grade_drop: float = 0.25
    vacancy_cap_over_high: float = 8.0
    dog_haircut_share: float = 0.6
    blowout_starter: tuple = ((4.5, 1.00), (7.5, 0.98), (10.5, 0.95),
                              (13.5, 0.91), (float("inf"), 0.86))
    blowout_bench: tuple = ((4.5, 1.00), (7.5, 1.02), (10.5, 1.06),
                            (13.5, 1.12), (float("inf"), 1.20))
    rest_mult: dict = field(default_factory=lambda: {
        "2plus": 1.01, "1day": 1.00, "b2b_home": 0.96, "b2b_road": 0.93,
        "b2b_road_30plus": 0.88, "3in4": 0.94, "4in6_road": 0.92})
    sd_cv: dict = field(default_factory=lambda: {
        "pts": 0.30, "reb": 0.40, "ast": 0.43, "pra": 0.24,
        "fg3m": 0.55, "stl": 0.70, "blk": 0.80})
    max_picks_per_slate: int = 4
    max_picks_per_game: int = 2
    thin_sample: int = 10
    # Nested minutes windows, most recent first: last 5 · games 6-10 · the
    # rest of the season. Nested, NOT overlapping — "last 5 at 40% and last
    # 10 at 30%" reads as overlapping windows, and implementing it that way
    # would count the last five games twice at 70%.
    recency_weights: tuple = (0.50, 0.30, 0.20)
    # --- market structure ----------------------------------------------------
    # Which markets are worth betting, and how hard each has to clear.
    # Empty tier map = this league gates on points-edge alone (the NBA's
    # original behaviour), so adding tiers to one league can't silently
    # re-tune the other.
    market_tier: dict = field(default_factory=dict)
    tier_min_edge: dict = field(default_factory=dict)
    # --- §8 the unified grade ------------------------------------------------
    grade_weights: dict = field(default_factory=dict)
    min_grade: int | None = None       # None = the grade is reported, not gating
    # Week-to-week coefficient of variation in minutes above which a role is
    # a coin flip and the projection is fiction. None = filter off.
    stability_max_cv: float | None = None
    # --- §8 bankroll caps, as fractions of bankroll --------------------------
    cap_per_play: float = 0.03
    cap_per_game: float = 0.06
    cap_per_slate: float = 0.15
    # --- provenance ---------------------------------------------------------
    calibrated: bool = True
    inherited_from: str = ""
    note: str = ""

    @property
    def probation(self) -> bool:
        """True when picks must be journaled and graded but NOT bet."""
        return not self.calibrated


NBA = LeagueTuning(
    key="nba", name="NBA",
    game_minutes=48, roster_size=15, season_games=82, personal_fouls=6,
    calibrated=True,
)

# 40 minutes, not 48 — so every minutes-denominated number is scaled by
# 40/48. That is arithmetic, not a guess: a cap of "8 minutes above his
# recent high" is a sixth of an NBA game and must stay a sixth of a WNBA
# one. The blowout MARGIN is left alone deliberately: it is a points
# threshold, and while WNBA teams score ~72% of an NBA team's total, I have
# no WNBA blowout sample to say whether the rotation response starts at the
# same margin. Inheriting a number and admitting it beats inventing one.
_MIN_SCALE = 40 / 48

# §7 — the WNBA's own beatability order, which is NOT the NBA's. Count
# stats tied tightly to minutes and role are tier 1 and PRA aggregates away
# single-category noise; points are efficiency-contaminated; made threes
# are low-frequency events where one hot night distorts every average.
WNBA_TIERS = {"reb": 1, "ast": 1, "pra": 1, "pts": 2, "fg3m": 3,
              "stl": 3, "blk": 3}
# §3.6 — minimum edge AFTER the haircut. Deliberately above the NFL/MLB
# thresholds: when a soft-market model disagrees with a soft market, the
# extra cushion is the protection against being confidently wrong together.
WNBA_TIER_MIN_EDGE = {1: 0.030, 2: 0.045, 3: 0.065}
# §8 — the unified 0-100 grade. Minutes/role certainty is 20% because
# minutes are the king input, and freshness is 15% because a stale injury
# report is how this league beats you.
WNBA_GRADE_WEIGHTS = {"edge": 40, "minutes_certainty": 20, "freshness": 15,
                      "movement": 10, "matchup": 10, "schedule": 5}

WNBA = replace(
    NBA,
    key="wnba", name="WNBA",
    game_minutes=40,
    roster_size=12,
    season_games=44,
    personal_fouls=5,
    vacancy_cap_over_high=round(NBA.vacancy_cap_over_high * _MIN_SCALE, 2),
    # §5 — last 5 · games 6-10 · rest of season, nested.
    recency_weights=(0.40, 0.30, 0.20),
    market_tier=WNBA_TIERS,
    tier_min_edge=WNBA_TIER_MIN_EDGE,
    grade_weights=WNBA_GRADE_WEIGHTS,
    min_grade=70,                      # "Below 70: no bet, no leans."
    stability_max_cv=0.35,
    # §8 — tighter than the NFL/MLB slate cap, because WNBA limits are lower
    # and re-betting a moved line is harder: a soft market punishes
    # over-concentration with worse fills, not just variance.
    cap_per_play=0.02, cap_per_game=0.05, cap_per_slate=0.12,
    calibrated=False,
    inherited_from="nba",
    note=("Market tiers, tier minimums, the 0-100 grade, the role-stability "
          "filter and the bankroll caps are the WNBA spec's own. What is "
          "still inherited from the NBA are the fitted numbers — margin SD, "
          "blowout curves, stat spreads — which are not yet fitted to WNBA "
          "results. Picks are journaled and graded on probation; they do "
          "not count as bets until the bucket clears the promotion bar."),
)

LEAGUES = {"nba": NBA, "wnba": WNBA}


def for_league(key: str) -> LeagueTuning:
    return LEAGUES.get((key or "nba").lower(), NBA)
