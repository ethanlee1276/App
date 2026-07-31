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

WNBA = replace(
    NBA,
    key="wnba", name="WNBA",
    game_minutes=40,
    roster_size=12,
    season_games=44,
    personal_fouls=5,
    vacancy_cap_over_high=round(NBA.vacancy_cap_over_high * _MIN_SCALE, 2),
    calibrated=False,
    inherited_from="nba",
    note=("Tuning inherited from the NBA model and NOT yet fitted to WNBA "
          "results. Minutes-denominated values are scaled to the 40-minute "
          "game; the fitted ones (margin SD, blowout curves, stat spreads, "
          "gate thresholds) are the NBA's. Picks are journaled and graded "
          "on probation — they do not count as bets until the bucket "
          "clears the promotion bar."),
)

LEAGUES = {"nba": NBA, "wnba": WNBA}


def for_league(key: str) -> LeagueTuning:
    return LEAGUES.get((key or "nba").lower(), NBA)
