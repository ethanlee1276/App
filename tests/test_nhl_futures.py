"""NHL futures: the season played out in points, the NHL's playoff field,
and every unplayed game from the clubs' own season pages.

Ethan, 2026-10-03: "do all of them" (line combinations, the parlay 2-leg
mode, futures, live lines). Checks, one rule each: a points league seeds on
points, two for a win and one for a loss past regulation, and projects them
with a band; the field is the top three of each division plus two wild
cards a conference; a better club wins more Cups; the schedule reader keeps
only unplayed regular-season games, once each; the Cup price rides the same
one-credit weekly futures pull; the page shows W-L-OT and points.

Run directly: `python3 tests/test_nhl_futures.py`
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import futures as F                                 # noqa: E402
from engine.divisions import MAPS                               # noqa: E402
from engine.sources import nhldata as N                         # noqa: E402

TEAMS = sorted(MAPS["nhl"])


def _season(games_each=10, seed=3):
    rng = random.Random(seed)
    fx = []
    for _ in range(games_each * len(TEAMS) // 2):
        h, a = rng.sample(TEAMS, 2)
        fx.append(F.Fixture(h, a))
    return fx


def test_a_points_league_seeds_on_points_and_projects_them():
    ratings = {t: 0.0 for t in TEAMS}
    ratings["COL"] = 0.8
    records = {t: (0, 0) for t in TEAMS}
    out = F.simulate("nhl", ratings, records, _season(), trials=600,
                     banked_points={"COL": 4, "EDM": 3})
    assert out["points_league"] is True
    by = {t["team"]: t for t in out["teams"]}
    col = by["COL"]
    assert col["points"] == 4 and by["EDM"]["points"] == 3, "the overtime loss already banked counts"
    assert col["proj_points_lo"] <= col["proj_points"] <= col["proj_points_hi"]
    # Every win is two points, and about OT_SHARE of losses add one.
    losses = col["remaining"] - col["proj_wins"]
    assert abs(col["proj_points"] - (4 + 2 * col["proj_wins"] + F.OT_SHARE * losses)) < 1.0, col
    assert col["p_title"] == max(t["p_title"] for t in out["teams"]), "the best club wins the most Cups"
    mlb = F.simulate("mlb", {"NYY": 0.1, "BOS": 0.0}, {"NYY": (0, 0), "BOS": (0, 0)},
                     [F.Fixture("NYY", "BOS")] * 4, trials=50)
    assert mlb["points_league"] is False and "proj_points" not in mlb["teams"][0]


def test_the_field_is_three_a_division_and_two_wild_cards():
    east = [t for t in TEAMS if MAPS["nhl"][t][0] == "Eastern"]
    # Atlantic clubs take the top eight records — but only three of them,
    # plus the two best wild cards, may come from one division.
    table = {t: (100 if MAPS["nhl"][t][1] == "Atlantic" else 50) + i for i, t in enumerate(east)}
    field = F._seed_field(F.SHAPES["nhl"], table, east, "nhl", random.Random(1))
    assert len(field) == 8
    atl = [t for t in field if MAPS["nhl"][t][1] == "Atlantic"]
    met = [t for t in field if MAPS["nhl"][t][1] == "Metropolitan"]
    assert len(atl) == 5 and len(met) == 3, (atl, met)
    assert F.SHAPES["nhl"].series_len == 7


def test_the_schedule_reader_keeps_unplayed_regular_season_games_once():
    def club(team, season):
        assert season == 2026
        return {"games": [
            {"id": 1, "gameType": 2, "gameState": "FUT", "homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "CGY"}},
            {"id": 2, "gameType": 2, "gameState": "OFF", "homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "VAN"}},
            {"id": 3, "gameType": 1, "gameState": "FUT", "homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "SEA"}},
            {"id": 4, "gameType": 2, "gameState": "PRE", "homeTeam": {"abbrev": "CGY"}, "awayTeam": {"abbrev": "EDM"}},
        ]}
    got = sorted(N.remaining_fixtures(2026, ["EDM", "CGY"], fetch=club))
    assert got == [("CGY", "EDM"), ("EDM", "CGY")], got
    def down(team, season):
        raise N.DataUnavailable("no page")
    assert N.remaining_fixtures(2026, ["EDM"], fetch=down) == []


def test_the_cup_price_rides_the_weekly_one_credit_pull_and_the_page_reads_points():
    from engine.sources import oddsapi
    assert oddsapi.FUTURES_KEYS["nhl"] == "icehockey_nhl_championship_winner"
    import futures_build
    assert "nhl" in futures_build.SPORTS and futures_build.SEASON_MARKETS["nhl"]
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert 'd.points_league ? "W-L-OT" : "W-L"' in js and "t.proj_points" in js
    # A failed price pull says why (a hand run printed "0 priced" and nothing else).
    from engine import futuresdata as FD
    real = oddsapi.fetch_outrights
    def boom(sport, cache_only=False):
        raise RuntimeError("no odds key in this shell")
    oddsapi.fetch_outrights = boom
    try:
        assert FD.title_prices("nhl", cache_only=False) == {}
        assert "no odds key in this shell" in FD.LAST_PRICE_NOTE
    finally:
        oddsapi.fetch_outrights = real
    assert "prices: {data['price_note']}" in open(os.path.join(ROOT, "futures_build.py"), encoding="utf-8").read()


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
