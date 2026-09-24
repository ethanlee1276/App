"""Picks read the forecast for kickoff — never the weather at another time.

Ethan, 2026-09-25: "a game on Sunday, we are showing its 62 degrees warm
there now, but the weather could be different on that Sunday. I want to
make sure weather on a day the game isn't on isn't affecting picks."

Two real faults, found checking exactly that:

* MLB READ THE WEATHER RIGHT NOW. `park_weather` asked Open-Meteo for its
  `current=` reading, cached per park, so a 7:05 game priced in the
  morning took the morning's temperature and wind, and a slate built the
  night before took that night's. It now reads the hourly forecast for the
  day of first pitch at the hour nearest it.
* THE NFL READ THE WRONG HOUR. The kickoff instant is Eastern and the
  forecast's hours are UTC; the offset was dropped, not converted, so a
  1 p.m. game took the 9 a.m. reading and Sunday night the 4 p.m. one.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import nflwx                                           # noqa: E402
from engine.cfb import wx                                          # noqa: E402
from engine.mlb.sources import mlbstats as MS                      # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LOGS = open(os.path.join(ROOT, "engine", "mlb", "sources", "statslogs.py"), encoding="utf-8").read()


def _board(day):
    hours = [f"{day}T{h:02d}:00" for h in range(24)]
    return {"hourly": {"time": hours, "temperature_2m": [40 + h for h in range(24)],
                       "wind_speed_10m": [h for h in range(24)], "wind_direction_10m": [180] * 24,
                       "precipitation_probability": [0] * 12 + [90] * 12,
                       "relative_humidity_2m": [50] * 24}}


def test_an_eastern_kickoff_reads_the_utc_hour():
    got = wx.pick_hour(_board("2026-09-27"), "2026-09-27T13:00:00-04:00")
    assert got["temp_f"] == 40 + 17, "1 p.m. Eastern is 17:00 UTC, not 13:00"
    assert wx.pick_hour(_board("2026-09-27"), "2026-09-27T19:10Z")["temp_f"] == 40 + 19, \
        "a UTC kickoff (college's) reads as before"


def test_sunday_night_asks_for_mondays_utc_board():
    asked = []

    def fc(lat, lon, day, kickoff):
        asked.append((day, kickoff))
        return {"temp_f": 60, "wind_mph": 5, "precip_chance": 0.0}
    g = types.SimpleNamespace(home="KC", away="BUF", roof="outdoors", weather=None,
                              kickoff="20:20", date="2026-09-27", neutral_site=False, venue="")
    assert nflwx.attach([g], forecast=fc) == 1
    assert asked == [("2026-09-28", "2026-09-27T20:20:00-04:00")], asked
    assert nflwx.utc_day("2026-09-27T13:00:00-04:00") == "2026-09-27"


def test_mlb_reads_first_pitch_never_right_now():
    seen = []
    real = MS._get_json

    def fake(url, name, ttl=None):
        seen.append((url, name))
        return _board(url.split("start_date=")[1][:10])
    MS._get_json = fake
    try:
        park = next(iter(MS.PARK_COORDS))
        w = MS.park_weather(park, "2026-09-25T23:05:00Z")
        night = MS.park_weather(park, "2026-09-26T01:10:00Z")
        none = MS.park_weather(park, None)
    finally:
        MS._get_json = real
    url, name = seen[0]
    assert "hourly=" in url and "current=" not in url
    assert "start_date=2026-09-25" in url and name == f"meteo_{park}_2026-09-25.json", \
        "the day of first pitch, cached per park PER DAY"
    assert w.temp_f == 40 + 23 and abs(w.precip_chance - 0.9) < 1e-9 and w.humidity == 0.5
    assert night.temp_f == 40 + 1, "a 9:10 Eastern first pitch reads 01:00 UTC on the next day's board"
    assert none == MS.MLBWeather(), "no first pitch is the neutral default, not a reading from now"
    assert LOGS.count('park_weather(park, g.get("gameDate"))') == 1


def test_the_page_says_it_is_the_kickoff_forecast():
    assert APP.count(" · kickoff forecast") == 2
    assert 'class="game-wx-chip" title="Forecast for kickoff"' in APP


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
