"""Hometown games: an NFL player's road game in the town he comes from.

Ethan, 2026-10-11: "one signal that I want to add for our NFL bets is
hometown returns ... when they come back to their hometown and play a game
in their hometown, I feel like that matters."

WHAT COUNTS, written before anything was measured (the repo's rule: never
choose a setting because a backtest liked it):

  * HOMETOWN = where he was born — the one hometown field the free sources
    publish (ESPN's roster `birthPlace`, Sleeper's `birth_city` /
    `birth_state`). A player born in one city and raised in another is
    read by his birthplace; that limit is the data's, and it is stated.
  * A HOMETOWN GAME = a ROAD game (his team is not the home team, and the
    game is not at a neutral site) whose stadium is within HOMETOWN_MILES
    of that birthplace. A player whose own team plays in his hometown is
    not "coming back" — he plays half his games there — so his home games
    are never flagged.
  * 50 miles covers a metro area: a Compton-born receiver at SoFi, a
    Baltimore kid at the Commanders' stadium, a Paterson native at MetLife.

WHAT IT DOES TO A PICK: nothing until history proves it. It raises two of
the scout's flags (engine/scout.py: ``hometown_over``, ``hometown_under``),
shown on the card; the five-season replay (engine/scouthist) scores each
against the same side in other games, and the bar there — fixed before any
run — decides. If hometown players really do rise to the occasion, the
UNDERS on them will have hit less often and get lowered toward their price;
if the occasion gets to them, the OVERS will. Never raised above the model.

WHERE THE MAP COMES FROM: the US Census Bureau's place gazetteer (public
domain; every incorporated place and CDP with its centre point), downloaded
once to the cache. Birthplaces abroad are not placed.

    sudo -u qellys python3 -m engine.hometown            # build and save the table
    sudo -u qellys python3 -m engine.hometown --dry-run  # build and report only

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import re
import sys
import zipfile
from pathlib import Path

#: The radius, fixed 2026-10-11 before any measurement.
HOMETOWN_MILES = 50.0
GAZETTEER_URL = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
                 "2023_Gazetteer/2023_Gaz_place_national.zip")
GAZ_CACHE = "census_gaz_places_2023.zip"
ESPN_ROOT = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
ROSTER_TTL = 24 * 3600
STORE = "nfl_hometowns.json"
#: The table is rebuilt by the weekly replay when it is older than this.
STALE_S = 6 * 86400

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR", "washington dc": "DC", "washington d.c.": "DC",
}
CODES = frozenset(STATES.values())
US = frozenset({"usa", "us", "u.s.", "u.s.a.", "united states", "united states of america", ""})


# --- names -------------------------------------------------------------------------
def norm_name(name) -> str:
    """"D.K. Metcalf", "DK Metcalf" and "dk metcalf" are one player; a
    suffix is dropped ("Marvin Harrison Jr." is "marvin harrison")."""
    s = re.sub(r"[.'’`]", "", str(name or "").lower())
    s = re.sub(r"[^a-z0-9 -]", " ", s)
    words = [w for w in s.replace("-", " ").split() if w not in ("jr", "sr", "ii", "iii", "iv", "v")]
    return " ".join(words)


def norm_city(city) -> str:
    """"St. Louis" and "Saint Louis" are one place; so are "Ft. Worth" and
    "Fort Worth"."""
    s = str(city or "").lower().strip()
    s = re.sub(r"^(st\.?|ste\.?)\s+", "saint ", s)
    s = re.sub(r"^ft\.?\s+", "fort ", s)
    s = re.sub(r"^mt\.?\s+", "mount ", s)
    s = re.sub(r"[.'’`]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


def state_code(state) -> str:
    s = str(state or "").strip()
    if s.upper() in CODES:
        return s.upper()
    return STATES.get(s.lower().replace(".", "").strip(), "") or STATES.get(s.lower().strip(), "")


# --- the map -------------------------------------------------------------------------
_SUFFIX = frozenset({"city", "town", "village", "borough", "cdp", "municipality", "government",
                     "metropolitan", "metro", "unified", "consolidated", "urban", "county", "and"})


def place_names(raw: str) -> tuple[str, list]:
    """(the place's own name, the extra names a consolidated government is
    also known by) — "Nashville-Davidson metropolitan government (balance)"
    is "nashville-davidson", also "nashville"."""
    consolidated = bool(re.search(r"\(balance\)|government|urban county", raw, re.I))
    words = re.sub(r"\(balance\)", "", raw, flags=re.I).split()
    while words and words[-1].lower() in _SUFFIX:
        words.pop()
    base = " ".join(words)
    extra = []
    if consolidated:
        extra = [p for p in re.split(r"[-/]", base) if p.strip()]
    if base.lower().startswith("urban "):
        extra.append(base[6:])
    return norm_city(base), [norm_city(p) for p in extra if norm_city(p)]


def parse_gazetteer(text: str) -> dict:
    """{(city, ST): (lat, lon)} from the Census place gazetteer (tab-separated,
    read by header name). Incorporated places come before CDPs, and a place's
    own name always beats another's alias."""
    lines = text.splitlines()
    if not lines:
        return {}
    head = [h.strip().upper() for h in lines[0].split("\t")]
    try:
        i_st, i_name = head.index("USPS"), head.index("NAME")
        i_lat, i_lon = head.index("INTPTLAT"), head.index("INTPTLONG")
    except ValueError:
        return {}
    rows = []
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) <= max(i_st, i_name, i_lat, i_lon):
            continue
        try:
            lat, lon = float(f[i_lat]), float(f[i_lon])
        except ValueError:
            continue
        rows.append((f[i_name].strip().endswith(" CDP"), f[i_st].strip().upper(), f[i_name].strip(), lat, lon))
    rows.sort(key=lambda r: r[0])                  # incorporated places first
    out, aliases = {}, []
    for _cdp, st, raw, lat, lon in rows:
        own, extra = place_names(raw)
        if own:
            out.setdefault((own, st), (lat, lon))
        aliases += [((a, st), (lat, lon)) for a in extra]
    for k, v in aliases:
        out.setdefault(k, v)
    return out


def load_gazetteer(fetch=None) -> dict:
    """The map, from the cached download (fetched once). {} when it cannot be
    had — the table is then built without coordinates and flags nothing."""
    from .sources.fetch import CACHE_DIR
    path = Path(CACHE_DIR) / GAZ_CACHE
    if not path.exists():
        try:
            raw = (fetch or _download)(GAZETTEER_URL)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(raw)
            tmp.replace(path)
        except Exception:                                     # noqa: BLE001
            return {}
    try:
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
            data = z.read(name)
    except Exception:                                         # noqa: BLE001
        return {}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return parse_gazetteer(text)


def _download(url: str) -> bytes:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "qellysbook/1.0 (hometown map)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def miles(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(min(1.0, h)))


# --- who was born where ---------------------------------------------------------------
def from_espn(payload: dict, team: str = "") -> list:
    """Birthplaces off one ESPN NFL roster (athletes grouped by unit)."""
    from .sources.espnrosters import _athletes
    out = []
    for a in _athletes(payload):
        name = str(a.get("fullName") or a.get("displayName") or "").strip()
        born = a.get("birthPlace") if isinstance(a.get("birthPlace"), dict) else {}
        if not name or not born.get("city"):
            continue
        pos = a.get("position")
        pos = (pos.get("abbreviation") or "") if isinstance(pos, dict) else (pos or "")
        out.append({"player": name, "pos": str(pos).upper(), "team": team, "city": str(born["city"]),
                    "state": str(born.get("state") or ""), "country": str(born.get("country") or ""),
                    "src": "espn"})
    return out


def from_sleeper(blob: dict) -> list:
    """Birthplaces off Sleeper's players file — which keeps retired players,
    so the five-season replay can place players no roster lists today."""
    out = []
    for p in (blob or {}).values():
        if not isinstance(p, dict) or not p.get("birth_city"):
            continue
        name = p.get("full_name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        if not name:
            continue
        out.append({"player": str(name), "pos": str(p.get("position") or "").upper(),
                    "team": str(p.get("team") or ""), "city": str(p["birth_city"]),
                    "state": str(p.get("birth_state") or ""), "country": str(p.get("birth_country") or ""),
                    "src": "sleeper"})
    return out


def build_table(entries: list, gaz: dict) -> dict:
    """{"players": {name: [entry]}, "counts": {...}} — ESPN's birthplace wins
    over Sleeper's for the same player at the same position; only entries
    the map can place are kept."""
    players: dict = {}
    seen = placed = abroad = unplaced = 0
    for e in sorted(entries, key=lambda e: e["src"] != "espn"):
        key = norm_name(e["player"])
        if not key:
            continue
        seen += 1
        if str(e.get("country") or "").strip().lower() not in US:
            abroad += 1
            continue
        st = state_code(e.get("state"))
        ll = gaz.get((norm_city(e["city"]), st)) if st else None
        if not ll:
            unplaced += 1
            continue
        rows = players.setdefault(key, [])
        if any(r["pos"] == e["pos"] for r in rows):
            continue
        placed += 1
        rows.append({"pos": e["pos"], "team": e.get("team") or "", "city": e["city"], "state": st,
                     "lat": round(ll[0], 4), "lon": round(ll[1], 4), "src": e["src"]})
    return {"players": players, "counts": {"listed": seen, "placed": placed, "abroad": abroad,
                                           "unplaced": unplaced}}


def lookup(table: dict, player, position="") -> dict | None:
    """His entry, or None. Two players with one name are told apart by
    position; with no way to tell them apart, neither is used."""
    rows = ((table or {}).get("players") or {}).get(norm_name(player)) or []
    if len(rows) == 1:
        return rows[0]
    pos = str(position or "").upper()
    match = [r for r in rows if r["pos"] == pos]
    return match[0] if len(match) == 1 else None


def hometown_game(entry: dict | None, team, home_team, neutral=False):
    """Miles from his birthplace to the stadium when this is a ROAD game
    within HOMETOWN_MILES of it; else None."""
    if not entry or not team or not home_team or neutral or team == home_team:
        return None
    from .stadiums import STADIUM_COORDS
    st = STADIUM_COORDS.get(str(home_team).upper())
    if not st:
        return None
    d = miles((entry["lat"], entry["lon"]), st)
    return round(d, 1) if d <= HOMETOWN_MILES else None


_NEUTRAL: dict = {}


def neutral_keys(path=None) -> set:
    """{(season, week, home team)} for every neutral-site game in the cached
    nflverse schedule — where the stadium is not the home team's own. Read
    from disk only, once per change of the file."""
    import csv
    from .sources.fetch import CACHE_DIR
    p = Path(path) if path else Path(CACHE_DIR) / "games.csv"
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        return set()
    if _NEUTRAL.get("stamp") != stamp:
        keys = set()
        try:
            with open(p, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    try:
                        season, week = int(r.get("season") or 0), int(float(r.get("week") or 0))
                    except ValueError:
                        continue
                    if str(r.get("location") or "").lower() == "neutral":
                        keys.add((season, week, str(r.get("home_team") or "")))
        except (OSError, ValueError):
            keys = set()
        _NEUTRAL["stamp"], _NEUTRAL["keys"] = stamp, keys
    return _NEUTRAL["keys"]


# --- the stored table -------------------------------------------------------------------
def _store() -> Path:
    from . import modelstate
    return Path(modelstate.path(STORE))


_CACHE: dict = {}


def load(path=None) -> dict:
    p = Path(path) if path else _store()
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if _CACHE.get("stamp") != stamp:
        try:
            _CACHE["table"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CACHE["table"] = {}
        _CACHE["stamp"] = stamp
    return _CACHE["table"]


def save(table: dict, path=None) -> None:
    p = Path(path) if path else _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    table = dict(table, at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(table, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def stale(path=None) -> bool:
    p = Path(path) if path else _store()
    try:
        return (_dt.datetime.now().timestamp() - p.stat().st_mtime) > STALE_S
    except OSError:
        return True


def espn_entries(fetch=None) -> tuple[list, list]:
    """(birthplace entries off every NFL roster, teams that would not load)."""
    from .sources.espnrosters import parse_teams
    from .sources.fetch import DEFAULT_AGENT, DataUnavailable, fetch_json
    fetch = fetch or (lambda url, name: fetch_json(url, name, ttl=ROSTER_TTL, user_agent=DEFAULT_AGENT))
    try:
        ids = parse_teams("nfl", fetch(f"{ESPN_ROOT}/teams", "espn_nfl_teams.json"))
    except DataUnavailable:
        return [], ["(team list)"]
    out, missed = [], []
    for ab, ident in sorted(ids.items()):
        try:
            out += from_espn(fetch(f"{ESPN_ROOT}/teams/{ident}/roster", f"espn_nfl_roster_{ident}.json"), ab)
        except DataUnavailable:
            missed.append(ab)
    return out, missed


def refresh(log=print, espn=None, sleeper=None, gaz=None) -> dict:
    """Build the table from today's rosters, Sleeper's file and the map, and
    save it. Never raises: a source that will not load is a logged line."""
    try:
        if espn is None:
            espn, missed = espn_entries()
            if missed:
                log(f"hometown: ESPN rosters that would not load: {', '.join(missed)}")
        if sleeper is None:
            from .offseason import load_sleeper_players
            sleeper = from_sleeper(load_sleeper_players() or {})
        if gaz is None:
            gaz = load_gazetteer()
        if not gaz:
            log("hometown: the Census place map could not be loaded — nothing can be placed")
        table = build_table(list(espn) + list(sleeper), gaz)
        table["sources"] = {"espn": len(espn), "sleeper": len(sleeper), "map_places": len(gaz)}
        save(table)
        return table
    except Exception as exc:                                  # noqa: BLE001
        log(f"hometown: not rebuilt ({type(exc).__name__}: {exc})")
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.hometown")
    ap.add_argument("--dry-run", action="store_true", help="build and report; save nothing")
    a = ap.parse_args(argv)
    espn, missed = espn_entries()
    from .offseason import load_sleeper_players
    sleeper = from_sleeper(load_sleeper_players() or {})
    gaz = load_gazetteer()
    table = build_table(espn + sleeper, gaz)
    c = table["counts"]
    print(f"birthplaces: {len(espn)} from ESPN rosters"
          + (f" ({len(missed)} teams would not load)" if missed else "")
          + f", {len(sleeper)} from Sleeper; Census map: {len(gaz)} places")
    print(f"placed {c['placed']} players; born abroad {c['abroad']}; "
          f"not found on the map {c['unplaced']}")
    from .stadiums import STADIUM_COORDS
    near = []
    for name, rows in table["players"].items():
        for r in rows:
            if r["pos"] not in ("QB", "RB", "WR", "TE"):
                continue
            team, d = min(((t, miles((r["lat"], r["lon"]), ll)) for t, ll in STADIUM_COORDS.items()),
                          key=lambda x: x[1])
            if d <= HOMETOWN_MILES and team != r["team"]:
                near.append((name, r, team, d))
    print(f"skill players born within {HOMETOWN_MILES:g} miles of another team's stadium: {len(near)}")
    for name, r, team, d in sorted(near, key=lambda x: x[0])[:15]:
        print(f"  {name:24} {r['pos']:3} {r['team'] or '—':4} born {r['city']}, {r['state']} — {d:.0f} mi from {team}")
    if not a.dry_run:
        table["sources"] = {"espn": len(espn), "sleeper": len(sleeper), "map_places": len(gaz)}
        save(table)
        print("saved; the board and the weekly replay read it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
