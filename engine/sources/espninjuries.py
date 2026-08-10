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

from .fetch import DEFAULT_AGENT, fetch_json

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

#: Injury designations move on a practice-report cadence, not a ticker's.
INJURY_TTL = 1800


def fetch_injuries(league: str):
    """The raw board for one league. KeyError for a league with no feed
    is the right failure — callers iterate LEAGUES, they don't guess."""
    return fetch_json(LEAGUES[league], f"espn_injuries_{league}.json",
                      ttl=INJURY_TTL, user_agent=DEFAULT_AGENT)


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
