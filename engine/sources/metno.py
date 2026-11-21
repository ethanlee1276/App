"""MET Norway's forecast, for the games the National Weather Service cannot answer.

Ethan, 2026-11-13, on RUN_NEXT's decision 8b ("a forecast for games abroad"):
"Yes if free." The NWS covers the US only, so a game in London, Munich,
Madrid, Mexico City or São Paulo read "weather not pulled" and its props
went without the weather. Norway's weather service publishes a worldwide
forecast (Locationforecast 2.0) that is free, needs no key, and allows
commercial use on two conditions, both kept here:

  * CREDIT. Its data is licensed under CC BY 4.0 and NLOD 2.0, so the site
    says "Weather data from MET Norway" wherever a reading from it shows
    (`CREDIT`; the weather page and the game page read ``source``).
  * NAME YOURSELF. Every request carries a User-Agent naming the site and its
    address (`nws.USER_AGENT`, the site's own and never a person's); a client
    that sends none is refused. Coordinates go to four decimals at most, and
    a forecast is kept for its caller's lifetime (an hour or more), well
    inside MET's request limits.

THE SHAPE THE BOARDS ALREADY READ, as `engine.sources.nws`: each hour one
entry of Open-Meteo's hourly table in UTC — ``time``, ``temperature_2m``
(°F), ``wind_speed_10m`` (mph), ``wind_direction_10m`` (degrees the wind
blows from), ``precipitation_probability`` (%) and ``relative_humidity_2m``
(%) — so `engine.cfb.wx.pick_hour`, the NFL's kickoff reading and MLB's
first pitch read it unchanged. MET gives hourly steps for about the first
two and a half days and six-hourly after; a kickoff more than two hours
from any step is a miss, the rule every weather reader runs on.

THE RAIN CHANCE. The "complete" product carries
``probability_of_precipitation`` on its hourly and six-hourly periods; a
step without one (MET leaves it off some hours) reads 0, as an NWS hour
with no chance does.

`engine.sources.nws.forecast` calls this only when the NWS has no forecast
for a place, and the table it returns says ``"source": "met-norway"``.
"""
from __future__ import annotations

import datetime as _dt

URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat:.4f}&lon={lon:.4f}"
SOURCE = "met-norway"
#: What the site prints beside a reading from this feed (its licence's
#: attribution), and where it links.
CREDIT = "Weather data from MET Norway"
CREDIT_URL = "https://www.met.no/en"
#: Metres a second to miles an hour.
MPH = 2.2369363


def _utc_hour(stamp: str) -> str | None:
    try:
        t = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")


def hourly_table(payload: dict) -> dict:
    """Locationforecast's timeseries as Open-Meteo's ``hourly`` table, UTC.
    Pure. A step with no time or no temperature is left out, so every column
    lines up with ``time``."""
    cols = {k: [] for k in ("time", "temperature_2m", "wind_speed_10m", "wind_direction_10m",
                            "precipitation_probability", "relative_humidity_2m")}
    for step in ((payload or {}).get("properties") or {}).get("timeseries") or []:
        at = _utc_hour(step.get("time"))
        data = step.get("data") or {}
        now = ((data.get("instant") or {}).get("details")) or {}
        temp_c = now.get("air_temperature")
        if at is None or temp_c is None:
            continue
        try:
            temp_f = float(temp_c) * 9 / 5 + 32
        except (TypeError, ValueError):
            continue
        wind = now.get("wind_speed")
        nxt = (data.get("next_1_hours") or data.get("next_6_hours") or {}).get("details") or {}
        pop = nxt.get("probability_of_precipitation")
        rh = now.get("relative_humidity")
        cols["time"].append(at)
        cols["temperature_2m"].append(round(temp_f, 1))
        cols["wind_speed_10m"].append(round(float(wind) * MPH, 1) if wind is not None else None)
        cols["wind_direction_10m"].append(float(now["wind_from_direction"])
                                          if now.get("wind_from_direction") is not None else None)
        cols["precipitation_probability"].append(float(pop) if pop is not None else 0.0)
        cols["relative_humidity_2m"].append(float(rh) if rh is not None else None)
    return {"hourly": cols, "source": SOURCE}


def _get(url: str, cache_name: str, ttl: int):
    from .fetch import fetch_json
    from .nws import USER_AGENT
    return fetch_json(url, cache_name, ttl=ttl, user_agent=USER_AGENT)


def forecast(lat: float, lon: float, ttl: int = 3 * 3600, fetch=None) -> dict:
    """The next nine days at one place as Open-Meteo's hourly table
    (`hourly_table`), from MET Norway. An empty table when it will not
    answer: the reader then finds no hour near kickoff, the miss every
    weather reader already handles."""
    get = fetch or _get
    lat, lon = round(float(lat), 4), round(float(lon), 4)
    try:
        payload = get(URL.format(lat=lat, lon=lon), f"metno_{lat:.4f}_{lon:.4f}.json", ttl)
    except Exception:                                     # noqa: BLE001
        return {"hourly": {}, "source": SOURCE}
    return hourly_table(payload)


#: The venues abroad the boards have played at or may (the NFL's
#: international games, MLB's Toronto and its overseas series, college
#: football's openers in Ireland): the read-only check reads each.
VENUES = {
    "London (Tottenham Hotspur Stadium)": (51.6043, -0.0664),
    "London (Wembley Stadium)": (51.5560, -0.2795),
    "Munich (Allianz Arena)": (48.2188, 11.6247),
    "Frankfurt (Deutsche Bank Park)": (50.0686, 8.6455),
    "Berlin (Olympiastadion)": (52.5147, 13.2395),
    "Madrid (Santiago Bernabéu)": (40.4531, -3.6883),
    "Dublin (Aviva Stadium)": (53.3352, -6.2285),
    "Mexico City (Estadio Banorte)": (19.3029, -99.1505),
    "São Paulo (Neo Química Arena)": (-23.5453, -46.4742),
    "Toronto (Rogers Centre)": (43.6414, -79.3894),
}


def check(fetch=None, out=print) -> int:
    """READ-ONLY: what MET Norway answers for each venue abroad — the next
    reading it has, at noon UTC tomorrow. Nothing is written but the
    forecast cache. Returns how many answered."""
    when = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0)
    at = when.strftime("%Y-%m-%dT%H:%M")
    answered = 0
    out(f"MET Norway's forecast for each venue abroad, {at} UTC ({CREDIT}):")
    for name, (lat, lon) in VENUES.items():
        table = forecast(lat, lon, ttl=3600, fetch=fetch).get("hourly") or {}
        times = table.get("time") or []
        if at not in times:
            out(f"  {name}: no reading" + (f" (it answered {len(times)} hours, none at {at})" if times else ""))
            continue
        i = times.index(at)
        answered += 1
        col = {k: (table.get(k) or [None] * len(times))[i] for k in table}
        wind = col.get("wind_speed_10m")
        out(f"  {name}: {col['temperature_2m']:.0f}°F, wind {wind if wind is not None else '?'} mph"
            f" from {col.get('wind_direction_10m') if col.get('wind_direction_10m') is not None else '?'}°,"
            f" {col.get('precipitation_probability') or 0:.0f}% chance of rain"
            f" ({len(times)} hours ahead read)")
    out(f"{answered} of {len(VENUES)} venues answered.")
    return answered


if __name__ == "__main__":
    import sys
    sys.exit(0 if check() else 1)
