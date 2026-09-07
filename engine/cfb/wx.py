"""Kickoff weather for the college slate.

Ethan, 2026-08-24: "can you now work on the cfb weather next."

The pieces existed on three shelves and nobody had joined them. ESPN's
scoreboard already names each game's VENUE and says whether it is indoor
(engine/sources/cfbdata stores both, plus a `weather_checked: False`
stamped per §2, waiting). CollegeFootballData's /venues endpoint carries
latitude and longitude for every college stadium — the one thing the
front end's old excuse ("no weather feed covers college venues") was
actually about, unlocked by the CFBD key the talent prior already needs.
And Open-Meteo answers hourly forecasts keylessly, the same service the
MLB board has read per-park all season.

JOINED ON THE VENUE, NOT THE HOME TEAM, deliberately: a neutral-site
game — a kickoff classic in Atlanta, a bowl — is played where it is
played, and the home school's stadium can be a thousand miles from the
weather that matters. ESPN names the actual venue per game; CFBD knows
where that venue is.

FORECAST AT THE KICKOFF HOUR, not "current". A Saturday slate is built
days ahead, and current conditions on Wednesday say nothing about
Saturday night. Open-Meteo's hourly forecast covers 16 days; the hour
nearest kickoff is the reading.

A MISS IS A MISS. A venue CFBD does not list, a forecast that will not
answer, a kickoff too far out — the game simply keeps
`weather_checked: False` and the card keeps saying "weather not
pulled". Nothing is invented; §2 stays intact.

Pure joins, tested offline; the two fetchers cache and degrade like
every other source here.
"""

from __future__ import annotations

import datetime as _dt

VENUES_TTL = 30 * 24 * 3600      # stadiums do not move
FORECAST_TTL = 3 * 3600

#: Eight-way compass from a bearing, for the card's "12mph NW".
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass(bearing: float | None) -> str:
    if bearing is None:
        return ""
    return _COMPASS[int(((float(bearing) % 360) + 22.5) // 45) % 8]


def fetch_venues() -> list:
    """Every college venue CFBD knows, with coordinates. Needs the key."""
    from ..sources import cfbd
    return cfbd._get("/venues", {}, "cfbd_venues.json", ttl=VENUES_TTL)


def venue_index(rows: list) -> dict:
    """{normalized venue name: {lat, lon, dome}}.

    Normalized with cfbdata.name_key — the same treatment ESPN's names
    get — so "Sanford Stadium" joins "Sanford Stadium" whatever the two
    feeds did about punctuation and case.
    """
    from ..sources.cfbdata import name_key
    out: dict = {}
    for v in rows or []:
        name = (v.get("name") or "").strip()
        lat, lon = v.get("latitude"), v.get("longitude")
        if not name or lat is None or lon is None:
            continue
        out[name_key(name)] = {"lat": float(lat), "lon": float(lon),
                               "dome": bool(v.get("dome"))}
    return out


def fetch_forecast(lat: float, lon: float, date: str) -> dict:
    """Open-Meteo's hourly board for one place and day. Keyless."""
    from ..sources.fetch import fetch_json
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat:.4f}&longitude={lon:.4f}"
           "&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,"
           "precipitation_probability"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph"
           f"&timezone=UTC&start_date={date}&end_date={date}")
    return fetch_json(url, f"cfb_wx_{lat:.2f}_{lon:.2f}_{date}.json",
                      ttl=FORECAST_TTL)


def pick_hour(payload: dict, kickoff_iso: str) -> dict | None:
    """The hourly reading nearest kickoff — pure.

    Kickoff is ESPN's UTC ISO string; the payload is requested in UTC,
    so the join is string arithmetic on hours, no timezone re-derivation
    to get wrong twice.
    """
    hourly = (payload or {}).get("hourly") or {}
    times = hourly.get("time") or []
    if not times or len(kickoff_iso) < 13:
        return None
    try:
        ko = _dt.datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    ko = ko.replace(tzinfo=None)
    best, gap = None, None
    for i, t in enumerate(times):
        try:
            at = _dt.datetime.fromisoformat(t)
        except ValueError:
            continue
        d = abs((at - ko).total_seconds())
        if gap is None or d < gap:
            best, gap = i, d
    if best is None or gap is None or gap > 2 * 3600:
        return None                    # nothing within two hours is a miss
    def col(key):
        vals = hourly.get(key) or []
        return vals[best] if best < len(vals) else None
    t = col("temperature_2m")
    w = col("wind_speed_10m")
    if t is None or w is None:
        return None
    return {
        "temp_f": round(float(t)),
        "wind_mph": round(float(w)),
        "wind_dir": compass(col("wind_direction_10m")),
        "precip_chance": round(float(col("precipitation_probability") or 0)
                               / 100.0, 2),
    }


def attach(games: list, vidx: dict, forecast=None) -> int:
    """Stamp `weather` and flip `weather_checked` on every game we can
    honestly answer for. Returns how many were stamped.

    `forecast(lat, lon, date, kickoff)` is injectable so the join tests
    offline; the default wires fetch_forecast + pick_hour.
    """
    from ..sources.cfbdata import name_key

    def _default(lat, lon, date, kickoff):
        return pick_hour(fetch_forecast(lat, lon, date), kickoff)

    fc = forecast or _default
    stamped = 0
    for g in games:
        if g.get("indoor"):
            # ESPN says the roof exists; that IS the weather report.
            g["weather"] = {"dome": True}
            g["weather_checked"] = True
            stamped += 1
            continue
        venue = vidx.get(name_key(g.get("venue") or ""))
        if not venue:
            continue                   # unknown venue: stays unpulled
        if venue.get("dome"):
            g["weather"] = {"dome": True}
            g["weather_checked"] = True
            stamped += 1
            continue
        kick = g.get("kickoff") or ""
        date = kick[:10]
        if not date:
            continue
        try:
            w = fc(venue["lat"], venue["lon"], date, kick)
        except Exception:                                 # noqa: BLE001
            w = None                   # a refused forecast is a miss
        if not w:
            continue
        g["weather"] = dict(w, dome=False)
        g["weather_checked"] = True
        stamped += 1
    return stamped
