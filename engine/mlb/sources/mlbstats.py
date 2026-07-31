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
    "rate field": "rate", "guaranteed rate": "rate",
    "progressive": "progressive", "comerica": "comerica",
    "kauffman": "kauffman", "target field": "target",
    "daikin": "daikin", "minute maid": "daikin",
    "angel stadium": "angel", "sutter": "sutter",
    "t-mobile": "tmobile", "globe life": "globelife",
    "rogers centre": "rogers", "truist": "truist",
    "citi field": "citi", "citizens bank": "cbp",
    "nationals park": "nationals", "american family": "amfam",
    "busch": "busch", "pnc": "pnc", "dodger": "dodger",
    "camden": "camden", "oriole park": "camden",
}

# Park coordinates for the weather lookup (starter set).
PARK_COORDS = {
    "wrigley": (41.948, -87.656), "coors": (39.756, -104.994),
    "loandepot": (25.778, -80.220), "yankee": (40.829, -73.926),
    "fenway": (42.346, -71.097), "oracle": (37.778, -122.389),
    "petco": (32.707, -117.157), "gabp": (39.097, -84.507),
    "tropicana": (27.768, -82.653), "chase": (33.445, -112.067),
    "rate": (41.830, -87.634), "progressive": (41.496, -81.685),
    "comerica": (42.339, -83.049), "kauffman": (39.051, -94.480),
    "target": (44.982, -93.278), "daikin": (29.757, -95.356),
    "angel": (33.800, -117.883), "sutter": (38.580, -121.513),
    "tmobile": (47.591, -122.332), "globelife": (32.747, -97.084),
    "rogers": (43.641, -79.389), "truist": (33.891, -84.468),
    "citi": (40.757, -73.846), "cbp": (39.906, -75.166),
    "nationals": (38.873, -77.007), "amfam": (43.028, -87.971),
    "busch": (38.623, -90.193), "pnc": (40.447, -80.006),
    "dodger": (34.074, -118.240), "camden": (39.284, -76.622),
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
    "rate": 127,       # CF to the SE
    "progressive": 20,
    "comerica": 150,
    "kauffman": 45,
    "target": 90,
    "daikin": 345,     # retractable (usually closed in summer)
    "angel": 65,
    "sutter": 60,
    "tmobile": 45,     # retractable
    "globelife": 5,    # retractable (usually closed in summer)
    "rogers": 0,       # retractable
    "truist": 45,
    "citi": 30,
    "cbp": 10,
    "nationals": 30,
    "amfam": 120,      # retractable
    "busch": 60,
    "pnc": 115,
    "dodger": 25,
    "camden": 30,
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


def _read_cached_json(path):
    """Parse a cache file, or None if it is missing/empty/corrupt.

    A truncated or empty cache file (interrupted write, a 200 with an empty
    body, a full disk) used to raise a raw JSONDecodeError straight out of
    this module — past every caller that only guards DataUnavailable, which
    is how one bad file killed the whole nightly auto-settle with
    "Expecting value: line 1 column 1". An unreadable cache is a MISS, not
    a fatal error."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _get_json(url: str, cache_name: str, ttl: int = 900, timeout: int = 30) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        fresh = _read_cached_json(path)
        if fresh is not None:
            return fresh                     # …otherwise fall through and refetch
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)              # parse BEFORE caching
        path.write_text(body)                # never cache an unparseable body
        return data
    except Exception as exc:
        stale = _read_cached_json(path) if path.exists() else None
        if stale is not None:
            return stale
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


def parse_results(schedule_json: dict) -> list[dict]:
    """Final scores from a schedule payload — pure, so it unit-tests offline.

    Only completed games are returned; anything still scheduled/in-progress (or
    missing a score) is skipped, so the history DB never learns from a partial
    game. Each row is ``{date, home, away, home_score, away_score, venue}``.
    """
    out: list[dict] = []
    for day in schedule_json.get("dates", []):
        for g in day.get("games", []):
            status = g.get("status", {}) or {}
            if status.get("abstractGameState") != "Final":
                continue
            # Suspended/cancelled games can be "Final" with no real result.
            if (status.get("codedGameState") or "") in {"C", "D", "T"}:
                continue
            teams = g.get("teams", {}) or {}
            home_t, away_t = teams.get("home", {}) or {}, teams.get("away", {}) or {}
            home = TEAM_ID_ABBR.get((home_t.get("team") or {}).get("id"),
                                    (home_t.get("team") or {}).get("abbreviation", ""))
            away = TEAM_ID_ABBR.get((away_t.get("team") or {}).get("id"),
                                    (away_t.get("team") or {}).get("abbreviation", ""))
            hs, as_ = home_t.get("score"), away_t.get("score")
            if not home or not away or hs is None or as_ is None:
                continue
            out.append({
                "date": (g.get("officialDate") or g.get("gameDate", ""))[:10],
                "home": home, "away": away,
                "home_score": float(hs), "away_score": float(as_),
                "venue": (g.get("venue", {}) or {}).get("name", ""),
                # Doubleheader leg — without it both legs share one game_id
                # in the history DB and the second's score ERASES the first.
                "game_number": int(g.get("gameNumber") or 1),
            })
    return out


# Games that will never produce a score: cancelled, postponed, or suspended
# with no result. The schedule keeps listing them, but waiting on them is
# waiting forever.
DEAD_GAME_STATES = {"C", "D", "T"}


def _game_is_resolved(g: dict) -> bool:
    """Has this game reached a state it will never leave?

    Final counts, and so does postponed/cancelled — a postponed game is not
    pending, it is not happening on this date at all. Anything else
    (scheduled, warmup, in progress) can still change.
    """
    status = g.get("status", {}) or {}
    return (status.get("abstractGameState") == "Final"
            or (status.get("codedGameState") or "") in DEAD_GAME_STATES)


def schedule_is_settled(schedule_json: dict) -> bool:
    """True when every game in the payload has reached a final state."""
    return all(_game_is_resolved(g)
               for day in schedule_json.get("dates", [])
               for g in day.get("games", []))


def parse_abandoned(schedule_json: dict) -> list[dict]:
    """Games the schedule says were postponed, cancelled or suspended.

    These are the ones that never get a score. Left sitting in the history
    DB as a scoreless row they look identical to a game still in progress,
    which is what the settle guard checks — so every bet on either team
    that day stays open forever, waiting on a game that will never be
    played. Callers use this to tell the two apart."""
    out: list[dict] = []
    for day in schedule_json.get("dates", []):
        for g in day.get("games", []):
            status = g.get("status", {}) or {}
            if (status.get("codedGameState") or "") not in DEAD_GAME_STATES:
                continue
            teams = g.get("teams", {}) or {}
            home_t, away_t = teams.get("home", {}) or {}, teams.get("away", {}) or {}
            home = TEAM_ID_ABBR.get((home_t.get("team") or {}).get("id"),
                                    (home_t.get("team") or {}).get("abbreviation", ""))
            away = TEAM_ID_ABBR.get((away_t.get("team") or {}).get("id"),
                                    (away_t.get("team") or {}).get("abbreviation", ""))
            if not home or not away:
                continue
            out.append({
                "date": (g.get("officialDate") or g.get("gameDate", ""))[:10],
                "home": home, "away": away,
                "game_number": int(g.get("gameNumber") or 1),
                "state": status.get("detailedState") or "Postponed",
            })
    return out


def fetch_schedule(start: str, end: str) -> dict:
    """Raw schedule payload for a date range (inclusive), one request.

    Cached for a day, because a date whose games have all finished is
    immutable — but NEVER cached when something was still in progress at
    capture time. That snapshot is provisional: replaying it for the next
    24 hours is how a settle pass run at 4 AM kept reporting the same
    "8/10 games final" it saw at 11 PM, and graded nothing.
    """
    url = (f"{STATS_BASE}/schedule?sportId=1"
           f"&startDate={start}&endDate={end}")
    cache = f"mlb_results_{start}_{end}.json"
    data = _get_json(url, cache, ttl=86400)
    if not schedule_is_settled(data):
        # Whatever we just used — cache hit or fresh fetch — is provisional.
        # Drop it and go back to the wire once, so a caller asking after the
        # last out gets the last out.
        path = CACHE_DIR / cache
        try:
            path.unlink()
        except OSError:
            pass
        data = _get_json(url, cache, ttl=0)
        # Still unsettled means the games really are in progress. Don't let
        # that snapshot linger either.
        if not schedule_is_settled(data):
            try:
                path.unlink()
            except OSError:
                pass
    return data


def fetch_results(start: str, end: str) -> list[dict]:
    """Final scores for every completed game between two dates (inclusive).

    One request covers the whole range, so ingesting a full season is a handful
    of calls rather than one per day."""
    return parse_results(fetch_schedule(start, end))


def fetch_abandoned(start: str, end: str) -> list[dict]:
    """Postponed/cancelled games in a date range — see parse_abandoned."""
    return parse_abandoned(fetch_schedule(start, end))


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


# --- transactions (the IL wire) ---------------------------------------------
def parse_transactions(data: dict) -> list[dict]:
    """Normalize the Stats API transactions payload. Pure, fixture-tested."""
    out = []
    for t in (data or {}).get("transactions", []) or []:
        person = ((t.get("person") or {}).get("fullName")) or ""
        if not person:
            continue
        team_id = ((t.get("toTeam") or {}).get("id")) \
            or ((t.get("fromTeam") or {}).get("id")) or 0
        out.append({
            "date": t.get("date") or t.get("effectiveDate") or "",
            "player": person,
            "team": TEAM_ID_ABBR.get(team_id, ""),
            "type": t.get("typeDesc") or t.get("typeCode") or "",
            "desc": t.get("description") or "",
        })
    return out


def fetch_transactions(start: str, end: str, ttl: int = 21600) -> list[dict]:
    """Roster transactions over a date range — one free request covers all
    30 teams' IL placements/activations, trades, recalls and options."""
    url = f"{STATS_BASE}/transactions?startDate={start}&endDate={end}"
    return parse_transactions(
        _get_json(url, f"mlb_tx_{start}_{end}.json", ttl=ttl))


# --- official batting splits (vs LHP / vs RHP) ------------------------------
def parse_batting_splits(payload: dict) -> dict[int, dict]:
    """``{person_id: {"vl": {"pa", "slg", "hr"}, "vr": {...}}}`` — pure."""
    out: dict[int, dict] = {}
    for p in (payload or {}).get("people", []) or []:
        pid = p.get("id")
        if not pid:
            continue
        for st in p.get("stats", []) or []:
            for sp in st.get("splits", []) or []:
                code = ((sp.get("split") or {}).get("code") or "").lower()
                if code not in ("vl", "vr"):
                    continue
                s = sp.get("stat", {}) or {}

                def _num(key):
                    try:
                        return float(s.get(key) or 0)
                    except (TypeError, ValueError):
                        return 0.0
                out.setdefault(int(pid), {})[code] = {
                    "pa": int(_num("plateAppearances")),
                    "slg": _num("slg"),
                    "hr": int(_num("homeRuns")),
                }
    return out


def fetch_batting_splits(person_ids, season: int, ttl: int = 86400,
                         chunk: int = 40) -> dict[int, dict]:
    """Official season splits for many hitters in a few batched requests —
    the ``people`` endpoint hydrates stats for up to dozens of ids per
    call, so a full slate costs a handful of cached-daily fetches."""
    ids = sorted({int(i) for i in person_ids if i})
    out: dict[int, dict] = {}
    for i in range(0, len(ids), chunk):
        part = ids[i:i + chunk]
        idstr = ",".join(str(x) for x in part)
        url = (f"{STATS_BASE}/people?personIds={idstr}"
               f"&hydrate=stats(group=[hitting],type=[statSplits],"
               f"sitCodes=[vl,vr],season={season})")
        cache = f"mlb_splits_{season}_{part[0]}_{part[-1]}_{len(part)}.json"
        try:
            out.update(parse_batting_splits(_get_json(url, cache, ttl=ttl)))
        except DataUnavailable:
            continue          # a missing chunk degrades, never blocks
    return out
