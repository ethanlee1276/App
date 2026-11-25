"""The leagues' published roster files, each parsed once per content (step AGM, 25 November 2026).

Ethan: "Also data on the player page takes a long time to load" ... "Ok keep going and work more on these issues as
they are not fixed". The roster build rewrites every league's file every half hour (launch.ROSTER_REBUILD_S), each
time with a new `generated_at` and, nearly always, the same rosters; and every reader keyed its parse on the file's
time. So every half hour the first college player's page read the 9.2 MB college file again (Jeremiah Smith's page:
the roster 1.3 s of its 1.4 on the live site), the search read it again behind itself and rebuilt its 41,888-name
list, and a team's roster tab, a player's link and Ask read it on every ask. In the one process that answers every
page, each of those is a wait for every other reader too.

Here a file whose time or size moved is read as bytes and compared, `generated_at` aside, with the one parsed: the
same rosters keep the parse they had (the same object, so whatever a reader built from it, keyed on it, stands), with
the new `generated_at` written onto it. Only rosters that changed are parsed again. One parse at a time per file.

`doc(path)` is the parsed file, or None for none on disk (or one that will not read, with nothing parsed before).
Readers treat it as read-only: it is shared.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading

#: The build's own stamp, the one part of a rewrite that says nothing about the rosters.
_STAMP = re.compile(rb'"generated_at":\s*"([^"]*)"')
_DOCS: dict = {}
_LOCKS: dict = {}
_LOCK = threading.Lock()


def _digest(raw: bytes) -> bytes:
    return hashlib.sha1(_STAMP.sub(b"", raw)).digest()


def doc(path) -> dict | None:
    """The roster file at `path`, parsed; None when there is none (see the module's docstring)."""
    path = str(path)
    try:
        st = os.stat(path)
    except OSError:
        return None
    seen = (st.st_mtime_ns, st.st_size)
    hit = _DOCS.get(path)
    if hit and hit[0] == seen:
        return hit[2]
    with _LOCK:
        lock = _LOCKS.setdefault(path, threading.Lock())
    with lock:
        hit = _DOCS.get(path)
        if hit and hit[0] == seen:
            return hit[2]                                 # read while this one waited
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            return hit[2] if hit else None
        digest = _digest(raw)
        if hit and hit[1] == digest:
            stamp = _STAMP.search(raw)
            if stamp and isinstance(hit[2], dict) and "generated_at" in hit[2]:
                hit[2]["generated_at"] = stamp.group(1).decode("utf-8", "replace")
            _DOCS[path] = (seen, digest, hit[2])
            return hit[2]
        try:
            parsed = json.loads(raw)
        except ValueError:
            return hit[2] if hit else None                # a file that will not read keeps the one in hand
        if not isinstance(parsed, dict):
            parsed = {}
        _DOCS[path] = (seen, digest, parsed)
        return parsed


def forget() -> None:
    """Every parse dropped (a test's fresh files)."""
    with _LOCK:
        _DOCS.clear()
