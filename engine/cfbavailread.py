"""THE BOX READS THE CONFERENCES' AVAILABILITY REPORTS (decision 20, step ADC, 23 November 2026).

The sixth look of engine/cfbavailprobe found every Power 4 conference's football availability report in one
vendor's public report: the Big Ten's, the ACC's and the Big 12's report pages and the SEC's page data each embed
app.hdintelligence.com/?source=<B10|SEC|ACC|B12>&sport=Football&conf=<same>&type=report. This module is the box's
reader of it: on a clock set to when the reports post (the evenings before a game, and on game days every ten
minutes, since each school's last report comes about 90 minutes before its kickoff), it asks for each conference's
current report, reads each school's filing out of whatever shape the data comes in (`filings`), and keeps them in
data/cfb_availability.json, which engine/sources/cfbavail lays over ESPN's college board.

It asks as a plain reader ("availability-reader/1.0"), never as a browser and never naming this site, one request
per conference per read. Off without a deploy: ``sudo ./deploy/setenv.sh QB_CFB_AVAIL_READ off``.
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
TIMEOUT_S = 20
MAX_BYTES = 4_000_000
#: A filing kept this long (the cache holds the current week and the one before it, for checking).
KEEP_S = 10 * 86400
#: The clock (Eastern time): on game days every ten minutes from 9 AM, on report evenings (from 5 PM, Monday to
#: Friday) every twenty, otherwise every three hours.
GAME_DAY_S = 10 * 60
EVENING_S = 20 * 60
QUIET_S = 3 * 3600
IDLE_S = 300
_LAST = {"at": 0.0, "archive": 0.0}


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
             "display_name", "athlete", "studentAthlete", "student_athlete", "athleteName", "athlete_name")
FIRST_KEYS = ("firstName", "first_name", "first")
LAST_KEYS = ("lastName", "last_name", "last")
STATUS_KEYS = ("status", "availability", "availabilityStatus", "availability_status", "designation",
               "participationStatus", "participation_status", "playerStatus", "player_status", "state")
POS_KEYS = ("position", "pos", "positionAbbreviation", "position_abbreviation")
SCHOOL_KEYS = ("school", "team", "teamName", "team_name", "schoolName", "school_name", "institution",
               "organization", "program", "club")
TIME_KEYS = ("released_at", "releasedAt", "published_at", "publishedAt", "submitted_at", "submittedAt",
             "report_time", "reportTime", "updated_at", "updatedAt", "created_at", "createdAt", "timestamp",
             "time", "date")
GAME_KEYS = ("game", "matchup", "event", "title", "opponent", "game_date", "gameDate", "kickoff", "start")
FINAL_RE = re.compile(r"game[\s-]*day|final|pre[\s-]*game|90", re.I)
_KNOWN = set(NAME_KEYS + FIRST_KEYS + LAST_KEYS + STATUS_KEYS + POS_KEYS + SCHOOL_KEYS + TIME_KEYS + GAME_KEYS) | {
    "players", "rows", "items", "data", "results", "reports", "report", "teams", "games", "entries", "list",
    "athletes", "roster", "availability_reports", "availabilityReports", "records", "content", "payload"}


def _text(v) -> str:
    if isinstance(v, dict):
        for k in ("name", "displayName", "display_name", "abbreviation", "label", "title", "value", "shortName"):
            if isinstance(v.get(k), str):
                return v[k]
        return ""
    return " ".join(str(v).split()) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _first(d: dict, keys) -> str:
    for k in keys:
        if k in d:
            t = _text(d[k])
            if t:
                return t
    return ""


def _player(d: dict) -> dict | None:
    """A player row in any of the shapes a report might use, or None."""
    word = ""
    for k in STATUS_KEYS:
        t = _text(d.get(k)) if k in d else ""
        if t and CA.status_of(t) is not None:
            word = t
            break
    if not word:
        return None
    name = _first(d, NAME_KEYS)
    if not name or CA.status_of(name) is not None and name == word:
        first, last = _first(d, FIRST_KEYS), _first(d, LAST_KEYS)
        name = f"{first} {last}".strip()
    if not name or len(name) > 60:
        return None
    return {"player": name, "pos": _first(d, POS_KEYS), "word": word}


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
                    "kind": ctx.get("kind", "")})
        return
    here = dict(ctx)
    school = _first(node, SCHOOL_KEYS)
    if school and not any(isinstance(node.get(k), (list, dict)) and k in SCHOOL_KEYS for k in node):
        here["school"] = school
    elif isinstance(node.get("school") or node.get("team"), dict):
        here["school"] = _text(node.get("school") or node.get("team")) or here.get("school", "")
    at = _first(node, TIME_KEYS)
    if at and CA._ts(at) is not None:
        here["at"] = at
    game = _first(node, GAME_KEYS)
    if game:
        here["game"] = game
    for k in ("type", "report_type", "reportType", "kind", "label", "version"):
        if isinstance(node.get(k), str) and node[k].strip():
            here["kind"] = node[k].strip()
            break
    # A dict that holds the rows under it and has a "name" is most likely the school (the nearest one wins).
    if isinstance(node.get("name"), str) and any(isinstance(v, list) for v in node.values()):
        here["maybe_school"] = node["name"]
    for k, v in node.items():
        if isinstance(v, (list, dict)):
            # …and a key that is no field name at all, holding rows, is most likely a school's name.
            sub = here if k in _KNOWN or not isinstance(v, list) else {**here, "maybe_school": k}
            _walk(v, sub, out)


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
        at = r["at"] if CA._ts(r["at"]) is not None else _dt.datetime.fromtimestamp(
            float(now), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        key = (r["school"], at)
        f = by.setdefault(key, {"conference": conf.lower(), "school": r["school"], "game": r["game"],
                                "filed_at": at, "final": bool(FINAL_RE.search(r["kind"] or "")), "players": []})
        f["players"].append({"player": r["player"], "pos": r["pos"], "word": r["word"]})
    return list(by.values())


# --- the cache -----------------------------------------------------------------------------------------------------
def merge(cache: dict, new: list[dict], now: float) -> dict:
    """The cache with ``new`` filings in: one per (conference, school, filed_at), the newest read of it kept,
    nothing older than KEEP_S."""
    by = {}
    for rep in (cache.get("reports") or []) + list(new):
        at = CA._ts(rep.get("filed_at"))
        if at is None or at < now - KEEP_S:
            continue
        by[(rep.get("conference"), rep.get("school"), rep.get("filed_at"))] = rep
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
#: THE DATA ADDRESS. The seventh look of engine/cfbavailprobe found the vendor's script naming /api/public-load;
#: it is asked with the embed's own query, as the conference pages embed it (type report: the current reports;
#: type archive: the weeks before, read every ARCHIVE_EVERY_S for checking the reading, never for picks).
DATA_URL = "https://app.hdintelligence.com/api/public-load?source={conf}&sport=Football&conf={conf}&type={kind}"
ARCHIVE_EVERY_S = 6 * 3600


def read_conf(conf: str, now: float, get=_get, kind: str = "report") -> tuple[list[dict], dict]:
    """(each school's filing in one conference's report data of ``kind``, what the read saw)."""
    url = DATA_URL.format(conf=conf, kind=kind)
    status, ctype, raw = get(url)
    seen = {"url": url, "status": status, "type": ctype.split(";")[0].strip(), "bytes": len(raw)}
    if status != "ok":
        return [], seen
    text = raw.decode("utf-8", errors="replace")
    seen["head"] = text[:3000]
    try:
        doc = json.loads(text)
    except ValueError:
        seen["error"] = "not JSON"
        return [], seen
    from .cfbavailprobe import shape
    seen["shape"] = shape(doc)
    got = filings(doc, conf, now)
    seen["filings"] = len(got)
    seen["players"] = sum(len(f["players"]) for f in got)
    seen["sample"] = got[:3]
    return got, seen


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


def read_once(now=None, get=_get, out=None, seen_out=None, game_days=None, checker=None) -> float:
    """Read every conference when its clock says so; the seconds until the next check."""
    now = time.time() if now is None else float(now)
    every = due_every(now, game_days)
    if now - _LAST["at"] < every or not DATA_URL:
        return min(IDLE_S, max(60, every - (now - _LAST["at"])))
    _LAST["at"] = now
    kinds = ["report"] + (["archive"] if now - _LAST.get("archive", 0.0) >= ARCHIVE_EVERY_S else [])
    if "archive" in kinds:
        _LAST["archive"] = now
    new, archive, seen = [], [], {}
    for conf in CONFS:
        for kind in kinds:
            got, saw = read_conf(conf, now, get, kind)
            (new if kind == "report" else archive).extend(got)
            seen[conf if kind == "report" else f"{conf} archive"] = saw
    cache = merge(CA.load(out), new, now)
    if "archive" in kinds:
        cache["archive"] = archive
        # THE CHECK, beside it: the past reports against the games' own box scores (never stops the read).
        try:
            cache["check"] = (checker or box_check)(archive)
        except Exception as exc:                               # noqa: BLE001
            cache["check"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    write(cache, now, out)
    p = Path(seen_out or SEEN)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"read_at": _dt.datetime.fromtimestamp(now, _dt.timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ"), "every_s": every, "conferences": seen,
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
    for f in archive or []:
        c = out.setdefault(f.get("conference") or "?", {"filings": 0, "keyed": 0, "men": 0, "known": 0,
                                                       "out": 0, "out_played": 0, "avail": 0, "avail_played": 0,
                                                       "contradicted": []})
        c["filings"] += 1
        team = CA.school_key(str(f.get("school") or ""), lookup)
        at = CA._ts(f.get("filed_at"))
        if not team or at is None:
            continue
        c["keyed"] += 1
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
