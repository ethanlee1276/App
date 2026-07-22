"""Data loading.

Reads a "slate" JSON file into the engine's dataclasses. This is the single
seam between the engine and the outside world: today it reads the bundled
sample slate, and in the live phase the same ``Slate`` object would be produced
by loaders that call nflverse for stats, an odds feed for lines, a weather API
and an injury feed. Nothing downstream needs to change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import (
    Team, DefenseProfile, Weather, Injury, Game, Prop, GameLog, SportsbookLine,
)


@dataclass
class Slate:
    date: str
    teams: dict[str, Team]
    games: list[Game]
    props: list[Prop]

    def team(self, abbr: str) -> Team:
        return self.teams[abbr]

    def game_for(self, prop: Prop) -> Game:
        for g in self.games:
            if prop.team in (g.home, g.away) and prop.opponent in (g.home, g.away):
                return g
        raise KeyError(f"No game found for {prop.player} ({prop.team} vs {prop.opponent})")


def _team(d: dict) -> Team:
    dd = d["defense"]
    return Team(
        abbr=d["abbr"],
        name=d["name"],
        proe=d.get("proe", 0.0),
        plays_per_game=d.get("plays_per_game", 63.0),
        defense=DefenseProfile(team=d["abbr"], **dd),
    )


def _weather(d: dict) -> Weather:
    return Weather(**d)


def _injury(d: dict) -> Injury:
    return Injury(**d)


def _prop(d: dict) -> Prop:
    logs = [GameLog(**g) for g in d["logs"]]
    lines = [SportsbookLine(**ln) for ln in d["lines"]]
    return Prop(
        player=d["player"],
        team=d["team"],
        opponent=d["opponent"],
        position=d["position"],
        market=d["market"],
        logs=logs,
        career_avg=d["career_avg"],
        vs_opponent_avg=d.get("vs_opponent_avg"),
        lines=lines,
        usage_role=d.get("usage_role", "starter"),
        headshot=d.get("headshot", ""),
    )


def load_slate(path: str | Path) -> Slate:
    data = json.loads(Path(path).read_text())
    teams = {t["abbr"]: _team(t) for t in data["teams"]}
    games = [
        Game(
            home=g["home"],
            away=g["away"],
            weather=_weather(g["weather"]),
            injuries=[_injury(i) for i in g.get("injuries", [])],
            spread=g.get("spread", 0.0),
            total=g.get("total", 44.0),
            roof=g.get("roof", ""),
            surface=g.get("surface", "grass"),
        )
        for g in data["games"]
    ]
    props = [_prop(p) for p in data["props"]]
    return Slate(date=data["date"], teams=teams, games=games, props=props)
