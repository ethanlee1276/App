"""The venue encoding contract, computed rather than assumed.

The redesign spec §5.1 makes one rule the difference between a venue mark
and clip-art:

    A venue mark never renders without encoding something. Amber stroke =
    that condition is material to tonight's plays. Never applied
    decoratively.

and §5.3 says the flag behind it is *"computed upstream by the model — true
when the condition actually moved the number for at least one play at that
venue."*

The prototype faked it with thresholds: wind >= 8mph, altitude >= 3000ft,
any roof. That answers a DIFFERENT question. It says the condition is BIG,
not that it did anything — a 10mph wind at a venue whose only priced market
is rushing yards moves nothing, and the mark should be dim. These tests pin
the real computation.

The second half is the past-performance table's conditions column (§6.4:
"add the conditions column — WIND for NFL, PARK for MLB"). It shipped
omitted because the slate carried no such data. It carries it now:

  MLB   the park needs no new source at all. A game log already records the
        opponent and whether the player was home, and those two facts name
        the venue exactly.
  NFL   the weekly player feed has no weather; the `games` table does. The
        join is by game_id, which is "AWAY@HOME".
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import pipeline as nfl_pipeline
from engine.db import SCHEMA, nfl_game_winds
from engine.mlb import pipeline as mlb_pipeline
from engine.mlb.parks import get_park, park_for_team, park_of_game


class _W:
    def __init__(self, **kw):
        self.dome = kw.get("dome", False)
        self.temp_f = kw.get("temp_f", 70)
        self.wind_mph = kw.get("wind_mph", 0)
        self.wind_dir = kw.get("wind_dir", "N")
        self.rain = kw.get("rain", False)
        self.snow = kw.get("snow", False)
        self.precip_chance = kw.get("precip_chance", 0.0)


class _G:
    def __init__(self, weather, roof="outdoors", home="CHI", away="GB"):
        self.weather, self.roof, self.home, self.away = weather, roof, home, away


# --- NFL: material means "it moved a number" --------------------------------
def test_a_calm_venue_is_not_material():
    """The dimness is the message (§5.1): "All-bone, zero amber —
    environment is neutral here"."""
    c = nfl_pipeline._conditions(_G(_W(wind_mph=2)), [])
    assert c["material"] is False
    assert c["markets_moved"] == []


def test_wind_that_moves_a_priced_market_is_material():
    priced = [{"market": "pass_yds", "team": "CHI", "opponent": "GB"}]
    c = nfl_pipeline._conditions(_G(_W(wind_mph=20)), priced)
    assert c["material"] is True
    assert "pass_yds" in c["markets_moved"]
    assert c["why"], "amber with no stated reason is decoration"


def test_wind_that_moves_nothing_priced_is_not_material():
    """The whole point of computing it. 20mph wind is a big number, and it
    moves passing markets — but if the only prop on the board at that venue
    is a market the wind model does not touch, nothing moved tonight.

    A threshold cannot tell these two cases apart; that is why it was
    replaced."""
    priced = [{"market": "made_up_market", "team": "CHI", "opponent": "GB"}]
    c = nfl_pipeline._conditions(_G(_W(wind_mph=20)), priced)
    assert c["material"] is False, "the threshold fallback is back"
    assert c["markets_moved"] == []


def test_a_roof_is_material_on_its_own_terms():
    """"Amber wash fill = roofed venue — the absence of weather IS
    information" (§5.1). evaluate_weather returns flat multipliers for a
    dome precisely because nothing else applies, so materiality cannot come
    from the multipliers here."""
    c = nfl_pipeline._conditions(_G(_W(dome=True), roof="dome"), [])
    assert c["material"] is True and c["roofed"] is True


def test_the_reasons_come_from_the_model_not_from_the_renderer():
    """So the mark and the card cannot disagree about why it is lit."""
    c = nfl_pipeline._conditions(_G(_W(wind_mph=26)), None)
    assert any("mph" in r for r in c["why"])


# --- MLB ---------------------------------------------------------------------
class _MW:
    def __init__(self, **kw):
        self.roof_closed = kw.get("roof_closed", False)
        self.temp_f = kw.get("temp_f", 70)
        self.wind_mph = kw.get("wind_mph", 0)
        self.wind_dir_rel = kw.get("wind_dir_rel", "cross")
        self.precip_chance = 0.0


class _MG:
    def __init__(self, park, weather, home="CHC", away="MIL"):
        self.park, self.weather, self.home, self.away = park, weather, home, away


def test_a_park_that_moves_a_priced_market_is_material():
    c = mlb_pipeline._conditions(_MG("coors", _MW()), get_park("coors"),
                                 [{"market": "home_runs", "team": "COL",
                                   "opponent": "CHC"}])
    assert c["material"] is True
    assert c["why"]


def test_wind_at_wrigley_is_material_even_though_the_park_is_not():
    """The case that caught a real bug. Wrigley's factors (hr 1.04, run
    1.02) sit UNDER evaluate_park's own thresholds, so the building moves
    nothing — but 16mph blowing out is the most famous wind effect in
    baseball, and the park's own profile says to check the wind before
    anything else there.

    The first version flagged this material with an EMPTY reason list,
    which is exactly what §5.1 forbids: an amber stroke encoding nothing.
    Weather is priced in the home-run model, not in evaluate_park, so the
    reasons have to come from there."""
    g = _MG("wrigley", _MW(wind_mph=16, wind_dir_rel="out"))
    c = mlb_pipeline._conditions(g, get_park("wrigley"), [])
    assert c["material"] is True
    assert c["why"], "material with no reason — decoration, not encoding"
    assert any("wind" in r.lower() for r in c["why"])


def test_the_reasons_do_not_say_the_same_thing_twice():
    """evaluate_park and park_weather_multiplier overlap on the park and
    word it differently, so exact-match dedupe was not enough: Coors came
    out saying both "boosts home runs (+22% vs average)" and "plays big for
    home runs (+22% HR factor)", and named its altitude twice."""
    c = mlb_pipeline._conditions(_MG("coors", _MW(temp_f=88)),
                                 get_park("coors"), [])
    why = [r.lower() for r in c["why"]]
    assert sum("home run" in r for r in why) <= 1, why
    assert sum("altitude" in r for r in why) <= 1, why


# --- the conditions column ---------------------------------------------------
def test_a_past_games_park_is_derivable_from_the_log_alone():
    """No new data source. Home means the player's own park; away means the
    opponent's."""
    assert park_of_game("CHC", "COL", True).name == "Wrigley Field"
    assert park_of_game("CHC", "COL", False).name == "Coors Field"
    assert park_of_game("ZZZ", "YYY", True) is None


def test_an_unknown_team_omits_the_column_rather_than_blanking_it():
    """A column of em dashes looks like the data is missing rather than not
    applicable, which is worse than no column."""
    class P:
        team = "ZZZ"

    class L:
        opponent = "YYY"
        home = True

    assert mlb_pipeline._log_park(P(), L()) == {}


def test_the_nfl_season_of_a_january_game_is_the_previous_year():
    """The bug that made the first conditions column come back empty. An
    NFL season spans the new year — week 18 of 2025 is played in January
    2026 — so keying on the calendar year sent every January slate looking
    in a season the database had not started yet."""
    assert nfl_pipeline.nfl_season_of("2026-01-04") == 2025
    assert nfl_pipeline.nfl_season_of("2025-09-14") == 2025
    assert nfl_pipeline.nfl_season_of("2026-02-08") == 2025
    assert nfl_pipeline.nfl_season_of("2026-09-14") == 2026


def test_the_wind_lookup_reads_the_games_table():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, wind)"
                 " VALUES ('nfl', 2025, '001', 'GB@CHI', 'CHI', 'GB', 14)")
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, away, wind)"
                 " VALUES ('nfl', 2025, '009', 'CHI@GB', 'GB', 'CHI', NULL)")
    idx = nfl_game_winds(conn, 2025)
    assert idx == {"GB@CHI": 14.0}, "a NULL wind must not become a 0mph claim"


def test_the_wind_lookup_does_not_trust_the_unpopulated_home_flag():
    """nflverse weekly rows carry no home flag and GameLog defaults it to
    True, so a lookup that trusted it would miss every away game. Only one
    of "A@B" and "B@A" is a real game, so trying both resolves it."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine",
                            "pipeline.py"), encoding="utf-8").read()
    fn = src[src.index("def _log_wind("):src.index("def _opportunity_shares(")]
    assert 'f"{opp}@{team}", f"{team}@{opp}"' in fn, \
        "the lookup is back to trusting log.home"


def test_a_missing_history_database_does_not_take_the_slate_down():
    """A board with no wind column is a board; a board that fails to build
    is nothing."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "engine",
                            "pipeline.py"), encoding="utf-8").read()
    fn = src[src.index("def _wind_index("):src.index("def _log_wind(")]
    assert "except Exception" in fn and "= {}" in fn


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
