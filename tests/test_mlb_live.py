"""Tests for the MLB live lineup / game-log adapters (offline, fixtures)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mlb.sources import statslogs as sl
from engine.mlb.models import TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS


# --- fixtures shaped like real MLB Stats API responses ----------------------
BOX = {
    "teams": {
        "home": {
            "team": {"id": 112, "abbreviation": "CHC"},
            "battingOrder": [1001, 1002, 1003],
            "players": {
                "ID1001": {"person": {"id": 1001, "fullName": "Leadoff Guy"},
                           "position": {"abbreviation": "CF"}, "battingOrder": "100"},
                "ID1002": {"person": {"id": 1002, "fullName": "Two Hole"},
                           "position": {"abbreviation": "SS"}, "battingOrder": "200"},
                "ID1003": {"person": {"id": 1003, "fullName": "Cleanup"},
                           "position": {"abbreviation": "1B"}, "battingOrder": "300"},
            },
        },
        "away": {"team": {"id": 143}, "battingOrder": [], "players": {}},
    }
}

PERSON = {"people": [{"id": 1001, "fullName": "Leadoff Guy",
                      "batSide": {"code": "L"}, "pitchHand": {"code": "R"},
                      "primaryPosition": {"abbreviation": "CF"}}]}

LOG = {"stats": [{"type": {"displayName": "gameLog"}, "group": {"displayName": "hitting"},
                  "splits": [
    {"date": "2024-04-01", "opponent": {"id": 138}, "isHome": True,
     "stat": {"hits": 1, "totalBases": 1, "homeRuns": 0}},
    {"date": "2024-04-02", "opponent": {"id": 138}, "isHome": True,
     "stat": {"hits": 2, "totalBases": 5, "homeRuns": 1}},
    {"date": "2024-04-03", "opponent": {"id": 158, "abbreviation": "MIL"}, "isHome": False,
     "stat": {"hits": 0, "totalBases": 0, "homeRuns": 0}},
]}]}

PLOG = {"stats": [{"splits": [
    {"opponent": {"id": 112}, "isHome": True, "stat": {"strikeOuts": 6}},
    {"opponent": {"id": 112}, "isHome": True, "stat": {"strikeOuts": 7}},
    {"opponent": {"id": 112}, "isHome": True, "stat": {"strikeOuts": 9}},
]}]}


# --- lineup -----------------------------------------------------------------
def test_parse_lineup_order_and_positions():
    lineup = sl.parse_lineup(BOX, "home")
    assert [e.spot for e in lineup] == [1, 2, 3]
    assert [e.name for e in lineup] == ["Leadoff Guy", "Two Hole", "Cleanup"]
    assert lineup[1].position == "SS" and lineup[1].person_id == 1002


def test_parse_lineup_empty_when_no_order():
    assert sl.parse_lineup(BOX, "away") == []


def test_last_final_game_picks_most_recent_final():
    """The projected-lineup source: from a team-scoped schedule, the newest
    FINAL game and which side the team occupied."""
    sched = {"dates": [
        {"date": "2026-07-23", "games": [
            {"gamePk": 111, "status": {"abstractGameState": "Final"},
             "teams": {"home": {"team": {"id": 112}}, "away": {"team": {"id": 143}}}}]},
        {"date": "2026-07-25", "games": [
            {"gamePk": 333, "status": {"abstractGameState": "Final"},
             "teams": {"home": {"team": {"id": 143}}, "away": {"team": {"id": 112}}}},
            # A postponed/scheduled game the same window must never win.
            {"gamePk": 444, "status": {"abstractGameState": "Preview"},
             "teams": {"home": {"team": {"id": 112}}, "away": {"team": {"id": 143}}}}]},
    ]}
    assert sl.last_final_game(sched, 112) == (333, "away")
    assert sl.last_final_game(sched, 143) == (333, "home")
    assert sl.last_final_game({"dates": []}, 112) is None


def test_projected_lineup_holds_recommendations():
    """A hitter from a PROJECTED lineup has a real batting spot — only the
    game-level lineups_confirmed flag stops him being recommended (and
    journaled) before the card is official."""
    from engine.betting import Recommendation
    from engine.mlb.rules import apply_mlb_rules
    from engine.mlb.models import MLBProp, MLBGame, MLBGameLog
    from engine.mlb.projection import build_mlb_projection

    prop = MLBProp("Projected Guy", "CHC", "MIL", "CF", TOTAL_BASES,
                   [MLBGameLog(i, "MIL", 1) for i in range(1, 6)], 1.0, None,
                   [], lineup_spot=2)
    game = MLBGame(home="CHC", away="MIL", park="wrigley",
                   lineups_confirmed=False)
    rec = Recommendation(player="Projected Guy", team="CHC", opponent="MIL",
                         market=TOTAL_BASES, side="OVER", book="FanDuel",
                         line=1.5, odds=-110, projection=1.9, proj_low=1.0,
                         proj_high=2.8, hit_prob=0.6, fair_prob=0.52,
                         edge=0.08, ev_per_unit=0.1, confidence=8.0,
                         stake_units=0.2, grade="Play")
    proj = build_mlb_projection(prop, game)
    d = apply_mlb_rules(rec, prop, game, proj)
    assert d.recommend is False
    assert any("confirmed lineup" in w for w in d.warnings)
    # Same prop with the lineup confirmed sails through.
    game.lineups_confirmed = True
    assert apply_mlb_rules(rec, prop, game, proj).recommend is True


# --- person -----------------------------------------------------------------
def test_parse_person_handedness():
    p = sl.parse_person(PERSON)
    assert p["bats"] == "L" and p["throws"] == "R" and p["position"] == "CF"


def test_parse_person_defaults_when_empty():
    p = sl.parse_person({"people": []})
    assert p["bats"] == "R" and p["throws"] == "R"


# --- game logs --------------------------------------------------------------
def test_game_log_most_recent_first_and_market_field():
    tb = sl.parse_game_log(LOG, TOTAL_BASES)
    assert [g.value for g in tb] == [0, 5, 1]          # newest first
    assert [g.game for g in tb] == [3, 2, 1]
    assert sl.parse_game_log(LOG, HITS)[0].value == 0
    assert sl.parse_game_log(LOG, HOME_RUNS)[1].value == 1


def test_game_log_opponent_resolution_and_home_flag():
    tb = sl.parse_game_log(LOG, TOTAL_BASES)
    assert tb[0].opponent == "MIL" and tb[0].home is False   # abbreviation present
    assert tb[1].opponent == "STL" and tb[1].home is True    # mapped from team id 138


def test_game_log_limit_and_empty():
    assert len(sl.parse_game_log(LOG, HITS, limit=2)) == 2
    assert sl.parse_game_log({}, HITS) == []


def test_all_thirty_parks_are_wired_end_to_end():
    """Every MLB park must resolve from its venue name to a real profile with
    weather coords and a wind orientation — 'Generic Park' on a live slate
    means a stadium fell through this wiring."""
    from engine.mlb.parks import PARKS
    from engine.mlb.sources.mlbstats import (
        VENUE_PARK, PARK_COORDS, PARK_ORIENTATION,
    )
    assert len(PARKS) == 30
    teams = [p.team for p in PARKS.values()]
    assert len(set(teams)) == 30            # one park per club, no dupes
    for frag, key in VENUE_PARK.items():
        assert key in PARKS, f"venue fragment {frag!r} maps to unknown {key!r}"
    for key in PARKS:
        assert key in PARK_COORDS, f"{key} missing weather coordinates"
        assert key in PARK_ORIENTATION, f"{key} missing wind orientation"
    # A few real venue strings resolve to the right park.
    def resolve(venue):
        v = venue.lower()
        return next((k for frag, k in VENUE_PARK.items() if frag in v), "generic")
    assert resolve("Daikin Park") == "daikin"
    assert resolve("Rate Field") == "rate"
    assert resolve("Sutter Health Park") == "sutter"
    assert resolve("Oriole Park at Camden Yards") == "camden"
    assert resolve("T-Mobile Park") == "tmobile"


def test_live_slate_builds_home_run_props_by_default():
    """The Long Shots board prices HOME_RUNS props — a live slate that never
    builds them means the board is empty forever, silently."""
    import inspect
    sig = inspect.signature(sl.build_live_slate)
    assert HOME_RUNS in sig.parameters["hitter_markets"].default


def test_game_log_no_limit_keeps_the_full_season():
    """limit=None is what ingestion uses: the API returns season-to-date, and
    capping at 15 meant every historical backfill day re-stored the same 15
    most-recent games instead of the season being backfilled."""
    season = {"stats": [{"splits": [
        {"date": f"2024-04-{d:02d}", "opponent": {"id": 138}, "isHome": True,
         "stat": {"hits": 1, "totalBases": 2, "homeRuns": 0}}
        for d in range(1, 21)]}]}                      # 20 games
    assert len(sl.parse_game_log(season, HITS)) == 15  # live default: capped
    full = sl.parse_game_log(season, HITS, limit=None)
    assert len(full) == 20
    assert full[0].date == "2024-04-20" and full[-1].date == "2024-04-01"


def test_pitcher_game_log_strikeouts():
    ks = sl.parse_game_log(PLOG, STRIKEOUTS)
    assert [g.value for g in ks] == [9, 7, 6]


def test_market_group_and_stat_maps():
    assert sl.MARKET_GROUP[STRIKEOUTS] == "pitching"
    assert sl.MARKET_GROUP[HITS] == "hitting"
    assert sl.MARKET_STAT[TOTAL_BASES] == "totalBases"


def test_proxy_line():
    assert sl._proxy_line(0.4, HOME_RUNS) == 0.5      # HR always 0.5
    assert sl._proxy_line(2.4, TOTAL_BASES) == 2.0    # round to .5, step under


# --- offline orchestrator integration ---------------------------------------
def test_build_live_slate_offline():
    SCHED = {"dates": [{"games": [{
        "gamePk": 999,
        "teams": {
            "home": {"team": {"id": 112}},
            "away": {"team": {"id": 143}, "probablePitcher":
                     {"id": 5001, "fullName": "Ace", "pitchHand": {"code": "R"}}},
        },
        "venue": {"name": "Wrigley Field"},
    }]}]}

    saved = (sl._get_json, sl.fetch_boxscore, sl.fetch_person,
             sl.fetch_game_log, sl.park_weather)
    sl._get_json = lambda url, cache, ttl=600: SCHED
    sl.fetch_boxscore = lambda pk: BOX
    sl.fetch_person = lambda pid: PERSON
    sl.fetch_game_log = lambda pid, group, season: (PLOG if group == "pitching" else LOG)
    sl.park_weather = lambda key: __import__("engine.mlb.models", fromlist=["MLBWeather"]).MLBWeather()
    try:
        slate = sl.build_live_slate("2024-06-20", hitter_markets=(TOTAL_BASES,))
        assert slate.games and slate.props
        assert slate.games[0].home == "CHC" and slate.games[0].park == "wrigley"
        assert slate.games[0].lineups_confirmed is True
        # 3 confirmed home hitters (1 market each) + 1 probable pitcher K prop.
        hitters = [p for p in slate.props if p.market == TOTAL_BASES]
        pitchers = [p for p in slate.props if p.market == STRIKEOUTS]
        assert len(hitters) == 3 and len(pitchers) == 1
        assert hitters[0].lineup_spot == 1 and hitters[0].bats == "L"
        assert hitters[0].lines[0].book == "proxy"
        # And the full MLB pipeline runs on the live-shaped slate.
        from engine.mlb.pipeline import run_mlb_slate
        result = run_mlb_slate(slate)
        assert result["counts"]["props_analyzed"] == len(slate.props)
    finally:
        (sl._get_json, sl.fetch_boxscore, sl.fetch_person,
         sl.fetch_game_log, sl.park_weather) = saved


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
