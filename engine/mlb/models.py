"""Core MLB data structures.

Plain dataclasses, mirroring the NFL engine's models so the downstream stages
(and eventually the live loaders for the MLB Stats API / Statcast) stay
interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- Prop markets -----------------------------------------------------------
TOTAL_BASES = "total_bases"
HITS = "hits"
HOME_RUNS = "home_runs"
STRIKEOUTS = "strikeouts"        # pitcher Ks

MARKET_LABELS = {
    TOTAL_BASES: "Total Bases",
    HITS: "Hits",
    HOME_RUNS: "Home Runs",
    STRIKEOUTS: "Strikeouts",
}

HITTER_MARKETS = {TOTAL_BASES, HITS, HOME_RUNS}
PITCHER_MARKETS = {STRIKEOUTS}


@dataclass
class MLBGameLog:
    """One past game for a player (most recent first). ``game`` is a simple
    recency index; ``opponent`` a team abbreviation."""

    game: int
    opponent: str
    value: float
    home: bool = True


@dataclass
class ParkProfile:
    """A ballpark's scoring personality, expressed as multipliers relative to
    a league-average park (1.0). ``altitude_ft`` drives the thin-air bonus."""

    key: str
    name: str
    team: str                    # home team abbreviation
    hr_factor: float = 1.0
    run_factor: float = 1.0
    k_factor: float = 1.0
    altitude_ft: int = 0
    roof: str = "open"           # open | retractable | dome
    surface: str = "grass"


@dataclass
class MLBWeather:
    """Game-time conditions. ``wind_dir_rel`` is relative to the park:
    "out" (toward the outfield), "in", or "cross". Roof-closed games are
    weather-neutral."""

    roof_closed: bool = False
    temp_f: float = 72.0
    wind_mph: float = 6.0
    wind_dir_rel: str = "cross"
    humidity: float = 0.50
    precip_chance: float = 0.0


@dataclass
class Pitcher:
    """The opposing starter, as the matchup analyzer sees him."""

    name: str
    throws: str                  # "L" | "R"
    slg_allowed_vs_l: float = 0.400   # SLG allowed to left-handed batters
    slg_allowed_vs_r: float = 0.400
    k_rate: float = 0.22              # strikeouts per batter faced
    xera: float = 4.00


@dataclass
class MLBGame:
    home: str
    away: str
    park: str                                  # ParkProfile.key
    total: float = 8.5                         # game run total (O/U)
    weather: MLBWeather = field(default_factory=MLBWeather)
    lineups_confirmed: bool = True
    live: Optional["object"] = None            # engine.models.LiveStatus
    # starting pitcher and bullpen rank (1 best .. 30 worst) per team
    pitchers: dict[str, Pitcher] = field(default_factory=dict)
    bullpen_rank: dict[str, int] = field(default_factory=dict)
    # opposing-team strikeout rate lookup for pitcher props
    team_k_rate: dict[str, float] = field(default_factory=dict)
    # Moneyline: American odds per side (0 = not offered) and a team strength
    # rating in expected run differential/game vs average. Drives the
    # game-level moneyline model in engine/gamebets.py.
    home_ml: int = 0
    away_ml: int = 0
    home_rating: float = 0.0
    away_rating: float = 0.0
    # Offense/defense split (runs scored / allowed vs league baseline) for the
    # totals model; run-line spread + prices; and total (O/U) prices.
    home_off: float = 0.0
    home_def: float = 0.0
    away_off: float = 0.0
    away_def: float = 0.0
    total_over_odds: int = -110
    total_under_odds: int = -110
    spread: float = 0.0          # home run line (e.g. -1.5); 0 = not offered
    spread_home_odds: int = -110
    spread_away_odds: int = -110


@dataclass
class StatcastProfile:
    """Batted-ball quality + expected stats for a player (Baseball Savant).

    Hitter fields drive expected-stats regression (xSLG vs SLG = luck signal)
    and quality-of-contact (barrel / hard-hit). Pitcher fields drive strikeout
    props (CSW% / whiff%) and contact suppression (barrel allowed). All optional
    — the engine uses whatever is present.
    """

    # hitter
    xslg: Optional[float] = None
    slg: Optional[float] = None
    xwoba: Optional[float] = None
    woba: Optional[float] = None
    barrel_pct: Optional[float] = None       # 0..1
    hard_hit_pct: Optional[float] = None
    # pitcher
    csw_pct: Optional[float] = None          # called strikes + whiffs
    whiff_pct: Optional[float] = None
    barrel_allowed_pct: Optional[float] = None


@dataclass
class MLBProp:
    player: str
    team: str
    opponent: str
    position: str                # "1B", "RF", "SP", ...
    market: str
    logs: list[MLBGameLog]
    career_avg: float
    vs_pitcher_avg: Optional[float]      # career average vs today's starter
    lines: list                          # engine.models.SportsbookLine
    bats: str = "R"                      # hitter handedness ("L"/"R"/"S")
    throws: str = "R"                    # pitcher handedness (SP props)
    lineup_spot: int = 0                 # 1-9 confirmed; 0 = not in lineup yet
    headshot: str = ""
    statcast: Optional["StatcastProfile"] = None
