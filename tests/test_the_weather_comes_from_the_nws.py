"""The boards' weather can come from the National Weather Service.

Ethan, 6 November 2026: "move the weather to the NWS". Open-Meteo's free API
is for non-commercial use by its own terms; the NWS forecast is the US
government's (public domain, free, no key, commercial use allowed). What
these hold:

  * the NWS hourly forecast becomes Open-Meteo's own hourly table, in UTC and
    the boards' units (°F, mph, degrees, percent), so the college and NFL
    kickoff reading (`cfb.wx.pick_hour`) and MLB's first-pitch reading read
    it unchanged;
  * two hops, as the API is built, under the site's own name (never a
    person's), cached apart from the weather desk's own NWS files;
  * outside the US the lookup has nothing, and the game keeps "weather not
    pulled": a miss, never another feed;
  * one setting picks the source, Open-Meteo until the box's side-by-side
    check says SWITCH;
  * the check: SWITCH when the two agree as two forecasts do, CHECK on a
    unit slip or when the NWS did not answer.

Run directly: `python3 tests/test_the_weather_comes_from_the_nws.py`
"""
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import wxsource as CLI                                               # noqa: E402
from engine.cfb import wx                                            # noqa: E402
from engine.sources import nws                                       # noqa: E402

#: The hourly forecast's own shape (api.weather.gov, /gridpoints/.../forecast/hourly).
PERIODS = {"properties": {"units": "us", "periods": [
    {"number": 1, "startTime": "2026-11-08T13:00:00-05:00", "endTime": "2026-11-08T14:00:00-05:00",
     "isDaytime": True, "temperature": 48, "temperatureUnit": "F",
     "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": 70},
     "relativeHumidity": {"unitCode": "wmoUnit:percent", "value": 88},
     "windSpeed": "14 mph", "windDirection": "NW", "shortForecast": "Rain Showers"},
    {"number": 2, "startTime": "2026-11-08T14:00:00-05:00", "endTime": "2026-11-08T15:00:00-05:00",
     "isDaytime": True, "temperature": 47, "temperatureUnit": "F",
     "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": None},
     "relativeHumidity": {"unitCode": "wmoUnit:percent", "value": 90},
     "windSpeed": "10 to 15 mph", "windDirection": "NNW"},
    {"number": 3, "startTime": "2026-11-08T15:00:00-05:00", "temperature": 10, "temperatureUnit": "C",
     "windSpeed": "Calm", "windDirection": ""},
    {"number": 4, "startTime": "not a time", "temperature": 40, "windSpeed": "5 mph"},
]}}


def test_the_hourly_forecast_becomes_the_boards_own_table():
    t = nws.hourly_table(PERIODS)
    h = t["hourly"]
    assert t["source"] == "nws"
    assert h["time"] == ["2026-11-08T18:00", "2026-11-08T19:00", "2026-11-08T20:00"], "UTC, and a bad time is left out"
    assert h["temperature_2m"] == [48.0, 47.0, 50.0], "°F, a Celsius hour converted"
    assert h["wind_speed_10m"] == [14.0, 12.5, 0.0], "mph; a range is its middle; calm is nothing"
    assert h["wind_direction_10m"] == [315.0, 337.5, None]
    assert h["precipitation_probability"] == [70.0, 0.0, 0.0]
    assert h["relative_humidity_2m"] == [88.0, 90.0, None]
    assert len({len(v) for v in h.values()}) == 1, "every column lines up with the hours"


def test_the_kickoff_reading_reads_it_unchanged():
    # A 1 p.m. Eastern kickoff, as the NFL writes it: the 18:00 UTC hour.
    got = wx.pick_hour(nws.hourly_table(PERIODS), "2026-11-08T13:00:00-05:00")
    assert got == {"temp_f": 48, "wind_mph": 14, "wind_dir": "NW", "precip_chance": 0.7}, got
    assert wx.pick_hour(nws.hourly_table(PERIODS), "2026-11-10T13:00:00-05:00") is None, \
        "no hour within two of kickoff is a miss"


def test_two_hops_under_the_sites_own_name_and_a_miss_abroad():
    asked = []

    def fetch(url, cache_name, ttl):
        asked.append((url, cache_name, ttl))
        if "/points/" in url:
            if url.endswith("51.5560,-0.2796"):                   # Wembley
                raise OSError("404 Data Unavailable For Requested Point")
            return {"properties": {"forecastHourly": "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly"}}
        return PERIODS
    t = nws.forecast(40.8135, -74.0745, ttl=600, fetch=fetch)
    assert t["hourly"]["time"][0] == "2026-11-08T18:00"
    assert [a[0] for a in asked] == ["https://api.weather.gov/points/40.8135,-74.0745",
                                    "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly"]
    assert asked[0][1].startswith("nws_grid_") and asked[1][1].startswith("nws_hourly_"), \
        "cached apart from the weather desk's nws_pt_ and nws_fc_ files"
    assert asked[0][2] == nws.GRID_TTL and asked[1][2] == 600
    abroad = nws.forecast(51.556, -0.2796, fetch=fetch)
    assert abroad["hourly"] == {} and wx.pick_hour(abroad, "2026-11-08T14:30:00Z") is None
    assert "qellysbook.com" in nws.USER_AGENT and "@" not in nws.USER_AGENT, "the site, never a person"


def test_one_setting_picks_the_source():
    saved = os.environ.pop(nws.ENV_SOURCE, None)
    try:
        assert nws.source() == "open-meteo" == nws.DEFAULT_SOURCE, "Open-Meteo until the check says SWITCH"
        os.environ[nws.ENV_SOURCE] = "NWS"
        assert nws.source() == "nws"
        os.environ[nws.ENV_SOURCE] = "open_meteo"
        assert nws.source() == "open-meteo"
        os.environ[nws.ENV_SOURCE] = "weather.com"
        assert nws.source() == "open-meteo", "an unknown name is the default, never a guess"
        # The college and NFL reader asks the source it is told to.
        os.environ[nws.ENV_SOURCE] = "nws"
        real = nws.forecast
        nws.forecast = lambda lat, lon, ttl=0, fetch=None: {"hourly": {"time": ["x"]}, "source": "nws", "at": (lat, lon)}
        try:
            got = wx.fetch_forecast(39.9008, -75.1675, "2026-11-08")
        finally:
            nws.forecast = real
        assert got["source"] == "nws" and got["at"] == (39.9008, -75.1675)
    finally:
        os.environ.pop(nws.ENV_SOURCE, None)
        if saved is not None:
            os.environ[nws.ENV_SOURCE] = saved


def test_mlb_reads_the_same_table_at_first_pitch():
    from engine.mlb.sources import mlbstats as M
    park = next(k for k in M.PARK_COORDS if k in M.PARK_ORIENTATION)
    saved = os.environ.get(nws.ENV_SOURCE)
    os.environ[nws.ENV_SOURCE] = "nws"
    real = nws.forecast
    nws.forecast = lambda lat, lon, ttl=0, fetch=None: nws.hourly_table(PERIODS)
    try:
        w = M.park_weather(park, "2026-11-08T18:10:00Z")
    finally:
        nws.forecast = real
        if saved is None:
            os.environ.pop(nws.ENV_SOURCE, None)
        else:
            os.environ[nws.ENV_SOURCE] = saved
    assert w.measured and w.temp_f == 48.0 and w.wind_mph == 14.0, w
    assert abs(w.humidity - 0.88) < 1e-9 and abs(w.precip_chance - 0.7) < 1e-9, w
    assert w.wind_dir_rel in ("in", "out", "cross")


def _table(start, temps, winds, rain=0.0):
    t0 = dt.datetime.fromisoformat(start)
    times = [(t0 + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(len(temps))]
    return {"hourly": {"time": times, "temperature_2m": temps, "wind_speed_10m": winds,
                       "precipitation_probability": [rain] * len(temps)}}


def test_the_check_switches_on_agreement_and_stops_on_a_slip():
    now = dt.datetime(2026, 11, 7, 12, 0, tzinfo=dt.timezone.utc)
    hours = CLI.sample_hours(now)
    assert hours[0] == "2026-11-07T18:00:00Z" and len(hours) == len(CLI.OFFSETS_H)
    n = 80
    om = _table("2026-11-07T12:00", [50.0 + (h % 7) for h in range(n)], [8.0 + (h % 5) for h in range(n)])
    near = _table("2026-11-07T12:00", [51.0 + (h % 7) for h in range(n)], [9.0 + (h % 5) for h in range(n)])
    places = {"PHI": (39.9, -75.17), "GB": (44.5, -88.06)}
    got = CLI.compare(places, hours, lambda a, b: near, lambda a, b: om)
    assert got["answered"] == 2 and got["pairs"] == 2 * len(hours)
    assert CLI.verdict(got).startswith("SWITCH"), CLI.verdict(got)
    # Kilometres an hour read as miles: every wind 1.6 times Open-Meteo's.
    kmh = _table("2026-11-07T12:00", [50.0 + (h % 7) for h in range(n)],
                 [(8.0 + (h % 5)) * 1.609 for h in range(n)])
    slip = CLI.verdict(CLI.compare(places, hours, lambda a, b: kmh, lambda a, b: om))
    assert slip.startswith("CHECK") and "wind" in slip, slip
    # The NWS refused the box.
    def refused(a, b):
        raise OSError("403")
    dead = CLI.verdict(CLI.compare(places, hours, refused, lambda a, b: om))
    assert dead.startswith("CHECK") and "0 of 2" in dead, dead
    lines = CLI.report(got)
    assert lines[-1].startswith("SWITCH") and any(l.startswith("  GB ") for l in lines)


def test_the_check_is_in_the_runbook_and_the_catchup_and_the_doctor_asks_the_nws():
    cmd = "cd /srv/qellys && sudo -u qellys nice -n 19 python3 wxsource.py --compare"
    assert cmd in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert cmd in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8")
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert '"Weather (National Weather Service)", "https://api.weather.gov/points/' in launch


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
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} of {len(tests)} failed.")
    sys.exit(1 if fails else 0)
