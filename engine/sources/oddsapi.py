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

import hashlib
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

#: THE ALTERNATE LADDERS, same four stats. A main line is hung where the
#: book thinks the coin is fair, so a calibrated probability at it sits
#: near 50% by construction and the Most Likely board — which asks for
#: 55% and a price no heavier than -250 — had nothing to show at main
#: lines (2026-09-07: 303 rows, 215 under the floor, none shown). The
#: rungs are where a 60-70% event is actually for sale. Each key is one
#: more market on every event call, billed per market per region like
#: the rest, and `CREDITS_PER_EVENT` in engine/oddsbudget carries the
#: new total. They map to the SAME engine market so a rung is priced by
#: the same projection as the main line; they are parsed apart and land
#: on `Prop.alt_lines`, never `Prop.lines`.
ALT_ODDS_TO_MARKET = {
    "player_pass_yds_alternate": PASS_YDS,
    "player_rush_yds_alternate": RUSH_YDS,
    "player_reception_yds_alternate": REC_YDS,
    "player_receptions_alternate": RECEPTIONS,
}

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

#: The oldest a cached payload may be and still price a GAME market.
#:
#: THE BUG THIS ENDS. `_request` with `cache_only` "serves the cached copy
#: at ANY age and never touches the network" — deliberately, because the
#: last paid pull's real prices beat proxies on a cycle the budget
#: declines. What nobody bounded is how old "any" gets. Ethan, 2026-09-08,
#: with his sportsbook beside our page: MIN -125 there, MIN ML -220 on our
#: Most Likely board, and the same story on a second game. Every book he
#: can bet is in `DEFAULT_BOOKS` and `parse_event_h2h` keeps the BEST
#: price per side across them, so a live payload could not have produced
#: -220 while DraftKings showed -125. The payload was old, and no field
#: anywhere carried its age.
#:
#: WHAT STALENESS COSTS, MEASURED. This box holds 5,241 college games with
#: both an OPENING and a CLOSING moneyline from one book — an opening
#: price being the extreme case of a stale one. De-vigged and compared:
#:
#:     median move 0.020 · 90th 0.066 · 99th 0.136
#:     the open and the close named a DIFFERENT favourite  3.19%
#:     moved more than ten points of win probability        3.5%
#:
#: So one game in thirty published from a stale pull shows the wrong side
#: as "most likely". On a sixteen-game Sunday that is half a game every
#: week, and Ethan's answer to that is not negotiable: "that can make us
#: give fake and false picks that can hurt us."
#:
#: SIX HOURS IS A POLICY, NOT A MEASUREMENT, and it is written here rather
#: than buried so it can be argued with. The cheap whole-slate game-lines
#: pull costs three credits (`apply_board_lines_to_slate`), so a board
#: that cannot refresh its game markets inside six hours has a budget
#: fault, and a budget fault should surface as a MISSING price — which the
#: census already knows how to say, "no real book price" — rather than as
#: a wrong one. Override on the box with QB_MAX_GAME_PRICE_AGE (seconds)
#: rather than a deploy.
def _max_game_price_age() -> float:
    import os as _os
    try:
        return float(_os.environ.get("QB_MAX_GAME_PRICE_AGE") or 6 * 3600)
    except (TypeError, ValueError):
        return 6 * 3600.0


MAX_GAME_PRICE_AGE = 6 * 3600.0


#: The same ceiling for PLAYER markets, as its own knob.
#:
#: The first cut of this (2026-09-08, earlier the same day) gated the
#: game markets and deliberately left props dated-but-served, on the
#: argument that gating them the day before the opener would empty the
#: board on a declined cycle. Ethan's answer, repeated word for word:
#: "this could be our issue with not showing picks and shit bc we are
#: pulling the wrong lines. Also that can make us give fake and false
#: picks that can hurt us." A pick is a prop. A prop priced off a
#: payload from days ago is the false pick he means, and an empty shelf
#: is the honest state of a board with no current price. So props answer
#: to a ceiling too — the same six hours by default, but a SEPARATE knob
#: (QB_MAX_PROP_PRICE_AGE), because the two are bought differently: game
#: lines refresh for three credits a slate, props for twelve a game, and
#: a box that can afford one cadence and not the other should be able to
#: say so without a deploy.
def _max_prop_price_age() -> float:
    import os as _os
    try:
        return float(_os.environ.get("QB_MAX_PROP_PRICE_AGE") or 6 * 3600)
    except (TypeError, ValueError):
        return 6 * 3600.0


MAX_PROP_PRICE_AGE = 6 * 3600.0


#: HOW OLD IS TOO OLD TO SHOW AT ALL — as against too old to BET, above.
#:
#: The ceilings above shipped 2026-09-08 as a single hard refusal at six
#: hours: past it, a game's markets and an event's player markets were
#: dropped outright. Hours later, the opener a day away:
#:
#:     "We have barely any moneylines show and barley and touchdowns
#:      shown. We need to fix that immediately."
#:
#: That is this refusal doing exactly what it was written to do, on a box
#: whose odds pull had not run inside six hours. A declined budget cycle,
#: spent credits or the pacer's own gap and EVERY game line and EVERY
#: touchdown quote disappears at once.
#:
#: THE ERROR WAS CONFLATING TWO QUESTIONS. A price from this morning is
#: not a WRONG price — it is a real quote that may have moved, and the
#: card already carries its age (`price_age_s`, drawn as a chip). "Too
#: old to stake" and "too old to put on the page" are different bars, and
#: collapsing them turned a labelling problem into an empty board, which
#: is its own way of being useless.
#:
#: So there are two now. Inside MAX_*_PRICE_AGE a row is FRESH and may be
#: recommended. Between that and this, the row SHOWS, carries its age,
#: and is marked `price_stale` so nothing downstream can present it as a
#: current recommendation. Past this, the number is too old to mean
#: anything about tonight and is dropped as before.
#:
#: Forty-eight hours because a line two days old is still recognisably
#: this week's market — Week 1 prices are hung on the Monday — while a
#: number older than that is describing a different injury report.
#: QB_MAX_GAME_PRICE_SHOW_AGE / QB_MAX_PROP_PRICE_SHOW_AGE override.
def _max_game_price_show_age() -> float:
    import os as _os
    try:
        return float(_os.environ.get("QB_MAX_GAME_PRICE_SHOW_AGE") or 48 * 3600)
    except (TypeError, ValueError):
        return 48 * 3600.0


def _max_prop_price_show_age() -> float:
    import os as _os
    try:
        return float(_os.environ.get("QB_MAX_PROP_PRICE_SHOW_AGE") or 48 * 3600)
    except (TypeError, ValueError):
        return 48 * 3600.0


MAX_GAME_PRICE_SHOW_AGE = 48 * 3600.0
MAX_PROP_PRICE_SHOW_AGE = 48 * 3600.0

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
    # "scorers" are the Yes/No markets (anytime TD) requested alongside the
    # over/under props. BILLING: each entry is one more market on every
    # event call — the API bills per market per region — so adding one
    # raises an NFL event pull from 7 to 8 credits. Priced in on purpose:
    # the TD board cannot exist without the quote (see _long_shots).
    "nfl": {"sport_key": "americanfootball_nfl",
            "markets": ODDS_TO_MARKET, "teams": TEAM_ABBR,
            "scorers": SCORER_ODDS_TO_MARKET,
            "alternates": ALT_ODDS_TO_MARKET},
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
    # COLLEGE FOOTBALL PRICES THE SAME FOUR PLAYER MARKETS THE NFL DOES,
    # under the same Odds API keys, because it is the same sport. It was
    # "full-game markets only" here until 2026-09-03 — which is not a bug
    # anyone introduced, it is a layer nobody had built: no college
    # yardage projection existed to price a quote against, so buying one
    # would have been paying for a number with nothing to compare it to.
    # `engine/cfb/props.py` and `engine/rankfit`'s college walk closed
    # that, and this is the feed catching up.
    #
    # BILLING, WHICH IS THE WHOLE REASON THIS IS NOT SIMPLY THE NFL'S
    # ENTRY: the meter charges per market per region on every event call,
    # and a college Saturday is sixty games where an NFL Sunday is
    # sixteen. Listing the markets here does NOT authorise a slate-wide
    # pull — nothing in this module walks a whole board of events for
    # player props; `cfb_build.attach_player_quotes` picks the games and
    # `oddsbudget.affordable_events` sets how many it may pick.
    #
    # The team map stays EMPTY on purpose. It is built at run time from
    # the ESPN feed instead — 134 schools is the kind of table that rots
    # the moment a conference reshuffles — and `apply_odds_to_slate`
    # prefers a slate's own team names over this table for exactly that
    # reason (see the WNBA note below). cfb_build passes the map it
    # derived into the parsers.
    "cfb": {"sport_key": "americanfootball_ncaaf",
            "markets": ODDS_TO_MARKET, "teams": {},
            "scorers": SCORER_ODDS_TO_MARKET,
            "alternates": ALT_ODDS_TO_MARKET},
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
    """The key to spend next: the SMALLEST live balance on the ring.

    Ethan, 2026-08-14, holding one 5,284-credit key and one 100,000-credit
    key: "use up the small key first."

    That was already happening, but only by accident — the ring is ordered
    by environment variable (``ODDS_API_KEY``, then ``_2``, ``_3``) and the
    small key happened to be the primary. Swap the two values and the
    behaviour silently inverts, draining the big plan while a nearly-empty
    one sits untouched. A preference nobody stated is a preference nobody
    can rely on, so it is a rule now.

    WHY SMALLEST-FIRST IS THE RIGHT POLICY. Plans refill on their own
    monthly cycles and a part-used small plan is the perishable one: credits
    left on it at the reset are gone. Draining it first converts the whole
    ring into "the big plan, plus whatever the small ones still had".

    A key we have never called is NOT spent — unknown is not zero — but it
    is also not known to be small, so it sorts after every measured key and
    behind ring order. That costs one cycle at most: `record_quota` writes a
    balance for every key the moment it is used, so a fresh ring follows
    environment order once and is sorted by real balances thereafter.

    If every key is known to be empty this still returns the first, so the
    caller gets the API's own "out of credits" answer rather than a guess
    from a state file that may be a month stale.
    """
    ring = api_keys(explicit)
    if not ring:
        raise OddsAPIError(
            "No Odds API key. Set ODDS_API_KEY in the environment or in "
            "secrets.local (ODDS_API_KEY_2, _3 … add spares) — get a free "
            "key at https://the-odds-api.com."
        )
    try:
        from ..oddsbudget import key_is_spent, key_state
        live = [k for k in ring if not key_is_spent(k)]
        if not live:
            return ring[0]

        def _rank(item):
            i, k = item
            rem = key_state(k).get("remaining")
            # float("inf") for an unmeasured key: it goes last among live
            # keys, and ring position breaks every tie.
            return (float("inf") if rem is None else float(rem), i)

        return min(((i, k) for i, k in enumerate(live)), key=_rank)[1]
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
    # BOTH APOSTROPHES. U+2019 (the typographic one) survives NFKD, so a
    # feed that writes "A\u2019ja Wilson" never joined a feed that writes
    # "A'ja Wilson" — the straight one was stripped and the curly one was
    # not, leaving "aja wilson" against "a\u2019ja wilson". That is why 100
    # of 105 stored WNBA photos still drew initials on 2026-08-10: the
    # ingest was fine and the JOIN was not. Same failure was waiting for
    # every O'Neale, D'Angelo and Ja'Marr on the other boards.
    s = s.lower().replace("-", " ").replace(".", " ")
    s = s.replace("'", "").replace("\u2019", "").replace("\u02bc", "")
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
    """Upcoming events for a sport. FREE — event lists do not count against
    the credit quota, which is what makes the fallback below affordable.

    AN EMPTY CACHED LIST IS A MISS, NOT AN ANSWER, and that distinction is
    the whole bug this fixes. `cache_only` serves a cached copy at ANY age
    and only raises when the file is absent — so an empty list is returned
    happily forever. For a sport with a continuous season that is harmless;
    for UFC it is fatal:

      * between cards — most of any week — this endpoint legitimately
        returns [], and that [] gets cached;
      * every later read is `cache_only`, gets the stale [], and never goes
        to the wire, because [] is not an exception;
      * `ufc_dossiers.card_fighters` therefore finds no fighters, the
        auto-drafter returns early, and no dossier is ever written;
      * when a card finally is priced, every bout hits "no dossier, no bet".

    Measured: a thirty-day-old empty file was served without complaint.
    Two cards in a row produced no bets and no data, which is exactly what
    that chain does. It is the same knot `refresh_ufc` untied for the BUILD
    — a thing that can only be read from a cache nothing seeds — left tied
    on the event list.

    So: entries in the cache are trusted; an empty one goes to the wire. A
    caller asking for cache_only is asking not to SPEND, and this costs
    nothing.
    """
    key = get_api_key(api_key)
    sport_key = SPORT_CONFIG[sport]["sport_key"]
    url = f"{ODDS_BASE}/sports/{sport_key}/events?{urllib.parse.urlencode({'apiKey': key})}"
    if cache_only:
        try:
            data, _ = _request(url, f"odds_events_{sport}.json", ttl=ttl,
                               cache_only=True)
            if data:
                return data
        except OddsAPIError:
            pass                      # nothing cached — same as an empty one
        try:
            data, _ = _request(url, f"odds_events_{sport}.json", ttl=ttl)
            return data
        except OddsAPIError:
            return []                 # offline: an empty card, as before
    data, _ = _request(url, f"odds_events_{sport}.json", ttl=ttl,
                       cache_only=False)
    return data


def fetch_sport_odds(sport: str, api_key: str | None = None,
                     markets: list[str] | None = None,
                     books: list[str] | None = None,
                     ttl: int = 600, cache_only: bool = False,
                     cache_tag: str = "") -> tuple[list, Quota]:
    """Every game's full-game lines in ONE request.

    The event-scoped endpoint above costs a request per game, which is the
    right trade for player props (they only exist per event). Full-game
    markets don't: this endpoint returns h2h/spreads/totals for the whole
    board for the price of one call per market. On a 60-game college
    Saturday that is the difference between three credits and sixty, and
    the budget pacer would simply never authorise sixty.

    ``cache_tag`` separates callers asking for DIFFERENT market sets. The
    cache is keyed by sport alone, so a one-market live pull and a
    three-market board pull would otherwise overwrite each other: the
    board would read back a payload with no spreads or totals in it and
    conclude the books had stopped posting them. Callers narrowing the
    market list must pass a tag.
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
    name = f"odds_board_{sport}{('_' + cache_tag) if cache_tag else ''}.json"
    data, quota = _request(url, name, ttl=ttl, cache_only=cache_only)
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
    # THE CACHE NAME CARRIES WHAT THE REQUEST ASKED FOR, and it did not.
    # Two failures shared one filename:
    #
    #   * A NARROWED MARKET LIST cached under the same key as a full one
    #     serves the narrow payload back to the full request for the rest
    #     of the TTL — a board reading it concludes the books stopped
    #     posting the markets it never asked for. `fetch_sport_odds` has
    #     guarded this with `cache_tag` since the live pull and the board
    #     pull started disagreeing, and `oddshistory` with an md5; this
    #     endpoint never did, because until college football pulled TWO
    #     different market sets per event no caller made two different
    #     requests for the same event.
    #
    #   * THE SPORT WAS MISSING, so `_classify`'s attribution loop — it
    #     scans the cache name for a league token — found none and
    #     journalled every event-scoped call ever made under sport "".
    #     Every credit spent on player props, in any league, unattributed.
    #
    # A stable digest rather than the market list itself: the list is
    # long, the filename is not, and the request is what has to be
    # distinguished rather than described.
    return _request(url, event_cache_name(event_id, markets, books, sport),
                    ttl=ttl, cache_only=cache_only)


def event_cache_name(event_id: str, markets: list[str] | None = None,
                     books: list[str] | None = None,
                     sport: str = "nfl") -> str:
    """The cache filename one event-odds request writes and reads.

    ONE DEFINITION, because a second reader now needs it.
    `event_cache_age` below answers "how old is the payload this call
    would serve", and it can only answer honestly by naming the same
    file `fetch_event_odds` names. Re-deriving the digest at the call
    site would work until the day one of the two changed.
    """
    markets = markets or list(SPORT_CONFIG[sport]["markets"])
    books = books or DEFAULT_BOOKS
    spec = ",".join(sorted(markets)) + "|" + ",".join(sorted(books))
    tag = hashlib.md5(spec.encode()).hexdigest()[:8]
    return f"odds_event_{sport}_{event_id}_{tag}.json"


def sport_cache_age(sport: str = "nfl", cache_tag: str = "",
                    now: float | None = None) -> float | None:
    """Seconds since the whole-slate odds payload was written, or None.

    The board-level twin of `event_cache_age`: `fetch_sport_odds` writes
    one file for the entire slate, so one age dates every game price that
    pull attached.
    """
    path = CACHE_DIR / f"odds_board_{sport}{('_' + cache_tag) if cache_tag else ''}.json"
    try:
        return max(0.0, (now if now is not None else time.time())
                   - path.stat().st_mtime)
    except OSError:
        return None


def price_is_current(age: float | None, now_max: float | None = None) -> bool:
    """May a payload this old price a GAME market? See MAX_GAME_PRICE_AGE.

    An age of None is a payload that was just fetched (nothing cached to
    date), which is current by construction — the caller has the bytes in
    hand.
    """
    if age is None:
        return True
    return float(age) <= (now_max if now_max is not None else _max_game_price_age())


def price_is_showable(age: float | None, now_max: float | None = None) -> bool:
    """May a payload this old go on the page AT ALL?

    The wider of the two ceilings — see MAX_GAME_PRICE_SHOW_AGE. A row
    between this and `price_is_current` shows with its age on it and is
    marked `price_stale`; past this it is dropped.
    """
    if age is None:
        return True
    return float(age) <= (now_max if now_max is not None
                          else _max_game_price_show_age())


def event_cache_age(event_id: str, markets: list[str] | None = None,
                    books: list[str] | None = None, sport: str = "nfl",
                    now: float | None = None) -> float | None:
    """Seconds since this event's cached payload was written, or None.

    `_request` with ``cache_only`` "serves the cached copy at ANY age and
    never touches the network", which is the whole point of the free tier
    — the last paid pull's real prices beat proxies. What it costs is the
    ability to tell a price that is WRONG from a price that is OLD, and
    Ethan has now hit that twice:

      2026-09-03  "The lines on the most likely best bet page ... are
                  completely wrong so we are giving bad bets."  The
                  arithmetic checked out end to end; the board simply
                  could not say the prices were three hours behind.
      2026-09-04  "Cam Edward's ... has a -300 line too score a touchdown
                  but on our site we are showing -155."

    The board-level `priced_at` stamp dates the last PULL. It does not
    date the quote beside a row: college buys player markets for at most
    `cfb_build.PLAYER_EVENT_CAP` games a cycle, ordered by attention
    tier, and every other game keeps whatever the last pull that reached
    it left on disk. This is how old that actually is.

    None when nothing is cached — an unpriceable game and a stale one are
    different facts and must not share an answer.
    """
    path = CACHE_DIR / event_cache_name(event_id, markets, books, sport)
    try:
        return max(0.0, (now if now is not None else time.time())
                   - path.stat().st_mtime)
    except OSError:
        return None


# --- parsing (pure; unit-tested without network) ----------------------------
def parse_event_lines(event_json: dict,
                      market_map: dict | None = None) -> dict[tuple[str, str], list[SportsbookLine]]:
    """Turn one event's odds payload into {(norm_player, market): [lines]}.

    Only the OVER outcome carries the odds we bet; we pair it with the matching
    UNDER price (same book, line) so the de-vig has both sides. ``market_map``
    selects the sport's Odds-API market keys (defaults to NFL).

    Reference-only books are left out: nobody here can bet them, so their
    lines must never be shopped as "the price to take". Their pair is read
    out separately by :func:`parse_event_sharp_lines`."""
    return _parse_lines(event_json, market_map, sharp=False)


def parse_event_sharp_lines(event_json: dict,
                            market_map: dict | None = None) -> dict[tuple[str, str], list[SportsbookLine]]:
    """The SHARP book's prop pairs, ``{(norm_player, market): [lines]}``.

    The same shape as :func:`parse_event_lines` and the same pairing,
    from the books that one skips. A sharp two-sided quote at a line is
    the anchor `betting.evaluate_prop` prices a soft book's number
    against — one book disagreeing with a sharper one, no model in it —
    exactly what `oddsapi` attaches to a `Game` as ``sharp_*`` for the
    game markets and what the football boards stake there. Empty when
    the sharp book quoted no props in the event, which is the common case
    outside the main markets: nothing changes, the model card prices."""
    return _parse_lines(event_json, market_map, sharp=True)


def _parse_lines(event_json: dict, market_map: dict | None,
                 sharp: bool) -> dict[tuple[str, str], list[SportsbookLine]]:
    market_map = market_map or ODDS_TO_MARKET
    out: dict[tuple[str, str], list[SportsbookLine]] = {}
    for bm in event_json.get("bookmakers", []):
        book_key = bm.get("key", "")
        if (book_key in SHARP_BOOKS) != sharp:
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


def consensus_h2h_fair(event_json: dict, team_map: dict) -> dict[str, float]:
    """``{team abbr: de-vigged fair}`` from REAL two-sided pairs.

    THE PAIR WE PUBLISH IS NOT A PAIR ANY BOOK POSTS. `parse_event_h2h`
    keeps the best price per SIDE across the field, which is the right
    number to bet — you can take each side at its own book — and the
    wrong number to de-vig, because the two halves come from different
    books and the hold between them is not any book's hold.

    MEASURED on this box's 11,366 college games with two or more books
    quoting both sides (median eleven books a game):

        hold on one book's own pair        3.64%
        hold on the shopped pair           0.67%
        shopped pair is an ARBITRAGE       24.4% of games
        de-vigged P differs from a real book's by
          more than 1 point                28.4% of games
          more than 2 points                7.9%

    A quarter of the time the "market implied" number on the card was
    de-vigged from a pair that sums to less than one — a fiction, and
    the number the football boards RANK moneylines on
    (`likely.GAME_RANK_MARKET`). Worse, that figure (0.722) was measured
    against the SCHEDULE's single consensus pair, so production was
    ranking on a different quantity than the one measured.

    So: de-vig each book's own pair, take the median per side, and
    renormalise. The median rather than the mean because one stale book
    should move a consensus by nothing. `{}` when no single book quoted
    both sides, and the caller then keeps what it had.

    WHAT THIS IS NOT: steadier. On a two-book field the median is their
    mean and on a three-book field it snaps to the middle one, so adding
    a book can move it several points — measured at three, against a
    tenth of one for the shopped number on the same pair. The case for
    it is not variance, it is BIAS: every book added can only thin the
    shopped pair (it is a max per side), so that error grows with the
    size of the payload rather than describing the game, while this one
    is sampling noise on real quotes. A number the board ranks on can
    survive noise; it cannot survive a bias that moves with how many
    books the pull happened to return.

    THE SHARP BOOK IS LEFT OUT, and not because its number is worse — it
    is better. It has its own path (`gamebets.price_moneyline_sharp`)
    where the soft price is priced AGAINST it, and folding it into the
    consensus would make the anchor and the thing it anchors share a
    number.
    """
    import statistics
    from ..odds import devig_two_way
    per: dict[str, list[float]] = {}
    for bm in event_json.get("bookmakers", []):
        if bm.get("key", "") in SHARP_BOOKS:
            continue
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            priced: dict[str, int] = {}
            for o in mkt.get("outcomes", []):
                abbr = team_map.get(o.get("name", ""))
                price = o.get("price")
                if abbr and price is not None:
                    priced[abbr] = int(price)
            if len(priced) != 2:
                continue           # one-sided: nothing to de-vig against
            (a, oa_), (b, ob) = sorted(priced.items())
            try:
                fa, fb = devig_two_way(oa_, ob)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            per.setdefault(a, []).append(float(fa))
            per.setdefault(b, []).append(float(fb))
    # Empty or complete, never half: the loop above only records a book
    # that mapped EXACTLY two sides, so a partial market cannot reach
    # here. Written as the emptiness test it actually is rather than a
    # count that looks like it is guarding a third state.
    if not per:
        return {}
    med = {t: statistics.median(v) for t, v in per.items()}
    total = sum(med.values())
    if total <= 0:
        return {}
    return {t: v / total for t, v in med.items()}


def best_h2h_books(event_json: dict, team_map: dict) -> dict[str, str]:
    """``{team abbr: book title}`` — WHO is offering the price we show.

    `parse_event_h2h` keeps the best price per side across the books we
    request, which is the right number to publish and, until now, a
    number with no name on it. The card said "best", so a reader holding
    his phone could not check our -125 against the book that is actually
    posting it. Ethan, 2026-09-08: "I don't want you too stop working
    until we display the right lines and prices the books show."

    Same rule as the price it names, or the name would be a lie: the
    sharp reference is skipped (nobody here can bet it), ties go to the
    first book seen, and a team with no quote gets no entry.
    """
    best: dict[str, tuple[int, str]] = {}
    for bm in event_json.get("bookmakers", []):
        key = bm.get("key", "")
        if key in SHARP_BOOKS:
            continue
        title = BOOK_TITLES.get(key, key)
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            for o in mkt.get("outcomes", []):
                abbr = team_map.get(o.get("name", ""))
                price = o.get("price")
                if not abbr or price is None:
                    continue
                price = int(price)
                if abbr not in best or price > best[abbr][0]:
                    best[abbr] = (price, title)
    return {abbr: title for abbr, (_p, title) in best.items()}


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
                    # The display name rides along: the college build keys
                    # its quotes by the normalised name and needs the real
                    # one back to journal and settle a stale flag.
                    {"book": book, "yes_odds": y, "no_odds": no.get(player),
                     "player": player})
    return out


def best_scorer_price(quotes: list[dict]) -> dict | None:
    """Most bettor-friendly quote across books (highest Yes payout).

    A CORRUPT PRICE IS NOT SHOPPED, and this `max` is exactly the shape
    that selects for one. American odds cannot fall strictly between -100
    and +100, and a number inside that gap is by construction better than
    any real price on its side of even money — so a -97 beats the -105 it
    is a corruption of, wins the board, and books the smaller implied
    probability it carries as edge the model never found.

    `engine.odds.best_over_line` was taught this on 2026-08-30 and this
    function was missed, which left the whole scorer-prop path — every
    anytime-touchdown quote in BOTH football leagues — shopping
    unguarded. If nothing survives the filter there is no real market
    here, and the caller's existing `is None` branch is the right answer.

    A PRICE NOBODY HERE CAN TAKE IS NOT SHOPPED EITHER. `parse_event_
    scorers` — alone among the price parsers in this module — does not
    drop the sharp reference, because `devig.board_fair` wants it: the
    fair is the MEDIAN de-vigged price across books, and a sharp book
    belongs in that median. It does not belong in this `max`. A sharp
    book runs a thinner margin, so on a favourite its price is by
    construction the highest American number on the board and wins the
    shop outright — and then the card prints, and `likely.HEAVIEST_PRICE`
    measures, a number at a book that does not take US action.

    Falls back to the full field when nothing bettable survives, the
    same doctrine as the dead-zone filter: a market where every quote is
    unusable still returns the price to display, and the caller decides
    what to do with it. Returning None there would drop the player, and
    a dropped player reads as a market nobody quoted.
    """
    from ..odds import (OUTLIER_GAP, american_to_prob, field_outliers,
                        is_quotable, is_sharp_book)
    clean = [q for q in (quotes or []) if is_quotable(q.get("yes_odds"))]
    if not clean:
        return None
    bettable = [q for q in clean if not is_sharp_book(q.get("book"))]
    field = bettable or clean
    # AND A PRICE OFF THE FIELD IS NOT SHOPPED — the third refusal with
    # the same shape, and the one Ethan's report was actually about
    # (odds.OUTLIER_GAP: Hard Rock -155 under three books at -260 to
    # -280). The refused quotes ride along on the winner as `refused`,
    # with the gap in points, so the card can say which book was left
    # out and why rather than silently printing a different number.
    flags = field_outliers([q["yes_odds"] for q in field])
    kept = [q for q, bad in zip(field, flags) if not bad]
    refused = []
    for q, bad in zip(field, flags):
        if not bad:
            continue
        others = sorted(american_to_prob(int(x["yes_odds"])) for x in field if x is not q)
        m = len(others)
        med = others[m // 2] if m % 2 else (others[m // 2 - 1] + others[m // 2]) / 2.0
        refused.append({"book": q.get("book", ""), "yes_odds": int(q["yes_odds"]),
                        "gap_pts": round(100.0 * (med - american_to_prob(int(q["yes_odds"]))), 1)})
    best = max(kept or field, key=lambda q: q["yes_odds"])
    if refused:
        best = {**best, "refused": refused}
    return best


def _modal_line(points: list[float]):
    """Most common line across books (the market consensus number)."""
    if not points:
        return None
    counts: dict[float, int] = {}
    for p in points:
        counts[p] = counts.get(p, 0) + 1
    return max(counts, key=lambda k: (counts[k], k))


def _total_quotes(event_json: dict, only_books: set | None = None):
    """The game total's quotes as ``(overs, unders)``, each
    ``[(point, price, book title)]`` in payload order.

    One walk, two readers: :func:`parse_event_totals` takes the numbers
    and :func:`best_total_books` takes the name beside them. Written as
    one function on purpose — a second walk written to name the book
    could pick a different book than the walk that picked the price, and
    a card that shows the right number under the wrong book's name is
    the exact failure this work exists to end.
    """
    overs: list[tuple] = []
    unders: list[tuple] = []
    for bm in event_json.get("bookmakers", []):
        bk = bm.get("key", "")
        if (bk in SHARP_BOOKS) if only_books is None else (bk not in only_books):
            continue
        title = BOOK_TITLES.get(bk, bk)
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "totals":
                continue
            for o in mkt.get("outcomes", []):
                name = (o.get("name") or "").lower()
                pt, pr = o.get("point"), o.get("price")
                if pt is None or pr is None:
                    continue
                (overs if name == "over" else unders).append(
                    (float(pt), int(pr), title))
    return overs, unders


def _spread_quotes(event_json: dict, team_map: dict, home: str, away: str,
                   only_books: set | None = None):
    """The spread's quotes as ``(home_pts, away_pts)``, each
    ``[(point, price, book title)]`` in payload order. Shared by
    :func:`parse_event_spreads` and :func:`best_spread_books` for the
    reason given on :func:`_total_quotes`."""
    home_pts: list[tuple] = []
    away_pts: list[tuple] = []
    for bm in event_json.get("bookmakers", []):
        bk = bm.get("key", "")
        if (bk in SHARP_BOOKS) if only_books is None else (bk not in only_books):
            continue
        title = BOOK_TITLES.get(bk, bk)
        for mkt in bm.get("markets", []):
            if mkt.get("key") != "spreads":
                continue
            for o in mkt.get("outcomes", []):
                abbr = team_map.get(o.get("name", ""))
                pt, pr = o.get("point"), o.get("price")
                if not abbr or pt is None or pr is None:
                    continue
                if abbr == home:
                    home_pts.append((float(pt), int(pr), title))
                elif abbr == away:
                    away_pts.append((float(pt), int(pr), title))
    return home_pts, away_pts


def _best_book(quotes) -> str:
    """Which book posts the best price among ``(price, title)`` pairs.

    Same rule as the number it names, or the name would be a lie:
    strictly greater wins, so ties go to the first book the payload
    listed, exactly as ``max`` picks the first maximal price. An empty
    list — a side no book posted at the published line — gets NO name,
    because the price shown there is the parsers' -110 fallback and no
    book is offering it.
    """
    best: int | None = None
    title = ""
    for price, name in quotes:
        if best is None or price > best:
            best, title = price, name
    return title


def best_total_books(event_json: dict) -> dict[str, str]:
    """``{"over"/"under": book title}`` — WHO is posting the total we show.

    The moneyline learned to say this first (`best_h2h_books`); the
    spread and the total kept publishing a shopped price with no name on
    it, which is the same defect one market over. Ethan, 2026-09-08: "I
    don't want you too stop working until we display the right lines and
    prices the books show."

    Read off the SAME quotes `parse_event_totals` prices from, at the
    same published line, so the name and the number cannot come apart. A
    side with no quote at that line is absent rather than guessed.
    """
    overs, unders = _total_quotes(event_json)
    line = _modal_line([p for p, _pr, _bk in overs])
    if line is None:
        return {}
    out = {}
    over = _best_book([(pr, bk) for p, pr, bk in overs if p == line])
    under = _best_book([(pr, bk) for p, pr, bk in unders if p == line])
    if over:
        out["over"] = over
    if under:
        out["under"] = under
    return out


def best_spread_books(event_json: dict, team_map: dict,
                      home: str, away: str) -> dict[str, str]:
    """``{team abbr: book title}`` — WHO is posting the spread we show.

    The away side is looked up at ``-line``, the same mirror
    `parse_event_spreads` prices it at: a book quoting the home team
    -3.5 quotes the away team +3.5, and a book that has moved off the
    consensus number posts neither, so it names nothing here either.
    """
    home_pts, away_pts = _spread_quotes(event_json, team_map, home, away)
    line = _modal_line([p for p, _pr, _bk in home_pts])
    if line is None:
        return {}
    out = {}
    h = _best_book([(pr, bk) for p, pr, bk in home_pts if p == line])
    a = _best_book([(pr, bk) for p, pr, bk in away_pts if p == -line])
    if h:
        out[home] = h
    if a:
        out[away] = a
    return out


def parse_event_totals(event_json: dict, only_books: set | None = None):
    """Return ``(line, best_over_odds, best_under_odds)`` for the game total,
    or ``None``. Uses the consensus line and the best price on each side.

    Sharp reference books are excluded from the bettable aggregate;
    ``only_books`` (API keys) restricts to those books instead — that's how
    the sharp book's own pair is read out as the fair-value anchor."""
    overs, unders = _total_quotes(event_json, only_books)
    line = _modal_line([p for p, _pr, _bk in overs])
    if line is None:
        return None
    over_odds = max((pr for p, pr, _bk in overs if p == line), default=-110)
    under_odds = max((pr for p, pr, _bk in unders if p == line), default=-110)
    return line, over_odds, under_odds


def parse_event_spreads(event_json: dict, team_map: dict, home: str, away: str,
                        only_books: set | None = None):
    """Return ``(home_spread, home_odds, away_odds)`` for the spread / run line,
    or ``None``. The home team's point is the stored spread. Sharp books are
    excluded unless ``only_books`` selects them explicitly."""
    home_pts, away_pts = _spread_quotes(event_json, team_map, home, away, only_books)
    line = _modal_line([p for p, _pr, _bk in home_pts])
    if line is None:
        return None
    home_odds = max((pr for p, pr, _bk in home_pts if p == line), default=-110)
    away_odds = max((pr for p, pr, _bk in away_pts if p == -line), default=-110)
    return line, home_odds, away_odds


# --- slate integration ------------------------------------------------------
@dataclass
class OddsAttachResult:
    matched: int = 0
    unmatched: list[str] = field(default_factory=list)
    # Scorer (Yes/No) props that got a real book quote — anytime TD.
    # Counted apart from `matched`, and their misses stay OUT of
    # `unmatched`: books quote touchdowns for a dozen skill players a
    # game, not a roster, so an unquoted TD prop is the ordinary case
    # and listing hundreds of them would bury the yardage diagnostics
    # this list exists for.
    scorers_matched: int = 0
    quota: Quota = field(default_factory=Quota)
    events_used: int = 0
    moneylines: int = 0          # games that got real h2h prices attached
    from_cache: bool = False     # prices reused from the last paid pull
    #: Games whose GAME markets were REFUSED for age — past
    #: MAX_GAME_PRICE_SHOW_AGE, so nothing off that payload reaches the
    #: page — and the oldest age refused.
    stale_game_prices: int = 0
    stale_price_age_s: float = 0.0
    #: Games priced from a payload between MAX_GAME_PRICE_AGE and
    #: MAX_GAME_PRICE_SHOW_AGE: SHOWN, marked `price_stale`, and never
    #: recommended. Counted apart from the refusals because a build note
    #: that adds the two together says "kept NO price" about games whose
    #: price is on the board — see `Game.price_stale`.
    shown_stale_game_prices: int = 0
    shown_stale_price_age_s: float = 0.0
    #: Events whose PLAYER markets were refused for age
    #: (MAX_PROP_PRICE_AGE) — no line, ladder, menu entry or scorer quote
    #: was indexed off them — and the oldest such payload.
    stale_prop_events: int = 0
    stale_prop_age_s: float = 0.0
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
    # How many of those were RECOVERED by the loose first-initial+surname
    # fallback. Counted separately from `matched` so a rise here is
    # visible: it means the exact name map is drifting, and the fallback
    # is a safety net rather than a licence to stop maintaining it.
    loose_matched: int = 0
    # Events the book HAS and we could not place on our slate. Every one of
    # these is a whole game's worth of prices we never looked at, and its
    # props are indistinguishable downstream from props the book never
    # priced. Each entry: {reason, home, away, …}.
    dropped_events: list = field(default_factory=list)
    # Events for a DIFFERENT day. list_events has no date filter, so a
    # four-game slate is matched against every upcoming fixture. Counted,
    # never reported as a fault — they are supposed to miss.
    other_day_events: int = 0
    #: Events refused because they are the OTHER meeting of the same two
    #: teams — see `_same_meeting`. Counted rather than swallowed: a
    #: rematch quietly relabelled onto this week's game is the wrong
    #: price wearing the right team's name, which is the hardest kind of
    #: wrong number to notice.
    reversed_events: int = 0
    # Events that DID place on the slate but had no cached payload, in
    # cache_only mode. Without this a cached rebuild looks identical whether
    # the join improved or not: the events match, then vanish one line later
    # because nobody ever paid for them.
    cache_misses: int = 0
    # Props that received an alternate ladder (`Prop.alt_lines`), and
    # cached rebuilds that were served the last paid pull's BASE-market
    # payload because no payload with the ladder existed yet — the
    # deploy-day case, see the fallback in `apply_odds_to_slate`.
    alt_matched: int = 0
    alt_fallback: int = 0


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


def _name_near_misses(slate, menu: dict, matched_keys: set,
                      recovered: set | None = None) -> list[dict]:
    """Slate props and book lines that are almost certainly the same player
    but whose exact keys didn't join.

    This is the difference between "the book never offered this market"
    (fine, expected — we project more players than books post) and "we paid
    for this price and threw it away" (a bug). Only the second kind belongs
    in anyone's attention.

    TWO THINGS THIS NO LONGER CLAIMS.

    `recovered` is the props the loose fallback already joined. Reporting
    those as misses is reporting a bug that has been fixed, every cycle,
    for as long as the two names disagree.

    And a loose key with SEVERAL book candidates is not a near miss at
    all. Measured 2026-08-22: this told Ethan that "Enrique Hernández" and
    "Elieser Hernández" were "almost certainly the same player" and that
    the fix was the name map. They are two different major leaguers. Doing
    what it said would have attached one man's prices to the other's
    projections — a bet at a number nobody offered, arrived at by
    following the tool's own advice."""
    by_loose: dict[str, list] = {}
    for (nkey, market), info in menu.items():
        if (nkey, market) in matched_keys:
            continue
        by_loose.setdefault(f"{_name_key_loose(info['player'])}|{market}", []).append(info["player"])
    out: list[dict] = []
    seen = recovered or set()
    for p in slate.props:
        if (normalize_name(p.player), p.market) in menu:
            continue                       # matched exactly — nothing to see
        if (normalize_name(p.player), p.market) in seen:
            continue                       # the loose fallback already got it
        cands = by_loose.get(f"{_name_key_loose(p.player)}|{p.market}")
        if not cands or len(set(cands)) != 1:
            # None: the book never priced this player. Several: a shared
            # first initial and surname, which is evidence of nothing.
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


def _slate_days(games) -> set[str]:
    """The calendar days this slate covers, a day either side.

    Both odds paths match against a list the endpoint returns with NO date
    filter — every upcoming fixture for the sport — so a four-game slate is
    matched against tomorrow's and Thursday's games too. Those are not on
    our slate and are not supposed to be.

    A day either side because kickoffs are UTC and a 7pm Eastern tip is
    already tomorrow there.

    AND IT READ `kickoff`, WHICH FOOTBALL DOES NOT DATE. An NFL game's
    kickoff is a bare Eastern clock — "20:20" — with the date two keys
    away in `date`, exactly as `ledger._kickoff_map` had to discover for
    the capture-lag stamp. Sliced to ten characters that is five, so
    every football game was skipped, `slate_days` came back EMPTY, and
    `_other_day` answers False for everything when it is: the filter was
    inert on both football paths for the whole season.

    That is what let a season-long payload put Week 12's prices on a
    Week 1 card. See `_same_meeting` for the other half of it.
    """
    import datetime as _dt
    out: set[str] = set()
    for g in games:
        k = str(getattr(g, "kickoff", "") or "")[:10]
        if len(k) != 10:
            # THE DATE, when the clock does not carry one.
            k = str(getattr(g, "date", "") or "")[:10]
        if len(k) != 10:
            continue
        try:
            d = _dt.date.fromisoformat(k)
        except ValueError:
            continue
        out |= {(d + _dt.timedelta(days=n)).isoformat() for n in (-1, 0, 1)}
    return out


def _other_day(ev, slate_days: set[str]) -> bool:
    """Is this event for a day our slate does not cover?

    ONE DEFINITION, TWO CALLERS. Reporting another day's game as a drop
    turns a correct result into three alarming lines, which is how a
    diagnostic stops being read — and a second copy of that rule is a
    second place for it to be got wrong. The board-lines path started life
    with its own inline copy and this is that copy, pulled up.
    """
    c = str(ev.get("commence_time") or "")[:10]
    return bool(slate_days) and len(c) == 10 and c not in slate_days


def _same_meeting(ev_home: str, ev_away: str, game) -> bool:
    """Is this event the same MEETING of these two teams as `game`?

    THE BUG THIS EXISTS FOR, found on 2026-09-09 with Week 1 hours away.
    Both odds paths look a game up by `frozenset((home, away))`, which is
    orientation-blind on purpose — it does not care which side of the
    pair the endpoint calls home. In a league where two teams meet ONCE
    that is harmless. The NFL plays its division rivals twice, home and
    away, and the endpoint returns every fixture of the season in one
    payload, so the September game and the November rematch are both in
    the file and both match the same slate game.

    The second one wins, and because home and away are reversed in a
    rematch the prices land on the opposite teams. On the board Ethan was
    reading:

        GB @ MIN   board MIN -220 / GB +200   ← the Nov 15 MIN @ GB game
        WAS @ PHI  board PHI +121 / WAS -125  ← the Nov 1 PHI @ WAS game
        DAL @ NYG  board NYG -218 / DAL +180  ← the Jan 3 NYG @ DAL game
        SF  @ LA   board LA  +120 / SF  -130  ← the Dec 13 LA @ SF game

    Every one of those is an exact price from the rematch, wearing the
    wrong team's name. Three of the four show the WRONG TEAM FAVOURED,
    which is Ethan's report of 2026-09-03 word for word: "none of these
    teams are favored to win on any sports book."

    THE ASSIGNMENT IS WHAT MAKES IT SILENT. Neither path asks whether the
    event it matched is the game it wants; the board path builds its
    team map positionally (`{event home: slate home}`) and the event path
    assigns `game.home_ml = mls[home]` off the EVENT's home. So a wrong
    match does not read as missing data or a mismatch — it reads as a
    perfectly ordinary price on the wrong team.

    So the orientation is checked rather than assumed, and an event that
    is the other meeting is refused. `_slate_days` above is the other
    half: with football's dates restored, most rematches never get this
    far. This is the bar that holds when they do — and it is the one that
    holds for a baseball series, where three games run in the SAME
    orientation on three consecutive days and only the date separates
    them.
    """
    return (bool(ev_home) and bool(ev_away)
            and ev_home == str(getattr(game, "home", "") or "")
            and ev_away == str(getattr(game, "away", "") or ""))


@dataclass
class BoardLinesResult:
    """What one board-level game-lines pull attached, and what it missed."""
    games_priced: int = 0        # games that got at least one market
    moneylines: int = 0
    totals: int = 0
    spreads: int = 0
    events_seen: int = 0         # events the endpoint returned
    #: Games whose price was REFUSED for age — see
    #: MAX_GAME_PRICE_SHOW_AGE — and how old the oldest of them was. A
    #: board that prices nothing because its pull is a day behind must
    #: say that, not read as a quiet slate.
    stale_game_prices: int = 0
    stale_price_age_s: float = 0.0
    #: Games priced past MAX_GAME_PRICE_AGE but inside the show ceiling:
    #: on the board, marked, unrecommended. Kept apart from the refusals
    #: so no note can call a shown price a dropped one.
    shown_stale_game_prices: int = 0
    shown_stale_price_age_s: float = 0.0
    quota: Quota = field(default_factory=Quota)
    from_cache: bool = False
    # Same two failure modes apply_odds_to_slate names separately, for the
    # same reason: an unmapped NAME is a stale team table, and a mapped pair
    # that is not on our slate is a wiring bug. A board that quietly prices
    # 9 of 16 games looks exactly like a light week.
    dropped_events: list = field(default_factory=list)
    other_day_events: int = 0
    #: Events refused because they are the OTHER meeting of the same two
    #: teams — see `_same_meeting`. Counted rather than swallowed: a
    #: rematch quietly relabelled onto this week's game is the wrong
    #: price wearing the right team's name, which is the hardest kind of
    #: wrong number to notice.
    reversed_events: int = 0


def apply_board_lines_to_slate(slate, api_key: str | None = None,
                               books: list[str] | None = None,
                               ttl: int = 300, sport: str = "nfl",
                               cache_only: bool = False) -> BoardLinesResult:
    """Refresh the GAME markets for a whole slate in ONE request.

    THE PRICE OF A MONEYLINE. `apply_odds_to_slate` above gets h2h, spreads
    and totals for free, in the sense that they ride along inside the
    event-scoped payload it is already buying for player props. But that
    payload is billed per market per region — CREDITS_PER_EVENT is 8 — and
    it is billed PER EVENT. So when the pacer declines the prop pull, as
    the daily cap now regularly makes it, there is no cheaper tier: the
    board keeps the last paid prices and the moneylines on the page age
    with the cycle. Ethan, 2026-09-03, looking at a board eight minutes old
    carrying prices fifty-five minutes old: "Getting the wrong numbers can
    fuck our picks bad."

    Refreshing one moneyline through that door costs 8 x every game on the
    slate — 136 credits for a sixteen-game Sunday, measured. This
    endpoint returns the same three markets for the ENTIRE board for three
    (three markets, one region, `_classify` bills markets x regions), which
    is the difference between a refresh the pacer will authorise several
    times a day and one it authorises never.

    WHAT IT DELIBERATELY DOES NOT DO is touch props. Player markets only
    exist per event, so nothing here can refresh them; a caller wanting
    fresh props still has to pay for the event pull. That split is the
    whole point, and it is why the two pulls stamp two different clocks
    upstream — a board whose lines are four minutes old and whose props are
    two hours old must not report one number for both.

    `cache_tag` is passed because it must be: `fetch_sport_odds` keys its
    cache by sport alone, and livelines already pulls a one-market h2h
    payload under that key. Without a tag the two would overwrite each
    other and this would read back a payload with no spreads or totals in
    it, and conclude the books had stopped posting them.
    """
    key = get_api_key(api_key)
    cfg = SPORT_CONFIG[sport]
    result = BoardLinesResult()
    result.from_cache = cache_only

    pair_games: dict[frozenset, list] = {}
    for g in slate.games:
        pair_games.setdefault(frozenset((g.home, g.away)), []).append(g)

    # THE SLATE'S OWN NAMES BEAT THE STATIC TABLE, for the reason spelled
    # out at length in apply_odds_to_slate: a hand-written {full name:
    # abbreviation} table has to agree with whatever the schedule feed
    # calls the same teams, and for the WNBA it did not — all five games
    # dropped. Same join here, so the two paths cannot disagree about who
    # is playing.
    slate_names: dict[str, str] = {}
    for g in slate.games:
        for nm, ab in ((getattr(g, "home_name", ""), g.home),
                       (getattr(g, "away_name", ""), g.away)):
            if nm and ab:
                slate_names[_team_key(nm)] = ab

    def _abbr(name: str) -> str | None:
        return slate_names.get(_team_key(name)) or cfg["teams"].get(name)

    slate_days = _slate_days(slate.games)

    try:
        events, quota = fetch_sport_odds(
            sport, api_key=key, markets=["h2h", "spreads", "totals"],
            books=books, ttl=ttl, cache_only=cache_only,
            cache_tag="lines")
    except OddsAPIError:
        if cache_only:
            return result          # never paid for; nothing on disk
        raise
    result.quota = quota
    result.events_seen = len(events)
    # ONE FILE, ONE AGE. `fetch_sport_odds` writes the whole slate's
    # payload to a single cache file, so this dates every price below.
    board_age = sport_cache_age(sport, "lines")

    for ev in events:
        home = _abbr(ev.get("home_team", ""))
        away = _abbr(ev.get("away_team", ""))
        if not home or not away:
            result.dropped_events.append(
                {"reason": "team name not in the map",
                 "home": ev.get("home_team", ""), "away": ev.get("away_team", ""),
                 "unmapped": [n for n, m in ((ev.get("home_team", ""), home),
                                             (ev.get("away_team", ""), away))
                              if not m]})
            continue
        # ANOTHER DAY'S GAME IS NOT THIS SLATE'S, whether or not we
        # happen to carry the pair. This check used to sit inside the
        # `not legs` branch, so it only ever ran for pairs we did NOT
        # have — which is precisely backwards: a pair we DO have is
        # exactly the one a later fixture can be mistaken for. Paired
        # with `_slate_days` reading football's date, this is what stops
        # a season-long payload pricing Week 1 off Week 12.
        if _other_day(ev, slate_days):
            result.other_day_events += 1
            continue
        pair = frozenset((home, away))
        legs = pair_games.get(pair) or []
        if not legs:
            # Reaching here means the pair is not on the slate AND the
            # kickoff is on a day the slate covers, which is a wiring bug
            # rather than another day's fixture — the day case returned
            # above.
            result.dropped_events.append(
                {"reason": "mapped, but that pair is not on our slate",
                 "home": ev.get("home_team", ""),
                 "away": ev.get("away_team", ""),
                 "mapped_to": [away, home]})
            continue
        # A pair can hold two games (a doubleheader); the event's start time
        # picks the leg, exactly as the prop path does. Football has none,
        # but this function is sport-agnostic and a silently merged
        # doubleheader is a wrong price rather than a missing one.
        game = _leg_by_commence(legs, ev.get("commence_time") or "")
        if game is None:
            continue
        # THE OTHER MEETING IS A DIFFERENT GAME. See `_same_meeting`: the
        # pair lookup is orientation-blind, so a rematch matches too, and
        # the map built below is positional — it would relabel the
        # rematch's prices onto this game's teams without a murmur.
        if not _same_meeting(home, away, game):
            result.reversed_events += 1
            continue

        # The parsers key on the exact strings THIS payload uses, so the map
        # comes off the event rather than out of a table (cfb_build reached
        # the same conclusion about 134 schools that rot on reshuffle).
        team_map = {ev.get("home_team", ""): home, ev.get("away_team", ""): away}
        # The whole-slate payload is one file, so one age dates every
        # price in it (see MAX_GAME_PRICE_AGE).
        # PAST THE SHOW CEILING the number is dropped exactly as before.
        # Between the two, it is attached and MARKED, because a board with
        # a dated price on a labelled card beats a board with nothing on
        # it (see MAX_GAME_PRICE_SHOW_AGE).
        if not price_is_showable(board_age):
            result.stale_game_prices += 1
            result.stale_price_age_s = float(board_age or 0.0)
            continue
        game.price_age_s = board_age
        game.priced_from = "board"
        game.price_stale = not price_is_current(board_age)
        if game.price_stale:
            result.shown_stale_game_prices += 1
            result.shown_stale_price_age_s = max(
                result.shown_stale_price_age_s or 0.0, float(board_age or 0.0))
        touched = False
        mls = parse_event_h2h(ev, team_map)
        if mls.get(home) is not None and mls.get(away) is not None:
            game.home_ml = mls[home]
            game.away_ml = mls[away]
            # WHO IS OFFERING IT — see `best_h2h_books`.
            _bk = best_h2h_books(ev, team_map)
            game.home_ml_book = _bk.get(home, "")
            game.away_ml_book = _bk.get(away, "")
            # …AND WHAT THE MARKET IMPLIES, off real two-sided pairs
            # rather than the shopped one (see `consensus_h2h_fair`).
            _fair = consensus_h2h_fair(ev, team_map)
            game.home_ml_fair = float(_fair.get(home) or 0.0)
            result.moneylines += 1
            touched = True
        for bk, prices in parse_event_h2h_by_book(ev, team_map).items():
            if bk == BOOK_TITLES.get("pinnacle") and home in prices and away in prices:
                game.sharp_home_ml = prices[home]
                game.sharp_away_ml = prices[away]
        tot = parse_event_totals(ev)
        if tot:
            game.total, game.total_over_odds, game.total_under_odds = tot
            game.total_measured = True         # a book posted it
            # …AND WHO POSTED IT (see `best_total_books`).
            _tb = best_total_books(ev)
            game.total_over_book = _tb.get("over", "")
            game.total_under_book = _tb.get("under", "")
            result.totals += 1
            touched = True
        sp = parse_event_spreads(ev, team_map, home, away)
        if sp:
            game.spread, game.spread_home_odds, game.spread_away_odds = sp
            game.spread_measured = True        # a book posted it
            _sb = best_spread_books(ev, team_map, home, away)
            game.home_spread_book = _sb.get(home, "")
            game.away_spread_book = _sb.get(away, "")
            result.spreads += 1
            touched = True
        stot = parse_event_totals(ev, only_books=SHARP_BOOKS)
        if stot:
            game.sharp_total, game.sharp_total_over_odds, \
                game.sharp_total_under_odds = stot
        ssp = parse_event_spreads(ev, team_map, home, away,
                                  only_books=SHARP_BOOKS)
        if ssp:
            game.sharp_spread, game.sharp_spread_home_odds, \
                game.sharp_spread_away_odds = ssp
        if touched:
            result.games_priced += 1

    return result


def _leg_by_commence(legs: list, commence: str):
    """Which leg of a doubleheader an event belongs to, by start time."""
    if len(legs) <= 1:
        return legs[0] if legs else None
    import datetime as _dt

    def _dist(g):
        try:
            a = commence.replace("Z", "+00:00")
            b = (g.kickoff or "").replace("Z", "+00:00")
            return abs((_dt.datetime.fromisoformat(a)
                        - _dt.datetime.fromisoformat(b)).total_seconds())
        except Exception:                                    # noqa: BLE001
            return float("inf")
    return min(legs, key=_dist)


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
    scorer_map = cfg.get("scorers") or {}
    alt_map = cfg.get("alternates") or {}
    markets = (list(cfg["markets"]) + list(scorer_map) + list(alt_map)
               + ["h2h", "totals", "spreads"])
    # The request as it was before the ladders — the payload a cached
    # rebuild can still find on the day the ladders first ship.
    base_markets = [m for m in markets if m not in alt_map]
    # Build a combined line index for the events that belong to this slate.
    index: dict[tuple[str, str], list[SportsbookLine]] = {}
    sharp_index: dict[tuple[str, str], list[SportsbookLine]] = {}
    alt_index: dict[tuple[str, str], list[SportsbookLine]] = {}
    alt_sharp_index: dict[tuple[str, str], list[SportsbookLine]] = {}
    menu: dict[tuple[str, str], dict] = {}
    # Yes/No scorer quotes, indexed the same way — parsed by their own
    # parser because the over/under one requires a point and these have
    # none (see SCORER_ODDS_TO_MARKET).
    scorer_index: dict[tuple[str, str], list[dict]] = {}
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

    # WHICH DAYS THIS SLATE COVERS — `_slate_days` / `_other_day` above,
    # shared with the board-lines path so the rule has one definition.
    slate_days = _slate_days(slate.games)

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
        # ANOTHER DAY'S GAME IS NOT THIS SLATE'S — asked of every event,
        # not only of pairs we do not carry. See the same change on the
        # board-lines path and `_slate_days` for why it was inert.
        if _other_day(ev, slate_days):
            result.other_day_events += 1
            continue
        if frozenset((home, away)) not in slate_pairs:
            # A later date's game is not a fault and never reaches here —
            # it returned above. What is left is a pair that should be on
            # THIS slate and is not, which is a wiring bug between our
            # abbreviations and the table's.
            result.dropped_events.append(
                {"reason": "mapped, but that pair is not on our slate",
                 "home": ev.get("home_team", ""),
                 "away": ev.get("away_team", ""),
                 "mapped_to": [away, home]})
            continue
        # WHICH FILE TO DATE. The age below is read off the cache file
        # named by the market list actually served; the deploy-day
        # fallback serves the BASE-market file, and dating the ladder's
        # name instead answers None — "nothing cached", current by
        # construction — for a payload that may be days old. That is the
        # any-age hole opened back up in one corner.
        _age_markets = markets
        try:
            payload, quota = fetch_event_odds(ev["id"], key, markets=markets,
                                              books=books, ttl=ttl, sport=sport,
                                              cache_only=cache_only)
        except OddsAPIError:
            if not cache_only:
                raise
            # THE DEPLOY-DAY MISS. The cache file is named by the market
            # list, so the first cached rebuild after the ladders ship
            # finds no payload under the new name while the last paid
            # pull's base-market payload sits beside it. Serving that
            # keeps every main line and game price on the board until the
            # next paid pull buys the ladders; the alternative was a board
            # of proxies for a cycle, which is the "no real book price"
            # census on a day nothing was wrong.
            payload = None
            if alt_map:
                try:
                    payload, quota = fetch_event_odds(
                        ev["id"], key, markets=base_markets, books=books,
                        ttl=ttl, sport=sport, cache_only=True)
                    result.alt_fallback += 1
                    _age_markets = base_markets
                except OddsAPIError:
                    payload = None
            if payload is None:
                # Never paid for, so there is nothing on disk. Counted: a
                # cached rebuild otherwise looks identical whether the
                # event join improved or not, because the newly-matched
                # events match and then disappear on this line.
                result.cache_misses += 1
                continue
        result.quota = quota
        result.events_used += 1
        pair = frozenset((home, away))
        game = _leg_for_event(pair, ev.get("commence_time") or "")
        # THE OTHER MEETING IS A DIFFERENT GAME — and on this path it
        # would carry the wrong week's PROPS as well as the wrong game
        # prices, so the whole event goes rather than just its lines.
        if game is not None and not _same_meeting(home, away, game):
            result.reversed_events += 1
            continue
        # Prop lines only index when this event IS the leg the slate's props
        # were built for — a doubleheader's other leg has different lineups
        # and different prices, and mixing them corrupts every quote.
        wanted = prop_leg.get(pair, 0)
        props_ok = (not wanted or game is None
                    or getattr(game, "game_number", 1) == wanted)
        # HOW OLD THIS PAYLOAD IS, read once and asked twice: of the
        # player markets against MAX_PROP_PRICE_AGE, of the game markets
        # against MAX_GAME_PRICE_AGE. A cached payload is served at any
        # age (`_request`); these two questions are where "any" ends.
        _age = event_cache_age(ev["id"], _age_markets, books, sport)
        if props_ok and not price_is_showable(_age, _max_prop_price_show_age()):
            # NOTHING off this payload reaches a prop: not a main line,
            # not a rung, not a scorer quote, not a menu entry. A prop
            # with no book line is proxy-priced and never a pick, which
            # is the honest state of a board with no current price.
            result.stale_prop_events += 1
            result.stale_prop_age_s = max(result.stale_prop_age_s or 0.0,
                                          float(_age or 0.0))
            props_ok = False
        if props_ok:
            for k, lines in parse_event_lines(payload, cfg["markets"]).items():
                index.setdefault(k, []).extend(lines)
            # The sharp book's own pairs, kept apart from the shopped
            # field — see `parse_event_sharp_lines`.
            for k, lines in parse_event_sharp_lines(payload, cfg["markets"]).items():
                sharp_index.setdefault(k, []).extend(lines)
            # THE LADDERS, parsed with their own map so a rung never lands
            # in the shopped field. Absent from a payload bought before
            # they shipped, or from a book that hangs none: empty, and
            # the board is exactly what it was.
            if alt_map:
                for k, lines in parse_event_lines(payload, alt_map).items():
                    alt_index.setdefault(k, []).extend(lines)
                for k, lines in parse_event_sharp_lines(payload, alt_map).items():
                    alt_sharp_index.setdefault(k, []).extend(lines)
            for k, disp in parse_event_players(payload, cfg["markets"]).items():
                menu.setdefault(k, {"player": disp, "home": home, "away": away})
            if scorer_map:
                for k, quotes in parse_event_scorers(payload, scorer_map).items():
                    scorer_index.setdefault(k, []).extend(quotes)
        # Attach real game-market prices to the matching game (each leg gets
        # its own moneyline/total/spread).
        #
        # …ONLY IF THE PAYLOAD IS YOUNG ENOUGH TO BE A PRICE. See
        # MAX_GAME_PRICE_AGE: this path serves a cached payload at any
        # age on a declined cycle, and a game market read off a stale one
        # is the wrong number rather than an old one. The player markets
        # were asked the same question above, against their own ceiling.
        if game is not None and not price_is_showable(_age):
            result.stale_game_prices += 1
            result.stale_price_age_s = max(result.stale_price_age_s or 0.0,
                                           float(_age or 0.0))
            game = None
        if game is not None:
            game.price_age_s = _age
            game.priced_from = "event"
            game.price_stale = not price_is_current(_age)
            if game.price_stale:
                result.shown_stale_game_prices += 1
                result.shown_stale_price_age_s = max(
                    result.shown_stale_price_age_s or 0.0, float(_age or 0.0))
            mls = parse_event_h2h(payload, cfg["teams"])
            if home in mls and away in mls:
                game.home_ml = mls[home]
                game.away_ml = mls[away]
                _bk = best_h2h_books(payload, cfg["teams"])
                game.home_ml_book = _bk.get(home, "")
                game.away_ml_book = _bk.get(away, "")
                _fair = consensus_h2h_fair(payload, cfg["teams"])
                game.home_ml_fair = float(_fair.get(home) or 0.0)
                result.moneylines += 1
            # The sharp book's own pair rides along as the fair-value anchor.
            for bk, prices in parse_event_h2h_by_book(payload, cfg["teams"]).items():
                if bk == BOOK_TITLES.get("pinnacle") and home in prices and away in prices:
                    game.sharp_home_ml = prices[home]
                    game.sharp_away_ml = prices[away]
            tot = parse_event_totals(payload)
            if tot:
                game.total, game.total_over_odds, game.total_under_odds = tot
                game.total_measured = True     # a book posted it
                _tb = best_total_books(payload)
                game.total_over_book = _tb.get("over", "")
                game.total_under_book = _tb.get("under", "")
            sp = parse_event_spreads(payload, cfg["teams"], home, away)
            if sp:
                game.spread, game.spread_home_odds, game.spread_away_odds = sp
                game.spread_measured = True    # a book posted it
                _sb = best_spread_books(payload, cfg["teams"], home, away)
                game.home_spread_book = _sb.get(home, "")
                game.away_spread_book = _sb.get(away, "")
            stot = parse_event_totals(payload, only_books=SHARP_BOOKS)
            if stot:
                game.sharp_total, game.sharp_total_over_odds, \
                    game.sharp_total_under_odds = stot
            ssp = parse_event_spreads(payload, cfg["teams"], home, away,
                                      only_books=SHARP_BOOKS)
            if ssp:
                game.sharp_spread, game.sharp_spread_home_odds, \
                    game.sharp_spread_away_odds = ssp

    # THE LOOSE FALLBACK. `_name_key_loose` already knew "Jim Jarvis" and
    # "James Jarvis" were one player — it was used only to REPORT the miss,
    # under a comment calling it "we paid for this price and threw it
    # away", which is exactly what then happened. Measured live on
    # 2026-08-22: three MLB prices bought and discarded on one slate.
    #
    # ONLY WHEN IT IS UNAMBIGUOUS. A first initial and a surname is a weak
    # key — two "J Rodriguez" on one slate is an ordinary Tuesday — so the
    # fallback fires only when exactly ONE book entry carries that loose
    # key for that market. Attaching the wrong player's price is a worse
    # outcome than attaching none: a missing price shows as no bet, and a
    # wrong price shows as a bet at a number nobody offered.
    loose: dict[str, list] = {}
    loose_hits: set = set()
    for (nkey, market), info in menu.items():
        k = f"{_name_key_loose(info['player'])}|{market}"
        loose.setdefault(k, []).append((nkey, market))

    scorer_markets = set(scorer_map.values())
    for prop in slate.props:
        if prop.market in scorer_markets:
            # Yes/No quotes become lines at 0.5 — "over half a touchdown"
            # IS "scores at least one", and downstream (the long-shot
            # candidate builder, the line index, the journal) all speak
            # SportsbookLine. A prop no book quoted keeps its empty list
            # and is NOT reported unmatched — books price a dozen skill
            # players a game, not a roster, and absence is the norm here.
            quotes = scorer_index.get((normalize_name(prop.player),
                                       prop.market)) or []
            if quotes:
                prop.lines = [SportsbookLine(
                    book=q["book"], line=0.5, over_odds=int(q["yes_odds"]),
                    under_odds=(int(q["no_odds"])
                                if q.get("no_odds") is not None else None))
                    for q in quotes]
                result.scorers_matched += 1
            continue
        lines = index.get((normalize_name(prop.player), prop.market))
        if not lines:
            cands = loose.get(f"{_name_key_loose(prop.player)}|{prop.market}")
            if cands and len(cands) == 1:
                lines = index.get(cands[0])
                if lines:
                    result.loose_matched += 1
                    loose_hits.add((normalize_name(prop.player), prop.market))
        if lines:
            prop.lines = lines
            result.matched += 1
            prop.sharp_lines = list(sharp_index.get(
                (normalize_name(prop.player), prop.market)) or [])
        else:
            result.unmatched.append(f"{prop.player} ({prop.market})")
        # The ladder rides whether or not a main line matched: a rung is
        # a real price with its own probability, and the Most Likely
        # board can stand on one where the Edge board has no main line
        # to shop. Under the EXACT key only — the loose first-initial
        # fallback above is a safety net for a main line, and a wrong
        # player's ladder is worse than none.
        nk = (normalize_name(prop.player), prop.market)
        prop.alt_lines = list(alt_index.get(nk) or [])
        prop.alt_sharp_lines = list(alt_sharp_index.get(nk) or [])
        if prop.alt_lines:
            result.alt_matched += 1

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
    result.name_misses = _name_near_misses(slate, menu, matched_keys,
                                           recovered=loose_hits)

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
