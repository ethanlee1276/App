"""Free live MLB data: the MLB Stats API and Open-Meteo weather.

Both APIs are free and keyless:

  * **MLB Stats API** (statsapi.mlb.com) — schedule, venues, probable
    pitchers, confirmed lineups, and per-player game logs.
  * **Open-Meteo** (api.open-meteo.com) — hourly forecast at each park's
    coordinates for temperature, wind speed/direction, humidity and
    precipitation probability.

Some managed/sandboxed environments block these hosts; calls then raise
:class:`DataUnavailable` with instructions, and cached JSON under
``data/cache/`` is used when present — the same pattern as the NFL feeds.
This module currently covers the schedule + weather layer (real games,
probable pitchers, park mapping, live conditions); lineups and per-player
game logs are the next adapter phase.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from ...sources.fetch import CACHE_DIR, USER_AGENT, DataUnavailable
from ..models import MLBGame, MLBWeather, Pitcher

STATS_BASE = "https://statsapi.mlb.com/api/v1"
METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# MLB Stats API team id -> our abbreviation.
TEAM_ID_ABBR = {
    108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN",
    114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KC", 119: "LAD",
    120: "WSH", 121: "NYM", 133: "OAK", 134: "PIT", 135: "SD", 136: "SEA",
    137: "SF", 138: "STL", 139: "TBR", 140: "TEX", 141: "TOR", 142: "MIN",
    143: "PHI", 144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL",
}

# Venue name fragment -> our park key (extend alongside parks.PARKS).
VENUE_PARK = {
    "wrigley": "wrigley", "coors": "coors", "loandepot": "loandepot",
    "yankee": "yankee", "fenway": "fenway", "oracle": "oracle",
    "petco": "petco", "great american": "gabp", "tropicana": "tropicana",
    "chase": "chase",
}

# Park coordinates for the weather lookup (starter set).
PARK_COORDS = {
    "wrigley": (41.948, -87.656), "coors": (39.756, -104.994),
    "loandepot": (25.778, -80.220), "yankee": (40.829, -73.926),
    "fenway": (42.346, -71.097), "oracle": (37.778, -122.389),
    "petco": (32.707, -117.157), "gabp": (39.097, -84.507),
    "tropicana": (27.768, -82.653), "chase": (33.445, -112.067),
}

# Park orientation = compass bearing (degrees from true north) from home plate
# toward center field. This is what turns an absolute wind bearing into a
# park-relative in/out/cross classification. Values are approximate published
# orientations — good enough for the 45°/135° buckets, refine per park as
# needed. Dome/retractable parks are included but only matter when the roof is
# open.
PARK_ORIENTATION = {
    "wrigley": 30,     # CF to the NNE
    "coors": 5,        # CF roughly north
    "loandepot": 40,   # retractable (usually closed)
    "yankee": 78,      # CF to the ENE
    "fenway": 45,      # CF to the NE
    "oracle": 88,      # CF roughly east, toward the bay
    "petco": 5,        # CF roughly north
    "gabp": 115,       # CF to the ESE, toward the river
    "tropicana": 45,   # dome
    "chase": 22,       # retractable
}


def _ang_diff(a: float, b: float) -> float:
    """Smallest absolute angle between two compass bearings (0-180)."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def relative_wind(from_deg: float, cf_bearing: float,
                  out_thresh: float = 45.0, in_thresh: float = 135.0) -> str:
    """Classify wind relative to a park.

    ``from_deg`` is the meteorological direction the wind blows *from* (as
    Open-Meteo reports it). Air therefore travels toward ``from_deg + 180``.
    When that travel bearing points toward center field the wind is blowing
    *out*; when it points back toward home plate it's blowing *in*.
    """
    blow_to = (from_deg + 180.0) % 360.0
    delta = _ang_diff(blow_to, cf_bearing)
    if delta <= out_thresh:
        return "out"
    if delta >= in_thresh:
        return "in"
    return "cross"


def _get_json(url: str, cache_name: str, ttl: int = 900, timeout: int = 30) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return json.loads(path.read_text())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        path.write_text(body)
        return json.loads(body)
    except Exception as exc:
        if path.exists():
            return json.loads(path.read_text())
        raise DataUnavailable(
            f"Could not fetch {url}: {exc}. This host may be blocked by the "
            f"environment's egress policy — run where statsapi.mlb.com / "
            f"api.open-meteo.com are reachable, or place a cached response at "
            f"{path}."
        ) from exc


def park_weather(park_key: str) -> MLBWeather:
    """Current conditions at a park via Open-Meteo. Wind direction relative to
    the park (in/out/cross) needs each park's orientation — until that's
    mapped, direction defaults to 'cross' (neutral)."""
    coords = PARK_COORDS.get(park_key)
    if not coords:
        return MLBWeather()
    lat, lon = coords
    url = (f"{METEO_BASE}?latitude={lat}&longitude={lon}"
           f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
           f"wind_direction_10m,precipitation_probability"
           f"&temperature_unit=fahrenheit&wind_speed_unit=mph")
    data = _get_json(url, f"meteo_{park_key}.json", ttl=1800)
    cur = data.get("current", {})

    # Convert the absolute wind bearing to park-relative in/out/cross when we
    # know the park's orientation; otherwise fall back to neutral "cross".
    cf_bearing = PARK_ORIENTATION.get(park_key)
    if cf_bearing is not None and "wind_direction_10m" in cur:
        wind_dir = relative_wind(float(cur["wind_direction_10m"]), cf_bearing)
    else:
        wind_dir = "cross"

    return MLBWeather(
        roof_closed=False,
        temp_f=float(cur.get("temperature_2m", 72.0)),
        wind_mph=float(cur.get("wind_speed_10m", 6.0)),
        wind_dir_rel=wind_dir,
        humidity=float(cur.get("relative_humidity_2m", 50.0)) / 100.0,
        precip_chance=float(cur.get("precipitation_probability", 0.0)) / 100.0,
    )


def build_games(date: str, with_weather: bool = True) -> list[MLBGame]:
    """Real games for a date (YYYY-MM-DD) with probable pitchers and, where
    the park is mapped, live weather."""
    url = (f"{STATS_BASE}/schedule?sportId=1&date={date}"
           f"&hydrate=probablePitcher,venue")
    data = _get_json(url, f"mlb_schedule_{date}.json", ttl=900)

    games: list[MLBGame] = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {})
            away = teams.get("away", {}).get("team", {})
            home_ab = TEAM_ID_ABBR.get(home.get("id"), home.get("abbreviation", ""))
            away_ab = TEAM_ID_ABBR.get(away.get("id"), away.get("abbreviation", ""))
            venue = (g.get("venue", {}).get("name") or "").lower()
            park = next((k for frag, k in VENUE_PARK.items() if frag in venue),
                        "generic")

            pitchers = {}
            for side, ab in (("home", home_ab), ("away", away_ab)):
                pp = teams.get(side, {}).get("probablePitcher")
                if pp:
                    pitchers[ab] = Pitcher(name=pp.get("fullName", "TBD"),
                                           throws=pp.get("pitchHand", {}).get("code", "R"))

            weather = MLBWeather()
            if with_weather and park in PARK_COORDS:
                try:
                    weather = park_weather(park)
                except DataUnavailable:
                    pass

            games.append(MLBGame(home=home_ab, away=away_ab, park=park,
                                 weather=weather, pitchers=pitchers,
                                 lineups_confirmed=False))
    return games
