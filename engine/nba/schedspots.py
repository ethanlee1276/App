"""Tonight's schedule spots for every NBA and WNBA team: context, not a price.

Ethan, 2026-10-15, from the brainstorm he asked to have built ("do every
one for every sport"): NBA schedule flags — the back-to-back, three games
in four nights, the trip, the altitude, the blowout risk. CONTEXT ONLY
UNTIL MEASURED: the minutes model already prices the rest buckets it was
fitted on (engine/nba/minutes.REST_MULT, the board's `rest` field); none
of the rest of what this says moves a number, and the page says so.

WHAT EACH TEAM GETS:
  * rest — the build's own bucket (`schedule_density`): rested, one day,
    the second night of a back-to-back, three in four, four in six;
  * the trip — miles from the arena of its last game in the past week to
    tonight's, and how many hours the clock moved;
  * altitude — tonight's arena's height, flagged when a visitor comes up
    from near sea level to Denver or Salt Lake City;
  * blowout watch — a spread of 10 or more, filled in once the game lines
    are in, because a starter's minutes in a lopsided game are the first
    thing a coach takes back.

THE ARENAS are public facts: each club's home floor, its coordinates, its
height and its time zone, as of the 2025-26 seasons. A club this table
does not know gets no trip and no altitude, never a guess.
"""

from __future__ import annotations

import datetime as _dt
import math

#: {league: {tricode: (arena, lat, lon, feet, UTC offset in standard time)}}
ARENAS = {
    "nba": {
        "ATL": ("State Farm Arena", 33.757, -84.396, 1050, -5),
        "BOS": ("TD Garden", 42.366, -71.062, 20, -5),
        "BKN": ("Barclays Center", 40.683, -73.975, 50, -5),
        "CHA": ("Spectrum Center", 35.225, -80.839, 750, -5),
        "CHI": ("United Center", 41.881, -87.674, 595, -6),
        "CLE": ("Rocket Arena", 41.497, -81.688, 650, -5),
        "DAL": ("American Airlines Center", 32.790, -96.810, 450, -6),
        "DEN": ("Ball Arena", 39.749, -105.008, 5280, -7),
        "DET": ("Little Caesars Arena", 42.341, -83.055, 600, -5),
        "GSW": ("Chase Center", 37.768, -122.388, 10, -8),
        "HOU": ("Toyota Center", 29.751, -95.362, 50, -6),
        "IND": ("Gainbridge Fieldhouse", 39.764, -86.156, 715, -5),
        "LAC": ("Intuit Dome", 33.945, -118.343, 100, -8),
        "LAL": ("Crypto.com Arena", 34.043, -118.267, 270, -8),
        "MEM": ("FedExForum", 35.138, -90.051, 260, -6),
        "MIA": ("Kaseya Center", 25.781, -80.188, 10, -5),
        "MIL": ("Fiserv Forum", 43.045, -87.917, 600, -6),
        "MIN": ("Target Center", 44.979, -93.276, 830, -6),
        "NOP": ("Smoothie King Center", 29.949, -90.082, 5, -6),
        "NYK": ("Madison Square Garden", 40.751, -73.993, 30, -5),
        "OKC": ("Paycom Center", 35.463, -97.515, 1200, -6),
        "ORL": ("Kia Center", 28.539, -81.384, 100, -5),
        "PHI": ("Wells Fargo Center", 39.901, -75.172, 20, -5),
        "PHX": ("Footprint Center", 33.446, -112.071, 1090, -7),
        "POR": ("Moda Center", 45.532, -122.667, 50, -8),
        "SAC": ("Golden 1 Center", 38.580, -121.500, 30, -8),
        "SAS": ("Frost Bank Center", 29.427, -98.438, 650, -6),
        "TOR": ("Scotiabank Arena", 43.643, -79.379, 250, -5),
        "UTA": ("Delta Center", 40.768, -111.901, 4300, -7),
        "WAS": ("Capital One Arena", 38.898, -77.021, 50, -5),
    },
    "wnba": {
        "ATL": ("Gateway Center Arena", 33.657, -84.452, 1000, -5),
        "CHI": ("Wintrust Arena", 41.854, -87.621, 595, -6),
        "CON": ("Mohegan Sun Arena", 41.491, -72.089, 100, -5),
        "DAL": ("College Park Center", 32.731, -97.109, 600, -6),
        "GSV": ("Chase Center", 37.768, -122.388, 10, -8),
        "IND": ("Gainbridge Fieldhouse", 39.764, -86.156, 715, -5),
        "LVA": ("Michelob Ultra Arena", 36.090, -115.176, 2000, -8),
        "LAS": ("Crypto.com Arena", 34.043, -118.267, 270, -8),
        "MIN": ("Target Center", 44.979, -93.276, 830, -6),
        "NYL": ("Barclays Center", 40.683, -73.975, 50, -5),
        "PHX": ("Footprint Center", 33.446, -112.071, 1090, -7),
        "POR": ("Moda Center", 45.532, -122.667, 50, -8),
        "SEA": ("Climate Pledge Arena", 47.622, -122.354, 150, -8),
        "TOR": ("Coca-Cola Coliseum", 43.636, -79.414, 250, -5),
        "WAS": ("CareFirst Arena", 38.843, -76.988, 50, -5),
    },
}

#: A visitor's arena below this, playing at one above HIGH_FT, is flagged.
LOW_FT, HIGH_FT = 1500, 4000
#: Trips at least this long are named; a time-zone move of any size is.
LONG_TRIP_MI = 1000
#: A spread this wide is a blowout watch.
BLOWOUT_SPREAD = 10.0

REST_WORDS = {"2plus": "Rested (2+ days)", "1day": "One day off",
              "b2b_home": "Second night of a back-to-back", "3in4": "Third game in four nights",
              "4in6_road": "Fourth game in six nights"}


def miles(a: tuple, b: tuple) -> float:
    """Great-circle miles between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def last_venue(sched_days: dict, team: str, date: str):
    """(days ago, the home club of the team's latest game in the window), or None."""
    try:
        d0 = _dt.date.fromisoformat(date)
    except ValueError:
        return None
    for off in range(1, 8):
        day = (d0 - _dt.timedelta(days=off)).isoformat()
        for g in sched_days.get(day) or []:
            if team in (g.get("home"), g.get("away")):
                return off, g.get("home")
    return None


def team_spot(league: str, team: str, home: str, density: dict, sched_days: dict, date: str) -> dict:
    arenas = ARENAS.get(league, {})
    out = {"team": team, "rest": density.get("rest", ""), "rest_word": REST_WORDS.get(density.get("rest", ""), ""),
           "games_in_4": density.get("games_in_4"), "games_in_6": density.get("games_in_6"), "flags": []}
    if out["rest"] in ("b2b_home", "3in4", "4in6_road"):
        out["flags"].append(out["rest"])
    tonight = arenas.get(home)
    last = last_venue(sched_days, team, date)
    if tonight and last and arenas.get(last[1]):
        was = arenas[last[1]]
        out["from"] = last[1]
        out["days_since"] = last[0]
        out["miles"] = round(miles(was[1:3], tonight[1:3]))
        out["tz_shift"] = tonight[4] - was[4]
        if out["miles"] >= LONG_TRIP_MI:
            out["flags"].append("long_trip")
        if out["tz_shift"]:
            out["flags"].append("clock")
    if tonight and team != home:
        mine = arenas.get(team)
        if tonight[3] >= HIGH_FT and mine and mine[3] < LOW_FT:
            out["flags"].append("altitude")
    return out


def spots(games: list, sched_days: dict, date: str, league: str, density: dict) -> list:
    """[{home, away, arena, feet, spread, teams: {home: spot, away: spot}}]
    for tonight's games. ``density`` is the build's own `schedule_density`
    per team, so the rest bucket here is the one the minutes model read."""
    arenas = ARENAS.get(league, {})
    out = []
    for g in games or []:
        h, a = g.get("home"), g.get("away")
        if not h or not a:
            continue
        teams = {}
        for side, t in (("home", h), ("away", a)):
            teams[side] = team_spot(league, t, h, (density or {}).get(t) or {}, sched_days or {}, date)
        venue = arenas.get(h)
        out.append({"home": h, "away": a, "arena": venue[0] if venue else "", "feet": venue[3] if venue else None,
                    "spread": None, "teams": teams})
    return out


def add_spreads(rows: list, spread_by_team: dict) -> list:
    """Fill each game's spread (the home side's) and the blowout watch."""
    for r in rows or []:
        s = spread_by_team.get(r["home"])
        if s is None:
            continue
        r["spread"] = s[0]
        if abs(s[0]) >= BLOWOUT_SPREAD:
            for side in ("home", "away"):
                if "blowout" not in r["teams"][side]["flags"]:
                    r["teams"][side]["flags"].append("blowout")
    return rows
