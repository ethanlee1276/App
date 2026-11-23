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

#: AND A MINUTE IN THE INACTIVES WINDOW (step ACH, 22 November 2026). An NFL club's inactives come out 90 minutes
#: before its kickoff, and its game's picks wait for both clubs' lists on this board
#: (engine/gameparlays.inactives_ready). On the Sunday the 4:25 games' lists reached our picks 25 to 42 minutes
#: after they came out, and up to ten of those minutes were this copy's age. From INACTIVES_WINDOW_MIN[0] minutes
#: before an NFL kickoff to INACTIVES_WINDOW_MIN[1] after it, the NFL board is asked again once its copy is a
#: minute old: at most one ask a minute while a window is open, against six an hour. Which games are near their
#: kickoff is read off the scoreboard copy the score loop keeps (data/cache/espn_nfl_scoreboard.json), never by
#: asking ESPN.
#: Off without a deploy: ``sudo ./deploy/setenv.sh QB_INACTIVES_FRESH off``.
INJURY_TTL_WINDOW = 60
INACTIVES_WINDOW_MIN = (100, 5)
INACTIVES_FRESH_ENV = "QB_INACTIVES_FRESH"


def nfl_kickoffs(path=None) -> list[float]:
    """Each game's kickoff (epoch seconds) on the NFL scoreboard copy the score loop keeps; [] without one."""
    import json
    from .fetch import _cache_path
    try:
        data = json.loads((path or _cache_path("espn_nfl_scoreboard.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for ev in (data.get("events") or []) if isinstance(data, dict) else []:
        t0 = _parse_iso_ts(ev.get("date")) if isinstance(ev, dict) else None
        if t0 is not None:
            out.append(t0)
    return out


def in_inactives_window(now: float | None = None, kickoffs=None) -> bool:
    """True while an NFL game kicks off within INACTIVES_WINDOW_MIN of ``now`` (``kickoffs``: epoch seconds, by
    default the scoreboard copy's)."""
    now = time.time() if now is None else now
    before, after = INACTIVES_WINDOW_MIN
    return any(t0 - before * 60 <= now <= t0 + after * 60
               for t0 in (nfl_kickoffs() if kickoffs is None else kickoffs))


def ttl_for(league: str, now: float | None = None, kickoffs=None) -> int:
    """How long ``league``'s copy is believed: INJURY_TTL_WINDOW for the NFL's in its inactives window, else
    INJURY_TTL."""
    import os
    if league != "nfl" or str(os.environ.get(INACTIVES_FRESH_ENV, "on")).strip().lower() in ("off", "0", "false",
                                                                                              "no"):
        return INJURY_TTL
    return INJURY_TTL_WINDOW if in_inactives_window(now, kickoffs) else INJURY_TTL


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


#: Asked of every board read (step ACT): a gzip body, which fetch_json unpacks.
GZIP = {"Accept-Encoding": "gzip"}


def fetch_injuries(league: str):
    """The raw board for one league. KeyError for a league with no feed
    is the right failure — callers iterate LEAGUES, they don't guess."""
    # PACKED (step ACT, 22 November): the NFL's board is 8.8 MB a read unpacked, read every minute in an inactives
    # window; asked for gzip, ESPN sends it packed and fetch_json unpacks it.
    return fetch_json(LEAGUES[league], f"espn_injuries_{league}.json",
                      ttl=ttl_for(league), user_agent=DEFAULT_AGENT, headers=GZIP)


#: ESPN keeps a player in the injuries feed after he is cleared, with the
#: status "Active" and no injury named. That is a RETURN notice, not a
#: designation — real news about a team, but the opposite of being hurt.
_ACTIVE = re.compile(r"^\s*active\s*$", re.I)


def is_return(row: dict) -> bool:
    """True for a cleared-to-play notice rather than a designation: ESPN's "Active" with no injury, or a school's
    own report saying he is available (engine/sources/cfbavail marks that row ``cleared``)."""
    return (bool(_ACTIVE.match(row.get("status") or "")) and not row.get("injury")) or row.get("cleared") is True


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


#: A BLURB'S LEAN (step ABT, moved here in step ABY so every page reads a blurb one way). On a Sunday morning the
#: blurb moves while the designation stands: at 7:24 AM ET Baker Mayfield was still "Questionable" and his blurb
#: said "Mayfield (foot/right thumb) is slated to play in Sunday's game against the Lions, Ian Rapoport of NFL
#: Network reports". A blurb that leans both ways ("With Omar Cooper ruled out, Mitchell is expected to play an
#: elevated role") is about someone else, and leans neither.
LEAN_OUT = re.compile(
    r"\b(won[’']?t play|will not play|ruled out|will miss|is out for|(?:is )?not expected to play|"
    r"isn[’']?t expected to play|not slated to play|not expected to start|won[’']?t suit up|will not suit up|"
    r"will sit out|won[’']?t be available|will not be available|is inactive|declared inactive|listed as inactive|"
    r"won[’']?t dress|will not dress|healthy scratch|won[’']?t travel|will not travel)\b", re.I)
LEAN_IN = re.compile(
    r"\b(slated to play|expected to play|set to play|plans? to play|will play|will start|expected to start|"
    r"slated to start|cleared to play|will be available|available to play|will suit up|will dress|good to go)\b",
    re.I)
#: Who reported it, where the blurb says ("..., Ian Rapoport of NFL Network reports.").
BY = re.compile(r"(?:,\s*|\bper\s+)([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,3}\s+of\s+(?:[Tt]he\s+)?"
                r"[A-Z][\w.'’&-]*(?:\s+[A-Z][\w.'’&-]*){0,4})(?:\s+reports?)?\.?\s*$")


def lean(comment, day: str | None = None) -> str | None:
    """"in", "out", or None: which way a blurb leans on its player's game on ``day`` (its weekday, Eastern; a
    blurb naming another day is about another game)."""
    text = " ".join(str(comment or "").split())
    if not about_game(text, day):
        return None
    out = bool(LEAN_OUT.search(text))
    inn = bool(LEAN_IN.search(LEAN_OUT.sub(" ", text)))
    if out == inn:
        return None
    return "out" if out else "in"


def reported_by(comment) -> str:
    """The reporter and outlet a blurb names at its end, or ""."""
    m = BY.search(" ".join(str(comment or "").split()))
    return m.group(1) if m else ""


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


#: How far after its posting a blurb's named day can fall: a Wednesday's blurb names Sunday's game, a Saturday's
#: ("McVay said Saturday that Williams ... is expected to play Wednesday") the Wednesday after it.
BLURB_AHEAD_DAYS = 4


def blurb_day(row: dict, now: dt.datetime | None = None):
    """The weekday (Eastern) of the game a row's blurb is about, when that game is today or later: the first day
    it names, today or later, within BLURB_AHEAD_DAYS of its posting ("Sunday" for a Friday blurb about Sunday's
    game); None for a
    blurb that names no day and was posted in the last day (about the next game); False for one about a game
    already played, or too old to say."""
    text = " ".join(str((row or {}).get("comment") or "").split())
    stamp = _parse_iso_ts((row or {}).get("date"))
    if not text or stamp is None:
        return False
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo("America/New_York")
    except Exception:                                        # noqa: BLE001
        return False
    today = (now or dt.datetime.now(dt.timezone.utc)).astimezone(zone).date()
    posted = dt.datetime.fromtimestamp(stamp, dt.timezone.utc).astimezone(zone).date()
    named = {m.lower() for m in WEEKDAYS.findall(text)}
    if not named:
        return None if (today - posted).days <= 1 else False
    for ahead in range(BLURB_AHEAD_DAYS + 1):
        d = posted + dt.timedelta(days=ahead)
        # A day already past is when it was said ("said Saturday"), or the game it was about: the next one named.
        if d >= today and d.strftime("%A").lower() in named:
            return d.strftime("%A")
    return False


#: The designations a lean can sit beside: a player cleared or already ruled out has nothing left to lean.
LEANS_ON = ("questionable", "doubtful", "day-to-day", "probable", "game-time decision", "gtd")


def newest_word(row: dict, now: dt.datetime | None = None) -> dict | None:
    """A listed player's newest word for his next game, off his row's blurb (step ABY): ``{"word", "day", "by"}``,
    the word "in" or "out" (which way the blurb leans), else under a bare "Day-To-Day" the league's own word
    (``designation``); the day the game's weekday (None when the blurb names none); ``by`` the reporter it names.
    None for a cleared or ruled-out player, a blurb about another game, or one that says neither."""
    status = str((row or {}).get("status") or "").strip().lower()
    if status not in LEANS_ON or not row.get("comment"):
        return None
    day = blurb_day(row, now)
    if day is False:
        return None
    word = lean(row["comment"], day)
    if not word and status == "day-to-day":
        word = designation(row["comment"], day)
    if not word:
        return None
    return {"word": word, "day": day, "by": reported_by(row["comment"])}


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
