"""BALLDONTLIE — a licensed scores feed, OFF until there is a key (RS6).

The live scores that grade bets and drive the Live tab come from ESPN's
public scoreboard in every league but MLB, a feed nobody licensed to us
(docs/DATA_SOURCES.md keeps that risk on the record). BALLDONTLIE sells
the same games' scores under an API key. The research paper's data item
was this client and a logger that reads the two feeds side by side
(engine/feedlatency), with one rule: a league moves to the licensed feed
only where it is as fast or faster. Nothing on the site reads this yet.

READ FROM THE OFFICIAL SDK. docs.balldontlie.io is outside the build
session's network, and a client written against an API nobody has read
would be a guess, so this follows BALLDONTLIE's own Python SDK (PyPI
``balldontlie`` 0.1.6, MIT), read line by line, without taking it as a
dependency (it pulls pydantic and requests for what is five GETs here):

  * base ``https://api.balldontlie.io``; the key goes BARE in the
    ``Authorization`` header (no "Bearer");
  * a list parameter repeats as ``name[]=value``; pages by cursor
    (``meta.next_cursor``, ``per_page``);
  * 401 a refused key, 429 over the plan's rate, 400 a bad parameter;
  * ``GET {nba,nfl,mlb}/v1/games?dates[]=YYYY-MM-DD``: id, date, status,
    the scores, the two teams (NBA and NFL say ``visitor_team``, MLB
    ``away_team`` with its runs in ``away_team_data``); NBA and MLB carry
    the period and clock too;
  * ``GET nba/v1/box_scores/live``: today's live NBA box scores.

The SDK covers the NBA, the NFL and MLB (and soccer); the WNBA, college
football and MMA the paper listed are not in it, so they are not here.

THE KEY: ``BALLDONTLIE_API_KEY``, put on the box with
``sudo ./deploy/setenv.sh BALLDONTLIE_API_KEY`` (typed at the prompt,
never in a file in the repo). Without it `enabled()` is False and every
call raises `BDLUnavailable`. ``python3 -m engine.sources.balldontlie
--probe`` says what the key's plan answers, without printing the key.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from .fetch import DataUnavailable
from ..secrets import load_local_secrets

BASE = "https://api.balldontlie.io"
KEY_ENV = "BALLDONTLIE_API_KEY"
UA = "qellys-book/0.1 (scores feed check)"
SPORTS = ("nba", "nfl", "mlb")
PER_PAGE = 100
#: A day's games are one page; the cap only stops a cursor that loops.
MAX_PAGES = 5
TIMEOUT_S = 15


class BDLUnavailable(DataUnavailable):
    """No key, a refused key, or the feed did not answer."""


class BDLRateLimited(BDLUnavailable):
    """429: over the plan's requests a minute."""


def api_key(explicit: str | None = None) -> str:
    load_local_secrets()
    key = (explicit or os.environ.get(KEY_ENV) or "").strip()
    if not key:
        raise BDLUnavailable(
            f"No BALLDONTLIE key. The licensed scores feed stays off until "
            f"{KEY_ENV} is set on the box (sudo ./deploy/setenv.sh {KEY_ENV}); "
            f"the site keeps reading ESPN's scoreboard as it always has.")
    return key


def enabled() -> bool:
    try:
        api_key()
        return True
    except BDLUnavailable:
        return False


def query(params: dict) -> list:
    """``[(name, value)]`` the way the SDK sends them: a list repeats as
    ``name[]``, None is left out."""
    out = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            out += [(f"{k}[]", str(x)) for x in v]
        else:
            out.append((k, str(v)))
    return out


def _headers(key: str) -> dict:
    return {"Authorization": key, "Accept": "application/json", "User-Agent": UA}


def get(path: str, params: dict | None = None, key: str | None = None,
        opener=None) -> tuple:
    """``(payload, headers)`` for one GET. ``opener`` is for tests
    (``urllib.request.urlopen`` by default)."""
    k = api_key(key)
    url = f"{BASE}/{path.lstrip('/')}"
    q = query(params or {})
    if q:
        url += "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers=_headers(k))
    try:
        with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            hdrs = {h.lower(): v for h, v in (resp.headers.items() if resp.headers else [])}
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise BDLUnavailable(f"BALLDONTLIE refused the key (401). Check {KEY_ENV}.") from exc
        if exc.code == 429:
            raise BDLRateLimited("BALLDONTLIE: over the plan's rate (429).") from exc
        raise BDLUnavailable(f"BALLDONTLIE answered {exc.code} for {path}.") from exc
    except Exception as exc:                                  # noqa: BLE001
        raise BDLUnavailable(f"BALLDONTLIE did not answer: {type(exc).__name__}: {exc}") from exc
    try:
        return json.loads(body), hdrs
    except ValueError as exc:
        raise BDLUnavailable(f"BALLDONTLIE sent something that is not JSON for {path}.") from exc


def pages(path: str, params: dict, key: str | None = None, opener=None) -> list:
    """Every row of a cursor-paged list."""
    rows, cursor = [], None
    for _ in range(MAX_PAGES):
        payload, _h = get(path, {**params, "per_page": PER_PAGE, "cursor": cursor}, key, opener)
        rows += list(payload.get("data") or [])
        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
    return rows


def _num(v):
    try:
        return None if v is None else int(round(float(v)))
    except (TypeError, ValueError):
        return None


_LIVE_WORDS = re.compile(r"qtr|quarter|half|progress|overtime|\bot\b|top|bot|mid|end|inning|period",
                         re.I)


def state_of(status: str, period) -> str:
    """``pre``, ``live`` or ``final`` from the feed's own words. A game not
    started reads its tip time as its status; a final says Final."""
    s = str(status or "")
    if "final" in s.lower():
        return "final"
    if (_num(period) or 0) > 0 or _LIVE_WORDS.search(s):
        return "live"
    return "pre"


def normalize(sport: str, g: dict) -> dict:
    """One game in one shape, whichever league it came from."""
    home = g.get("home_team") or {}
    away = g.get("visitor_team") or g.get("away_team") or {}
    if sport == "mlb":
        hs = _num((g.get("home_team_data") or {}).get("runs"))
        as_ = _num((g.get("away_team_data") or {}).get("runs"))
        clock = g.get("display_clock") or ""
    else:
        hs, as_ = _num(g.get("home_team_score")), _num(g.get("visitor_team_score"))
        clock = g.get("time") or ""
    period = g.get("period")
    return {
        "id": g.get("id"), "sport": sport, "date": str(g.get("date") or "")[:10],
        "status": str(g.get("status") or ""), "state": state_of(g.get("status"), period),
        "period": _num(period), "clock": str(clock or ""),
        "home": str(home.get("abbreviation") or ""), "away": str(away.get("abbreviation") or ""),
        "home_name": str(home.get("full_name") or home.get("display_name") or g.get("home_team_name") or ""),
        "away_name": str(away.get("full_name") or away.get("display_name") or g.get("away_team_name") or ""),
        "home_score": hs, "away_score": as_,
    }


def games(sport: str, dates: list, key: str | None = None, opener=None) -> list:
    """The league's games on these dates (``YYYY-MM-DD``), normalized."""
    if sport not in SPORTS:
        raise BDLUnavailable(f"BALLDONTLIE's SDK has no {sport!r}; it covers {', '.join(SPORTS)}.")
    rows = pages(f"{sport}/v1/games", {"dates": sorted(set(dates))}, key, opener)
    return [normalize(sport, g) for g in rows]


def probe(key: str | None = None, opener=None, today: str | None = None) -> list:
    """What the key's plan answers, one line a call. Never the key."""
    import datetime as _dt
    day = today or _dt.date.today().isoformat()
    lines = []
    for path, params in ([(f"{s}/v1/games", {"dates": [day]}) for s in SPORTS]
                         + [("nba/v1/box_scores/live", {})]):
        try:
            payload, hdrs = get(path, params, key, opener)
            n = len(payload.get("data") or [])
            limits = ", ".join(f"{h}: {v}" for h, v in sorted(hdrs.items())
                               if "limit" in h or "remaining" in h)
            first = (payload.get("data") or [{}])[0] if n else {}
            lines.append(f"{path}: ok, {n} row(s)" + (f"; fields: {', '.join(sorted(first))}" if first else "")
                         + (f"; {limits}" if limits else ""))
        except BDLUnavailable as exc:
            lines.append(f"{path}: {exc}")
    return lines


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--probe" not in argv:
        print(__doc__.strip().split("\n\n")[0])
        print(f"\n  --probe   what the key's plan answers ({'a key is set' if enabled() else 'no key set'})")
        return 0
    if not enabled():
        print(f"No {KEY_ENV} set; nothing to probe.")
        return 1
    for line in probe():
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
