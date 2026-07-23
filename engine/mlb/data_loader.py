"""MLB slate loading.

Reads a slate JSON into the MLB dataclasses — the single seam between this
engine and the outside world, exactly like the NFL loader. The live phase
plugs the free MLB Stats API (statsapi.mlb.com: schedule, probable pitchers,
lineups, game logs) and Open-Meteo (per-park weather) in behind the same
``MLBSlate`` object.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..models import SportsbookLine, LiveStatus
from .models import (
    MLBGame, MLBProp, MLBGameLog, MLBWeather, Pitcher, StatcastProfile,
)


@dataclass
class MLBSlate:
    date: str
    games: list[MLBGame]
    props: list[MLBProp]

    def game_for(self, prop: MLBProp) -> MLBGame:
        for g in self.games:
            if prop.team in (g.home, g.away) and prop.opponent in (g.home, g.away):
                return g
        raise KeyError(f"No game for {prop.player} ({prop.team} vs {prop.opponent})")


def _game(d: dict) -> MLBGame:
    return MLBGame(
        home=d["home"], away=d["away"], park=d["park"],
        date=d.get("date", ""), kickoff=d.get("kickoff", ""),
        total=d.get("total", 8.5),
        weather=MLBWeather(**d.get("weather", {})),
        lineups_confirmed=d.get("lineups_confirmed", True),
        pitchers={k: Pitcher(**v) for k, v in d.get("pitchers", {}).items()},
        bullpen_rank=d.get("bullpen_rank", {}),
        team_k_rate=d.get("team_k_rate", {}),
        live=LiveStatus(**d["live"]) if d.get("live") else None,
        home_ml=d.get("home_ml", 0),
        away_ml=d.get("away_ml", 0),
        home_rating=d.get("home_rating", 0.0),
        away_rating=d.get("away_rating", 0.0),
        home_off=d.get("home_off", 0.0),
        home_def=d.get("home_def", 0.0),
        away_off=d.get("away_off", 0.0),
        away_def=d.get("away_def", 0.0),
        total_over_odds=d.get("total_over_odds", -110),
        total_under_odds=d.get("total_under_odds", -110),
        spread=d.get("spread", 0.0),
        spread_home_odds=d.get("spread_home_odds", -110),
        spread_away_odds=d.get("spread_away_odds", -110),
    )


def _prop(d: dict) -> MLBProp:
    return MLBProp(
        player=d["player"], team=d["team"], opponent=d["opponent"],
        position=d["position"], market=d["market"],
        logs=[MLBGameLog(**g) for g in d["logs"]],
        career_avg=d["career_avg"],
        vs_pitcher_avg=d.get("vs_pitcher_avg"),
        lines=[SportsbookLine(**ln) for ln in d["lines"]],
        bats=d.get("bats", "R"), throws=d.get("throws", "R"),
        lineup_spot=d.get("lineup_spot", 0),
        headshot=d.get("headshot", ""),
        statcast=StatcastProfile(**d["statcast"]) if d.get("statcast") else None,
    )


def load_mlb_slate(path: str | Path) -> MLBSlate:
    data = json.loads(Path(path).read_text())
    return MLBSlate(
        date=data["date"],
        games=[_game(g) for g in data["games"]],
        props=[_prop(p) for p in data["props"]],
    )
