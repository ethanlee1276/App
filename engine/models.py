"""Core data structures shared across the engine.

These are intentionally plain dataclasses with no behaviour so that they can
be constructed just as easily from the bundled sample slate as from a live
nflverse / odds-feed loader later on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --- Positions we model props for -------------------------------------------
QB = "QB"
RB = "RB"
WR = "WR"
TE = "TE"

# --- Prop markets -----------------------------------------------------------
PASS_YDS = "pass_yds"
RUSH_YDS = "rush_yds"
REC_YDS = "rec_yds"
RECEPTIONS = "receptions"

# Human labels for the markets, used in the UI and explanations.
MARKET_LABELS = {
    PASS_YDS: "Passing Yards",
    RUSH_YDS: "Rushing Yards",
    REC_YDS: "Receiving Yards",
    RECEPTIONS: "Receptions",
}


@dataclass
class GameLog:
    """A single player's production in one past game (most recent first)."""

    week: int
    opponent: str
    value: float          # the stat value for the market in question
    home: bool = True


@dataclass
class DefenseProfile:
    """How a defense performs, used by the matchup analyzer.

    Numbers are expressed as multipliers relative to league average where a
    value > 1.0 means the defense gives up *more* than average (good for the
    offense) and < 1.0 means it is stingy.
    """

    team: str
    vs_qb: float = 1.0          # passing yards allowed vs league avg
    vs_wr1: float = 1.0
    vs_wr2: float = 1.0
    vs_slot: float = 1.0
    vs_te: float = 1.0
    vs_rb_rush: float = 1.0     # rush yards allowed vs league avg
    vs_rb_recv: float = 1.0
    pressure_rate: float = 0.22  # share of dropbacks pressured
    rush_rank: int = 16          # 1 = toughest vs run, 32 = weakest
    pass_rank: int = 16


@dataclass
class Weather:
    """Game-day weather. A dome sets ``dome=True`` and other fields are ignored."""

    dome: bool = False
    temp_f: float = 65.0
    wind_mph: float = 5.0
    wind_dir: str = ""           # compass, e.g. "NW" (not in the nflverse feed)
    precip_chance: float = 0.0   # 0..1
    rain: bool = False
    snow: bool = False


@dataclass
class Injury:
    """A single injury relevant to a game.

    ``status`` is one of: OUT, DOUBTFUL, QUESTIONABLE, IR, GTD (game-time).
    ``role`` describes what the player does so the engine can reason about
    knock-on effects (e.g. an OUT elite CB helps the opposing WR).
    """

    player: str
    team: str
    position: str
    role: str          # e.g. "elite_cb", "LT", "slot_cb", "dt", "wr1"
    status: str


@dataclass
class Team:
    abbr: str
    name: str
    defense: DefenseProfile
    proe: float = 0.0            # pass-rate over expected (game-script proxy)
    plays_per_game: float = 63.0


@dataclass
class SportsbookLine:
    """A prop line at one book. ``odds`` is American (e.g. -115, +100)."""

    book: str
    line: float
    over_odds: int = -110
    under_odds: int = -110


@dataclass
class Prop:
    """A single prop market for a player, with lines across books."""

    player: str
    team: str
    opponent: str
    position: str
    market: str
    logs: list[GameLog]
    career_avg: float
    vs_opponent_avg: Optional[float]     # historical avg vs this opponent
    lines: list[SportsbookLine]
    # role used for injury matchup reasoning (e.g. "wr1", "slot", "rb1")
    usage_role: str = "starter"
    # official headshot URL when a data source provides one (nflverse
    # weekly stats carry headshot_url); the UI falls back to an SVG avatar
    headshot: str = ""


@dataclass
class LiveStatus:
    """Live game state, shared by both sports. ``state`` is scheduled | live |
    final. Populated by a live-scores adapter (ESPN for NFL, MLB Stats API for
    MLB) or provided in a slate for illustration."""

    state: str = "scheduled"
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    period: str = ""             # "Q3", "Top 5th", "HALFTIME", "F/10"
    clock: str = ""              # "10:32" (NFL) or "" (MLB)
    detail: str = ""             # freeform, e.g. "2nd & 7 at DEN 45"
    start_time: str = ""         # ISO or human, for scheduled games
    outs: Optional[int] = None            # MLB: 0-2
    bases: Optional[list] = None          # MLB: occupied bases, e.g. [2] or [1, 3]


def live_to_dict(live) -> Optional[dict]:
    """Serialize a LiveStatus for the pipeline JSON (None stays None)."""
    if live is None:
        return None
    return {
        "state": live.state,
        "home_score": live.home_score,
        "away_score": live.away_score,
        "period": live.period,
        "clock": live.clock,
        "detail": live.detail,
        "start_time": live.start_time,
        "outs": live.outs,
        "bases": live.bases,
    }


@dataclass
class Game:
    home: str
    away: str
    weather: Weather
    injuries: list[Injury] = field(default_factory=list)
    date: str = ""               # game date, YYYY-MM-DD
    kickoff: str = ""            # kickoff time (nflverse "HH:MM" ET, or ISO)
    spread: float = 0.0          # home spread; negative = home favored
    total: float = 44.0
    roof: str = ""               # dome | closed | outdoors | open (raw nflverse)
    surface: str = "grass"       # grass | fieldturf | ... (drives stadium color)
    live: Optional[LiveStatus] = None
    # Moneyline: American odds per side (0 = not offered) and a team strength
    # rating in net points/game vs league average (0 = average). Drives the
    # game-level moneyline model in engine/gamebets.py.
    home_ml: int = 0
    away_ml: int = 0
    home_rating: float = 0.0
    away_rating: float = 0.0
    # Offense/defense split (points scored / allowed vs league baseline) for the
    # totals model, and the book prices for the total (O/U) and the spread.
    home_off: float = 0.0
    home_def: float = 0.0
    away_off: float = 0.0
    away_def: float = 0.0
    total_over_odds: int = -110
    total_under_odds: int = -110
    spread_home_odds: int = -110
    spread_away_odds: int = -110
