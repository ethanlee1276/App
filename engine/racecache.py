"""A race is played out again only when what it is built from has moved.

The NFL playoff race (engine/nflrace, 10,000 seasons), the college one
(engine/cfprace, 6,000) and the NBA Cup (engine/nbacup, 10,000) each play
the rest of a season out thousands of times, and each ran on every board
build — every cycle of the loop, about every quarter hour — though between
two builds nothing it reads has usually changed: no game has finished, no
rating has moved, the day is the same. The NFL build ran 577 of its
600-second limit on the morning of Sunday 8 November, and the race's
10,000 seasons (3.6 seconds on a fast machine) sat inside it.

Each race now writes a fingerprint of everything it was built from beside
its numbers (``inputs``): the games played and their scores, the games left,
the ratings, the day, the number of runs and the race's own code. The next
build asks first (`kept`); the same fingerprint keeps the last race, with
its own "Built" time. Each race seeds its random runs afresh, so two
builds off the same inputs differed only by the noise of the draw; the kept
race is one of those draws, and holds still until something it reads moves.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: Bumped by hand only if a race's output must change without its inputs or
#: its module's source changing.
VERSION = 1


def source_of(module_file) -> str:
    """A fingerprint of a race module's own code, so a race built by older
    code is never kept past a deploy that changed it."""
    try:
        return hashlib.sha1(Path(module_file).read_bytes()).hexdigest()
    except OSError:
        return ""


def key(*parts) -> str:
    """One fingerprint of everything a race is built from (JSON-ordered, so
    the same inputs always give the same key)."""
    blob = json.dumps([VERSION, *parts], sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def kept(path, inputs: str) -> dict | None:
    """The race last written at ``path`` (its full copy, `gate.board_source`)
    when it was built from exactly ``inputs``; None when it was not, or when
    there is none or it will not read — then the race is built."""
    try:
        from . import gate
        got = json.loads(Path(gate.board_source(Path(path))).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(got, dict) and inputs and got.get("inputs") == inputs and got.get("generated_at"):
        return got
    return None
