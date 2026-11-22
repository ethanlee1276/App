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
    # Hockey (2026-10-03): ESPN's NHL board, same envelope.
    "nhl": f"{ROOT}/hockey/nhl/injuries",
    # Men's college basketball (2026-11-13), the college football board's
    # twin: schools have no reporting duty, so it runs sparse, and a league
    # whose board will not load is a note on the page, never a blank one
    # for the others (`injuries_build`).
    "cbb": f"{ROOT}/basketball/mens-college-basketball/injuries",
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


#: A BLURB'S GAME (steps ABT and ABU, 22 November 2026). ESPN files a blurb with each designation, and the blurb
#: is often newer than the designation, or older: on the Sunday morning eight NBA players read "Day-To-Day" with a
#: blurb about Friday's or Saturday's game. A blurb is read only for the game it names: one naming a weekday
#: other than the game's is about another game, and one about the rest of a game under way is about that game.
WEEKDAYS = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
IN_GAME = re.compile(r"\b(rest of|remainder of|won[’']?t return|will not return|did not return|didn[’']?t return|"
                     r"exited|left (?:the|\w+'s) (?:game|contest))\b", re.I)


def about_game(text, day: str | None = None) -> bool:
    """True when a blurb can be about the game on ``day`` (its weekday, Eastern): not about the rest of a game
    under way, and naming no weekday or that one."""
    text = " ".join(str(text or "").split())
    if not text or IN_GAME.search(text):
        return False
    if day:
        named = {m.lower() for m in WEEKDAYS.findall(text)}
        if named and day.lower() not in named:
            return False
    return True


#: THE LEAGUE'S OWN WORD UNDER "DAY-TO-DAY" (step ABU). ESPN files an NBA player who is probable, questionable
#: or doubtful all as "Day-To-Day", and the blurb under it keeps the league's word: on the Sunday morning,
#: "Siakam (hip) is listed as questionable for Sunday's game against New York", "Cunningham (knee) is probable
#: to play Sunday in Atlanta", "Antetokounmpo (groin) is listed as questionable for Sunday's game against
#: Oklahoma City". Probable plays nearly always and doubtful nearly never, and "Day-To-Day" said neither.
DESIGNATION = re.compile(r"\b(?:is|was|been|be|remains|considered|now|downgraded to|upgraded to)\s+"
                         r"(?:listed\s+(?:as\s+)?)?(probable|questionable|doubtful|a game-time decision)\b", re.I)


def designation(comment, day: str | None = None) -> str | None:
    """"probable", "questionable", "doubtful" or "game-time decision": the league's word a blurb gives for the
    game on ``day``; None when it gives none, or is about another game."""
    if not about_game(comment, day):
        return None
    words = {m.lower() for m in DESIGNATION.findall(" ".join(str(comment or "").split()))}
    if len(words) != 1:
        return None
    word = words.pop()
    return "game-time decision" if word == "a game-time decision" else word


def word_for_today(row: dict, now: dt.datetime | None = None) -> dict | None:
    """The league's own word under a bare "Day-To-Day" for today's or tomorrow's game (Eastern), for the
    Injuries page (step ABW): ``{"word", "day"}``, the day None when the blurb names none (then only a blurb
    filed in the last day counts). None for any other status, or a blurb about another day."""
    if str((row or {}).get("status") or "").strip().lower() != "day-to-day" or not row.get("comment"):
        return None
    try:
        from zoneinfo import ZoneInfo
        et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    except Exception:                                        # noqa: BLE001
        return None
    text = " ".join(str(row["comment"]).split())
    named = {m.lower() for m in WEEKDAYS.findall(text)}
    if named:
        for d in (et, et + dt.timedelta(days=1)):
            day = d.strftime("%A")
            if day.lower() in named:
                word = designation(text, day)
                return {"word": word, "day": day} if word else None
        return None
    stamp = _parse_iso_ts(row.get("date"))
    if stamp is None or et.timestamp() - stamp > 86400:
        return None
    word = designation(text)
    return {"word": word, "day": None} if word else None


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
            # The type and its detail, the detail only where it adds a word: the
            # feed files a concussion as type "Concussion", detail "Concussion",
            # and sixteen NFL players read "Concussion Concussion" (2026-11-17).
            kind = details.get("type") if details.get("type") != "Not Specified" else None
            more = details.get("detail") if details.get("detail") != "Not Specified" else None
            if kind and more and str(more).strip().lower() in str(kind).strip().lower():
                more = None
            what = " ".join(str(s) for s in (kind, more) if s) or None
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
