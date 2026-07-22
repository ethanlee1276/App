"""Tests for the Odds API adapter. Network is stubbed with a fixture payload
shaped like a real The Odds API v4 event-odds response."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as oa
from engine.models import (
    Team, DefenseProfile, Weather, Game, Prop, GameLog, SportsbookLine,
    PASS_YDS, REC_YDS,
)
from engine.data_loader import Slate


# A representative event-odds payload (two books, two markets, over/under each).
EVENT = {
    "id": "evt123",
    "home_team": "Kansas City Chiefs",
    "away_team": "Buffalo Bills",
    "bookmakers": [
        {
            "key": "draftkings", "title": "DraftKings",
            "markets": [
                {"key": "player_pass_yds", "outcomes": [
                    {"name": "Over", "description": "Josh Allen", "price": -115, "point": 258.5},
                    {"name": "Under", "description": "Josh Allen", "price": -105, "point": 258.5},
                ]},
                {"key": "player_reception_yds", "outcomes": [
                    {"name": "Over", "description": "Amon-Ra St. Brown", "price": -110, "point": 79.5},
                    {"name": "Under", "description": "Amon-Ra St. Brown", "price": -110, "point": 79.5},
                ]},
            ],
        },
        {
            "key": "fanduel", "title": "FanDuel",
            "markets": [
                {"key": "player_pass_yds", "outcomes": [
                    {"name": "Over", "description": "Josh Allen", "price": -108, "point": 257.5},
                    {"name": "Under", "description": "Josh Allen", "price": -112, "point": 257.5},
                ]},
            ],
        },
    ],
}


def test_normalize_name():
    assert oa.normalize_name("Amon-Ra St. Brown") == "amon ra st brown"
    assert oa.normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert oa.normalize_name("Patrick Mahomes") == "patrick mahomes"


def test_parse_event_lines_pairs_and_maps():
    idx = oa.parse_event_lines(EVENT)
    allen = idx[(oa.normalize_name("Josh Allen"), PASS_YDS)]
    # Two books quoted Allen passing yards.
    books = {l.book for l in allen}
    assert books == {"DraftKings", "FanDuel"}
    dk = next(l for l in allen if l.book == "DraftKings")
    assert dk.line == 258.5 and dk.over_odds == -115 and dk.under_odds == -105
    # Receiving market maps + normalizes the hyphenated name.
    assert (oa.normalize_name("Amon-Ra St. Brown"), REC_YDS) in idx


def test_parse_ignores_unknown_markets():
    ev = {"bookmakers": [{"key": "dk", "markets": [
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "X", "price": 120, "point": None}]}]}]}
    assert oa.parse_event_lines(ev) == {}


def _mini_slate():
    teams = {
        "KC": Team("KC", "KC", DefenseProfile("KC")),
        "BUF": Team("BUF", "BUF", DefenseProfile("BUF")),
    }
    game = Game(home="KC", away="BUF", weather=Weather(dome=False), spread=-2.5, total=47.0)
    logs = [GameLog(week=w, opponent="X", value=260) for w in range(1, 6)]
    prop = Prop(
        player="Josh Allen", team="BUF", opponent="KC", position="QB",
        market=PASS_YDS, logs=logs, career_avg=255, vs_opponent_avg=None,
        lines=[SportsbookLine(book="proxy", line=250.0)], usage_role="starter",
    )
    return Slate(date="2024-W05", teams=teams, games=[game], props=[prop])


def test_apply_odds_replaces_proxy(monkeypatch):
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport='nfl': [
        {"id": "evt123", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"}
    ])
    monkeypatch.setattr(oa, "fetch_event_odds",
                        lambda eid, key, books=None, ttl=300, sport='nfl': (EVENT, oa.Quota("491", "9")))

    slate = _mini_slate()
    res = oa.apply_odds_to_slate(slate, api_key="testkey")
    assert res.matched == 1 and res.events_used == 1
    prop = slate.props[0]
    # Proxy line gone; real book lines attached.
    assert all(l.book != "proxy" for l in prop.lines)
    assert {l.book for l in prop.lines} == {"DraftKings", "FanDuel"}

    # And the model now shops the best (lowest) real line.
    from engine.odds import best_over_line
    assert best_over_line(prop.lines).line == 257.5  # FanDuel


def test_mlb_market_mapping_and_parse():
    # An MLB event payload uses batter_/pitcher_ market keys.
    ev = {"bookmakers": [
        {"key": "draftkings", "title": "DraftKings", "markets": [
            {"key": "batter_total_bases", "outcomes": [
                {"name": "Over", "description": "Aaron Judge", "price": -120, "point": 1.5},
                {"name": "Under", "description": "Aaron Judge", "price": 100, "point": 1.5}]},
            {"key": "pitcher_strikeouts", "outcomes": [
                {"name": "Over", "description": "Zack Wheeler", "price": -115, "point": 7.5},
                {"name": "Under", "description": "Zack Wheeler", "price": -105, "point": 7.5}]},
        ]}]}
    idx = oa.parse_event_lines(ev, oa.MLB_ODDS_TO_MARKET)
    assert (oa.normalize_name("Aaron Judge"), "total_bases") in idx
    assert (oa.normalize_name("Zack Wheeler"), "strikeouts") in idx
    tb = idx[(oa.normalize_name("Aaron Judge"), "total_bases")][0]
    assert tb.line == 1.5 and tb.over_odds == -120 and tb.under_odds == 100
    # NFL market keys are ignored under the MLB map.
    assert oa.parse_event_lines({"bookmakers": [{"key": "dk", "markets": [
        {"key": "player_pass_yds", "outcomes": []}]}]}, oa.MLB_ODDS_TO_MARKET) == {}


def test_mlb_apply_odds_end_to_end(monkeypatch):
    from engine.mlb.models import MLBGame, MLBProp, MLBGameLog
    from engine.mlb.data_loader import MLBSlate
    ev = {"bookmakers": [{"key": "fanduel", "title": "FanDuel", "markets": [
        {"key": "batter_total_bases", "outcomes": [
            {"name": "Over", "description": "Aaron Judge", "price": -125, "point": 2.5},
            {"name": "Under", "description": "Aaron Judge", "price": 105, "point": 2.5}]}]}]}
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport="nfl": [
        {"id": "e1", "home_team": "Colorado Rockies", "away_team": "New York Yankees"}])
    monkeypatch.setattr(oa, "fetch_event_odds",
                        lambda eid, key, books=None, ttl=300, sport="nfl": (ev, oa.Quota()))

    game = MLBGame(home="COL", away="NYY", park="coors")
    prop = MLBProp("Aaron Judge", "NYY", "COL", "RF", "total_bases",
                   [MLBGameLog(i, "X", 2) for i in range(1, 6)], 2.1, None,
                   [SportsbookLine("proxy", 2.0)], bats="R", lineup_spot=2)
    slate = MLBSlate(date="2024-06-20", games=[game], props=[prop])
    res = oa.apply_odds_to_slate(slate, api_key="k", sport="mlb")
    assert res.matched == 1
    assert prop.lines[0].book == "FanDuel" and prop.lines[0].line == 2.5


def test_apply_odds_reports_unmatched(monkeypatch):
    monkeypatch.setattr(oa, "list_events", lambda key, ttl=300, sport='nfl': [
        {"id": "evt123", "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills"}
    ])
    monkeypatch.setattr(oa, "fetch_event_odds",
                        lambda eid, key, books=None, ttl=300, sport='nfl': ({"bookmakers": []}, oa.Quota()))
    slate = _mini_slate()
    res = oa.apply_odds_to_slate(slate, api_key="testkey")
    assert res.matched == 0 and res.unmatched


if __name__ == "__main__":
    class MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, val)
        def undo(self):
            for obj, name, val in reversed(self._undo): setattr(obj, name, val)

    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in fns:
        needs_mp = fn.__code__.co_argcount == 1
        mp = MP() if needs_mp else None
        try:
            fn(mp) if needs_mp else fn()
            print(f"  ok  {name}")
        finally:
            if mp: mp.undo()
    print(f"\n{len(fns)} tests passed.")
