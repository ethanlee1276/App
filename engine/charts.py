"""One door for every player chart: ``/api/players/chart?kind=&sport=&player=&season=``.

Ethan, 2026-10-13, on the list of charts the data could carry next: "Yes
do all of them and don't stop till they are all done, then make sure they
are all routed correctly like nfl." The carry and route charts each got an
endpoint of their own (/api/players/carries, /api/players/routes), and
they keep them. Every chart since is a KIND here: the leagues it draws,
the function that builds it from the database, and the table whose rows
say whether the league's charts are still being filled — so a new chart
is a line in this table, not another endpoint, and the page asks every
chart the same way (js/carrychart.js `ask`).

What every answer carries, whatever the kind: the builder's own dict
(``{}`` for a player with nothing on file), his face where the site has
one (`statlogs.face`), or ``{"filling": true}`` when no one in the league
has a row yet — the charts being filled is not the same as none for him.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sys
import threading
import time
import zlib
from collections import OrderedDict


def _carries(conn, sport, player, season):
    from . import carries
    return carries.chart(conn, sport, player, season)


def _routes(conn, sport, player, season):
    from . import targets
    return targets.chart(conn, player, season, sport=sport)


def _passes(conn, sport, player, season):
    from . import passes
    return passes.chart(conn, player, season, sport=sport)


def _kicks(conn, sport, player, season):
    from . import kicks
    return kicks.chart(conn, player, season)


def _ufc_fights(conn, sport, player, season):
    from .ufc import history
    return history.chart(conn, player, season)


def _spray(conn, sport, player, season):
    from .mlb import charts as M
    return M.hits_chart(conn, player, season)


def _mlb_pitches(conn, sport, player, season):
    from .mlb import charts as M
    return M.pitches_chart(conn, player, season)


def _nba_shots(conn, sport, player, season):
    """The NBA's shot chart, and college basketball's off its own table
    (engine/nba/shots ``league``; 2026-11-13)."""
    from .nba import shots as N
    return N.chart(conn, player, season, league=sport)


def _shots_stored(conn, sport):
    """Has the league's own shot table any row at all?"""
    from .nba.shots import table_of
    return _any_row(table_of(sport))(conn, sport)


def _nhl_shotmap(conn, sport, player, season):
    from .nhl import charts as H
    return H.shot_map(conn, player, season)


def _nhl_saves(conn, sport, player, season):
    from .nhl import charts as H
    return H.save_map(conn, player, season)


def _role(conn, sport, player, season):
    from . import role
    return role.chart(conn, sport, player, season)


def _matchup(conn, sport, player, season, opp="", fam=""):
    from . import matchview
    return matchview.chart(conn, sport, player, opp, season, hint=fam)


def _matchup_stored(conn, sport):
    """The league's own chart table (the matchup reads it)."""
    if sport in ("nfl", "cfb"):
        return _rows_in("targets" if sport == "nfl" else "carries")(conn, sport)
    return _any_row({"nba": "nba_shots", "cbb": "cbb_shots", "nhl": "nhl_shots", "mlb": "mlb_pa"}[sport])(conn, sport)


def _logged(conn, sport):
    """Has the league any box score stored at all?"""
    try:
        return bool(conn.execute("SELECT 1 FROM player_game_logs WHERE sport=? LIMIT 1", (sport,)).fetchone())
    except Exception:                                              # noqa: BLE001
        return True


def _any_row(table):
    """A league table with no sport column: has it any rows at all?"""
    def stored(conn, sport):
        try:
            return bool(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone())
        except Exception:                                          # noqa: BLE001
            return True
    return stored


def _rows_in(table):
    def stored(conn, sport):
        from .carries import stored as _stored
        return _stored(conn, sport, table=table)
    return stored


#: kind -> (the leagues it draws, builder(conn, sport, player, season),
#: stored(conn, sport): has the league any rows at all).
KINDS = {
    "carries": (("nfl", "cfb"), _carries, _rows_in("carries")),
    "routes": (("nfl", "cfb"), _routes, _rows_in("targets")),
    # College's from 2026-11-17: every throw and sack the college play file
    # names the passer of, drawn without depth or side (engine/passes).
    "passes": (("nfl", "cfb"), _passes, _rows_in("passes")),
    # The kicker's (2026-10-14): every field goal and extra point he tried,
    # off the same play-by-play read (engine/kicks).
    "kicks": (("nfl",), _kicks, _rows_in("kicks")),
    # Baseball's pair (2026-10-13, Ethan: "Can we do a hit tracker for
    # mlb?"): every ball a hitter put in play, and every pitch a pitcher
    # threw (engine/mlb/charts).
    "spray": (("mlb",), _spray, _any_row("mlb_pa")),
    "pitches": (("mlb",), _mlb_pitches, _any_row("mlb_pitches")),
    # Basketball's (2026-10-13): every shot he took, where from, made or
    # missed, off the league's own play-by-play (engine/nba/shots). College
    # basketball's from 2026-11-13, off each final's ESPN summary, on the
    # college court.
    "shots": (("nba", "cbb"), _nba_shots, _shots_stored),
    # Hockey's pair (2026-10-13): a skater's every attempt and a goalie's
    # every shot faced, off the shots the xG model already stores
    # (engine/nhl/charts).
    "shotmap": (("nhl",), _nhl_shotmap, _any_row("nhl_shots")),
    "saves": (("nhl",), _nhl_saves, _any_row("nhl_shots")),
    # Every league's (2026-10-14): how much he is used, game by game, off
    # the box scores the boards already read (engine/role).
    "role": (("nfl", "cfb", "nba", "wnba", "mlb", "nhl", "cbb"), _role, _logged),
    # A fighter's (2026-10-14): every bout on his record, how and when it
    # ended (engine/ufc/history).
    "fights": (("ufc",), _ufc_fights, _any_row("ufc_fights")),
    # Tonight's opponent beside his chart (2026-10-14): the zones of his own
    # chart, what the opponent allows in each against the league, and the
    # fit (engine/matchview). The one kind that is told the opponent.
    "matchup": (("nfl", "cfb", "nba", "cbb", "nhl", "mlb"), _matchup, _matchup_stored),
}
#: The kinds that also take tonight's opponent and the chart a page leads with.
TOLD_OPP = ("matchup",)


def known(kind: str, sport: str) -> bool:
    spec = KINDS.get(kind)
    return bool(spec) and sport in spec[0]


def answer(conn, kind: str, sport: str, player: str, season: int | None = None,
           opp: str = "", fam: str = "", took=None) -> dict:
    """The chart a page draws, as every chart's endpoint answers it. ``took``, a list, gets its parts' milliseconds
    (step AGI): the role chart's own, else the build's whole, then the face and the roster's facts."""
    from . import photos, statlogs
    t0 = [time.perf_counter()]

    def mark(part):
        if took is not None:
            now = time.perf_counter()
            took.append((part, (now - t0[0]) * 1000.0))
            t0[0] = now
    _leagues, build, stored = KINDS[kind]
    if kind == "role":
        from . import role as _rolechart
        out = _rolechart.chart(conn, sport, player, season, took=took) or {}
        t0[0] = time.perf_counter()
    else:
        out = (build(conn, sport, player, season, opp, fam) if kind in TOLD_OPP
               else build(conn, sport, player, season)) or {}
        mark("build")
    if out:
        out["kind"] = kind
        # The site's own photo first; a chart that knows his face from its
        # own record (a fighter's ESPN id) keeps it when the site has none.
        out["face"] = statlogs.face(conn, sport, out["player"]) or out.get("face") or ""
        # His league's action photo for his card, where it publishes one
        # (engine/photos: MLB's and the NHL's, off the id in his headshot).
        out["action"] = out.get("action") or photos.action_url(sport, out["face"])
        mark("face")
        # His position and number for the chart's head, off his club's
        # published roster where the chart's own record names neither.
        if not out.get("position") or not out.get("jersey"):
            meta = statlogs.roster_meta(sport, out["player"], out.get("team") or "")
            if meta.get("position") and not out.get("position"):
                out["position"] = meta["position"]
            if meta.get("number") and not out.get("jersey"):
                out["jersey"] = meta["number"]
            mark("roster")
    elif not stored(conn, sport):
        out = {"filling": True}
    return out


# --- the answers, kept ------------------------------------------------------------
#: A built chart is kept this long, as the bytes the endpoint sends.
ANSWER_TTL = 15 * 60
#: ...and past that, up to this long after it was built, it ANSWERS AT ONCE and is rebuilt behind it (step AFM,
#: 25 November 2026): Amon-Ra St. Brown's role chart, asked a while after it was kept, took 7.5 s to answer, where
#: the kept one answers in a dictionary lookup. Older than this, the reader waits for a fresh one.
ANSWER_STALE_MAX = 60 * 60
#: ...a chart of his own games, up to a day (step AGJ, 25 November 2026). Each kept answer carries his games' stamp
#: (step AFQ): a box score of his since, and the reader waits for a fresh one whatever its age, so what a day adds is
#: only the reader who comes back to him hours later answered at once. A matchup also reads his opponent's games,
#: which his stamp does not see, so it keeps the hour.
OWN_STALE_MAX = 24 * 60 * 60
#: ...and the kept answers stay under this many bytes, oldest read out first.
ANSWER_CAP = 32 * 1024 * 1024
_KEPT: "OrderedDict[tuple, tuple]" = OrderedDict()
_BYTES = [0]
_LOCK = threading.Lock()
_BUILDING: dict = {}


def answer_json(db_path, kind: str, sport: str, player: str, season: int | None = None,
                opp: str = "", fam: str = "", took=None) -> bytes:
    """`answer`, encoded — the one built in the last fifteen minutes when
    there is one, and one build however many ask for it at once.

    Ethan, 2026-10-14, with a pick page that read "The hit tracker didn't
    load. Try again in a moment.": "It should be snappy and basically be
    loaded already when you scroll down too go view it." A chart changes
    when a game is ingested, a few times a day; it was rebuilt from the
    database on every ask — every reader, every pick page opened again,
    and three at a time from one page (his chart, his role and tonight's
    matchup). Kept, a second reader's chart is a dictionary lookup.

    One build at a time per answer: a reader whose chart is being built
    by another request waits for that build rather than starting a second
    one beside it. What is kept is only a chart — never "still being
    filled" (the league's rows are arriving) and never ``{}`` (nothing on
    file for him yet), both of which can change within the minute. The
    database is opened only when a build is needed."""
    told = kind in TOLD_OPP
    key = (str(db_path), kind, sport, player, season, opp if told else "", fam if told else "")
    args = (db_path, kind, sport, player, season, opp, fam)
    mine = False
    for _ in range(2):
        with _LOCK:
            hit = _KEPT.get(key)
            now = time.time()
            if hit and now < hit[0]:
                _KEPT.move_to_end(key)
                return hit[1]
        # Not in memory (a restart since it was built, or read out under the cap): the one kept on disk, as past its
        # time (step AGJ).
        disk = hit is None and _disk_load(key, took)
        if disk:
            hit = disk
        # Past its fifteen minutes, not past its window, and his games as they were when it was built: answered now,
        # rebuilt behind it, one build at a time (step AFM). A box score of his landed since (step AFQ): the reader
        # waits for the fresh one, so a game just played is never answered with the chart from before it.
        if hit and now < hit[0] - ANSWER_TTL + _stale_max(key) and _same_games(hit, db_path, sport, player):
            with _LOCK:
                if key not in _BUILDING:
                    _BUILDING[key] = threading.Event()
                    threading.Thread(target=_behind, args=(key, args), daemon=True, name="chart-behind").start()
            return hit[1]
        with _LOCK:
            ev = _BUILDING.get(key)
            if ev is None:
                ev = _BUILDING[key] = threading.Event()
                mine = True
                break
        ev.wait(60)
    try:
        return _built(key, *args, took=took)
    finally:
        if mine:
            with _LOCK:
                _BUILDING.pop(key, None)
            ev.set()


def _built(key: tuple, db_path, kind, sport, player, season, opp, fam, took=None) -> bytes:
    """One answer built from the database, kept when it is a chart, with his games' stamp read before it."""
    from . import db as _db
    t0 = time.perf_counter()
    conn = _db.connect(str(db_path))
    try:
        stamp = _stamp_of(conn, sport, player)
        if took is not None:
            took.append(("stamp", (time.perf_counter() - t0) * 1000.0))
        # The parts asked for only when timed (a stand-in `answer`, as tests have, takes no `took`).
        out = answer(conn, kind, sport, player, season, opp=opp, fam=fam,
                     **({"took": took} if took is not None else {}))
    finally:
        conn.close()
    body = json.dumps(out).encode()
    if out and not out.get("filling"):
        _keep(key, body, stamp)
    return body


def _stamp_of(conn, sport: str, player: str) -> tuple:
    """(rows, highest rowid) of his games in player_game_logs, off the (sport, player) index alone: a new or
    corrected box score moves it, since engine/db.upsert_player_logs files a changed row under a new rowid."""
    r = conn.execute("SELECT COUNT(*), MAX(rowid) FROM player_game_logs WHERE sport=? AND player=?",
                     (sport, player)).fetchone()
    return int(r[0] or 0), int(r[1] or 0)


def _same_games(hit: tuple, db_path, sport: str, player: str) -> bool:
    """True when the kept answer's player has the games it was built from (or it carries no stamp to tell)."""
    if len(hit) < 3 or hit[2] is None:
        return True
    try:
        from . import db as _db
        conn = _db.connect(str(db_path))
        try:
            return _stamp_of(conn, sport, player) == hit[2]
        finally:
            conn.close()
    except Exception:                                     # noqa: BLE001 — unreadable: a fresh build tells
        return False


_BEHIND_SAID = [False]


def _behind(key: tuple, args: tuple) -> None:
    """A kept answer rebuilt in the background. A failure leaves the kept one answering until the hour is up,
    which looks like a chart nothing changed in; so the first failure in a process says so, once, in the
    service's log (as engine/playerpage._rebuild_ranks does)."""
    try:
        _built(key, *args)
    except Exception as exc:                              # noqa: BLE001 — the kept answer stands meanwhile
        if not _BEHIND_SAID[0]:
            _BEHIND_SAID[0] = True
            print(f"⚠️  a chart not rebuilt behind its kept answer ({key[1]}, {key[2]}: {type(exc).__name__}: "
                  f"{exc}): the kept one answers until it is an hour old", file=sys.stderr)
    finally:
        with _LOCK:
            ev = _BUILDING.pop(key, None)
        if ev is not None:
            ev.set()


def _stale_max(key: tuple) -> float:
    """How long after it was built a kept answer still answers at once while his games are the same."""
    return ANSWER_STALE_MAX if key[1] in TOLD_OPP else max(ANSWER_STALE_MAX, OWN_STALE_MAX)


def _keep(key: tuple, body: bytes, stamp=None, expires: float | None = None, disk: bool = True) -> None:
    with _LOCK:
        old = _KEPT.pop(key, None)
        if old:
            _BYTES[0] -= len(old[1])
        if len(body) > ANSWER_CAP // 8:
            return                       # one answer never crowds out the rest
        _KEPT[key] = (time.time() + ANSWER_TTL if expires is None else expires, body, stamp)
        _BYTES[0] += len(body)
        while _BYTES[0] > ANSWER_CAP and _KEPT:
            _, (_, b, *_) = _KEPT.popitem(last=False)
            _BYTES[0] -= len(b)
    if disk:
        _disk_save(key, body, stamp)


# --- the answers, kept on disk -----------------------------------------------------------
#: CHARTS SURVIVE A RESTART (step AGJ, 25 November 2026; Ethan: "Ok keep going and work more on these issues as they
#: are not fixed"). Every update restarts the server, and the kept answers lived only in its memory: the first reader
#: of each chart after an update waited for its build, Jahmyr Gibbs's role chart 26.4 s and Juan Soto's 32.8 s on the
#: live site. Each chart kept is also written beside the history file (cache/charts/), with his games' stamp and when
#: it was built. One missing from memory is read from there and answers at once while his games are the ones it was
#: built from, and a new one is built behind it: an update may have changed the code that built it, so one off the
#: disk is never taken as fresh. A box score of his since, and the reader waits for a fresh one, as with a kept one.
#: Kept a day at most, the newest DISK_CAP.
DISK_CAP = 4000
_DISK_SAID = [False]
_DISK_DIRS: set = set()
_DISK_SAVES = [0]


def _disk_file(key: tuple) -> str:
    """Where an answer is kept on disk: cache/charts/ beside its history file; "" for a database in memory."""
    path = str(key[0] or "")
    if not path or path == ":memory:" or path.startswith("file:"):
        return ""
    name = hashlib.sha1(json.dumps(list(key[1:])).encode()).hexdigest()[:24]
    return os.path.join(os.path.dirname(os.path.abspath(path)), "cache", "charts", f"{name}.gz")


def _disk_save(key: tuple, body: bytes, stamp=None) -> None:
    """An answer written to disk, as its key, his games' stamp and when, then the bytes the endpoint sends."""
    path = _disk_file(key)
    if not path:
        return
    where = os.path.dirname(path)
    head = json.dumps({"key": list(key[1:]), "stamp": list(stamp) if stamp else None,
                       "built": time.time()}).encode()
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        os.makedirs(where, exist_ok=True)
        with open(tmp, "wb") as fh:
            fh.write(gzip.compress(head + b"\n" + body, compresslevel=5))
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        # It still answers from memory; only the next restart builds it again, so say so once.
        if not _DISK_SAID[0]:
            _DISK_SAID[0] = True
            print(f"⚠️  a chart not kept on disk ({type(exc).__name__}: {exc}): a restart builds it again",
                  file=sys.stderr)
        return
    with _LOCK:
        _DISK_DIRS.add(where)
        _DISK_SAVES[0] += 1
        prune = _DISK_SAVES[0] % 50 == 1
    if prune:
        _disk_prune(where)


def _disk_prune(where: str) -> None:
    """Past a day, or past the newest DISK_CAP, gone (and a write a crash left behind)."""
    try:
        with os.scandir(where) as it:
            files = [(e.stat().st_mtime, e.path) for e in it if e.name.endswith((".gz", ".tmp"))]
    except OSError:
        return
    now = time.time()
    files.sort(reverse=True)
    for i, (mtime, path) in enumerate(files):
        if i >= DISK_CAP or now - mtime > max(ANSWER_STALE_MAX, OWN_STALE_MAX) or (
                path.endswith(".tmp") and now - mtime > 600):
            try:
                os.unlink(path)
            except OSError:
                pass


def _disk_load(key: tuple, took=None):
    """The answer kept on disk, held in memory as past its time, as ``(expires, body, stamp)``; None when there is
    none, it is past its window, or it cannot be read."""
    path = _disk_file(key)
    if not path:
        return None
    t0 = time.perf_counter()
    try:
        with open(path, "rb") as fh:
            raw = gzip.decompress(fh.read())
        head, _, body = raw.partition(b"\n")
        meta = json.loads(head)
    except (OSError, EOFError, ValueError, zlib.error):
        return None
    if not isinstance(meta, dict) or meta.get("key") != json.loads(json.dumps(list(key[1:]))) or not body:
        return None
    built, now = float(meta.get("built") or 0.0), time.time()
    if now - built > _stale_max(key):
        return None
    stamp = tuple(meta["stamp"]) if meta.get("stamp") else None
    expires = min(built + ANSWER_TTL, now - 1)
    _keep(key, body, stamp, expires=expires, disk=False)
    with _LOCK:
        _DISK_DIRS.add(os.path.dirname(path))
    if took is not None:
        took.append(("disk", (time.perf_counter() - t0) * 1000.0))
    return expires, body, stamp


def forget() -> None:
    """Every kept answer dropped (a test's fresh database, a rebuilt table), on disk too."""
    with _LOCK:
        _KEPT.clear()
        _BYTES[0] = 0
        dirs = list(_DISK_DIRS)
        _DISK_DIRS.clear()
    for where in dirs:
        shutil.rmtree(where, ignore_errors=True)
