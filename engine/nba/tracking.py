"""NBA player tracking from stats.nba.com: a RESEARCH backfill that nothing on the site reads (NT1).

Ethan, 2026-11-05, on the data hunt's one parked source: "do it". The lab
(docs/NBA_LAB.md, "Every NBA source") could not reach the league's player
tracking: touches, drives, passes, potential assists and rebound chances.
Every number the board reads comes from the box score, which counts what
happened and not the chances that made it. Potential assists might read a
passer more steadily than his assists do, and rebound chances a big man more
steadily than his rebounds. Whether they do is a measurement. So this file
only fetches and stores; ``nbatrackcheck.py`` measures, fitted on one season
and judged on the other; and the board reads none of it unless that
measurement says so and the owner then decides (THE TERMS, below).

WHAT IS FETCHED. The league's own tracking dashboard (``leaguedashptstats``,
the JSON behind nba.com/stats/players/passing and its siblings), one game
date at a time (DateFrom = DateTo), every player who played that day,
totals, regular season, for four of its measures:

  * Passing: passes made and received, assists, secondary and free-throw
    assists, potential assists, assist points created;
  * Possessions: touches (front court, elbow, post, paint), time of
    possession, seconds and dribbles a touch, points a touch;
  * Drives: drives, and the shots, free throws, points, passes, assists and
    turnovers off them;
  * Rebounding: rebound chances (offensive, defensive, total), contested
    rebounds, chances deferred.

Every column an answer carries is kept, with the headers it came with, so a
field this file does not name is not lost.

READ FROM THE OPEN-SOURCE CLIENT. stats.nba.com is outside the build
session's network (the lab reaches GitHub and the package registries only),
so the request follows ``nba_api`` 1.12.0 (PyPI, MIT), read line by line:
base ``https://stats.nba.com/stats/{endpoint}``; every parameter the
endpoint takes, sent sorted by name and empty when unused; and the headers
nba.com's own pages send: Referer and Origin ``https://www.nba.com``, the
two ``x-nba-stats-*`` headers, and a desktop browser's User-Agent, without
which the API holds the request open until it times out. Nothing else is
sent: no account, no address, no key.

GENTLE, AND STOPPED BY ITS OWN SIGNS. About 1,320 requests cover two seasons
(some 165 game days a season, four measures each). One goes every PACE_S
seconds plus up to half that again at random, so about 110 minutes in all; a
run stops at its time budget and the next one resumes where it stopped, each
date and measure marked done once stored. Three failures in a row, or a 403
or 429 at all, end the run: the league refuses many cloud servers' addresses
outright, and a run that keeps knocking learns nothing more.

THE TERMS. NBA.com's terms of use allow personal, non-commercial use of its
content. A paid product reading this would raise the same open question the
box's reads of ``cdn.nba.com`` already do (docs/DATA_SOURCES.md keeps that
on the record). So this is research: it lives in its own database
(``data/research/nba_tracking.db``, not in the nightly backup, since it can
be fetched again), and nothing the site serves or builds reads it.

    python3 -m engine.nba.tracking --probe [YYYY-MM-DD]   # one request, stores nothing
    python3 -m engine.nba.tracking --status               # what is stored, read-only
    python3 -m engine.nba.tracking --backfill [--minutes 120] [--seasons 2024,2025]

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import json
import random
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

BASE = "https://stats.nba.com/stats/leaguedashptstats"
MEASURES = ("Passing", "Possessions", "Drives", "Rebounding")
STORE = Path(__file__).resolve().parents[2] / "data" / "research" / "nba_tracking.db"
TIMEOUT_S = 30
#: Seconds between requests, plus up to half again at random.
PACE_S = 4.0
#: Failures in a row that end a run (a refusal ends it at once).
STOP_AFTER = 3
DEFAULT_MINUTES = 120
#: The two seasons the measurement needs, by default: the last two the box
#: stores before the one in progress.
DEFAULT_SEASONS = 2
#: An answer's identity columns; every other column is a number.
ID_COLS = ("PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION")

#: nba_api 1.12.0's STATS_HEADERS (nba_api/stats/library/http.py), less the
#: three Sec-* hints, plus the two x-nba-stats headers nba.com's own pages
#: send. Brotli is not offered: the standard library cannot read it.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}


class TrackUnavailable(RuntimeError):
    """The league did not answer, or answered with something unusable."""


class TrackRefused(TrackUnavailable):
    """403 or 429: the league said no. A run stops at the first one."""


def season_label(season: int) -> str:
    """2024 -> "2024-25": the league names a season for both its years."""
    return f"{int(season)}-{(int(season) + 1) % 100:02d}"


def params(day: str, season: int, measure: str) -> list:
    """The query, as nba_api sends `LeagueDashPtStats`: every parameter,
    sorted by name, empty when unused (its one optional ``ISTRound`` is
    left out, as nba_api leaves out a None). One day: DateFrom = DateTo."""
    mdy = f"{day[5:7]}/{day[8:10]}/{day[:4]}"
    p = {
        "LastNGames": "0", "Month": "0", "OpponentTeamID": "0", "PerMode": "Totals",
        "PlayerOrTeam": "Player", "PtMeasureType": measure, "Season": season_label(season),
        "SeasonType": "Regular Season", "College": "", "Conference": "", "Country": "",
        "DateFrom": mdy, "DateTo": mdy, "Division": "", "DraftPick": "", "DraftYear": "",
        "GameScope": "", "Height": "", "LeagueID": "00", "Location": "", "Outcome": "",
        "PORound": "", "PlayerExperience": "", "PlayerPosition": "", "SeasonSegment": "",
        "StarterBench": "", "TeamID": "", "VsConference": "", "VsDivision": "", "Weight": "",
    }
    return sorted(p.items())


def url(day: str, season: int, measure: str) -> str:
    return BASE + "?" + urllib.parse.urlencode(params(day, season, measure))


def _body(resp) -> bytes:
    raw = resp.read()
    enc = str((resp.headers.get("Content-Encoding") if resp.headers else "") or "").lower()
    if "gzip" in enc or raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    if "deflate" in enc:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def parse(payload: dict) -> tuple:
    """``(headers, rows)`` from an answer: its first result set (the
    endpoint has one), each row as the list it came as."""
    sets = payload.get("resultSets") or payload.get("resultSet") or []
    if isinstance(sets, dict):
        sets = [sets]
    if not sets:
        raise TrackUnavailable("the answer carried no result set")
    first = sets[0]
    heads = [str(h) for h in (first.get("headers") or [])]
    rows = [list(r) for r in (first.get("rowSet") or [])]
    missing = [c for c in ("PLAYER_ID", "PLAYER_NAME") if c not in heads]
    if missing:
        raise TrackUnavailable(f"the answer's columns lack {', '.join(missing)}")
    return heads, rows


def fetch(day: str, season: int, measure: str, opener=None, timeout: float = TIMEOUT_S) -> tuple:
    """``(headers, rows)`` for one day and one measure. ``opener`` is for
    tests (``urllib.request.urlopen`` by default)."""
    req = urllib.request.Request(url(day, season, measure), headers=dict(HEADERS))
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            body = _body(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise TrackRefused(f"stats.nba.com refused the request ({exc.code})") from exc
        raise TrackUnavailable(f"stats.nba.com answered {exc.code}") from exc
    except Exception as exc:                                  # noqa: BLE001
        raise TrackUnavailable(f"stats.nba.com did not answer: {type(exc).__name__}: {exc}") from exc
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise TrackUnavailable(f"stats.nba.com sent something that is not JSON ({len(body)} bytes)") from exc
    return parse(payload)


# --- the store ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS done (
    date TEXT, measure TEXT, season INTEGER, n INTEGER, headers TEXT, at TEXT,
    PRIMARY KEY (date, measure)
);
CREATE TABLE IF NOT EXISTS rows (
    date TEXT, measure TEXT, player_id INTEGER, player TEXT, team TEXT, vals TEXT,
    PRIMARY KEY (date, measure, player_id)
);
"""


def open_store(path=None) -> sqlite3.Connection:
    p = Path(path or STORE)
    if str(p) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.executescript(SCHEMA)
    return conn


def read_store(path=None):
    """The store opened read-only, or None when there is none yet."""
    p = Path(path or STORE)
    if not p.exists():
        return None
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def keep(conn, day: str, season: int, measure: str, heads: list, rows: list) -> int:
    """Store one answer and mark its date and measure done, in one commit."""
    i = {h: k for k, h in enumerate(heads)}
    out = []
    for r in rows:
        try:
            pid = int(r[i["PLAYER_ID"]])
        except (TypeError, ValueError, IndexError):
            continue
        team = r[i["TEAM_ABBREVIATION"]] if "TEAM_ABBREVIATION" in i else ""
        out.append((day, measure, pid, str(r[i["PLAYER_NAME"]] or ""), str(team or ""),
                    json.dumps(r, separators=(",", ":"))))
    with conn:
        conn.execute("DELETE FROM rows WHERE date=? AND measure=?", (day, measure))
        conn.executemany("INSERT OR REPLACE INTO rows VALUES (?,?,?,?,?,?)", out)
        conn.execute("INSERT OR REPLACE INTO done VALUES (?,?,?,?,?,?)",
                     (day, measure, int(season), len(out), json.dumps(heads),
                      _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    return len(out)


def _days(hist) -> list:
    """``[(date, season)]`` for every NBA day the box stores box scores
    for, the season read off the DATE (engine/seasons: named for the year it
    starts), never off the stored label, so the league is always asked for
    the season it names that day by."""
    from ..seasons import season_of
    days = {str(r[0])[:10] for r in hist.execute("SELECT DISTINCT period FROM player_game_logs WHERE sport='nba'")}
    return sorted((d, season_of("nba", d)) for d in days if len(d) == 10)


def game_days(hist, seasons: list) -> list:
    """``[(date, season)]`` of those seasons, oldest first."""
    want = {int(x) for x in seasons or []}
    return [(d, s) for d, s in _days(hist) if s in want]


def stored_seasons(hist) -> list:
    return sorted({s for _d, s in _days(hist)})


def default_seasons(hist, today: str | None = None) -> list:
    """The last DEFAULT_SEASONS seasons the box stores before today's."""
    from ..seasons import season_of
    now = season_of("nba", today or _dt.date.today().isoformat())
    return [s for s in stored_seasons(hist) if s < now][-DEFAULT_SEASONS:]


def todo(hist, store, seasons: list, today: str | None = None) -> list:
    """``[(date, season, measure)]`` not yet stored, oldest first. Today and
    yesterday wait: the league's tracking for a night fills in overnight."""
    cut = (_dt.date.fromisoformat(today) if today else _dt.date.today()) - _dt.timedelta(days=1)
    have = {(d, m) for d, m in store.execute("SELECT date, measure FROM done")}
    return [(d, s, m) for d, s in game_days(hist, seasons) if d < cut.isoformat()
            for m in MEASURES if (d, m) not in have]


def backfill(hist, store, seasons: list, minutes: float = DEFAULT_MINUTES, max_requests: int = 0,
             pace_s: float = PACE_S, opener=None, sleep=time.sleep, clock=time.monotonic,
             log=print, today: str | None = None) -> dict:
    """Fetch and store what `todo` lists until it is done, the time budget
    runs out, ``max_requests`` have gone (0 = no cap), or the league says
    no. Returns ``{"asked", "stored", "rows", "left", "stopped"}``."""
    work = todo(hist, store, seasons, today)
    out = {"asked": 0, "stored": 0, "rows": 0, "left": len(work), "stopped": ""}
    if not work:
        out["stopped"] = "nothing left to fetch"
        return out
    end = clock() + max(0.0, float(minutes)) * 60.0
    fails = 0
    for n, (day, season, measure) in enumerate(work):
        if max_requests and out["asked"] >= max_requests:
            out["stopped"] = f"stopped at {max_requests} requests (--max)"
            break
        if n:
            sleep(pace_s + random.uniform(0.0, pace_s / 2.0))
        if clock() >= end:
            out["stopped"] = f"stopped at the {minutes:g}-minute budget; the next run resumes here"
            break
        out["asked"] += 1
        try:
            heads, rows = fetch(day, season, measure, opener=opener)
        except TrackRefused as exc:
            out["stopped"] = f"{exc}; stopped (the league refuses this address, or asks us to slow down)"
            break
        except TrackUnavailable as exc:
            fails += 1
            log(f"  {day} {measure}: {exc}")
            if fails >= STOP_AFTER:
                out["stopped"] = (f"{fails} failures in a row ({exc}); stopped. The league may not answer "
                                  f"this box's address")
                break
            continue
        fails = 0
        out["rows"] += keep(store, day, season, measure, heads, rows)
        out["stored"] += 1
        if out["stored"] % 40 == 0:
            log(f"  {out['stored']} stored, through {day}")
    out["left"] = len(todo(hist, store, seasons, today))
    if not out["stopped"]:
        out["stopped"] = "done" if not out["left"] else "stopped"
    return out


def load(store, dates=None) -> dict:
    """``{(date, normalized name): {"_team", "_min", FIELD: value, ...}}``,
    every measure stored for that day merged into one row a player."""
    from ..sources.oddsapi import normalize_name
    heads = {(d, m): json.loads(h or "[]") for d, m, h in store.execute(
        "SELECT date, measure, headers FROM done")}
    want = set(dates) if dates else None
    out: dict = {}
    for d, m, player, team, vals in store.execute("SELECT date, measure, player, team, vals FROM rows"):
        if want is not None and d not in want:
            continue
        h = heads.get((d, m)) or []
        try:
            v = json.loads(vals)
        except ValueError:
            continue
        row = out.setdefault((d, normalize_name(player)), {"_team": team})
        for name, x in zip(h, v):
            if name in ID_COLS or name in ("GP", "W", "L"):
                continue
            if name == "MIN":
                try:
                    row["_min"] = float(x)
                except (TypeError, ValueError):
                    pass
                continue
            try:
                row[name] = float(x)
            except (TypeError, ValueError):
                continue
    return out


def status(hist, store) -> list:
    """What is stored, by season and measure, against the days the box has."""
    lines = []
    have: dict = {}
    for season, m, n, rows in store.execute(
            "SELECT season, measure, COUNT(*), SUM(n) FROM done GROUP BY season, measure"):
        have[(int(season), m)] = (int(n), int(rows or 0))
    seasons = sorted({s for s, _m in have} | set(default_seasons(hist)))
    for s in seasons:
        days = len({d for d, _s in game_days(hist, [s])})
        parts = [f"{m} {have.get((s, m), (0, 0))[0]}/{days} days ({have.get((s, m), (0, 0))[1]:,} rows)"
                 for m in MEASURES]
        lines.append(f"{season_label(s)}: " + "; ".join(parts))
    last = store.execute("SELECT MAX(at) FROM done").fetchone()[0]
    lines.append(f"last stored: {last or 'nothing yet'}")
    return lines or ["nothing stored yet"]


def probe(hist=None, day: str | None = None, opener=None) -> list:
    """One request (Passing) for one stored day, two or more days back: what
    the league answered, the row count and the columns. Stores nothing."""
    if day is None and hist is not None:
        cut = (_dt.date.today() - _dt.timedelta(days=2)).isoformat()
        row = hist.execute("SELECT MAX(period) FROM player_game_logs WHERE sport='nba' AND period <= ?",
                           (cut,)).fetchone()
        if row and row[0]:
            day = str(row[0])[:10]
    if day is None:
        return ["No stored NBA day to ask about; pass one: --probe YYYY-MM-DD"]
    from ..seasons import season_of
    season = season_of("nba", day)
    started = time.monotonic()
    try:
        heads, rows = fetch(day, season, "Passing", opener=opener)
    except TrackUnavailable as exc:
        return [f"{day} Passing: {exc} (after {time.monotonic() - started:.0f} s)",
                "Nothing stored. If it timed out, the league is likely refusing this box's address."]
    sample = ""
    if rows:
        i = {h: k for k, h in enumerate(heads)}
        r = rows[0]
        sample = (f"; first row: {r[i['PLAYER_NAME']]}"
                  + (f", potential assists {r[i['POTENTIAL_AST']]}" if "POTENTIAL_AST" in i else ""))
    return [f"{day} Passing: ok, {len(rows)} player(s) in {time.monotonic() - started:.1f} s{sample}",
            "columns: " + ", ".join(heads),
            "Nothing stored."]


def _hist():
    from .. import db
    return sqlite3.connect(f"file:{db.DEFAULT_DB}?mode=ro", uri=True)


def _arg(argv: list, name: str, default=None):
    if name in argv:
        k = argv.index(name)
        if k + 1 < len(argv) and not argv[k + 1].startswith("--"):
            return argv[k + 1]
    return default


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--probe" in argv:
        hist = _hist()
        try:
            for line in probe(hist, _arg(argv, "--probe")):
                print(" ", line)
        finally:
            hist.close()
        return 0
    if "--status" in argv:
        store = read_store()
        if store is None:
            print("Nothing stored yet (no data/research/nba_tracking.db).")
            return 0
        hist = _hist()
        try:
            for line in status(hist, store):
                print(" ", line)
        finally:
            hist.close()
            store.close()
        return 0
    if "--backfill" in argv:
        hist = _hist()
        store = open_store()
        try:
            raw = _arg(argv, "--seasons")
            seasons = [int(x) for x in raw.split(",")] if raw else default_seasons(hist)
            if not seasons:
                print("No finished NBA season stored on this box to backfill.")
                return 1
            minutes = float(_arg(argv, "--minutes", DEFAULT_MINUTES))
            cap = int(_arg(argv, "--max", 0) or 0)
            left = len(todo(hist, store, seasons))
            print(f"Tracking backfill for {', '.join(season_label(s) for s in seasons)}: {left} request(s) left, "
                  f"one every {PACE_S:g}-{PACE_S * 1.5:g} s, for up to {minutes:g} minutes.")
            res = backfill(hist, store, seasons, minutes=minutes, max_requests=cap)
            print(f"Asked {res['asked']}, stored {res['stored']} ({res['rows']:,} player rows); "
                  f"{res['left']} left. {res['stopped'][:1].upper() + res['stopped'][1:]}.")
        finally:
            hist.close()
            store.close()
        return 0
    print(__doc__.strip().split("\n\n")[0])
    print("\n  --probe [YYYY-MM-DD]   one request, stores nothing\n  --status              what is stored"
          "\n  --backfill [--minutes N] [--seasons 2024,2025] [--max N]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
