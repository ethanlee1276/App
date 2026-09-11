"""Tests for the nflverse injuries adapter (offline, fixture-driven)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import injuries as inj
from engine.injuries import evaluate_injuries
from engine.models import (
    Team, DefenseProfile, Weather, Game, Prop, GameLog, SportsbookLine, RUSH_YDS, PASS_YDS,
)
from engine.data_loader import Slate


def _row(name, team, pos, status, week=5):
    return {"season": "2024", "week": str(week), "team": team, "position": pos,
            "full_name": name, "report_status": status}


ROWS = [
    _row("Josh Allen", "BUF", "QB", "Questionable"),
    _row("Ed Oliver", "BUF", "DT", "Out"),
    _row("Healthy Guy", "KC", "WR", ""),          # blank status -> skipped
    _row("Last Week", "KC", "RB", "Out", week=4),  # wrong week -> skipped
]


def test_map_status():
    assert inj._map_status("Out") == "OUT"
    assert inj._map_status("questionable") == "QUESTIONABLE"
    assert inj._map_status("Injured Reserve") == "IR"
    assert inj._map_status("") == ""


def test_injuries_for_week_filters_and_maps():
    got = inj.injuries_for_week(ROWS, week=5)
    names = {i.player for i in got}
    assert names == {"Josh Allen", "Ed Oliver"}  # blank + wrong-week dropped
    oliver = next(i for i in got if i.player == "Ed Oliver")
    assert oliver.status == "OUT" and oliver.role == "dt"  # position -> role


def _slate():
    teams = {"KC": Team("KC", "KC", DefenseProfile("KC")),
             "BUF": Team("BUF", "BUF", DefenseProfile("BUF"))}
    game = Game(home="KC", away="BUF", weather=Weather(dome=True), spread=-2.5, total=47.0)
    allen = Prop("Josh Allen", "BUF", "KC", "QB", PASS_YDS,
                 [GameLog(w, "X", 260) for w in range(1, 6)], 255, None,
                 [SportsbookLine("proxy", 250.0)], "starter")
    pacheco = Prop("Isiah Pacheco", "KC", "BUF", "RB", RUSH_YDS,
                   [GameLog(w, "X", 70) for w in range(1, 6)], 68, None,
                   [SportsbookLine("proxy", 65.0)], "rb1")
    return Slate("2024-W05", teams, [game], [allen, pacheco])


def test_attach_populates_and_reports_holds(monkeypatch):
    monkeypatch.setattr(inj, "load_injuries", lambda season: ROWS)
    slate = _slate()
    res = inj.attach_injuries_to_slate(slate, 2024, 5)

    # Both BUF injuries land on the KC-BUF game.
    game_names = {i.player for i in slate.games[0].injuries}
    assert game_names == {"Josh Allen", "Ed Oliver"}

    # Allen (a prop player) is Questionable -> flagged for a hold; Pacheco isn't.
    assert res.holds == ["Josh Allen"]
    assert res.by_status.get("OUT") == 1 and res.by_status.get("QUESTIONABLE") == 1


def test_knock_on_effect_from_feed(monkeypatch):
    monkeypatch.setattr(inj, "load_injuries", lambda season: ROWS)
    slate = _slate()
    inj.attach_injuries_to_slate(slate, 2024, 5)

    # Opposing DT (Ed Oliver, BUF) ruled out should lift Pacheco's rush projection.
    pacheco = slate.props[1]
    game = slate.games[0]
    effect = evaluate_injuries(pacheco, game.injuries)
    assert effect.multiplier > 1.0
    assert any("Ed Oliver" in r for r in effect.reasons)


def test_pipeline_holds_injured_prop(monkeypatch):
    monkeypatch.setattr(inj, "load_injuries", lambda season: ROWS)
    slate = _slate()
    inj.attach_injuries_to_slate(slate, 2024, 5)
    from engine.pipeline import run_slate
    result = run_slate(slate)
    allen = next(r for r in result["recommendations"] if r["player"] == "Josh Allen")
    assert allen["recommended"] is False
    assert any("QUESTIONABLE" in w for w in allen["warnings"])


if __name__ == "__main__":
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        needs = fn.__code__.co_argcount == 1
        mp = MP() if needs else None
        try:
            fn(mp) if needs else fn()
            print(f"  ok  {name}")
        finally:
            if mp: mp.undo()
    print(f"\n{len(fns)} tests passed.")
