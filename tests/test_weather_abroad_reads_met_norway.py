"""A game abroad reads MET Norway's forecast (engine/sources/metno).

Ethan, 2026-11-13, on RUN_NEXT's decision 8b ("a forecast for games
abroad"): "Yes if free." The National Weather Service covers the US only, so
Munich's, London's and Mexico City's games read "weather not pulled". MET
Norway's worldwide forecast is free, keyless and allows commercial use with
a credit and a User-Agent naming the site.

Guarded here:
  * its forecast becomes the hourly table every weather reader already
    reads, in °F and mph, hourly steps and six-hourly ones alike;
  * the NWS path falls back to it only where the NWS has no forecast, and a
    test's own fetch is never sent to the real MET instead;
  * every request names the site (never a person) and sends at most four
    decimals of a place;
  * a reading from it says so, through each board, and the pages credit it;
  * the read-only check on the box reads each venue abroad.

    python3 tests/test_weather_abroad_reads_met_norway.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.cfb import wx                                     # noqa: E402
from engine.sources import metno, nws                         # noqa: E402

PAYLOAD = {"properties": {"timeseries": [
    {"time": "2026-11-15T14:00:00Z", "data": {
        "instant": {"details": {"air_temperature": 10.0, "wind_speed": 5.0, "wind_from_direction": 270.0,
                                "relative_humidity": 81.0}},
        "next_1_hours": {"details": {"probability_of_precipitation": 40.0}}}},
    {"time": "2026-11-15T15:00:00Z", "data": {
        "instant": {"details": {"air_temperature": 9.0, "wind_speed": 0.0}}}},
    {"time": "2026-11-18T18:00:00Z", "data": {
        "instant": {"details": {"air_temperature": -2.0, "wind_speed": 8.0, "wind_from_direction": 10.0}},
        "next_6_hours": {"details": {"probability_of_precipitation": 75.0}}}},
    {"time": "2026-11-18T19:00:00Z", "data": {"instant": {"details": {"wind_speed": 3.0}}}},
]}}


def test_its_forecast_is_the_table_every_reader_reads():
    t = metno.hourly_table(PAYLOAD)
    assert t["source"] == "met-norway"
    h = t["hourly"]
    assert h["time"] == ["2026-11-15T14:00", "2026-11-15T15:00", "2026-11-18T18:00"], "no temperature, no hour"
    assert h["temperature_2m"] == [50.0, 48.2, 28.4]
    assert h["wind_speed_10m"] == [11.2, 0.0, 17.9]
    assert h["wind_direction_10m"] == [270.0, None, 10.0]
    assert h["precipitation_probability"] == [40.0, 0.0, 75.0], "the hour's chance, else the six hours'"
    assert h["relative_humidity_2m"] == [81.0, None, None]
    assert {len(v) for v in h.values()} == {3}


def test_a_kickoff_reads_it_and_says_whose_it_is():
    w = wx.pick_hour(metno.hourly_table(PAYLOAD), "2026-11-15T14:30:00Z")
    assert w == {"temp_f": 50, "wind_mph": 11, "wind_dir": wx.compass(270.0), "precip_chance": 0.4,
                 "source": "met-norway"}
    us = {"hourly": {"time": ["2026-11-15T14:00"], "temperature_2m": [50.0], "wind_speed_10m": [11.0],
                     "wind_direction_10m": [270.0], "precipitation_probability": [40.0]}, "source": "nws"}
    assert "source" not in wx.pick_hour(us, "2026-11-15T14:30:00Z"), "every other reading is as it was"


def test_the_nws_path_falls_back_only_where_it_has_no_forecast():
    asked = []

    def met(url, name, ttl):
        asked.append(url)
        return PAYLOAD

    def nws_abroad(url, name, ttl):
        if "/points/" in url:
            return {"properties": {}}                    # what a 404 leaves: no forecast here
        raise AssertionError("no hourly ask without a grid")

    keep = nws.ABROAD_FETCH
    nws.ABROAD_FETCH = met
    try:
        got = nws.forecast(48.21884567, 11.62473, fetch=nws_abroad)
        assert got["source"] == "met-norway" and got["hourly"]["time"]
        assert asked == ["https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=48.2188&lon=11.6247"], \
            "four decimals at most"

        def nws_home(url, name, ttl):
            if "/points/" in url:
                return {"properties": {"forecastHourly": "https://api.weather.gov/gridpoints/OKX/1,1/forecast/hourly"}}
            return {"properties": {"periods": [{"startTime": "2026-11-15T09:00:00-05:00", "temperature": 50,
                                                 "windSpeed": "10 mph", "windDirection": "W"}]}}
        asked.clear()
        got = nws.forecast(40.8135, -74.0745, fetch=nws_home)
        assert got["source"] == "nws" and not asked, "a US place never asks MET"
    finally:
        nws.ABROAD_FETCH = keep
    # A test's own fetch with no MET stand-in: nothing goes to the real MET.
    got = nws.forecast(51.6043, -0.0664, fetch=lambda u, n, t: {"properties": {}})
    assert got == {"hourly": {}, "source": "nws"}


def test_every_request_names_the_site_never_a_person():
    import inspect
    src = inspect.getsource(metno._get)
    assert "user_agent=USER_AGENT" in src and "from .nws import USER_AGENT" in src
    assert "qellysbook.com" in nws.USER_AGENT and "@" not in nws.USER_AGENT
    assert metno.CREDIT == "Weather data from MET Norway"


def test_a_reading_from_it_reaches_each_board():
    from engine.mlb.models import MLBWeather
    from engine.models import Weather
    assert Weather().source == "" and MLBWeather().source == ""
    nfl = (ROOT / "engine" / "nflwx.py").read_text()
    assert 'source=str(got.get("source") or "")' in nfl
    for p in ("engine/pipeline.py", "engine/mlb/pipeline.py"):
        assert '**({"source": w.source} if getattr(w, "source", "") else {}),' in (ROOT / p).read_text(), p
    mlb = (ROOT / "engine" / "mlb" / "sources" / "mlbstats.py").read_text()
    assert 'source="met-norway" if (data or {}).get("source") == "met-norway" else ""' in mlb
    cfb = (ROOT / "engine" / "cfb" / "wx.py").read_text()
    assert "g[\"weather\"] = dict(w, dome=False)" in cfb, "college carries pick_hour's dict whole"


def test_the_pages_credit_it():
    app = (ROOT / "web" / "js" / "app.js").read_text()
    det = (ROOT / "web" / "js" / "detail.js").read_text()
    wxp = app[app.index("function renderWeather() {"):app.index("function renderWeather() {") + 4000]
    assert 'w.source === "met-norway" ? " · MET Norway" : ""' in wxp
    assert 'https://www.met.no/en' in wxp and "Weather data from MET Norway</a>" in wxp
    assert 'w.source === "met-norway" ? " · weather data from MET Norway" : ""' in det


def test_the_box_check_reads_each_venue_abroad():
    import datetime as dt
    when = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).replace(hour=12, minute=0, second=0,
                                                                              microsecond=0)
    stamp = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"properties": {"timeseries": [{"time": stamp, "data": {
        "instant": {"details": {"air_temperature": 12.0, "wind_speed": 4.0, "wind_from_direction": 200.0}},
        "next_1_hours": {"details": {"probability_of_precipitation": 10.0}}}}]}}
    lines = []
    n = metno.check(fetch=lambda u, name, ttl: payload if "lat=51.6043" in u else {}, out=lines.append)
    assert n == 1 and lines[-1] == f"1 of {len(metno.VENUES)} venues answered."
    assert "Weather data from MET Norway" in lines[0]
    assert any(line.startswith("  London (Tottenham Hotspur Stadium): 54°F") for line in lines)
    assert any("Munich (Allianz Arena): no reading" in line for line in lines)


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
