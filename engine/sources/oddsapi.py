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

# MLB market keys (engine.mlb.models markets). Kept as strings to avoid an
# import cycle with the MLB package.
MLB_ODDS_TO_MARKET = {
    "batter_total_bases": "total_bases",
    "batter_hits": "hits",
    "batter_home_runs": "home_runs",
    "pitcher_strikeouts": "strikeouts",
}

# Default books to shop, matching the project vision. Keys are The Odds API's.
DEFAULT_BOOKS = [
    "draftkings", "fanduel", "betmgm", "williamhill_us",  # Caesars = William Hill US
    "espnbet", "fanatics", "hardrockbet",
]
# Pretty names for the UI / explanations.
BOOK_TITLES = {
    "draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM",
    "williamhill_us": "Caesars", "espnbet": "ESPN BET", "fanatics": "Fanatics",
    "hardrockbet": "Hard Rock",
}

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

# Per-sport wiring: The Odds API sport key, market map, and team-name map.
SPORT_CONFIG = {
    "nfl": {"sport_key": "americanfootball_nfl",
            "markets": ODDS_TO_MARKET, "teams": TEAM_ABBR},
    "mlb": {"sport_key": "baseball_mlb",
            "markets": MLB_ODDS_TO_MARKET, "teams": MLB_TEAM_ABBR},
}


class OddsAPIError(RuntimeError):
    pass


def get_api_key(explicit: str | None = None) -> str:
    load_local_secrets()  # pull ODDS_API_KEY from secrets.local if present
    key = explicit or os.environ.get("ODDS_API_KEY")
    if not key:
        raise OddsAPIError(
            "No Odds API key. Set ODDS_API_KEY in the environment or pass "
            "api_key=... — get a free key at https://the-odds-api.com."
        )
    return key


# --- name matching ----------------------------------------------------------
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b", re.I)


def normalize_name(name: str) -> str:
    """Loose key for matching player names across sources (drops punctuation,
    suffixes and casing so 'Amon-Ra St. Brown' == 'amon ra st brown')."""
    s = name.lower().replace("-", " ").replace(".", " ").replace("'", "")
    s = _SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


# --- HTTP (captures quota headers) -----------------------------------------
@dataclass
class Quota:
    remaining: str = "?"
    used: str = "?"


def _request(url: str, cache_name: str, ttl: int = 300,
             timeout: int = 30) -> tuple[object, Quota]:
    """GET JSON with a short cache. Returns (parsed_json, quota).

    The API key is only ever in the URL, never in the cache filename.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return json.loads(path.read_text()), Quota()

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
            raise OddsAPIError(f"Odds API auth/quota error {exc.code}: {detail}") from exc
        raise OddsAPIError(f"Odds API HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        if path.exists():  # fall back to stale cache when offline
            return json.loads(path.read_text()), Quota()
        raise OddsAPIError(f"Odds API request failed: {exc}") from exc

    path.write_text(body)
    return json.loads(body), quota


# --- endpoints --------------------------------------------------------------
def list_events(api_key: str | None = None, ttl: int = 300,
                sport: str = "nfl") -> list[dict]:
    key = get_api_key(api_key)
    sport_key = SPORT_CONFIG[sport]["sport_key"]
    url = f"{ODDS_BASE}/sports/{sport_key}/events?{urllib.parse.urlencode({'apiKey': key})}"
    data, _ = _request(url, f"odds_events_{sport}.json", ttl=ttl)
    return data


def fetch_event_odds(event_id: str, api_key: str | None = None,
                     markets: list[str] | None = None,
                     books: list[str] | None = None,
                     ttl: int = 300, sport: str = "nfl") -> tuple[dict, Quota]:
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
    return _request(url, f"odds_event_{event_id}.json", ttl=ttl)


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
                under_price = unders.get((player, point), -110)
                key = (normalize_name(player), market)
                out.setdefault(key, []).append(SportsbookLine(
                    book=book, line=float(point),
                    over_odds=over_price, under_odds=under_price,
                ))
    return out


def parse_event_h2h(event_json: dict, team_map: dict) -> dict[str, int]:
    """Extract the best moneyline (American odds) per team from an event payload.

    The ``h2h`` market rides in the same event-odds response as the player
    props, so this costs no extra request. For each team we keep the most
    bettor-friendly price across books (higher American odds = better payout,
    which is monotonic across the sign boundary)."""
    best: dict[str, int] = {}
    for bm in event_json.get("bookmakers", []):
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


def _modal_line(points: list[float]):
    """Most common line across books (the market consensus number)."""
    if not points:
        return None
    counts: dict[float, int] = {}
    for p in points:
        counts[p] = counts.get(p, 0) + 1
    return max(counts, key=lambda k: (counts[k], k))


def parse_event_totals(event_json: dict):
    """Return ``(line, best_over_odds, best_under_odds)`` for the game total,
    or ``None``. Uses the consensus line and the best price on each side."""
    overs: list[tuple] = []
    unders: list[tuple] = []
    for bm in event_json.get("bookmakers", []):
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


def parse_event_spreads(event_json: dict, team_map: dict, home: str, away: str):
    """Return ``(home_spread, home_odds, away_odds)`` for the spread / run line,
    or ``None``. The home team's point is the stored spread."""
    home_pts: list[tuple] = []
    away_pts: list[tuple] = []
    for bm in event_json.get("bookmakers", []):
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


def apply_odds_to_slate(slate, api_key: str | None = None,
                        books: list[str] | None = None,
                        ttl: int = 300, sport: str = "nfl") -> OddsAttachResult:
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

    # Which team pairs are in this slate?
    slate_pairs = {frozenset((g.home, g.away)) for g in slate.games}

    events = list_events(key, ttl=ttl, sport=sport)
    games_by_pair = {frozenset((g.home, g.away)): g for g in slate.games}
    # Player-prop markets plus the three game markets in one request per event.
    markets = list(cfg["markets"]) + ["h2h", "totals", "spreads"]
    # Build a combined line index for the events that belong to this slate.
    index: dict[tuple[str, str], list[SportsbookLine]] = {}
    for ev in events:
        home = cfg["teams"].get(ev.get("home_team", ""))
        away = cfg["teams"].get(ev.get("away_team", ""))
        if not home or not away or frozenset((home, away)) not in slate_pairs:
            continue
        payload, quota = fetch_event_odds(ev["id"], key, markets=markets,
                                          books=books, ttl=ttl, sport=sport)
        result.quota = quota
        result.events_used += 1
        for k, lines in parse_event_lines(payload, cfg["markets"]).items():
            index.setdefault(k, []).extend(lines)
        # Attach real game-market prices to the matching game.
        game = games_by_pair.get(frozenset((home, away)))
        if game is not None:
            mls = parse_event_h2h(payload, cfg["teams"])
            if home in mls and away in mls:
                game.home_ml = mls[home]
                game.away_ml = mls[away]
                result.moneylines += 1
            tot = parse_event_totals(payload)
            if tot:
                game.total, game.total_over_odds, game.total_under_odds = tot
            sp = parse_event_spreads(payload, cfg["teams"], home, away)
            if sp:
                game.spread, game.spread_home_odds, game.spread_away_odds = sp

    for prop in slate.props:
        lines = index.get((normalize_name(prop.player), prop.market))
        if lines:
            prop.lines = lines
            result.matched += 1
        else:
            result.unmatched.append(f"{prop.player} ({prop.market})")

    # Append a timestamped snapshot so repeated runs build a line-movement
    # history (engine.linemoves reads it; proxy lines are skipped).
    if result.matched:
        from ..linemoves import record_snapshots
        record_snapshots(slate.props)

    return result
