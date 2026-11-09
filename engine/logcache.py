"""Results read off the game logs, kept until the rows they read change.

The heartbeat at 00:56 on 9 November had the NHL build reading every
player's games of two seasons (about a million rows of player_game_logs)
in 17 of its 25 board seconds, on every build, ten minutes apart, while
those rows change about once a day: when the night's box scores are
ingested. The fantasy file's season means read the same seasons again in
the board's write stage, for every sport.

KEPT AGAINST A KEY THE ROWS THEMSELVES GIVE. A result is stored with the
count and the highest rowid of exactly the rows it read (one sport's
seasons), and served while both still match. Every write to the table is
an INSERT OR REPLACE (`engine.db._upsert`), which files the row under a
rowid above every other, so a new row or a corrected one raises the
highest rowid; the two delete paths (a provisional box score purged, a
player's rows repaired) lower the count. The key is read before the result
is computed, so a write landing in between is caught on the next call
rather than stored as current. It is counted off the primary key's own
index, which holds no values, so it costs about a tenth of the read it
saves (0.08 against 1.9 seconds on a million-row fixture).

AND AGAINST THE CODE THAT COMPUTED IT. The key carries a hash of the
source file that computes the result (``code``), so a deploy that changes
how it is built reads the table afresh instead of serving the old shape
until the next box score lands.

ONLY THE PRODUCTION HISTORY FILE (`engine.db.DEFAULT_DB`). The tests and
the Lab open files of their own and read them fresh, as they always did;
`force=True` lets a test exercise the cache on a file of its own.

Standard library only. Never raises: a cache it cannot read or write is a
read from the table, as before.
"""
from __future__ import annotations

import hashlib
import os
import pickle

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


def _path(name: str, sport: str, seasons: list, db: str) -> str:
    from . import feedstate
    tag = hashlib.sha1(f"{db}|{seasons}".encode()).hexdigest()[:10]
    return os.path.join(feedstate.directory(), DIRNAME, f"{name}-{sport}-{tag}.pkl")


def code_hash(path) -> str:
    """sha1 of a source file's bytes ("" when it cannot be read)."""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except Exception:                                        # noqa: BLE001
        return ""


def memo(conn, name: str, sport: str, seasons, compute, code=None, force: bool | None = None):
    """``compute()``, or the result stored for the same rows when they have
    not changed since. ``seasons`` are the seasons ``compute`` reads;
    ``code`` the source file that computes it (its caller's ``__file__``)."""
    if not (enabled_for(conn) if force is None else force):
        return compute()
    try:
        seasons = sorted({int(s) for s in seasons})
        rows, top = scope_key(conn, sport, seasons)
        db = db_file(conn)
        key = {"v": VERSION, "name": name, "sport": sport, "seasons": seasons,
               "db": db, "rows": rows, "top": top, "code": code_hash(code) if code else ""}
        path = _path(name, sport, seasons, db)
    except Exception:                                        # noqa: BLE001
        return compute()
    try:
        with open(path, "rb") as fh:
            stored = pickle.load(fh)
        if isinstance(stored, dict) and stored.get("key") == key:
            return stored["value"]
    except Exception:                                        # noqa: BLE001
        pass
    value = compute()
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as fh:
            pickle.dump({"key": key, "value": value}, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except Exception:                                        # noqa: BLE001
        try:
            os.unlink(tmp)
        except Exception:                                    # noqa: BLE001
            pass
    return value
