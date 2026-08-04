"""The Odds API adapter — real sportsbook player-prop lines.

Fetches NFL player props (passing/rushing/receiving yards, receptions) across
books from https://the-odds-api.com and attaches them to a Slate's props,
replacing the nflverse recent-form proxy lines with real numbers so the model
prices its projections against actual books.

Requires an API key (free tier available). Set ``ODDS_API_KEY`` in the
environment or pass ``api_key=...``. Player props are event-scoped on The Odds
API, so pulling a full slate costs one request per game per market group; the
responses are cached briefly under ``data/cache/`` to conserve quota.

The Odds API host may be blocked by restrictive egress policies (as in some
managed sandboxes); run this where outbound access to api.the-odds-api.com is
allowed.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .fetch import CACHE_DIR, USER_AGENT
from ..secrets import load_local_secrets
from ..models import (
    SportsbookLine, PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS,
)

ODDS_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"

# The Odds API market key  <->  engine market constant (NFL).
ODDS_TO_MARKET = {
    "player_pass_yds": PASS_YDS,
    "player_rush_yds": RUSH_YDS,
    "player_reception_yds": REC_YDS,
    "player_receptions": RECEPTIONS,
}
MARKET_TO_ODDS = {v: k for k, v in ODDS_TO_MARKET.items()}

# "Does this player score at all" markets. These are Yes/No with no line, so
# they need their own parser — the over/under one above requires a point and
# deliberately skips them.
SCORER_ODDS_TO_MARKET = {
    "player_anytime_td": "anytime_td",
}

# MLB market keys (engine.mlb.models markets). Kept as strings to avoid an
# import cycle with the MLB package.
MLB_ODDS_TO_MARKET = {
    "batter_total_bases": "total_bases",
    "batter_hits": "hits",
    "batter_home_runs": "home_runs",
    "pitcher_strikeouts": "strikeouts",
    "pitcher_outs": "outs",
}

# Default books to shop, matching the project vision. Keys are The Odds API's.
# Pinnacle rides along as the SHARP REFERENCE — its de-vigged price is the
# best free estimate of a bet's true probability, which is what the
# sharp-anchor strategy prices soft books against. The API bills bookmakers
# in groups of 10 as one region, so listing 10 costs the same as 8.
#
# ESPN BET became theScore Bet (PENN ended the ESPN deal; the rebrand
# completed December 2025). The API's key for the renamed book couldn't be
# confirmed from docs, so all three plausible keys are requested — unknown
# bookmaker keys are ignored, and whichever answers gets the right title.
DEFAULT_BOOKS = [
    "draftkings", "fanduel", "betmgm", "williamhill_us",  # Caesars = William Hill US
    "espnbet", "thescorebet", "thescore",
    "fanatics", "hardrockbet", "pinnacle",
]
# Pretty names for the UI / explanations.
BOOK_TITLES = {
    "draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM",
    "williamhill_us": "Caesars", "fanatics": "Fanatics",
    "espnbet": "theScore Bet", "thescorebet": "theScore Bet",
    "thescore": "theScore Bet",
    "hardrockbet": "Hard Rock", "pinnacle": "Pinnacle",
}
# Books a user can actually bet at (Pinnacle doesn't take US action); the
# sharp reference must never be quoted as the price to take.
SHARP_BOOKS = {"pinnacle"}

# The Odds API uses full team names; nflverse uses abbreviations.
TEAM_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}

# The Odds API uses full team names; the MLB engine uses abbreviations.
MLB_TEAM_ABBR = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
    "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Oakland Athletics": "OAK", "Athletics": "OAK",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD",
    "San Francisco Giants": "SF", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}

# NBA market keys (engine.nba stat names) and team-name map.
NBA_ODDS_TO_MARKET = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
    "player_threes": "fg3m",
    # PRA is the WNBA spec's headline tier-1 market — it aggregates away
    # single-category noise, which is exactly what you want from a 44-game
    # season where one cold shooting night distorts a season average. It
    # costs nothing extra to request: player props are billed per event,
    # not per market.
    "player_points_rebounds_assists": "pra",
}
NBA_TEAM_ABBR = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU",
    "Indiana Pacers": "IND", "LA Clippers": "LAC",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}

# Per-sport wiring: The Odds API sport key, market map, and team-name map.
WNBA_TEAM_ABBR = {
    "Atlanta Dream": "ATL", "Chicago Sky": "CHI", "Connecticut Sun": "CON",
    "Dallas Wings": "DAL", "Golden State Valkyries": "GSV",
    "Indiana Fever": "IND", "Las Vegas Aces": "LVA", "Los Angeles Sparks": "LAS",
    "Minnesota Lynx": "MIN", "New York Liberty": "NYL",
    "Phoenix Mercury": "PHX", "Portland Fire": "POR",
    "Seattle Storm": "SEA", "Toronto Tempo": "TOR",
    "Washington Mystics": "WAS",
}

SPORT_CONFIG = {
    "nfl": {"sport_key": "americanfootball_nfl",
            "markets": ODDS_TO_MARKET, "teams": TEAM_ABBR},
    "mlb": {"sport_key": "baseball_mlb",
            "markets": MLB_ODDS_TO_MARKET, "teams": MLB_TEAM_ABBR},
    "nba": {"sport_key": "basketball_nba",
            "markets": NBA_ODDS_TO_MARKET, "teams": NBA_TEAM_ABBR},
    # Same markets and the same book keys; only the league and the team
    # names differ. The WNBA expanded twice in two years, so this map is
    # the 2026 field.
    "wnba": {"sport_key": "basketball_wnba",
             "markets": NBA_ODDS_TO_MARKET, "teams": WNBA_TEAM_ABBR},
    # MMA events are one bout each; "teams" are fighter names, so the map is
    # identity (ufc_build reads the h2h payload directly).
    "ufc": {"sport_key": "mma_mixed_martial_arts", "markets": {}, "teams": {}},
    # College football is full-game markets only, and its team map is BUILT
    # at run time from the ESPN feed rather than listed here — 134 schools
    # is the kind of table that rots the moment a conference reshuffles.
    # cfb_build passes the map it derived into the parsers.
    "cfb": {"sport_key": "americanfootball_ncaaf", "markets": {}, "teams": {}},
}


# --- futures ----------------------------------------------------------------
#
# Futures live under their OWN sport keys, not as a market on the league's
# board — "who wins the World Series" is a different endpoint from "tonight's
# Mets game". One market, one region, so `_classify` bills each of these at
# ONE credit per call. Four sports pulled once a week is four credits a week,
# about seventeen a month, against a 20,000-credit plan.
#
# That cheapness is the entire reason this is safe to automate, and it is
# also fragile: adding a second market or a second region to this call
# doubles it, and adding a per-event loop would multiply it by thirty. There
# is a test asserting the request stays one market and one region.
FUTURES_KEYS = {
    "nfl": "americanfootball_nfl_super_bowl_winner",
    "mlb": "baseball_mlb_world_series_winner",
    "nba": "basketball_nba_championship_winner",
    "cfb": "americanfootball_ncaaf_championship_winner",
}

#: A week. Futures are the slowest market a book runs — a division number
#: posted in March can sit untouched through a July injury — so pulling one
#: more often buys nothing and spends every time. The cache TTL IS the
#: cadence: within a week the call never reaches the wire.
FUTURES_TTL = 7 * 86400


class OddsAPIError(RuntimeError):
    pass


def _classify(url: str, cache_name: str) -> tuple[str, str, int, str]:
    """(kind, sport, credits, detail) for one paid call.

    Credits are the API's own billing rule — per market, per region — read off
    the request that was actually sent, rather than an assumption about what a
    build usually asks for. Historical calls carry a large multiplier that
    only the-odds-api's meter knows exactly; the constant is the measured
    figure from harvest_odds.py's own note.
    """
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    markets = len([m for m in (q.get("markets") or [""])[0].split(",") if m])
    regions = len([r for r in (q.get("regions") or ["us"])[0].split(",") if r])
    per = max(1, markets) * max(1, regions)
    hist = "/historical/" in url
    if "events" in cache_name and "event_" not in cache_name:
        kind, cost = ("hist_events" if hist else "live_events"), (10 if hist else 1)
    elif "board" in cache_name:
        kind, cost = ("hist_board" if hist else "live_board"), per * (5 if hist else 1)
    else:
        kind, cost = ("hist_event" if hist else "live_event"), per * (5 if hist else 1)
    sport = ""
    for token in cache_name.replace(".json", "").split("_"):
        if token in ("nfl", "mlb", "nba", "wnba", "cfb", "ufc"):
            sport = token
            break
    return kind, sport, cost, cache_name


def _url_key(url: str) -> str:
    """The apiKey this URL is carrying, so a result can be attributed to the
    key that paid for it."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return (q.get("apiKey") or [""])[0]


def _with_key(url: str, key: str) -> str:
    """The same request, billed to a different key."""
    parts = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(parts.query)
    q["apiKey"] = [key]
    return urllib.parse.urlunparse(
        parts._replace(query=urllib.parse.urlencode(q, doseq=True)))


def _next_key(after: str) -> str | None:
    """The next key on the ring with credits left, or None if that was the
    last one."""
    ring = api_keys()
    try:
        from ..oddsbudget import key_is_spent
    except Exception:
        return None
    try:
        start = ring.index(after) + 1
    except ValueError:
        start = 0
    for k in ring[start:]:
        if not key_is_spent(k):
            return k
    return None


def api_keys(explicit: str | None = None) -> list[str]:
    """Every key we can pay with, in the order to try them.

    A plan is a fixed monthly allowance, and running two of them is the
    cheapest way to double it — so the key is a RING rather than a single
    value. Accepted forms, all optional beyond the first::

        ODDS_API_KEY=aaa                 # the primary
        ODDS_API_KEY_2=bbb               # ...and as many numbered spares
        ODDS_API_KEY_3=ccc               #    as you like
        ODDS_API_KEYS=aaa,bbb,ccc        # or the whole ring on one line

    Order is the order given: the primary first, then 2, 3, and so on. An
    explicit key passed in code wins outright, because a caller asking for a
    specific key means it.
    """
    load_local_secrets()
    if explicit:
        return [explicit]
    ring: list[str] = []
    primary = os.environ.get("ODDS_API_KEY")
    if primary:
        ring.append(primary.strip())
    for extra in (os.environ.get("ODDS_API_KEYS") or "").split(","):
        if extra.strip():
            ring.append(extra.strip())
    i = 2
    while True:
        nxt = os.environ.get(f"ODDS_API_KEY_{i}")
        if not nxt:
            break
        ring.append(nxt.strip())
        i += 1
    seen, ordered = set(), []
    for k in ring:                       # first mention wins, no duplicates
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def get_api_key(explicit: str | None = None) -> str:
    """The key to spend next: the first on the ring with credits left.

    A key we have never called is not spent — unknown is not zero. If every
    key is known to be empty this still returns the first, so the caller gets
    the API's own "out of credits" answer rather than a guess from a state
    file that may be a month stale.
    """
    ring = api_keys(explicit)
    if not ring:
        raise OddsAPIError(
            "No Odds API key. Set ODDS_API_KEY in the environment or in "
            "secrets.local (ODDS_API_KEY_2, _3 … add spares) — get a free "
            "key at https://the-odds-api.com."
        )
    try:
        from ..oddsbudget import key_is_spent
        for k in ring:
            if not key_is_spent(k):
                return k
    except Exception:                    # budgeting must never block a fetch
        pass
    return ring[0]


# --- name matching ----------------------------------------------------------
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b", re.I)


def normalize_name(name: str) -> str:
    """Loose key for matching player names across sources (drops punctuation,
    suffixes, casing and accents so 'Amon-Ra St. Brown' == 'amon ra st brown'
    and 'Ronald Acuña Jr.' == 'ronald acuna').

    Accent folding matters more than it looks: the MLB feed spells names with
    diacritics and odds feeds often don't, so without it every Acuña, Ramírez
    and Suárez silently fails to join — real lines that were paid for simply
    never match their game logs.
    """
    import unicodedata
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("-", " ").replace(".", " ").replace("'", "")
    s = _SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


# --- HTTP (captures quota headers) -----------------------------------------
@dataclass
class Quota:
    remaining: str = "?"
    used: str = "?"


def _read_cached_json(path):
    """Parse a cache file, or None when missing/empty/corrupt — a broken
    cache is a MISS, not a raw JSONDecodeError thrown past every caller
    that only guards OddsAPIError."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _request(url: str, cache_name: str, ttl: int = 300,
             timeout: int = 30, cache_only: bool = False) -> tuple[object, Quota]:
    """GET JSON with a short cache. Returns (parsed_json, quota).

    ``cache_only`` serves the cached copy at ANY age and never touches the
    network — the zero-cost path that lets every refresh cycle keep the last
    paid pull's real prices instead of overwriting them with proxies. Raises
    when nothing is cached yet.

    The API key is only ever in the URL, never in the cache filename.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if cache_only:
        cached = _read_cached_json(path) if path.exists() else None
        if cached is not None:
            return cached, Quota()
        raise OddsAPIError(f"no cached odds yet for {cache_name}")
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        fresh = _read_cached_json(path)
        if fresh is not None:
            return fresh, Quota()

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            quota = Quota(
                remaining=resp.headers.get("x-requests-remaining", "?"),
                used=resp.headers.get("x-requests-used", "?"),
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code in (401, 403):
            # A spent quota comes back as a 401 with no remaining-header, so
            # record it explicitly — otherwise the budgeter keeps believing the
            # assumed balance and retries a call that cannot succeed.
            if "OUT_OF_USAGE_CREDITS" in detail or "quota has been reached" in detail:
                spent = _url_key(url)
                try:
                    from ..oddsbudget import mark_key_spent
                    mark_key_spent(spent)
                except Exception:
                    pass
                # A ring exists so that one empty plan is not the end of the
                # night. Swap in the next key with credits and retry the same
                # request — the call cost nothing, because it was refused.
                nxt = _next_key(spent)
                if nxt:
                    return _request(_with_key(url, nxt), cache_name, ttl=ttl,
                                    timeout=timeout, cache_only=cache_only)
                raise OddsAPIError(
                    "Every Odds API key is out of credits. Real book lines are "
                    "unavailable until a plan resets; scores, projections and "
                    "the rest of the app keep working. Add another key as "
                    "ODDS_API_KEY_2 in secrets.local, or see the-odds-api.com "
                    "for your reset date."
                ) from exc
            raise OddsAPIError(f"Odds API auth/quota error {exc.code}: {detail}") from exc
        raise OddsAPIError(f"Odds API HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        stale = _read_cached_json(path) if path.exists() else None
        if stale is not None:          # fall back to stale cache when offline
            return stale, Quota()
        raise OddsAPIError(f"Odds API request failed: {exc}") from exc

    path.write_text(body)
    # Record what the API says is left so the budgeter schedules against the
    # real account rather than an assumption.
    try:
        from ..oddsbudget import record_quota, log_spend
        record_quota(quota.remaining, quota.used, key=_url_key(url))
        log_spend(*_classify(url, cache_name))
    except Exception:      # budgeting must never break a fetch
        pass
    return json.loads(body), quota


# --- endpoints --------------------------------------------------------------
def list_events(api_key: str | None = None, ttl: int = 300,
                sport: str = "nfl", cache_only: bool = False) -> list[dict]:
    key = get_api_key(api_key)
    sport_key = SPORT_CONFIG[sport]["sport_key"]
    url = f"{ODDS_BASE}/sports/{sport_key}/events?{urllib.parse.urlencode({'apiKey': key})}"
    data, _ = _request(url, f"odds_events_{sport}.json", ttl=ttl,
                       cache_only=cache_only)
    return data


def fetch_sport_odds(sport: str, api_key: str | None = None,
                     markets: list[str] | None = None,
                     books: list[str] | None = None,
                     ttl: int = 600, cache_only: bool = False) -> tuple[list, Quota]:
    """Every game's full-game lines in ONE request.

    The event-scoped endpoint above costs a request per game, which is the
    right trade for player props (they only exist per event). Full-game
    markets don't: this endpoint returns h2h/spreads/totals for the whole
    board for the price of one call per market. On a 60-game college
    Saturday that is the difference between three credits and sixty, and
    the budget pacer would simply never authorise sixty.
    """
    key = get_api_key(api_key)
    cfg = SPORT_CONFIG[sport]
    params = {
        "apiKey": key,
        "regions": "us",
        "markets": ",".join(markets or ["h2h", "spreads", "totals"]),
        "oddsFormat": "american",
        "bookmakers": ",".join(books or DEFAULT_BOOKS),
    }
    url = (f"{ODDS_BASE}/sports/{cfg['sport_key']}/odds"
           f"?{urllib.parse.urlencode(params)}")
    data, quota = _request(url, f"odds_board_{sport}.json", ttl=ttl,
                           cache_only=cache_only)
    return (data if isinstance(data, list) else []), quota


def fetch_outrights(sport: str, api_key: str | None = None,
                    ttl: int = FUTURES_TTL, cache_only: bool = False
                    ) -> tuple[list, Quota]:
    """One league's championship futures, in one request.

    Deliberately narrow: a single market and a single region, which is what
    keeps this at one credit. The bookmaker list is NOT pinned — futures are
    posted by fewer books than game lines, and asking for a fixed five can
    come back empty while three others are pricing it.
    """
    key = get_api_key(api_key)
    sport_key = FUTURES_KEYS.get(sport)
    if not sport_key:
        return [], Quota()
    params = {"apiKey": key, "regions": "us", "markets": "outrights",
              "oddsFormat": "american"}
    url = f"{ODDS_BASE}/sports/{sport_key}/odds?{urllib.parse.urlencode(params)}"
    data, quota = _request(url, f"odds_board_futures_{sport}.json", ttl=ttl,
                           cache_only=cache_only)
    return (data if isinstance(data, list) else []), quota


def parse_outrights(payload: list, teams: dict | None = None) -> dict:
    """``{team: {"odds", "book", "implied"}}`` — the best price per team.

    Books name a futures runner in full ("Los Angeles Dodgers"), so the
    league's name map converts it to the abbreviation the rest of the
    system uses. A runner we cannot map is DROPPED rather than guessed at:
    a mis-mapped futures price is attached to the wrong team's projection,
    which is worse than showing no price at all.
    """
    teams = teams or {}
    best: dict[str, dict] = {}
    for event in payload or []:
        for bk in event.get("bookmakers", []) or []:
            for mkt in bk.get("markets", []) or []:
                if mkt.get("key") != "outrights":
                    continue
                for o in mkt.get("outcomes", []) or []:
                    name = o.get("name") or ""
                    abbr = teams.get(name) or _futures_abbr(name, teams)
                    price = o.get("price")
                    if not abbr or price is None:
                        continue
                    price = int(price)
                    cur = best.get(abbr)
                    # Best price for the bettor: the longest number.
                    if cur is None or _dec(price) > _dec(cur["odds"]):
                        best[abbr] = {"odds": price,
                                      "book": bk.get("title") or bk.get("key", ""),
                                      "implied": round(1.0 / _dec(price), 4)}
    return best


def _dec(american: int) -> float:
    a = int(american)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def _futures_abbr(name: str, teams: dict) -> str:
    """Last-resort match on a normalised team name.

    College football has no static map at all and the pro leagues rename
    the odd franchise, so an exact-key lookup alone would silently drop
    runners. Still exact once normalised — nothing fuzzy, because a futures
    price on the wrong team is worse than no price.
    """
    def key(s: str) -> str:
        return "".join(c for c in (s or "").lower() if c.isalnum())
    want = key(name)
    for full, abbr in teams.items():
        if key(full) == want:
            return abbr
    return ""


def fetch_event_odds(event_id: str, api_key: str | None = None,
                     markets: list[str] | None = None,
                     books: list[str] | None = None,
                     ttl: int = 300, sport: str = "nfl",
                     cache_only: bool = False) -> tuple[dict, Quota]:
    key = get_api_key(api_key)
    cfg = SPORT_CONFIG[sport]
    markets = markets or list(cfg["markets"])
    books = books or DEFAULT_BOOKS
    params = {
        "apiKey": key,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
        "bookmakers": ",".join(books),
    }
    url = (f"{ODDS_BASE}/sports/{cfg['sport_key']}/events/{event_id}/odds"
           f"?{urllib.parse.urlencode(params)}")
    return _request(url, f"odds_event_{event_id}.json", ttl=ttl,
                    cache_only=cache_only)


# --- parsing (pure; unit-tested without network) ----------------------------
def parse_event_lines(event_json: dict,
                      market_map: dict | None = None) -> dict[tuple[str, str], list[SportsbookLine]]:
    """Turn one event's odds payload into {(norm_player, market): [lines]}.

    Only the OVER outcome carries the odds we bet; we pair it with the matching
    UNDER price (same book, line) so the de-vig has both sides. ``market_map``
    selects the sport's Odds-API market keys (defaults to NFL)."""
    market_map = market_map or ODDS_TO_MARKET
    out: dict[tuple[str, str], list[SportsbookLine]] = {}
    for bm in event_json.get("bookmakers", []):
        book_key = bm.get("key", "")
        if book_key in SHARP_BOOKS:
            # Reference-only books: nobody here can bet them, so their lines
            # must never be shopped as "the price to take".
            continue
        book = BOOK_TITLES.get(book_key, book_key)
        for mkt in bm.get("markets", []):
            market = market_map.get(mkt.get("key", ""))
            if not market:
                continue
            # Index outcomes by (player, point) to pair Over/Under prices.
            overs: dict[tuple[str, float], int] = {}
            unders: dict[tuple[str, float], int] = {}
            for o in mkt.get("outcomes", []):
                player = o.get("description", "")
                point = o.get("point")
                price = o.get("price")
                if player is None or point is None or price is None:
                    continue
                side = (o.get("name") or "").lower()
                if side == "over":
                    overs[(player, float(point))] = int(price)
                elif side == "under":
                    unders[(player, float(point))] = int(price)
            for (player, point), over_price in overs.items():
                # NO fabricated opposite side: many prop markets (home runs
                # especially) are quoted Over-only, and inventing an under at
                # -110 manufactured huge fake edges on bets nobody can place.
                # 0 = "not offered".
                under_price = unders.get((player, point), 0)
                key = (normalize_name(player), market)
                out.setdefault(key, []).append(SportsbookLine(
                    book=book, line=float(point),
                    over_odds=over_price, under_odds=under_price,
                ))
    return out


def parse_event_players(event_json: dict,
                        market_map: dict | None = None) -> dict[tuple[str, str], str]:
    """Every player the books have priced in this event:
    ``{(norm_player, market): display_name}``.

    The book's posted menu is the market's own statement of who is expected
    to play tonight — the roster source that never waits for an official
    lineup card."""
    market_map = market_map or ODDS_TO_MARKET
    out: dict[tuple[str, str], str] = {}
    for bm in event_json.get("bookmakers", []):
        if bm.get("key", "") in SHARP_BOOKS:
            continue
        for mkt in bm.get("markets", []):
            market = market_map.get(mkt.get("key", ""))
            if not market:
                continue
            for o in mkt.get("outcomes", []):
                player = o.get("description")
                if player:
                    out.setdefault((normalize_name(player), market), player)
    return out


def parse_event_h2h(event_json: dict, team_map: dict) -> dict[str, int]:
    """Extract the best moneyline (American odds) per team from an event payload.

    The ``h2h`` market rides in the same event-odds response as the player
    props, so this costs no extra request. For each team we keep the most
    bettor-friendly price across books (higher American odds = better payout,
    which is monotonic across the sign boundary)."""
    best: dict[str, int] = {}
    for bm in event_json.get("bookmakers", []):
        if bm.get("key", "") in SHARP_BOOKS:
            continue                    # reference-only, not a bettable price
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            for o in mkt.get("outcomes", []):
                abbr = team_map.get(o.get("name", ""))
                price = o.get("price")
                if not abbr or price is None:
                    continue
                price = int(price)
                if abbr not in best or price > best[abbr]:
                    best[abbr] = price
    return best


def parse_event_h2h_by_book(event_json: dict, team_map: dict) -> dict[str, dict[str, int]]:
    """Moneylines per book: ``{book_title: {team_abbr: american_odds}}``.

    Unlike :func:`parse_event_h2h` this keeps EVERY book — including the
    sharp reference — because the sharp-anchor strategy needs the sharp
    book's two-sided price to de-vig, and the soft books' prices to shop."""
    out: dict[str, dict[str, int]] = {}
    for bm in event_json.get("bookmakers", []):
        book = BOOK_TITLES.get(bm.get("key", ""), bm.get("key", ""))
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            for o in mkt.get("outcomes", []):
                abbr = team_map.get(o.get("name", ""))
                price = o.get("price")
                if abbr and price is not None:
                    out.setdefault(book, {})[abbr] = int(price)
    return out


def parse_event_scorers(event_json: dict,
                        market_map: dict | None = None) -> dict[tuple[str, str], list[dict]]:
    """Parse Yes/No "to score" markets (anytime touchdown) from an event.

    Returns ``{(normalised_player, market): [{book, yes_odds, no_odds}]}``.
    The No side is usually quoted too, which lets the caller de-vig properly
    instead of assuming a hold.
    """
    market_map = market_map or SCORER_ODDS_TO_MARKET
    out: dict[tuple[str, str], list[dict]] = {}
    for bm in event_json.get("bookmakers", []):
        book = BOOK_TITLES.get(bm.get("key", ""), bm.get("key", ""))
        for mkt in bm.get("markets", []):
            market = market_map.get(mkt.get("key", ""))
            if not market:
                continue
            yes: dict[str, int] = {}
            no: dict[str, int] = {}
            for o in mkt.get("outcomes", []):
                player = o.get("description") or o.get("participant") or ""
                price = o.get("price")
                if not player or price is None:
                    continue
                side = (o.get("name") or "").strip().lower()
                if side in ("yes", "over", player.strip().lower()):
                    yes[player] = int(price)
                elif side == "no":
                    no[player] = int(price)
            for player, y in yes.items():
                out.setdefault((normalize_name(player), market), []).append(
                    {"book": book, "yes_odds": y, "no_odds": no.get(player)})
    return out


def best_scorer_price(quotes: list[dict]) -> dict | None:
    """Most bettor-friendly quote across books (highest Yes payout)."""
    if not quotes:
        return None
    return max(quotes, key=lambda q: q["yes_odds"])


def _modal_line(points: list[float]):
    """Most common line across books (the market consensus number)."""
    if not points:
        return None
    counts: dict[float, int] = {}
    for p in points:
        counts[p] = counts.get(p, 0) + 1
    return max(counts, key=lambda k: (counts[k], k))


def parse_event_totals(event_json: dict, only_books: set | None = None):
    """Return ``(line, best_over_odds, best_under_odds)`` for the game total,
    or ``None``. Uses the consensus line and the best price on each side.

    Sharp reference books are excluded from the bettable aggregate;
    ``only_books`` (API keys) restricts to those books instead — that's how
    the sharp book's own pair is read out as the fair-value anchor."""
    overs: list[tuple] = []
    unders: list[tuple] = []
    for bm in event_json.get("bookmakers", []):
        bk = bm.get("key", "")
        if (bk in SHARP_BOOKS) if only_books is None else (bk not in only_books):
            continue
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "totals":
                continue
            for o in mkt.get("outcomes", []):
                name = (o.get("name") or "").lower()
                pt, pr = o.get("point"), o.get("price")
                if pt is None or pr is None:
                    continue
                (overs if name == "over" else unders).append((float(pt), int(pr)))
    line = _modal_line([p for p, _ in overs])
    if line is None:
        return None
    over_odds = max((pr for p, pr in overs if p == line), default=-110)
    under_odds = max((pr for p, pr in unders if p == line), default=-110)
    return line, over_odds, under_odds


def parse_event_spreads(event_json: dict, team_map: dict, home: str, away: str,
                        only_books: set | None = None):
    """Return ``(home_spread, home_odds, away_odds)`` for the spread / run line,
    or ``None``. The home team's point is the stored spread. Sharp books are
    excluded unless ``only_books`` selects them explicitly."""
    home_pts: list[tuple] = []
    away_pts: list[tuple] = []
    for bm in event_json.get("bookmakers", []):
        bk = bm.get("key", "")
        if (bk in SHARP_BOOKS) if only_books is None else (bk not in only_books):
            continue
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "spreads":
                continue
            for o in mkt.get("outcomes", []):
                abbr = team_map.get(o.get("name", ""))
                pt, pr = o.get("point"), o.get("price")
                if not abbr or pt is None or pr is None:
                    continue
                if abbr == home:
                    home_pts.append((float(pt), int(pr)))
                elif abbr == away:
                    away_pts.append((float(pt), int(pr)))
    line = _modal_line([p for p, _ in home_pts])
    if line is None:
        return None
    home_odds = max((pr for p, pr in home_pts if p == line), default=-110)
    away_odds = max((pr for p, pr in away_pts if p == -line), default=-110)
    return line, home_odds, away_odds


# --- slate integration ------------------------------------------------------
@dataclass
class OddsAttachResult:
    matched: int = 0
    unmatched: list[str] = field(default_factory=list)
    quota: Quota = field(default_factory=Quota)
    events_used: int = 0
    moneylines: int = 0          # games that got real h2h prices attached
    from_cache: bool = False     # prices reused from the last paid pull
    # Players the books have priced who matched NO slate prop — the book's
    # menu knows who's playing before the official lineup does. Each entry:
    # {player, market, home, away, lines}.
    book_only: list = field(default_factory=list)
    # NEAR-misses: a slate prop and a book line for what is almost certainly
    # the same player, whose normalized keys still didn't match. Every one of
    # these is a price we PAID for and then ignored, and it hides inside the
    # "no real book price" bucket looking like a market the book never
    # offered. Loud on purpose. Each entry: {prop, book, market}.
    name_misses: list = field(default_factory=list)
    # Events the book HAS and we could not place on our slate. Every one of
    # these is a whole game's worth of prices we never looked at, and its
    # props are indistinguishable downstream from props the book never
    # priced. Each entry: {reason, home, away, …}.
    dropped_events: list = field(default_factory=list)
    # Events for a DIFFERENT day. list_events has no date filter, so a
    # four-game slate is matched against every upcoming fixture. Counted,
    # never reported as a fault — they are supposed to miss.
    other_day_events: int = 0
    # Events that DID place on the slate but had no cached payload, in
    # cache_only mode. Without this a cached rebuild looks identical whether
    # the join improved or not: the events match, then vanish one line later
    # because nobody ever paid for them.
    cache_misses: int = 0


def _team_key(name: str) -> str:
    """A team name reduced to what two feeds can be expected to agree on.

    Case, punctuation and spacing only. Deliberately NOT clever: dropping
    the city or matching on the nickname alone would collide the moment a
    league has a Los Angeles Sparks and a Los Angeles Lakers, and a join
    that is wrong is worse than one that misses.
    """
    return "".join(c for c in (name or "").lower() if c.isalnum())


def _name_key_loose(name: str) -> str:
    """First initial + last name — the shape that survives the disagreements
    normalize_name can't fix: nicknames ("Mike"/"Michael"), dropped middle
    names, and feeds that shorten to "J. Chourio"."""
    parts = normalize_name(name).split()
    if not parts:
        return ""
    return f"{parts[0][:1]} {parts[-1]}"


def _name_near_misses(slate, menu: dict, matched_keys: set) -> list[dict]:
    """Slate props and book lines that are almost certainly the same player
    but whose exact keys didn't join.

    This is the difference between "the book never offered this market"
    (fine, expected — we project more players than books post) and "we paid
    for this price and threw it away" (a bug). Only the second kind belongs
    in anyone's attention."""
    by_loose: dict[str, list] = {}
    for (nkey, market), info in menu.items():
        if (nkey, market) in matched_keys:
            continue
        by_loose.setdefault(f"{_name_key_loose(info['player'])}|{market}", []).append(info["player"])
    out: list[dict] = []
    for p in slate.props:
        if (normalize_name(p.player), p.market) in menu:
            continue                       # matched exactly — nothing to see
        cands = by_loose.get(f"{_name_key_loose(p.player)}|{p.market}")
        if not cands:
            continue
        out.append({"prop": p.player, "book": cands[0], "market": p.market})
    return out


def _is_active(game, window_hours: float) -> bool:
    """Is this game live, or starting soon enough that its price still matters?"""
    live = getattr(game, "live", None)
    if live is not None and getattr(live, "state", "") == "live":
        return True
    if live is not None and getattr(live, "state", "") == "final":
        return False
    kickoff = (getattr(game, "kickoff", "") or "")
    if not kickoff:
        return True          # unknown start time — assume it still matters
    try:
        import datetime as _dt
        stamp = kickoff.replace("Z", "+00:00")
        start = _dt.datetime.fromisoformat(stamp)
        now = _dt.datetime.now(start.tzinfo) if start.tzinfo else _dt.datetime.now()
        hours = (start - now).total_seconds() / 3600.0
        return hours <= window_hours
    except (ValueError, TypeError):
        return True


def apply_odds_to_slate(slate, api_key: str | None = None,
                        books: list[str] | None = None,
                        ttl: int = 300, sport: str = "nfl",
                        only_active: bool = False,
                        active_window_hours: float = 6.0,
                        cache_only: bool = False) -> OddsAttachResult:
    """Replace each prop's proxy line with real book lines where available.

    Matches Odds API events to slate games by team abbreviation, then props by
    normalized player name + market. Works for ``sport`` "nfl" or "mlb"; during
    a live game the event-odds endpoint returns current (in-play) prices, so the
    same call yields live lines. Props with no market found keep their proxy
    line and are reported in ``unmatched``. ``ttl`` is short (30s) for live use.
    """
    key = get_api_key(api_key)
    cfg = SPORT_CONFIG[sport]
    result = OddsAttachResult()
    result.from_cache = cache_only

    # Which team pairs are in this slate?
    slate_pairs = {frozenset((g.home, g.away)) for g in slate.games}

    events = list_events(key, ttl=ttl, sport=sport, cache_only=cache_only)
    # A pair can hold TWO games (MLB doubleheader) — keep them all, matched
    # to events by first-pitch time below. Collapsing to one game merged
    # both legs' prices under one line, silently.
    pair_games: dict[frozenset, list] = {}
    for g in slate.games:
        pair_games.setdefault(frozenset((g.home, g.away)), []).append(g)
    games_by_pair = {k: v[0] for k, v in pair_games.items()}
    # Which leg of each doubleheader the slate's PROPS belong to (props are
    # built for one leg only — the next to be played).
    prop_leg: dict[frozenset, int] = {}
    for p in getattr(slate, "props", []):
        gn = getattr(p, "game_number", 0)
        if gn:
            prop_leg[frozenset((p.team, p.opponent))] = gn

    def _leg_for_event(pair, commence: str):
        legs = pair_games.get(pair) or []
        if len(legs) <= 1:
            return legs[0] if legs else None
        # Two legs: the event's commence time picks the right one.
        def _dist(g):
            try:
                a = commence.replace("Z", "+00:00")
                b = (g.kickoff or "").replace("Z", "+00:00")
                import datetime as _dt
                return abs((_dt.datetime.fromisoformat(a)
                            - _dt.datetime.fromisoformat(b)).total_seconds())
            except Exception:
                return float("inf")
        return min(legs, key=_dist)

    # Only re-price games whose number can actually still move for us: in-play
    # and about-to-start games. A game tomorrow doesn't need a fresh quote every
    # cycle, and skipping it multiplies how often the ones that matter can be
    # refreshed within the same request budget.
    if only_active:
        active = {frozenset((g.home, g.away)) for g in slate.games
                  if _is_active(g, active_window_hours)}
        if active:
            games_by_pair = {k: v for k, v in games_by_pair.items() if k in active}
            pair_games = {k: v for k, v in pair_games.items() if k in active}
            slate_pairs = slate_pairs & active
    # Player-prop markets plus the three game markets in one request per event.
    markets = list(cfg["markets"]) + ["h2h", "totals", "spreads"]
    # Build a combined line index for the events that belong to this slate.
    index: dict[tuple[str, str], list[SportsbookLine]] = {}
    menu: dict[tuple[str, str], dict] = {}
    # THE SLATE'S OWN NAMES BEAT THE STATIC TABLE.
    #
    # SPORT_CONFIG carries a hand-written {full name: abbreviation} map per
    # league, and it has to agree with whatever the schedule feed calls the
    # same teams. For the WNBA it did not: the table used league-style codes
    # (LVA, NYL, GSV) and the ESPN schedule uses ESPN's own, so every event
    # mapped to a pair that was not on our slate and all five games were
    # dropped. 761 props reported as unpriced, on a night the book had
    # priced every game.
    #
    # A table maintained by hand against a feed that renames and expands is
    # the wrong shape for this. cfb_build already reached that conclusion —
    # "134 schools is the kind of table that rots the moment a conference
    # reshuffles" — and builds its map from the feed instead. This does the
    # same wherever the schedule carries team names: the join runs feed-name
    # to feed-abbreviation, so the two halves cannot disagree.
    slate_names: dict[str, str] = {}
    for g in slate.games:
        for nm, ab in ((getattr(g, "home_name", ""), g.home),
                       (getattr(g, "away_name", ""), g.away)):
            if nm and ab:
                slate_names[_team_key(nm)] = ab

    def _abbr(name: str) -> str | None:
        return slate_names.get(_team_key(name)) or cfg["teams"].get(name)

    # WHICH DAYS THIS SLATE COVERS. list_events returns every UPCOMING event
    # for the sport with no date filter, so a four-game slate is matched
    # against a list that also holds tomorrow's and Thursday's games. Those
    # are not on our slate and are not supposed to be — reporting them as
    # dropped turns a correct result into three alarming lines, which is how
    # a diagnostic stops being read.
    #
    # A day either side, because kickoffs are UTC and a 7pm Eastern tip is
    # already tomorrow there.
    import datetime as _dt
    slate_days: set[str] = set()
    for g in slate.games:
        k = str(getattr(g, "kickoff", "") or "")[:10]
        if len(k) == 10:
            try:
                d = _dt.date.fromisoformat(k)
            except ValueError:
                continue
            slate_days |= {(d + _dt.timedelta(days=n)).isoformat()
                           for n in (-1, 0, 1)}

    def _other_day(ev) -> bool:
        c = str(ev.get("commence_time") or "")[:10]
        return bool(slate_days) and len(c) == 10 and c not in slate_days

    for ev in events:
        home = _abbr(ev.get("home_team", ""))
        away = _abbr(ev.get("away_team", ""))
        # An event we cannot place on the slate is dropped here, and it used
        # to be dropped in silence — three different failures sharing one
        # `continue`, none of them counted. Downstream all anyone saw was a
        # low events_used, and every prop in those games landed in the "no
        # real book price" bucket looking exactly like a market the book
        # never offered. Measured on a WNBA board: 1 event matched out of 4
        # games, 761 props reported as unpriced, and nothing anywhere said
        # the other three games had simply failed to map.
        #
        # The two causes need opposite fixes, so they are named separately.
        # An unmapped NAME is a stale team table — the league renamed or
        # expanded and SPORT_CONFIG never heard. A mapped pair that is not
        # on the slate means our own abbreviations and the table's disagree,
        # which is a wiring bug, not a data one.
        if not home or not away:
            result.dropped_events.append(
                {"reason": "team name not in the map",
                 "home": ev.get("home_team", ""), "away": ev.get("away_team", ""),
                 "unmapped": [n for n, m in ((ev.get("home_team", ""), home),
                                             (ev.get("away_team", ""), away))
                              if not m]})
            continue
        if frozenset((home, away)) not in slate_pairs:
            # A later date's game is not a fault, so it is not reported as
            # one. Only a pair that should be on THIS slate and is not.
            if not _other_day(ev):
                result.dropped_events.append(
                    {"reason": "mapped, but that pair is not on our slate",
                     "home": ev.get("home_team", ""),
                     "away": ev.get("away_team", ""),
                     "mapped_to": [away, home]})
            else:
                result.other_day_events += 1
            continue
        try:
            payload, quota = fetch_event_odds(ev["id"], key, markets=markets,
                                              books=books, ttl=ttl, sport=sport,
                                              cache_only=cache_only)
        except OddsAPIError:
            if cache_only:
                # Never paid for, so there is nothing on disk. Counted: a
                # cached rebuild otherwise looks identical whether the
                # event join improved or not, because the newly-matched
                # events match and then disappear on this line.
                result.cache_misses += 1
                continue
            raise
        result.quota = quota
        result.events_used += 1
        pair = frozenset((home, away))
        game = _leg_for_event(pair, ev.get("commence_time") or "")
        # Prop lines only index when this event IS the leg the slate's props
        # were built for — a doubleheader's other leg has different lineups
        # and different prices, and mixing them corrupts every quote.
        wanted = prop_leg.get(pair, 0)
        props_ok = (not wanted or game is None
                    or getattr(game, "game_number", 1) == wanted)
        if props_ok:
            for k, lines in parse_event_lines(payload, cfg["markets"]).items():
                index.setdefault(k, []).extend(lines)
            for k, disp in parse_event_players(payload, cfg["markets"]).items():
                menu.setdefault(k, {"player": disp, "home": home, "away": away})
        # Attach real game-market prices to the matching game (each leg gets
        # its own moneyline/total/spread).
        if game is not None:
            mls = parse_event_h2h(payload, cfg["teams"])
            if home in mls and away in mls:
                game.home_ml = mls[home]
                game.away_ml = mls[away]
                result.moneylines += 1
            # The sharp book's own pair rides along as the fair-value anchor.
            for bk, prices in parse_event_h2h_by_book(payload, cfg["teams"]).items():
                if bk == BOOK_TITLES.get("pinnacle") and home in prices and away in prices:
                    game.sharp_home_ml = prices[home]
                    game.sharp_away_ml = prices[away]
            tot = parse_event_totals(payload)
            if tot:
                game.total, game.total_over_odds, game.total_under_odds = tot
            sp = parse_event_spreads(payload, cfg["teams"], home, away)
            if sp:
                game.spread, game.spread_home_odds, game.spread_away_odds = sp
            stot = parse_event_totals(payload, only_books=SHARP_BOOKS)
            if stot:
                game.sharp_total, game.sharp_total_over_odds, \
                    game.sharp_total_under_odds = stot
            ssp = parse_event_spreads(payload, cfg["teams"], home, away,
                                      only_books=SHARP_BOOKS)
            if ssp:
                game.sharp_spread, game.sharp_spread_home_odds, \
                    game.sharp_spread_away_odds = ssp

    for prop in slate.props:
        lines = index.get((normalize_name(prop.player), prop.market))
        if lines:
            prop.lines = lines
            result.matched += 1
        else:
            result.unmatched.append(f"{prop.player} ({prop.market})")

    # The reverse gap: book-priced players with NO slate prop to land on
    # (not in a posted or projected lineup). Surface them so the caller can
    # build props straight from the book's menu — the lines exist, they're
    # real, and dropping them was leaving the board behind the books.
    matched_keys = {(normalize_name(p.player), p.market) for p in slate.props}
    for k, info in menu.items():
        if k in matched_keys:
            continue
        result.book_only.append({"player": info["player"], "market": k[1],
                                 "home": info["home"], "away": info["away"],
                                 "lines": index.get(k, [])})
    result.name_misses = _name_near_misses(slate, menu, matched_keys)

    # Append a timestamped snapshot so repeated runs build a line-movement
    # history (engine.linemoves reads it; proxy lines are skipped).
    if result.matched and not cache_only:
        # Cached prices are re-reads of an already-recorded snapshot; only a
        # paid pull carries new line-movement information.
        from ..linemoves import record_snapshots
        # The slate comes along so each row carries its game's start time:
        # this same call returns IN-PLAY prices for games already running
        # (see this function's docstring), and an in-play price must never
        # be mistaken for a closing line.
        record_snapshots(slate.props, slate=slate)

    return result
