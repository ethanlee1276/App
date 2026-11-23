"""THE BOX READS THE CONFERENCES' AVAILABILITY REPORTS (decision 20, step ADC, 23 November 2026).

The sixth look of engine/cfbavailprobe found every Power 4 conference's football availability report in one
vendor's public report: the Big Ten's, the ACC's and the Big 12's report pages and the SEC's page data each embed
app.hdintelligence.com/?source=<B10|SEC|ACC|B12>&sport=Football&conf=<same>&type=report. This module is the box's
reader of it: on a clock set to when the reports post (the evenings before a game, and on game days every ten
minutes, since each school's last report comes about 90 minutes before its kickoff), it asks for each conference's
current report, reads each school's filing out of whatever shape the data comes in (`filings`), and keeps them in
data/cfb_availability.json, which engine/sources/cfbavail lays over ESPN's college board.

It asks as a plain reader ("availability-reader/1.0"), never as a browser and never naming this site, with the
same public calls the vendor's own public view makes (no key, no sign-in), one request per conference per read. Off without a deploy: ``sudo ./deploy/setenv.sh QB_CFB_AVAIL_READ off``.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .sources import cfbavail as CA

ENV = "QB_CFB_AVAIL_READ"
AGENT = "availability-reader/1.0"
CONFS = ("B10", "SEC", "ACC", "B12")
TIMEOUT_S = 60
#: The vendor's current reports carry every school's logo and the network's as images inside the data: the
#: SEC's and the ACC's ran past 4 MB on the first read (21:47 UTC) and came back cut.
MAX_BYTES = 40_000_000
#: A filing kept this long (the cache holds the current week and the one before it, for checking).
KEEP_S = 10 * 86400
#: THE CLOCK. Each current report says when it posts (publishDate and postedTime, in its conference's time) and
#: when its game kicks off (footer), so each conference is read two minutes after each of its reports posts and
#: 85 and 40 minutes before each of its kickoffs (the game-day report comes about 90 minutes before), and between
#: those only as a safety net (Eastern time): every two hours on a game day from 9 AM, every three on a weekday
#: evening from 5 PM, every six otherwise. A read is about 12 MB across the four (the reports carry their logos as
#: images), so the clock is the reports' own, not a fast poll.
GAME_DAY_S = 2 * 3600
EVENING_S = 3 * 3600
QUIET_S = 6 * 3600
IDLE_S = 300
AFTER_POST_S = 120
BEFORE_KICK_S = (85 * 60, 40 * 60)
_LAST = {"at": {}, "archive": 0.0}
#: {conference: [epoch seconds a read is due]} from its last read.
_NEXT: dict = {}
#: What each conference's last read saw, kept between reads for the check file.
_SEEN: dict = {}
ZONES = {"ET": "America/New_York", "EST": "America/New_York", "EDT": "America/New_York", "CT": "America/Chicago",
         "CST": "America/Chicago", "CDT": "America/Chicago", "MT": "America/Denver", "MST": "America/Phoenix",
         "PT": "America/Los_Angeles", "PST": "America/Los_Angeles", "AZ": "America/Phoenix"}


def on() -> bool:
    return str(os.environ.get(ENV, "on")).strip().lower() not in ("off", "0", "false", "no")


# --- the clock ---------------------------------------------------------------------------------------------------
def due_every(now: float, game_days=None) -> int:
    """Seconds between reads at ``now``: GAME_DAY_S on a day with a college game (``game_days``, Eastern dates;
    Saturday when none are given) from 9 AM to midnight, EVENING_S on a weekday evening from 5 PM, QUIET_S else."""
    from zoneinfo import ZoneInfo
    t = _dt.datetime.fromtimestamp(float(now), ZoneInfo("America/New_York"))
    days = set(game_days or ())
    game_day = t.date().isoformat() in days if days else t.weekday() == 5
    if game_day and t.hour >= 9:
        return GAME_DAY_S
    if t.weekday() < 5 and t.hour >= 17:
        return EVENING_S
    return QUIET_S


# --- the shape-free read -----------------------------------------------------------------------------------------
NAME_KEYS = ("player", "name", "playerName", "player_name", "fullName", "full_name", "displayName",
             "display_name", "athlete", "studentAthlete", "student_athlete", "athleteName", "athlete_name",
             "student-athlete", "student_athlete_name", "playerFullName")
FIRST_KEYS = ("firstName", "first_name", "first", "fname")
LAST_KEYS = ("lastName", "last_name", "last", "lname")
STATUS_KEYS = ("status", "availability", "availabilityStatus", "availability_status", "designation",
               "participationStatus", "participation_status", "playerStatus", "player_status", "state",
               "current_status", "currentStatus")
POS_KEYS = ("position", "pos", "positionAbbreviation", "position_abbreviation")
SCHOOL_KEYS = ("school", "team", "teamName", "team_name", "schoolName", "school_name", "institution",
               "organization", "program", "club")
#: WHEN A REPORT WAS FILED: only keys that say so. A bare "date" or "time" is the game's own (the vendor's
#: reports carry their kickoff as footer.date and footer.time), and a filing dated by its game would lose to
#: every older ESPN row filed on game day.
TIME_KEYS = ("released_at", "releasedAt", "published_at", "publishedAt", "publish_datetime", "submitted_at",
             "submittedAt", "report_time", "reportTime", "report_datetime", "updated_at", "updatedAt",
             "created_at", "createdAt", "timestamp", "last_updated", "lastUpdated")
GAME_KEYS = ("game", "matchup", "event", "title", "opponent", "game_name", "gameName")
#: Keys of a player row that are never his status (scanned when no status key names one).
NOT_STATUS = {k.lower() for k in NAME_KEYS + FIRST_KEYS + LAST_KEYS + POS_KEYS + SCHOOL_KEYS + TIME_KEYS
              + GAME_KEYS} | {"jersey", "number", "num", "class", "year", "injury", "notes", "note", "comment"}
FINAL_RE = re.compile(r"game[\s-]*day|final|pre[\s-]*game|90", re.I)
_KNOWN = {k.lower() for k in NAME_KEYS + FIRST_KEYS + LAST_KEYS + STATUS_KEYS + POS_KEYS + SCHOOL_KEYS
          + TIME_KEYS + GAME_KEYS} | {
    "players", "rows", "items", "data", "results", "reports", "report", "teams", "games", "entries", "list",
    "athletes", "roster", "availability_reports", "availabilityreports", "records", "content", "payload",
    "footer", "header", "home", "away", "report_days", "columns"}


def _text(v) -> str:
    if isinstance(v, dict):
        for k in ("name", "displayName", "display_name", "abbreviation", "label", "title", "value", "shortName"):
            if isinstance(v.get(k), str):
                return v[k]
        return ""
    return " ".join(str(v).split()) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _lower(d: dict) -> dict:
    """The dict's keys, folded: the vendor writes "Team" and "Player" where another writes "team"."""
    return {str(k).lower(): v for k, v in d.items()}


def _first(d: dict, keys) -> str:
    low = _lower(d)
    for k in keys:
        k = k.lower()
        if k in low:
            t = _text(low[k])
            if t:
                return t
    return ""


def _player(d: dict) -> dict | None:
    """A player row in any of the shapes a report might use, or None. Its status is a status key's word, else the
    last status word among its other columns (a table with one column per report reads left to right)."""
    low = _lower(d)
    word = ""
    for k in STATUS_KEYS:
        t = _text(low.get(k.lower())) if k.lower() in low else ""
        if t and CA.status_of(t) is not None:
            word = t
            break
    if not word:
        best = (-1, -1)
        for i, (k, v) in enumerate(low.items()):
            if k in NOT_STATUS or k.endswith("_id") or isinstance(v, (dict, list)):
                continue
            t = _text(v)
            if t and len(t) <= 40 and CA.status_of(t) is not None and (_col_rank(k), i) > best:
                best, word = (_col_rank(k), i), t
    if not word:
        return None
    name = _first(d, NAME_KEYS)
    if not name or CA.status_of(name) is not None and name == word:
        first, last = _first(d, FIRST_KEYS), _first(d, LAST_KEYS)
        name = f"{first} {last}".strip()
    if not name or len(name) > 60:
        return None
    return {"player": name, "pos": _first(d, POS_KEYS), "word": word}


def _col_rank(name: str) -> int:
    """Which of a row's report columns is the newest: the vendor names them Initial, Update 1, Update 2 and Game Day,
    and sends them in alphabetical order (the first read took Update 2 for Game Day's word)."""
    n = str(name or "").strip().lower()
    if re.search(r"game[\s_-]*day|final|pre[\s_-]*game", n):
        return 100
    m = re.search(r"update\s*(\d+)", n)
    if m:
        return 10 + int(m.group(1))
    if "initial" in n:
        return 1
    return 0


def _iso_day(text: str) -> str:
    """A date as YYYY-MM-DD from "2026-11-21" or "11/21/2026" (or "11/21/26"); "" when it is neither."""
    t = str(text or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return m.group(0)[:10]
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", t)
    if m:
        y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        return f"{y:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    if re.match(r"^[A-Za-z]{3}, \d{1,2} [A-Za-z]{3} \d{4}", t):         # "Sat, 26 Sep 2026 00:00:00 GMT"
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(t).date().isoformat()
        except (TypeError, ValueError):
            return ""
    return ""


def _kickoff(node: dict) -> str:
    """A report's game day (and time), where it carries one: footer {date, time} (the vendor's current reports),
    game_date/game_time, or a past week's row's own Date (its archive)."""
    low = _lower(node)
    foot = _lower(low["footer"]) if isinstance(low.get("footer"), dict) else {}
    day = hm = ""
    for src, dk, tk in ((foot, "date", "time"), (low, "game_date", "game_time"), (low, "gamedate", "gametime"),
                        (low, "game date", "game time"), (low, "date", "time"), (low, "week", "")):
        day = _iso_day(_text(src.get(dk))) if src else ""
        if day:
            hm = _text(src.get(tk)) if tk else ""
            break
    if not day:
        return ""
    return day + (f" {hm}" if re.match(r"^\d{1,2}:\d{2}", hm or "") else "")


def _zone(node: dict) -> str:
    return ZONES.get(str(_lower(node).get("conferencetimezone") or "").strip().upper(), "America/Chicago")


def _local(day: str, hm: str, zone: str) -> float | None:
    """Epoch seconds of a local date and time in ``zone``, or None."""
    from zoneinfo import ZoneInfo
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day or "") or not re.match(r"^\d{1,2}:\d{2}", hm or ""):
        return None
    h, m = (int(x) for x in hm.split(":")[:2])
    try:
        d = _dt.datetime.fromisoformat(day).replace(hour=h, minute=m, tzinfo=ZoneInfo(zone))
    except ValueError:
        return None
    return d.timestamp()


def _posted(node: dict) -> str:
    """When a current report was posted (publishDate and postedTime, in its conference's time), as UTC ISO, for a
    report that has posted; "" for one still pending or with no such fields."""
    low = _lower(node)
    if re.search(r"pending", _text(low.get("reporttype")) or "", re.I):
        return ""
    t = _local(_text(low.get("publishdate")), _text(low.get("postedtime")), _zone(node))
    return "" if t is None else _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def due_times(doc, now: float) -> list[float]:
    """When a conference's current reports next want reading: two minutes after each report still to post, and
    85 and 40 minutes before each kickoff still to come."""
    out = []
    for rep in (doc.values() if isinstance(doc, dict) else []):
        if not isinstance(rep, dict):
            continue
        low = _lower(rep)
        zone = _zone(rep)
        post = _local(_text(low.get("publishdate")), _text(low.get("postedtime")), zone)
        if post is not None and post + AFTER_POST_S > now:
            out.append(post + AFTER_POST_S)
        foot = _lower(low["footer"]) if isinstance(low.get("footer"), dict) else {}
        kick = _local(_text(foot.get("date")), _text(foot.get("time")), zone)
        for lead in BEFORE_KICK_S:
            if kick is not None and kick - lead > now:
                out.append(kick - lead)
    return sorted(set(out))


def _walk(node, ctx: dict, out: list) -> None:
    if isinstance(node, list):
        for x in node:
            _walk(x, ctx, out)
        return
    if not isinstance(node, dict):
        return
    row = _player(node)
    if row is not None:
        school = _first(node, SCHOOL_KEYS) or ctx.get("school", "") or ctx.get("maybe_school", "")
        own_at = _first(node, TIME_KEYS)
        at = own_at if CA._ts(own_at) is not None else ctx.get("at", "")
        out.append({**row, "school": school, "at": at, "game": _first(node, GAME_KEYS) or ctx.get("game", ""),
                    "kickoff": _kickoff(node) or ctx.get("kickoff", ""), "kind": ctx.get("kind", "")})
        return
    here = dict(ctx)
    low = _lower(node)
    school = _first(node, SCHOOL_KEYS)
    if school and not any(isinstance(low.get(k.lower()), (list, dict)) for k in SCHOOL_KEYS):
        here["school"] = school
    else:
        for k in ("school", "team"):
            if isinstance(low.get(k), dict) and _text(low[k]):
                here["school"] = _text(low[k])
                break
    at = _first(node, TIME_KEYS)
    if at and CA._ts(at) is not None:
        here["at"] = at
    posted = _posted(node)
    if posted:
        here["at"] = posted
    if re.search(r"pending", _text(low.get("reporttype")) or "", re.I):
        return                                                 # not posted yet: nothing in it is a filing
    game = _first(node, GAME_KEYS)
    if game:
        here["game"] = game
    kick = _kickoff(node)
    if kick:
        here["kickoff"] = kick
    for k in ("report_type", "reporttype", "type", "kind", "label", "version"):
        if isinstance(low.get(k), str) and low[k].strip():
            here["kind"] = low[k].strip()
            break
    # A dict that holds the rows under it and has a "name" is most likely the school (the nearest one wins).
    if isinstance(low.get("name"), str) and any(isinstance(v, list) for v in node.values()):
        here["maybe_school"] = low["name"]
    # A SCHOOL'S POSTED REPORT THAT LISTS NOBODY is still its report: a team entry of a posted report (its name and
    # its list of rows) is marked as filed even when the list is empty, so a healthy team's game-day report counts.
    if here.get("school") and here.get("at") and any(isinstance(low.get(k), list) for k in ("rows", "players")):
        out.append({"player": "", "pos": "", "word": "", "school": here["school"], "at": here["at"],
                    "game": here.get("game", ""), "kickoff": here.get("kickoff", ""), "kind": here.get("kind", "")})
    for k, v in node.items():
        if isinstance(v, (list, dict)):
            # …and a key that is no field name at all, holding rows, is most likely a school's name (a report id,
            # all digits, never is).
            named = str(k).lower() not in _KNOWN and isinstance(v, list) and not str(k).isdigit()
            _walk(v, {**here, "maybe_school": k} if named else here, out)


def filings(doc, conf: str, now: float) -> list[dict]:
    """Each school's filing in a conference's report data (``doc``, parsed JSON of any shape): {conference,
    school, game, filed_at, final, players: [{player, pos, word}]}. A row with no time of its own takes ``now``
    (the time it was read: a report the vendor shows is the current one), and a school with no name is left out."""
    rows: list[dict] = []
    _walk(doc, {}, rows)
    by: dict[tuple, dict] = {}
    for r in rows:
        if not r["school"]:
            continue
        dated = CA._ts(r["at"]) is not None
        at = r["at"] if dated else _dt.datetime.fromtimestamp(float(now), _dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        # One filing per school per read per game: a past week's reports carry no time of their own, and without
        # their game's day every one of a school's weeks would read as one filing.
        key = (r["school"], at, r.get("kickoff", "")[:10])
        f = by.setdefault(key, {"conference": conf.lower(), "school": r["school"], "game": r["game"],
                                "kickoff": r.get("kickoff", ""), "filed_at": at, "seen": not dated,
                                "final": bool(FINAL_RE.search(r["kind"] or "")), "players": []})
        if r["player"]:
            f["players"].append({"player": r["player"], "pos": r["pos"], "word": r["word"]})
    return list(by.values())


# --- the cache -----------------------------------------------------------------------------------------------------
def _same(a: dict, b: dict) -> bool:
    """Two reads of one school's filing for one game that say the same thing, man for man."""
    def words(r):
        return sorted((CA.player_name(p.get("player")), " ".join(str(p.get("word") or "").split()).lower())
                      for p in r.get("players") or [])
    return a.get("kickoff") == b.get("kickoff") and words(a) == words(b)


def merge(cache: dict, new: list[dict], now: float) -> dict:
    """The cache with ``new`` filings in: one per (conference, school, filed_at), the newest read of it kept,
    nothing older than KEEP_S. A filing with no time of its own is dated by the read that first saw it ("seen"):
    a later read that finds the school's filing for that game unchanged adds nothing, so its time stays the first
    sight of it, and only a changed filing is a new one."""
    by = {}
    latest: dict = {}
    for rep in (cache.get("reports") or []) + list(new):
        at = CA._ts(rep.get("filed_at"))
        if at is None or at < now - KEEP_S:
            continue
        game = (rep.get("conference"), rep.get("school"), rep.get("kickoff"))
        prev = latest.get(game)
        if rep.get("seen") and prev is not None and _same(prev, rep):
            continue
        by[(rep.get("conference"), rep.get("school"), rep.get("filed_at"))] = rep
        if prev is None or at >= CA._ts(prev.get("filed_at")):
            latest[game] = rep
    reports = sorted(by.values(), key=lambda r: (CA._ts(r["filed_at"]), r.get("school") or ""))
    return {**cache, "reports": reports}


def write(cache: dict, now: float, out=None) -> Path:
    p = Path(out or CA.CACHE)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {**cache, "read_at": _dt.datetime.fromtimestamp(float(now), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)
    return p


# --- the read ------------------------------------------------------------------------------------------------------
def _get(url: str):
    """(status, content type, body) of one plain GET; a failure is its name, never an exception."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json",
                                                   "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            ctype = resp.headers.get("Content-Type") or ""
            raw = resp.read(MAX_BYTES)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return "ok", ctype, raw
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}", "", b""
    except Exception as exc:                                   # noqa: BLE001
        return type(exc).__name__, "", b""


#: What the box saw on its last read, on our site for checking from where I build (no browser or user reads it).
SEEN = Path(__file__).resolve().parent.parent / "web" / "data" / "cfb_availability_read.json"
#: THE DATA CALLS (the eighth look, 21:26 UTC). /api/public-load answered 405 to a GET: it is the embed's
#: permission check, asked by POST, whose answer only switches the public view on. The rows come from the report
#: screens' own calls, which the vendor's public view makes with no key and no sign-in: POST
#: /api/get-publish-public (the current reports) and /api/get-archive-public (the weeks before, read every
#: ARCHIVE_EVERY_S for checking the reading, never for picks), each with {sport, organization, conference}: the
#: embed's own sport, source and conf.
BASE = "https://app.hdintelligence.com"
DATA = {"report": "/api/get-publish-public", "archive": "/api/get-archive-public"}
ARCHIVE_EVERY_S = 6 * 3600


def _post(url: str, body: dict):
    """(status, content type, body) of one plain JSON POST; a failure is its name, never an exception."""
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"User-Agent": AGENT, "Accept": "application/json",
                                              "Content-Type": "application/json", "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            ctype = resp.headers.get("Content-Type") or ""
            raw = resp.read(MAX_BYTES)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return "ok", ctype, raw
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}", "", b""
    except Exception as exc:                                   # noqa: BLE001
        return type(exc).__name__, "", b""


def read_conf(conf: str, now: float, post=_post, kind: str = "report") -> tuple[list[dict], dict, object]:
    """(each school's filing in one conference's report data of ``kind``, what the read saw, the data itself)."""
    url = BASE + DATA[kind]
    status, ctype, raw = post(url, {"sport": "Football", "organization": conf, "conference": conf})
    seen = {"url": url, "status": status, "type": ctype.split(";")[0].strip(), "bytes": len(raw),
            "at": _dt.datetime.fromtimestamp(float(now), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if status != "ok":
        return [], seen, None
    text = raw.decode("utf-8", errors="replace")
    seen["head"] = re.sub(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]{40,}", "data:image…", text[:20000])[:3000]
    try:
        doc = json.loads(text)
    except ValueError:
        seen["error"] = "not JSON"
        return [], seen, None
    from .cfbavailprobe import shape
    seen["shape"] = shape(doc)
    got = filings(doc, conf, now)
    seen["filings"] = len(got)
    seen["players"] = sum(len(f["players"]) for f in got)
    seen["sample"] = got[:3]
    if kind == "report" and isinstance(doc, dict):
        reps = [r for r in doc.values() if isinstance(r, dict)]
        seen["reports"] = [{"type": r.get("ReportType"), "posts": f"{r.get('publishDate')} {r.get('postedTime')}",
                            "kickoff": f"{(r.get('footer') or {}).get('date')} {(r.get('footer') or {}).get('time')}",
                            "teams": [g.get("teamName") for g in r.get("games") or [] if isinstance(g, dict)],
                            "rows": [len(g.get("rows") or []) for g in r.get("games") or [] if isinstance(g, dict)]}
                           for r in reps][:40]
    return got, seen, doc


def box_check(archive: list[dict]) -> dict:
    """`check_archive` against the box's own history and the board's schools."""
    from . import db as _db
    from .sources import cfbdata as _cd
    lookup = _cd.team_lookup(_cd.parse_teams(_cd.fetch_teams()))
    conn = _db.connect()
    try:
        return check_archive(archive, conn, lookup)
    finally:
        conn.close()


def read_once(now=None, post=_post, out=None, seen_out=None, game_days=None, checker=None) -> float:
    """Read each conference whose clock says so (its reports' own post times and kickoffs, or the safety net), and
    every conference's archive every ARCHIVE_EVERY_S; the seconds until the next check."""
    now = time.time() if now is None else float(now)
    every = due_every(now, game_days)
    last = _LAST["at"]
    due = [c for c in CONFS if now - last.get(c, 0.0) >= every
           or any(last.get(c, 0.0) < t <= now for t in _NEXT.get(c, ()))]
    archive_due = now - _LAST.get("archive", 0.0) >= ARCHIVE_EVERY_S
    if not due and not archive_due:
        soon = [t - now for c in CONFS for t in _NEXT.get(c, ()) if t > now]
        return max(60.0, min([float(IDLE_S)] + soon))
    new, archive = [], []
    for conf in due:
        last[conf] = now
        got, saw, doc = read_conf(conf, now, post, "report")
        new += got
        _SEEN[conf] = saw
        _NEXT[conf] = due_times(doc, now) if doc is not None else []
    if archive_due:
        _LAST["archive"] = now
        for conf in CONFS:
            got, saw, _doc = read_conf(conf, now, post, "archive")
            archive += got
            _SEEN[f"{conf} archive"] = saw
    cache = merge(CA.load(out), new, now)
    if archive_due:
        cache["archive"] = archive
        # THE CHECK, beside it: the past reports against the games' own box scores (never stops the read).
        try:
            cache["check"] = (checker or box_check)(archive)
        except Exception as exc:                               # noqa: BLE001
            cache["check"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    write(cache, now, out)
    stamp = lambda t: _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    p = Path(seen_out or SEEN)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"read_at": stamp(now), "every_s": every, "conferences": _SEEN,
                               "next": {c: [stamp(t) for t in _NEXT.get(c, ())[:12]] for c in CONFS},
                               "kept": len(cache.get("reports") or []), "check": cache.get("check"),
                               "trusted": CA.on()}, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)
    return IDLE_S


# --- the check -----------------------------------------------------------------------------------------------------
def check_archive(archive: list[dict], conn, lookup: dict) -> dict:
    """How the reading of past reports agrees with the games themselves, per conference: of the men a filing listed
    Out, how many have stats in their school's game within five days after it (the game contradicts the reading),
    and of those it listed Available or Probable, how many do (the game bears it out); with how many schools the
    board could key and how many men our logs know at all. The numbers that decide `cfbavail.TRUSTED`."""
    from .sources.oddsapi import normalize_name
    out: dict = {}
    logs: dict = {}

    def played(team: str, season: int) -> dict:
        if (team, season) not in logs:
            rows = conn.execute(
                "SELECT l.player, l.period, g.date FROM player_game_logs l LEFT JOIN games g ON g.sport='cfb' "
                "AND g.season=l.season AND g.period=l.period AND g.game_id=l.game_id "
                "WHERE l.sport='cfb' AND l.team=? AND l.season=?", (team, season)).fetchall()
            by: dict = {}
            for r in rows:
                day = str(r[2] or r[1] or "")[:10]
                by.setdefault(normalize_name(r[0] or ""), set()).add(day)
            logs[(team, season)] = by
        return logs[(team, season)]
    # EACH SCHOOL'S LAST WORD ON EACH GAME: an early "Out" can turn "Available" by game day, so only the last
    # filing a school made in a game's week is held to the game.
    last: dict = {}
    for f in archive or []:
        at = CA._ts(f.get("filed_at"))
        if at is None:
            continue
        game_day = _iso_day((f.get("kickoff") or "")[:10])
        wk = game_day or _dt.datetime.fromtimestamp(at, _dt.timezone.utc).isocalendar()[:2]
        key = (f.get("conference"), f.get("school"), wk)
        if key not in last or at > CA._ts(last[key].get("filed_at")):
            last[key] = f
    for f in last.values():
        c = out.setdefault(f.get("conference") or "?", {"filings": 0, "keyed": 0, "men": 0, "known": 0,
                                                       "out": 0, "out_played": 0, "avail": 0, "avail_played": 0,
                                                       "contradicted": []})
        c["filings"] += 1
        team = CA.school_key(str(f.get("school") or ""), lookup)
        at = CA._ts(f.get("filed_at"))
        if not team or at is None:
            miss = c.setdefault("unkeyed", [])
            if f.get("school") not in miss and len(miss) < 10:
                miss.append(f.get("school"))
            continue
        c["keyed"] += 1
        game_day = _iso_day((f.get("kickoff") or "")[:10])
        if game_day:
            # Its own game: the day and the one either side (a late kickoff is the next day in UTC); a past week's
            # row names only its week's Saturday, so its Wednesday to Sunday.
            g = _dt.date.fromisoformat(game_day)
            d0 = g
            span = (-1, 0, 1) if len((f.get("kickoff") or "").strip()) > 10 else (-3, -2, -1, 0, 1)
            window = {(g + _dt.timedelta(days=i)).isoformat() for i in span}
        else:
            d0 = _dt.datetime.fromtimestamp(at, _dt.timezone.utc).date()
            window = {(d0 + _dt.timedelta(days=i)).isoformat() for i in range(6)}
        season = d0.year if d0.month >= 7 else d0.year - 1
        by = played(team, season)
        for p in f.get("players") or []:
            name = normalize_name(CA.player_name(p.get("player")))
            status = CA.status_of(p.get("word"))
            if not name or status is None:
                continue
            c["men"] += 1
            days = by.get(name)
            if days is None:
                continue
            c["known"] += 1
            in_game = bool(days & window)
            if status == "OUT":
                c["out"] += 1
                if in_game:
                    c["out_played"] += 1
                    if len(c["contradicted"]) < 12:
                        c["contradicted"].append(f"{f.get('school')}: {p.get('player')} ({f.get('filed_at')})")
            elif status == "":
                c["avail"] += 1
                c["avail_played"] += int(in_game)
    return out
