"""Results read off the game logs, kept until the rows they read change.

The heartbeat at 00:56 on 9 November had the NHL build reading every
player's games of two seasons (about a million rows of player_game_logs)
in 17 of its 25 board seconds, on every build, ten minutes apart, while
those rows change about once a day: when the night's box scores are
ingested. The fantasy file's season means read the same seasons again in
the board's write stage, for every sport.

KEPT AGAINST THE LOGS' OWN COUNT OF THEIR CHANGES (2026-11-09). Every row
added to, taken from or changed in player_game_logs counts one more for its
sport and season in `log_generations`, by triggers in the history file
itself (engine/db SCHEMA), whoever writes it; a result is stored with the
counts of the seasons it read, and the table's random epoch, and served
while they still match. Reading them is one small query: the count it
replaced read every index entry of the rows (4.65 seconds for the NHL's
556,969 on the box at 03:05 on 9 November, served or not). A file the
schema has not reached has no such table, and falls back to the key below.

THE FALLBACK: A KEY THE ROWS THEMSELVES GIVE. A result is stored with the
count and the highest rowid of exactly the rows it read (one sport's
seasons), and served while both still match. Every write to the table goes
through `engine.db.upsert_player_logs`, which files a new or changed row
under a rowid above every other and leaves a row already stored exactly as
given where it is, so the results pulls that re-read days they already hold
(the daily catch-up, the settle pass's open-pick days) move nothing. The
key is read before the result is computed, so a write landing in between is
caught on the next call rather than stored as current. It is counted off
the primary key's own index, which holds no values, so it costs about a
tenth of the read it saves (0.08 against 1.9 seconds on a million-row
fixture).

A DELETE OR AN UPDATE IN PLACE FORGETS. The generations count both. The
fallback key does not: taking rows away lowers the count, but the next row
written can then take a freed rowid back (SQLite numbers a new row one above
the highest it holds), so a delete followed by as many new rows could give
the same key; and an UPDATE keeps a row's rowid. So the paths that do
either (the provisional box-score purge, the bet repair's log delete, the
season relabel) also call `forget(sport)`, which drops that sport's stored
results. A new one should too.

AND AGAINST THE CODE THAT COMPUTED IT. The key carries a hash of the
source file that computes the result (``code``), so a deploy that changes
how it is built reads the table afresh instead of serving the old shape
until the next box score lands.

WHAT EACH READ DID IS NOTED (2026-11-09). Beside each stored result, one
small file says what its last call did: served or read again, why (no copy
yet, rows changed, code changed, unreadable), and where its seconds went
(the key, the load, the read, the store). `status()` gathers them for the
heartbeat (launch._logcache_public), so whether the cache holds on the box
is a glance, not a guess from a build's timings.

THE WHOLE SPORT, AND WHAT ELSE A READ TAKES (2026-11-09). ``seasons=None``
keys a read on every season of its sport (the comps' spot index walks a
market's whole history), counted the same way. ``extra`` folds the read's
other inputs into its key (the date a read stops before, the schools a
table counts as FBS), so a new day or a new school reads again; ``code``
may name several source files when a read leans on another module's
helpers (the name normaliser).

ONLY THE PRODUCTION HISTORY FILE (`engine.db.DEFAULT_DB`). The tests and
the Lab open files of their own and read them fresh, as they always did;
`force=True` lets a test exercise the cache on a file of its own.

Standard library only. Never raises: a cache it cannot read or write is a
read from the table, as before.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import time

#: Bumped when a cached result's shape (or its key's) changes, so an old
#: file is ignored. 2: keyed on the logs' generations. 3: whole-sport keys,
#: extra inputs and several code files.
VERSION = 3
DIRNAME = "logcache"
#: The triggers that move `log_generations` (engine/db SCHEMA).
TRIGGERS = ("log_generations_insert", "log_generations_delete", "log_generations_update")


def db_file(conn) -> str:
    """The connection's main database file ("" for an in-memory one)."""
    try:
        for row in conn.execute("PRAGMA database_list").fetchall():
            if row[1] == "main":
                return os.path.realpath(row[2]) if row[2] else ""
    except Exception:                                        # noqa: BLE001
        pass
    return ""


def enabled_for(conn) -> bool:
    """True when `conn` is the production history file."""
    try:
        from .db import DEFAULT_DB
        path = db_file(conn)
        return bool(path) and path == os.path.realpath(str(DEFAULT_DB))
    except Exception:                                        # noqa: BLE001
        return False


def _seasons(seasons):
    """The sorted seasons a read covers, or None for the whole sport."""
    return None if seasons is None else sorted({int(s) for s in seasons})


def scope_key(conn, sport: str, seasons) -> tuple:
    """(rows, highest rowid) of one sport's seasons in player_game_logs
    (every season of it when ``seasons`` is None)."""
    seasons = _seasons(seasons)
    if seasons is None:
        r = conn.execute("SELECT COUNT(*), MAX(rowid) FROM player_game_logs WHERE sport=?",
                         (sport,)).fetchone()
    else:
        r = conn.execute(
            "SELECT COUNT(*), MAX(rowid) FROM player_game_logs WHERE sport=? "
            f"AND season IN ({','.join('?' * len(seasons))})",
            [sport, *seasons]).fetchone()
    return int(r[0] or 0), int(r[1] or 0)


def generations(conn, sport: str, seasons):
    """(epoch, ((season, count of changes), ...)) for one sport's seasons
    (every season it has a count for, a missing season included, when
    ``seasons`` is None), off `log_generations`; None when the file has no
    such table (or no epoch), and the caller counts the rows instead."""
    seasons = _seasons(seasons)
    try:
        # ALL THREE TRIGGERS, OR NO COUNTS. A table whose triggers are not
        # all there (a build killed between the schema's statements, a hand
        # that dropped one) would hold counts that stop moving, and serve a
        # result through every new box score; the row count never can.
        armed = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND tbl_name='player_game_logs' "
            f"AND name IN ({','.join('?' * len(TRIGGERS))})", TRIGGERS).fetchone()[0]
        if armed != len(TRIGGERS):
            return None
        epoch = conn.execute("SELECT gen FROM log_generations WHERE sport='~epoch'").fetchone()
        if epoch is None or epoch[0] is None:
            return None
        if seasons is None:
            # A season never written since the triggers were made has no
            # row, and its rows have not changed: absent is the same count
            # on both sides of the comparison.
            # -1 stands for rows filed with no season, which count too.
            every = conn.execute("SELECT season, gen FROM log_generations WHERE sport=?",
                                 (sport,)).fetchall()
            return int(epoch[0]), tuple(sorted(
                (-1 if r[0] is None else int(r[0]), int(r[1] or 0)) for r in every))
        got = {int(r[0]): int(r[1] or 0) for r in conn.execute(
            "SELECT season, gen FROM log_generations WHERE sport=? "
            f"AND season IN ({','.join('?' * len(seasons))})", [sport, *seasons])}
    except Exception:                                        # noqa: BLE001
        return None
    return int(epoch[0]), tuple((s, got.get(s, 0)) for s in seasons)


def folder() -> str:
    from . import feedstate
    return os.path.join(feedstate.directory(), DIRNAME)


def _path(name: str, sport: str, seasons: list, db: str) -> str:
    tag = hashlib.sha1(f"{db}|{seasons}".encode()).hexdigest()[:10]
    return os.path.join(folder(), f"{name}-{sport}-{tag}.pkl")


def code_hash(path) -> str:
    """sha1 of a source file's bytes, or of several files' in order ("" for
    one that cannot be read)."""
    if isinstance(path, (list, tuple)):
        return hashlib.sha1("|".join(code_hash(p) for p in path).encode()).hexdigest()
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except Exception:                                        # noqa: BLE001
        return ""


def _why(stored, key: dict) -> str:
    """Why a stored result is not the one asked for."""
    if not isinstance(stored, dict):
        return "unreadable"
    if stored.get("v") != key["v"]:
        return "new shape"
    if stored.get("code") != key["code"]:
        return "code changed"
    if any(stored.get(k) != key.get(k) for k in ("epoch", "gens", "rows", "top")):
        return "rows changed"
    if stored.get("extra") != key.get("extra"):
        return "inputs changed"
    return "key changed"


#: Set once a note could not be written in this process (said once).
_NOTE_FAILED = [False]


def _note(path: str, entry: dict) -> None:
    """What this call did, beside its stored result. Never raises: a lost
    note must never cost the read it describes. But a missing note reads on
    the heartbeat like a read that never ran, so the first failure in a
    process says so in the build's log, which no quiet build prints."""
    tmp = f"{path}.{os.getpid()}.note"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(entry, fh)
        os.replace(tmp, path[:-len(".pkl")] + ".json")
    except Exception as exc:                                 # noqa: BLE001
        try:
            os.unlink(tmp)
        except Exception:                                    # noqa: BLE001
            pass
        if not _NOTE_FAILED[0]:
            _NOTE_FAILED[0] = True
            print(f"  ⚠️  kept game-log read not noted ({type(exc).__name__}: {exc})")


def memo(conn, name: str, sport: str, seasons, compute, code=None, force: bool | None = None,
         clock=time.monotonic, extra=None):
    """``compute()``, or the result stored for the same rows when they have
    not changed since. ``seasons`` are the seasons ``compute`` reads (None:
    every season of the sport); ``code`` the source file that computes it
    (its caller's ``__file__``, or several); ``extra`` any other input it
    reads, JSON-shaped (a date, a hash), which must match too."""
    if not (enabled_for(conn) if force is None else force):
        return compute()
    t0 = clock()
    try:
        seasons = _seasons(seasons)
        gens = generations(conn, sport, seasons)
        if gens is not None:
            said = {"epoch": gens[0], "gens": gens[1]}
            shown = {"gens": {str(k): v for k, v in gens[1]}}
        else:
            rows, top = scope_key(conn, sport, seasons)
            said = {"rows": rows, "top": top}
            shown = {"rows": rows}
        db = db_file(conn)
        key = {"v": VERSION, "name": name, "sport": sport, "seasons": seasons,
               "db": db, **said, "code": code_hash(code) if code else "",
               "extra": extra}
        path = _path(name, sport, seasons, db)
    except Exception:                                        # noqa: BLE001
        return compute()
    note = {"name": name, "sport": sport, "seasons": seasons, "at": int(time.time()),
            **shown, "key_s": round(clock() - t0, 2)}
    why = "no copy"
    t1 = clock()
    try:
        with open(path, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            stored = pickle.load(fh)
        if isinstance(stored, dict) and stored.get("key") == key:
            note.update(kept=True, load_s=round(clock() - t1, 2), mb=round(size / 1e6, 1))
            _note(path, note)
            return stored["value"]
        why = _why(stored.get("key") if isinstance(stored, dict) else None, key)
    except FileNotFoundError:
        pass
    except Exception:                                        # noqa: BLE001
        why = "unreadable"
    t2 = clock()
    value = compute()
    note.update(kept=False, why=why, read_s=round(clock() - t2, 2))
    t3 = clock()
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as fh:
            pickle.dump({"key": key, "value": value}, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        note.update(store_s=round(clock() - t3, 2), mb=round(os.path.getsize(path) / 1e6, 1))
    except Exception as exc:                                 # noqa: BLE001
        note["not_stored"] = type(exc).__name__
        try:
            os.unlink(tmp)
        except Exception:                                    # noqa: BLE001
            pass
    _note(path, note)
    prune()
    return value


#: A kept read nothing has asked for in this many days is dropped (its note
#: is rewritten on every call, served or not): a renamed read, last season's
#: usage table, a market no board prices any more.
PRUNE_DAYS = 10

#: Set once this process has pruned (once is enough: builds are minutes).
_PRUNED = [False]


def prune(now: float | None = None) -> int:
    """Drop every kept read whose note is older than PRUNE_DAYS, once a
    process; returns how many files went. Never raises: a file it cannot
    drop is left for the next process, and costs only disk."""
    if _PRUNED[0]:
        return 0
    _PRUNED[0] = True
    t = time.time() if now is None else float(now)
    n = 0
    try:
        names = os.listdir(folder())
    except OSError:
        return 0
    for fn in names:
        if not fn.endswith(".json"):
            continue
        note = os.path.join(folder(), fn)
        try:
            if t - os.path.getmtime(note) < PRUNE_DAYS * 86400:
                continue
        except OSError:
            continue
        for path in (note[:-len(".json")] + ".pkl", note):
            try:
                os.unlink(path)
                n += 1
            except OSError:
                pass
    return n


def forget(sport: str) -> int:
    """Drop every result stored for ``sport`` (after a delete or an update
    in place, see the module's note). Returns how many it dropped; never
    raises."""
    n = 0
    try:
        for fn in os.listdir(folder()):
            parts = fn.split("-")
            if len(parts) >= 3 and parts[-2] == sport and fn.endswith(".pkl"):
                try:
                    os.unlink(os.path.join(folder(), fn))
                    n += 1
                except OSError:
                    pass
    except Exception:                                        # noqa: BLE001
        pass
    return n


def status() -> dict:
    """Each kept read's last call, the newest per name and sport, keyed
    ``name.sport``: served (``kept``) or read again and ``why``, and its
    seconds. {} when nothing is noted yet; ``{"error": <its type>}`` when the
    notes cannot be listed, which no quiet box answers. Never raises."""
    newest: dict = {}
    try:
        for fn in os.listdir(folder()):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder(), fn)) as fh:
                    e = json.load(fh)
            except Exception:                                # noqa: BLE001
                continue
            k = f"{e.get('name')}.{e.get('sport')}"
            if k not in newest or (e.get("at") or 0) > (newest[k].get("at") or 0):
                newest[k] = e
    except FileNotFoundError:
        return {}
    except Exception as exc:                                 # noqa: BLE001
        return {"error": type(exc).__name__}
    return {k: {f: v for f, v in e.items() if f not in ("name", "sport")}
            for k, e in sorted(newest.items())}
