"""Kickoff weather for the college slate.

Ethan, 2026-08-24: "can you now work on the cfb weather next."

The old excuse — "no weather feed covers college venues" — was three
existing shelves nobody had joined: ESPN's scoreboard names each game's
venue and indoor flag (and has stamped `weather_checked: False` per §2
since the board shipped), CFBD's /venues carries every stadium's
coordinates behind the key the talent prior already needs, and
Open-Meteo answers hourly forecasts keylessly — the same service the MLB
board reads per park.

THE TWO DECISIONS WORTH PINNING:

  * Joined on the VENUE, not the home team. A kickoff classic in
    Atlanta is played in Atlanta; the home school's stadium can be a
    thousand miles from the sky that matters. ESPN names the actual
    venue per game.
  * A miss is a miss. Unknown venue, refused forecast, kickoff too far
    out — the game keeps weather_checked False and the card keeps
    saying "weather not pulled". §2 stays intact: nothing invented.

Run directly: `python3 tests/test_cfb_weather.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.cfb import wx                                    # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


VIDX = wx.venue_index([
    {"name": "Sanford Stadium", "latitude": 33.95, "longitude": -83.373,
     "dome": False},
    {"name": "Mercedes-Benz Stadium", "latitude": 33.755,
     "longitude": -84.401, "dome": True},
    {"name": "Nameless Field"},                       # no coordinates
])


def _game(**over):
    g = {"home": "UGA", "away": "CLEM", "venue": "Sanford Stadium",
         "indoor": False, "kickoff": "2026-09-05T23:30Z",
         "weather_checked": False}
    g.update(over)
    return g


def _fc(lat, lon, date, kickoff):
    assert (round(lat, 2), round(lon, 2)) == (33.95, -83.37), (lat, lon)
    assert date == "2026-09-05"
    return {"temp_f": 78, "wind_mph": 12, "wind_dir": "SE",
            "precip_chance": 0.35}


# --- the join --------------------------------------------------------------

def test_an_outdoor_game_gets_the_kickoff_forecast():
    g = _game()
    n = wx.attach([g], VIDX, forecast=_fc)
    assert n == 1
    assert g["weather"] == {"temp_f": 78, "wind_mph": 12, "wind_dir": "SE",
                            "precip_chance": 0.35, "dome": False}
    assert g["weather_checked"] is True


def test_the_join_is_on_the_venue_not_the_home_team():
    """The neutral-site case the design exists for: Georgia 'hosting' in
    Atlanta reads the dome it is actually played in, not Sanford's sky."""
    g = _game(venue="Mercedes-Benz Stadium", neutral_site=True)
    called = []
    wx.attach([g], VIDX, forecast=lambda *a: called.append(a) or None)
    assert g["weather"] == {"dome": True}
    assert g["weather_checked"] is True
    assert called == [], "a domed venue was asked for a forecast"


def test_espn_saying_indoor_is_already_the_answer():
    g = _game(indoor=True, venue="Some New Dome Nobody Indexed")
    n = wx.attach([g], VIDX, forecast=lambda *a: 1 / 0)
    assert n == 1 and g["weather"] == {"dome": True}


def test_an_unknown_venue_stays_honestly_unpulled():
    g = _game(venue="Field That Is Not In The Index")
    n = wx.attach([g], VIDX, forecast=_fc)
    assert n == 0
    assert "weather" not in g
    assert g["weather_checked"] is False


def test_a_refused_forecast_is_a_miss_not_a_crash():
    g = _game()
    n = wx.attach([g], VIDX, forecast=lambda *a: (_ for _ in ()).throw(
        RuntimeError("network says no")))
    assert n == 0 and "weather" not in g


def test_a_venue_without_coordinates_never_enters_the_index():
    from engine.sources.cfbdata import name_key
    assert name_key("Nameless Field") not in VIDX


# --- the hour picker -------------------------------------------------------

def test_the_reading_is_the_hour_nearest_kickoff():
    payload = {"hourly": {
        "time": ["2026-09-05T22:00", "2026-09-05T23:00", "2026-09-06T00:00"],
        "temperature_2m": [81.1, 78.3, 75.9],
        "wind_speed_10m": [8.2, 11.7, 13.0],
        "wind_direction_10m": [140, 150, 160],
        "precipitation_probability": [10, 35, 40]}}
    w = wx.pick_hour(payload, "2026-09-05T23:30Z")
    assert w == {"temp_f": 78, "wind_mph": 12, "wind_dir": "SE",
                 "precip_chance": 0.35}


def test_nothing_within_two_hours_is_a_miss():
    payload = {"hourly": {"time": ["2026-09-05T00:00"],
                          "temperature_2m": [70.0],
                          "wind_speed_10m": [5.0],
                          "wind_direction_10m": [0],
                          "precipitation_probability": [0]}}
    assert wx.pick_hour(payload, "2026-09-05T23:30Z") is None
    assert wx.pick_hour({}, "2026-09-05T23:30Z") is None
    assert wx.pick_hour(payload, "not a time") is None


def test_the_compass_reads_eight_ways():
    # Each point owns ±22.5°: N covers 337.5–22.5, so 23° is already NE.
    for bearing, want in ((0, "N"), (22, "N"), (23, "NE"), (90, "E"),
                          (225, "SW"), (315, "NW"), (359, "N")):
        assert wx.compass(bearing) == want, (bearing, want)
    assert wx.compass(None) == ""


# --- the wiring ------------------------------------------------------------

def test_the_build_stamps_and_ships_it():
    src = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert "_wx.attach(games, _wx.venue_index(_wx.fetch_venues()))" in src, \
        "cfb_build no longer pulls weather"
    i = src.index('out["games"] = [')
    seg = src[i:i + 1600]
    for field in ('"weather": g.get("weather")',
                  '"weather_checked": g.get("weather_checked", False)',
                  '"park_name": g.get("venue", "")'):
        assert field in seg, f"the slate payload lost {field}"


def test_the_card_uses_the_reading_and_keeps_the_honest_miss():
    """The NaN guard survives as the FALLBACK: a stamped game reads like
    the NFL's, an unstamped one still says "weather not pulled" instead
    of NaN°F.

    COLLEGE'S SENTENCE IS THE SHARED ONE NOW (2026-08-26). This branch
    used to be college-only, because college was the only league that
    knew whether anyone had looked. Then the NFL's turned out to be a
    prior wearing a forecast's clothes — nflverse fills temp and wind
    from the played game, so every forward board took 60°F / 6mph — and
    the honest line college already had is the right answer for both.
    Same claim, one branch instead of two."""
    assert "Outdoor · weather not pulled" in APP, \
        "the honest miss line is gone — an unstamped game will print NaN"
    i = APP.index("const wxKnown =")
    seg = APP[i:i + 420]
    assert "g.weather_checked" in seg, \
        "college's own stamp is no longer what makes its reading count"
    assert "Math.round(w.temp_f)" in seg, \
        "a stamped college game still hides its reading"


def test_the_weather_tab_is_open_for_cfb():
    i = APP.index("const HIDDEN_VIEWS")
    block = APP[i:APP.index("};", i)]
    line = block[block.index("cfb:"):]
    line = line[:line.index("]")]
    assert '"weather"' not in line, "the weather tab is hidden again for CFB"
    k = APP.index("const HIDDEN_WHY")
    why = APP[k:APP.index("};", k)]
    cfb_why = why[why.index("cfb:"):why.index("},", why.index("cfb:"))]
    assert "weather" not in cfb_why, \
        "HIDDEN_WHY still explains a tab that is no longer hidden"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
