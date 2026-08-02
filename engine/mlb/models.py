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
    recency index; ``opponent`` a team abbreviation.

    ``date`` (YYYY-MM-DD) is the game's real calendar date when the source
    provides it. The recency index shifts every time a newer game arrives, so
    persisting history keys on the date instead — otherwise the same real game
    lands under a different key on each ingest and the record duplicates."""

    game: int
    opponent: str
    value: float
    home: bool = True
    date: str = ""


@dataclass
class ParkProfile:
    """A ballpark's scoring personality, expressed as multipliers relative to
    a league-average park (1.0). ``altitude_ft`` drives the thin-air bonus.

    Everything from ``lf_ft`` down is reference detail for the site, not
    model input: the factors above already encode how the park plays, and
    feeding the dimensions in as well would double-count them. They exist
    so a game page can show *why* a park carries the factor it does —
    Fenway's below-average home-run factor makes sense the moment you see
    a 310-foot line in front of a 37-foot wall.

    Distances are the published foul-line and center-field measurements;
    a handful of parks move fences between seasons, and where the current
    number is contested ``plays`` says so rather than the field asserting
    false precision.
    """

    key: str
    name: str
    team: str                    # home team abbreviation
    hr_factor: float = 1.0
    run_factor: float = 1.0
    k_factor: float = 1.0
    altitude_ft: int = 0
    roof: str = "open"           # open | retractable | dome
    surface: str = "grass"
    # --- reference only, never fed to the model ---
    lf_ft: int = 0               # left-field line
    cf_ft: int = 0               # straightaway center
    rf_ft: int = 0               # right-field line
    lf_wall_ft: float = 8.0      # wall height down the left-field line
    rf_wall_ft: float = 8.0      # wall height down the right-field line
    capacity: int = 0
    opened: int = 0
    plays: str = ""              # one line on the park's character


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
    date: str = ""                             # game date, YYYY-MM-DD
    kickoff: str = ""                          # first pitch (ISO datetime)
    # Doubleheaders: the same two teams twice on one date. game_number (1/2)
    # plus the flag disambiguate everything downstream — game ids, which
    # game a prop is for, and the labels the site shows.
    game_number: int = 1
    doubleheader: bool = False
    # MLB Stats API gamePk — lets the build re-fetch this game's boxscore
    # (live per-player stats for the live-pick tracker).
    game_pk: int = 0
    total: float = 8.5                         # game run total (O/U)
    weather: MLBWeather = field(default_factory=MLBWeather)
    lineups_confirmed: bool = True
    live: Optional["object"] = None            # engine.models.LiveStatus
    # The schedule's own abstractGameState, lowercased ("final", "live",
    # "preview"), stamped by build_live_slate. ``live`` above is richer but
    # is only filled by attach_live, which the site build calls and the
    # ingest does not — so anything that must know whether a game is over
    # WITHOUT the live overlay reads this instead. Empty = genuinely
    # unknown, which is not the same as "over".
    sched_state: str = ""
    # starting pitcher and bullpen rank (1 best .. 30 worst) per team
    pitchers: dict[str, Pitcher] = field(default_factory=dict)
    bullpen_rank: dict[str, int] = field(default_factory=dict)
    # Measured relief workload per team (engine.mlb.bullpen): weighted relief
    # innings over the last two days. High = tired arms tonight.
    bullpen_fatigue: dict[str, float] = field(default_factory=dict)
    # opposing-team strikeout rate lookup for pitcher props
    team_k_rate: dict[str, float] = field(default_factory=dict)
    # Moneyline: American odds per side (0 = not offered) and a team strength
    # rating in expected run differential/game vs average. Drives the
    # game-level moneyline model in engine/gamebets.py.
    # Home-plate umpire (announced a few hours before first pitch) and his
    # measured effect profile: >1.0 k_factor = calls a big zone, more
    # strikeouts; run_factor scales the scoring environment. 1.0 = league
    # average / unknown ump.
    plate_umpire: str = ""
    ump_k_factor: float = 1.0
    ump_run_factor: float = 1.0
    home_ml: int = 0
    away_ml: int = 0
    # The sharp reference book's own two-sided prices (0 = not quoted).
    # De-vigged they are the fair-value anchor the soft prices are judged
    # against; never themselves a price to take.
    sharp_home_ml: int = 0
    sharp_away_ml: int = 0
    sharp_total: float = 0.0
    sharp_total_over_odds: int = 0
    sharp_total_under_odds: int = 0
    sharp_spread: float = 0.0
    sharp_spread_home_odds: int = 0
    sharp_spread_away_odds: int = 0
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
    person_id: int = 0                   # MLB Stats API id (splits lookups)
    bats: str = "R"                      # hitter handedness ("L"/"R"/"S")
    throws: str = "R"                    # pitcher handedness (SP props)
    lineup_spot: int = 0                 # 1-9 confirmed; 0 = not in lineup yet
    headshot: str = ""
    statcast: Optional["StatcastProfile"] = None
    # Measured platoon split vs tonight's starter hand (engine.mlb.platoon):
    # 1.0 = unmeasured/neutral, in which case the matchup layer's generic
    # handedness bump applies instead.
    platoon_factor: float = 1.0
    platoon_note: str = ""
    # Official season splits vs LHP/RHP from the MLB Stats API
    # ({"vl": {"pa", "slg", "hr"}, "vr": {...}}); None = not fetched. The
    # HR model reads the power split; the matchup layer uses the SLG split
    # as a fallback when our own logs can't measure the player.
    platoon_official: Optional[dict] = None
    # Measured opportunity (engine.mlb.opportunity): tonight's expected PA
    # from slot + run environment vs the player's OWN average. 1.0 =
    # unmeasured, in which case the static lineup-spot bump applies instead.
    pa_factor: float = 1.0
    pa_note: str = ""
    # Measured streak reversion (engine.mlb.streaks): league-wide next-game
    # factor when the player's current 5-game stretch is hot or cold.
    streak_factor: float = 1.0
    streak_note: str = ""
    # Which game of a doubleheader this prop belongs to (0 = not a DH day /
    # unspecified). Set by the slate builder; game_for() matches on it.
    game_number: int = 0
