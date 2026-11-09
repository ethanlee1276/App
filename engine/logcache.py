"""Results read off the game logs, kept until the rows they read change.

The heartbeat at 00:56 on 9 November had the NHL build reading every
player's games of two seasons (about a million rows of player_game_logs)
in 17 of its 25 board seconds, on every build, ten minutes apart, while
those rows change about once a day: when the night's box scores are
ingested. The fantasy file's season means read the same seasons again in
the board's write stage, for every sport.

KEPT AGAINST A KEY THE ROWS THEMSELVES GIVE. A result is stored with the
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

A DELETE OR AN UPDATE IN PLACE FORGETS. Taking rows away lowers the count,
but the next row written can then take a freed rowid back (SQLite numbers a
new row one above the highest it holds), so a delete followed by as many
new rows could give the same key; and an UPDATE keeps a row's rowid. The
paths that do either (the provisional box-score purge, the bet repair's log
delete, the season relabel) call `forget(sport)`, which drops that sport's
stored results. A new one must too.

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

#: Bumped when a cached result's shape changes, so an old file is ignored.
VERSION = 1
DIRNAME = "logcache"


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


def scope_key(conn, sport: str, seasons) -> tuple:
    """(rows, highest rowid) of one sport's seasons in player_game_logs."""
    seasons = sorted({int(s) for s in seasons})
    r = conn.execute(
        "SELECT COUNT(*), MAX(rowid) FROM player_game_logs WHERE sport=? "
        f"AND season IN ({','.join('?' * len(seasons))})",
        [sport, *seasons]).fetchone()
    return int(r[0] or 0), int(r[1] or 0)


def folder() -> str:
    from . import feedstate
    return os.path.join(feedstate.directory(), DIRNAME)


def _path(name: str, sport: str, seasons: list, db: str) -> str:
    tag = hashlib.sha1(f"{db}|{seasons}".encode()).hexdigest()[:10]
    return os.path.join(folder(), f"{name}-{sport}-{tag}.pkl")


def code_hash(path) -> str:
    """sha1 of a source file's bytes ("" when it cannot be read)."""
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
    if (stored.get("rows"), stored.get("top")) != (key["rows"], key["top"]):
        return "rows changed"
    return "key changed"


def _note(path: str, entry: dict) -> None:
    """What this call did, beside its stored result. Never raises."""
    tmp = f"{path}.{os.getpid()}.note"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as fh:
            json.dump(entry, fh)
        os.replace(tmp, path[:-len(".pkl")] + ".json")
    except Exception:                                        # noqa: BLE001
        try:
            os.unlink(tmp)
        except Exception:                                    # noqa: BLE001
            pass


def memo(conn, name: str, sport: str, seasons, compute, code=None, force: bool | None = None,
         clock=time.monotonic):
    """``compute()``, or the result stored for the same rows when they have
    not changed since. ``seasons`` are the seasons ``compute`` reads;
    ``code`` the source file that computes it (its caller's ``__file__``)."""
    if not (enabled_for(conn) if force is None else force):
        return compute()
    t0 = clock()
    try:
        seasons = sorted({int(s) for s in seasons})
        rows, top = scope_key(conn, sport, seasons)
        db = db_file(conn)
        key = {"v": VERSION, "name": name, "sport": sport, "seasons": seasons,
               "db": db, "rows": rows, "top": top, "code": code_hash(code) if code else ""}
        path = _path(name, sport, seasons, db)
    except Exception:                                        # noqa: BLE001
        return compute()
    note = {"name": name, "sport": sport, "seasons": seasons, "at": int(time.time()),
            "rows": rows, "key_s": round(clock() - t0, 2)}
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
    return value


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
    seconds. {} when nothing is noted; never raises."""
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
    except Exception:                                        # noqa: BLE001
        return {}
    return {k: {f: v for f, v in e.items() if f not in ("name", "sport")}
            for k, e in sorted(newest.items())}
