"""League-wide injury reports from ESPN's site API — every sport, one shape.

The site already had injuries, but only for the NFL and only inside the
fantasy page (nflverse practice reports feeding the usage model). Ethan,
2026-08-10: "we should have it for every sport and it should be easier to
find them [than] digging through fantasy." This module is that: ESPN
publishes a keyless `/injuries` endpoint per league, in the same envelope
this repo already reads for NFL live scores, the CFB board and the whole
NBA/WNBA ingest:

    /apis/site/v2/sports/{sport}/{league}/injuries

Per team it lists every player currently carrying a designation — status
(Out, Injured Reserve, Day-To-Day, Questionable, the ILs), the date the
item was posted, the injury itself, a return date when one is projected,
and a headshot URL. That is a CURRENT-STATUS board, which is what an
injury page is for; the nflverse practice-participation detail stays in
fantasy where it feeds the model.

The parser is PURE and fixture-tested, reads only by key name, and drops
rather than guesses: a row with no player or no status is not a row.
UFC has no injury report anywhere — there is no commission feed and no
ESPN endpoint — so the league map simply does not contain it, and the
page's tab hides for that sport rather than rendering an empty promise.
"""

from __future__ import annotations

import datetime as dt
import re
import time

from .fetch import CACHE_DIR, DEFAULT_AGENT, fetch_json

ROOT = "https://site.api.espn.com/apis/site/v2/sports"

#: Every league with a real feed. CFB's exists but runs sparse — schools
#: have no reporting duty — which the page says instead of hiding.
LEAGUES = {
    "nfl": f"{ROOT}/football/nfl/injuries",
    "mlb": f"{ROOT}/baseball/mlb/injuries",
    "nba": f"{ROOT}/basketball/nba/injuries",
    "wnba": f"{ROOT}/basketball/wnba/injuries",
    "cfb": f"{ROOT}/football/college-football/injuries",
}

#: How long a fetched injury board is believed before ESPN is asked again.
#:
#: Was 1800 under a comment calling injuries "a practice-report cadence,
#: not a ticker's" — an August assumption that stopped being true the
#: week the season started. Ethan, 2026-09-01, ten minutes after a
#: running back went on IR: "how often does the NFL Injuries pull data" —
#: and the honest answer was "up to half an hour behind ESPN, plus a
#: build cycle". An IR move re-prices every back behind the man on the
#: depth chart, and the rules engine's own-player hold reads this feed;
#: both deserve better than a 30-minute-old answer. Ten minutes keeps the
#: endpoint's courtesy (six keyless calls an hour per league) while the
#: refresh loop, which runs far more often than this, picks changes up
#: on the first cycle after the cache turns.
INJURY_TTL = 600


def _cache_file(league: str):
    return CACHE_DIR / f"espn_injuries_{league}.json"


def cache_age_s(league: str) -> float | None:
    """Seconds since this league's cached board was last WRITTEN, or None
    if nothing is cached.

    The load-bearing measurement behind the staleness banner. ``fetch_json``
    answers a failed request with the cached copy and raises nothing — the
    right call for a board that should survive a blip, but it means a build
    can stamp ``generated_at`` on data collected days ago and every surface
    reads it as current. The cache file's mtime only advances on a
    SUCCESSFUL fetch, so its age is the true age of the rows: under the TTL
    means fresh, far over it means the feed has been declining and nobody
    was told."""
    p = _cache_file(league)
    try:
        return max(0.0, time.time() - p.stat().st_mtime)
    except OSError:
        return None


def fetch_injuries(league: str):
    """The raw board for one league. KeyError for a league with no feed
    is the right failure — callers iterate LEAGUES, they don't guess."""
    return fetch_json(LEAGUES[league], f"espn_injuries_{league}.json",
                      ttl=INJURY_TTL, user_agent=DEFAULT_AGENT)


#: ESPN keeps a player in the injuries feed after he is cleared, with the
#: status "Active" and no injury named. That is a RETURN notice, not a
#: designation — real news about a team, but the opposite of being hurt.
_ACTIVE = re.compile(r"^\s*active\s*$", re.I)


def is_return(row: dict) -> bool:
    """True for a cleared-to-play notice rather than a designation."""
    return bool(_ACTIVE.match(row.get("status") or "")) and not row.get("injury")


#: How long a cleared-to-play notice stays news. A DESIGNATION is a
#: current status the league keeps re-filing, so it stays as long as the
#: feed lists it. A RETURN notice is one moment — "he practiced" — and
#: ESPN never retires the row, so left alone it becomes a standing claim
#: of health that nobody is re-verifying. Cade Mays broke a wrist bone in
#: camp on 2026-08-09; nine days later the page still said "Active" off a
#: return notice, because August carries no filing duty that would have
#: produced a newer row to beat it.
RETURN_NOTE_DAYS = 14


def drop_stale_returns(rows: list[dict], now: float | None = None) -> list[dict]:
    """Keep every designation; keep return notices only while they are
    recent enough to still be news. An UNDATED return notice is dropped
    outright — with no date it can never age out, which is exactly the
    standing-claim trap this cut exists to close."""
    cutoff = (now if now is not None else time.time()) \
        - RETURN_NOTE_DAYS * 86400
    kept = []
    for r in rows:
        if not is_return(r):
            kept.append(r)
            continue
        stamp = _parse_iso_ts(r.get("date"))
        if stamp is not None and stamp >= cutoff:
            kept.append(r)
    return kept


def _parse_iso_ts(stamp) -> float | None:
    """ESPN's ISO stamp → epoch seconds, or None for anything unparseable."""
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(
            str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def current_rows(rows: list[dict]) -> list[dict]:
    """One row per player: the NEWEST filing that player carries.

    ESPN lists every item a player has accumulated, so a man who was hurt,
    returned, and was hurt again appears three times. Rendered verbatim
    that reads as three separate players and lets a months-old "Active"
    sit beside a current "Out" — which is exactly how an injured player
    ends up looking available. Newest wins; undated rows lose to dated
    ones and otherwise keep the feed's own order."""
    best: dict[tuple, tuple[str, int, dict]] = {}
    for i, r in enumerate(rows):
        key = ((r.get("team") or "").lower(), (r.get("player") or "").lower())
        stamp = r.get("date") or ""
        prev = best.get(key)
        # ISO-8601 from one source sorts lexically; an undated row only
        # wins when nothing dated has been seen for that player.
        if prev is None or (stamp, -i) > (prev[0], -prev[1]):
            best[key] = (stamp, i, r)
    return [v[2] for v in sorted(best.values(), key=lambda v: v[1])]


def parse_injuries(payload) -> list[dict]:
    """ESPN's envelope → flat rows, one per player designation.

    Keys only, no positions; missing fields stay None so the page can
    show a dash instead of inventing certainty. `date` is ESPN's ISO
    stamp for when the item was posted — the page's "recent" cut sorts
    on it, so it passes through untouched.
    """
    rows = []
    for team in ((payload or {}).get("injuries") or []):
        if not isinstance(team, dict):
            continue
        team_name = team.get("displayName") or ""
        for inj in (team.get("injuries") or []):
            if not isinstance(inj, dict):
                continue
            ath = inj.get("athlete") or {}
            player = ath.get("displayName") or ath.get("fullName")
            status = inj.get("status")
            if not player or not status:
                continue
            details = inj.get("details") or {}
            what = " ".join(s for s in (details.get("type"),
                                        details.get("detail"))
                            if s and s != "Not Specified") or None
            rows.append({
                "team": team_name,
                "player": player,
                "pos": ((ath.get("position") or {}).get("abbreviation")
                        or None),
                "status": status,
                "date": inj.get("date"),
                "injury": what,
                "side": (details.get("side")
                         if details.get("side") not in (None, "Not Specified")
                         else None),
                "return_date": details.get("returnDate"),
                "comment": inj.get("shortComment") or None,
                "face": ((ath.get("headshot") or {}).get("href") or None),
            })
    return rows
