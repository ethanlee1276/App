"""The National Weather Service's hourly forecast, in the shape the boards read.

Ethan, 6 November 2026: "move the weather to the NWS". Open-Meteo's own pages
say its free API is for non-commercial use, and a site that sells memberships
is commercial. The NWS forecast is the US government's: public domain, free,
no key, and commercial use is allowed. The weather desk has read it since
August (`engine/kalshiweather.nws_high`), from the same box.

TWO HOPS, AS THE API IS BUILT. ``/points/{lat},{lon}`` names the forecast
grid a place falls in, and that grid's ``forecastHourly`` lists the next six
and a half days hour by hour. The grid lookup is cached for a week (a
stadium's grid does not move), the forecast for as long as its caller asks,
each under its own name (``nws_grid_*``, ``nws_hourly_*``): the weather desk's
own NWS files (``nws_pt_*``, ``nws_fc_*``) hold other endpoints' answers.

THE SHAPE THE BOARDS ALREADY READ. Every hour becomes one column entry of
Open-Meteo's hourly table, in UTC: ``time`` ("YYYY-MM-DDTHH:MM"),
``temperature_2m`` (°F), ``wind_speed_10m`` (mph), ``wind_direction_10m``
(degrees the wind blows from), ``precipitation_probability`` (%) and
``relative_humidity_2m`` (%). So `engine.cfb.wx.nearest_hour` and `pick_hour`,
the NFL's kickoff reading (`engine.nflwx`) and MLB's first-pitch reading
(`engine.mlb.sources.mlbstats.park_weather`) read it with no change at all.

US ONLY. Outside the US (a London, Munich or Rio game) the points lookup
answers 404 and the game keeps "weather not pulled": a miss is a miss, the
rule the whole weather layer runs on. Nothing is invented and nothing falls
back to another feed.

Which source the boards read is `source()`: ``QB_WEATHER_SOURCE`` (``nws`` or
``open-meteo``). The default stays Open-Meteo until the box's side-by-side
check (``python3 wxsource.py --compare``, runbook KY) reads the two at the
same kickoffs; the switch is then one setting.
"""

from __future__ import annotations

import datetime as _dt
import os
import re

#: The setting that picks the boards' forecast source.
ENV_SOURCE = "QB_WEATHER_SOURCE"
SOURCES = ("nws", "open-meteo")
DEFAULT_SOURCE = "open-meteo"

POINTS_URL = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
#: The grid a place falls in does not move; a week is generous.
GRID_TTL = 7 * 24 * 3600
#: The NWS asks every client to name itself, so a misbehaving one can be
#: told apart. The site's own name and address; never a person's.
USER_AGENT = "qellys-book/0.1 (+https://qellysbook.com)"

#: The sixteen compass points the hourly forecast names a wind by.
_POINTS16 = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
_DEGREES = {p: i * 22.5 for i, p in enumerate(_POINTS16)}
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def source() -> str:
    """The boards' forecast source: ``QB_WEATHER_SOURCE`` when it names one."""
    want = (os.environ.get(ENV_SOURCE) or "").strip().lower().replace("_", "-")
    return want if want in SOURCES else DEFAULT_SOURCE


def wind_mph(text) -> float | None:
    """'10 mph' -> 10.0; '5 to 10 mph' -> 7.5 (the middle); 'Calm' -> 0.0;
    anything else None. The hourly forecast states a speed in mph when asked
    for US units, which is its default."""
    s = str(text or "").strip().lower()
    if not s:
        return None
    if "calm" in s:
        return 0.0
    nums = [float(n) for n in _NUMBER.findall(s)]
    if not nums:
        return None
    mph = sum(nums) / len(nums)
    if "km/h" in s or "kph" in s:
        mph /= 1.609344
    elif "kt" in s or "knot" in s:
        mph *= 1.150779
    return mph


def wind_degrees(text) -> float | None:
    """'NW' -> 315.0, 'SSE' -> 157.5; blank or unknown None."""
    return _DEGREES.get(str(text or "").strip().upper())


def _value(field):
    """A quantity the API wraps as ``{"unitCode": ..., "value": n}``."""
    if isinstance(field, dict):
        return field.get("value")
    return field


def _utc_hour(stamp: str) -> str | None:
    try:
        t = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None                     # a period always carries its zone
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")


def hourly_table(payload: dict) -> dict:
    """The hourly forecast's periods as Open-Meteo's ``hourly`` table, UTC.
    Pure. A period with no time or no temperature is left out, so every
    column lines up with ``time``."""
    cols = {k: [] for k in ("time", "temperature_2m", "wind_speed_10m", "wind_direction_10m",
                            "precipitation_probability", "relative_humidity_2m")}
    for p in ((payload or {}).get("properties") or {}).get("periods") or []:
        at = _utc_hour(p.get("startTime"))
        temp = p.get("temperature")
        if at is None or temp is None:
            continue
        try:
            temp = float(temp)
        except (TypeError, ValueError):
            continue
        if str(p.get("temperatureUnit") or "F").upper() == "C":
            temp = temp * 9 / 5 + 32
        cols["time"].append(at)
        cols["temperature_2m"].append(round(temp, 1))
        cols["wind_speed_10m"].append(wind_mph(p.get("windSpeed")))
        cols["wind_direction_10m"].append(wind_degrees(p.get("windDirection")))
        pop, rh = _value(p.get("probabilityOfPrecipitation")), _value(p.get("relativeHumidity"))
        cols["precipitation_probability"].append(float(pop) if pop is not None else 0.0)
        cols["relative_humidity_2m"].append(float(rh) if rh is not None else None)
    return {"hourly": cols, "source": "nws"}


def _get(url: str, cache_name: str, ttl: int):
    from .fetch import fetch_json
    return fetch_json(url, cache_name, ttl=ttl, user_agent=USER_AGENT)


def forecast_url(lat: float, lon: float, fetch=None) -> str | None:
    """The hourly forecast's address for a place, from the points lookup;
    None outside the US or when the lookup will not answer."""
    get = fetch or _get
    try:
        pt = get(POINTS_URL.format(lat=lat, lon=lon), f"nws_grid_{lat:.4f}_{lon:.4f}.json", GRID_TTL)
    except Exception:                                     # noqa: BLE001
        return None
    url = ((pt or {}).get("properties") or {}).get("forecastHourly") or ""
    return url or None


def forecast(lat: float, lon: float, ttl: int = 3 * 3600, fetch=None) -> dict:
    """The next six and a half days at one place, hour by hour, as
    Open-Meteo's hourly table (`hourly_table`). An empty table when the NWS
    has no forecast for the place: the reader then finds no hour near
    kickoff, which is the miss every weather reader already handles."""
    get = fetch or _get
    url = forecast_url(lat, lon, fetch=get)
    if not url:
        return {"hourly": {}, "source": "nws"}
    try:
        payload = get(url, f"nws_hourly_{lat:.4f}_{lon:.4f}.json", ttl)
    except Exception:                                     # noqa: BLE001
        return {"hourly": {}, "source": "nws"}
    return hourly_table(payload)
