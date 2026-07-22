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
from ..models import (
    SportsbookLine, PASS_YDS, RUSH_YDS, REC_YDS, RECEPTIONS,
)

ODDS_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"

# The Odds API market key  <->  engine market constant.
ODDS_TO_MARKET = {
    "player_pass_yds": PASS_YDS,
    "player_rush_yds": RUSH_YDS,
    "player_reception_yds": REC_YDS,
    "player_receptions": RECEPTIONS,
}
MARKET_TO_ODDS = {v: k for k, v in ODDS_TO_MARKET.items()}

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


class OddsAPIError(RuntimeError):
    pass


def get_api_key(explicit: str | None = None) -> str:
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
def list_events(api_key: str | None = None, ttl: int = 300) -> list[dict]:
    key = get_api_key(api_key)
    url = f"{ODDS_BASE}/sports/{SPORT}/events?{urllib.parse.urlencode({'apiKey': key})}"
    data, _ = _request(url, "odds_events.json", ttl=ttl)
    return data


def fetch_event_odds(event_id: str, api_key: str | None = None,
                     markets: list[str] | None = None,
                     books: list[str] | None = None,
                     ttl: int = 300) -> tuple[dict, Quota]:
    key = get_api_key(api_key)
    markets = markets or list(ODDS_TO_MARKET)
    books = books or DEFAULT_BOOKS
    params = {
        "apiKey": key,
        "regions": "us",
        "markets": ",".join(markets),
        "oddsFormat": "american",
        "bookmakers": ",".join(books),
    }
    url = f"{ODDS_BASE}/sports/{SPORT}/events/{event_id}/odds?{urllib.parse.urlencode(params)}"
    return _request(url, f"odds_event_{event_id}.json", ttl=ttl)


# --- parsing (pure; unit-tested without network) ----------------------------
def parse_event_lines(event_json: dict) -> dict[tuple[str, str], list[SportsbookLine]]:
    """Turn one event's odds payload into {(norm_player, market): [lines]}.

    Only the OVER outcome carries the odds we bet; we pair it with the matching
    UNDER price (same book, line) so the de-vig has both sides.
    """
    out: dict[tuple[str, str], list[SportsbookLine]] = {}
    for bm in event_json.get("bookmakers", []):
        book_key = bm.get("key", "")
        book = BOOK_TITLES.get(book_key, book_key)
        for mkt in bm.get("markets", []):
            market = ODDS_TO_MARKET.get(mkt.get("key", ""))
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


# --- slate integration ------------------------------------------------------
@dataclass
class OddsAttachResult:
    matched: int = 0
    unmatched: list[str] = field(default_factory=list)
    quota: Quota = field(default_factory=Quota)
    events_used: int = 0


def apply_odds_to_slate(slate, api_key: str | None = None,
                        books: list[str] | None = None,
                        ttl: int = 300) -> OddsAttachResult:
    """Replace each prop's proxy line with real book lines where available.

    Matches Odds API events to slate games by team abbreviation, then props by
    normalized player name + market. Props with no market found keep their proxy
    line and are reported in ``unmatched``.
    """
    key = get_api_key(api_key)
    result = OddsAttachResult()

    # Which team pairs are in this slate?
    slate_pairs = {frozenset((g.home, g.away)) for g in slate.games}

    events = list_events(key, ttl=ttl)
    # Build a combined line index for the events that belong to this slate.
    index: dict[tuple[str, str], list[SportsbookLine]] = {}
    for ev in events:
        home = TEAM_ABBR.get(ev.get("home_team", ""))
        away = TEAM_ABBR.get(ev.get("away_team", ""))
        if not home or not away or frozenset((home, away)) not in slate_pairs:
            continue
        payload, quota = fetch_event_odds(ev["id"], key, books=books, ttl=ttl)
        result.quota = quota
        result.events_used += 1
        for k, lines in parse_event_lines(payload).items():
            index.setdefault(k, []).extend(lines)

    for prop in slate.props:
        lines = index.get((normalize_name(prop.player), prop.market))
        if lines:
            prop.lines = lines
            result.matched += 1
        else:
            result.unmatched.append(f"{prop.player} ({prop.market})")

    return result
