"""Historical odds — what the books were actually offering at a past moment.

This is the feed that makes a real edge measurable. Without it, a backtest can
only score the model against a naive baseline line, which answers "does it beat
a trailing average?" — a much easier question than the one that matters. With
point-in-time book prices we can replay a past slate, price every pick against
the number a bettor could genuinely have taken, and measure ROI and closing-line
value for real.

The Odds API exposes this under ``/v4/historical/...``. Two things differ from
the live endpoints and both matter:

* the payload is wrapped in an envelope — ``{"timestamp", "previous_timestamp",
  "next_timestamp", "data": ...}`` — where ``data`` is the shape the live
  parsers already understand, so this module unwraps and reuses them rather than
  duplicating parsing logic;
* historical requests are billed at a **higher credit cost** than live ones, so
  harvesting is deliberately cache-first and long-lived: a past price never
  changes, so it should be fetched at most once, ever.

Snapshots land on whatever timestamps the provider recorded, so the returned
envelope reports the actual snapshot time — always store that rather than the
requested time, or a "closing line" may silently be an hour stale.
"""

from __future__ import annotations

import datetime as _dt
import json
import urllib.parse
from dataclasses import dataclass, field

from .fetch import CACHE_DIR
from .oddsapi import (
    ODDS_BASE, SPORT_CONFIG, SCORER_ODDS_TO_MARKET, OddsAPIError, _request,
    get_api_key, parse_event_lines, parse_event_h2h, parse_event_scorers,
    DEFAULT_BOOKS,
)

# A past price is immutable, so cache it effectively forever.
FOREVER = 10 * 365 * 24 * 3600


@dataclass
class Snapshot:
    """Odds as they stood at one moment."""
    requested: str                    # the timestamp we asked for
    taken: str                        # the timestamp the provider actually has
    data: object = None               # unwrapped payload (live-endpoint shape)
    previous: str = ""
    next: str = ""

    @property
    def drift_minutes(self) -> float | None:
        """How far the returned snapshot sits from the one requested."""
        try:
            a = _dt.datetime.fromisoformat(self.requested.replace("Z", "+00:00"))
            b = _dt.datetime.fromisoformat(self.taken.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
        return abs((b - a).total_seconds()) / 60.0


def iso_utc(when) -> str:
    """Normalise a date/datetime/string to the API's ISO-8601 Z format."""
    if isinstance(when, str):
        return when if when.endswith("Z") else when.rstrip("+00:00") + "Z"
    if isinstance(when, _dt.date) and not isinstance(when, _dt.datetime):
        when = _dt.datetime(when.year, when.month, when.day, 23, 0)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _unwrap(payload, requested: str) -> Snapshot:
    """Pull the live-shaped body out of the historical envelope."""
    if isinstance(payload, dict) and "data" in payload:
        return Snapshot(
            requested=requested,
            taken=str(payload.get("timestamp") or requested),
            data=payload.get("data"),
            previous=str(payload.get("previous_timestamp") or ""),
            next=str(payload.get("next_timestamp") or ""),
        )
    # Some responses may already be bare; treat them as the body itself.
    return Snapshot(requested=requested, taken=requested, data=payload)


def _cache_key(kind: str, sport: str, when: str, extra: str = "") -> str:
    stamp = when.replace(":", "").replace("-", "")
    tail = f"_{extra}" if extra else ""
    return f"odds_hist_{kind}_{sport}_{stamp}{tail}.json"


def fetch_historical_events(sport: str, when, api_key: str | None = None) -> Snapshot:
    """Events that existed at ``when`` (a date, datetime, or ISO string)."""
    key = get_api_key(api_key)
    stamp = iso_utc(when)
    sport_key = SPORT_CONFIG[sport]["sport_key"]
    params = {"apiKey": key, "date": stamp}
    url = f"{ODDS_BASE}/historical/sports/{sport_key}/events?{urllib.parse.urlencode(params)}"
    payload, _ = _request(url, _cache_key("events", sport, stamp), ttl=FOREVER)
    return _unwrap(payload, stamp)


def fetch_historical_event_odds(event_id: str, sport: str, when,
                                markets: list[str] | None = None,
                                books: list[str] | None = None,
                                api_key: str | None = None) -> Snapshot:
    """Odds for one event as they stood at ``when``."""
    key = get_api_key(api_key)
    stamp = iso_utc(when)
    cfg = SPORT_CONFIG[sport]
    markets = markets or (list(cfg["markets"]) + ["h2h", "totals", "spreads"])
    params = {
        "apiKey": key, "date": stamp, "regions": "us",
        "markets": ",".join(markets), "oddsFormat": "american",
        "bookmakers": ",".join(books or DEFAULT_BOOKS),
    }
    url = (f"{ODDS_BASE}/historical/sports/{cfg['sport_key']}/events/{event_id}/odds"
           f"?{urllib.parse.urlencode(params)}")
    payload, _ = _request(url, _cache_key("event", sport, stamp, event_id), ttl=FOREVER)
    return _unwrap(payload, stamp)


# --- turning a snapshot into rows -------------------------------------------
@dataclass
class HistoricalOdds:
    """Flattened prices from one snapshot, ready for the DB."""
    sport: str
    taken: str
    event_id: str
    home: str = ""
    away: str = ""
    props: dict = field(default_factory=dict)      # (player, market) -> [SportsbookLine]
    moneylines: dict = field(default_factory=dict)  # team -> american odds
    scorers: dict = field(default_factory=dict)     # (player, market) -> [quote dicts]


def parse_snapshot(snap: Snapshot, sport: str) -> HistoricalOdds:
    """Parse a historical event-odds snapshot with the live parsers."""
    body = snap.data if isinstance(snap.data, dict) else {}
    cfg = SPORT_CONFIG[sport]
    home = cfg["teams"].get(body.get("home_team", ""), body.get("home_team", ""))
    away = cfg["teams"].get(body.get("away_team", ""), body.get("away_team", ""))
    return HistoricalOdds(
        sport=sport, taken=snap.taken, event_id=str(body.get("id", "")),
        home=home, away=away,
        props=parse_event_lines(body, cfg["markets"]),
        moneylines=parse_event_h2h(body, cfg["teams"]),
        scorers=parse_event_scorers(body, SCORER_ODDS_TO_MARKET),
    )


def to_rows(hist: HistoricalOdds) -> list[dict]:
    """Flatten parsed history into ``odds_history`` rows."""
    rows: list[dict] = []
    for (player, market), lines in hist.props.items():
        for ln in lines:
            rows.append({
                "sport": hist.sport, "taken_at": hist.taken,
                "event_id": hist.event_id, "home": hist.home, "away": hist.away,
                "player": player, "market": market, "book": ln.book,
                "line": ln.line, "over_odds": ln.over_odds,
                "under_odds": ln.under_odds,
            })
    for (player, market), quotes in hist.scorers.items():
        for q in quotes:
            rows.append({
                "sport": hist.sport, "taken_at": hist.taken,
                "event_id": hist.event_id, "home": hist.home, "away": hist.away,
                "player": player, "market": market, "book": q["book"],
                "line": 0.5, "over_odds": q["yes_odds"],
                "under_odds": q.get("no_odds"),
            })
    for team, price in hist.moneylines.items():
        rows.append({
            "sport": hist.sport, "taken_at": hist.taken,
            "event_id": hist.event_id, "home": hist.home, "away": hist.away,
            "player": team, "market": "moneyline", "book": "best",
            "line": 0.0, "over_odds": price, "under_odds": None,
        })
    return rows
