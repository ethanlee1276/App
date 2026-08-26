"""The persisted CFB team map — the one thing between college football
and closing-line value.

THE GAP THIS CLOSES (docs/IDEAS.md, 2026-08-25). The nightly closing-odds
harvest is journal-driven: any night MLB or NFL bets journal, their
closes are harvested and CLV accrues. CFB was the deliberate exception,
and the blocker was never the API — it was a NAME. The odds-history
parsers key every price through ``SPORT_CONFIG[sport]["teams"]``, which
maps the book's spelling of a team ("Ohio State Buckeyes") to the
canonical abbreviation the journal stores. CFB's map is built at RUN
TIME inside cfb_build from the ESPN feed, because 134 schools across
conferences that reshuffle every other year is exactly the table that
rots the moment it is hardcoded. In memory during a build, gone
afterwards — so a harvest stored school names no settle pass could join
to a bet.

WHY A FILE AND NOT A CONSTANT. The map is still never hand-written. It
is HARVESTED FROM OUR OWN BUILDS: every cfb_build resolves the book's
names against the live ESPN feed to price its board, and this module
writes those resolutions down as it goes. The table therefore describes
the schools the books actually quoted us, accumulates across the season
as more teams appear, and self-corrects when a school is renamed —
because the next build that prices that game overwrites the entry.

ACCUMULATE, NEVER REPLACE. One Tuesday slate is a dozen games; the
season is 134 schools. A build writes what it learned ON TOP of what is
already stored, so the map grows monotonically instead of shrinking to
whatever was playing that night — which would make a harvest's coverage
depend on the day it happened to run.
"""

from __future__ import annotations

import json
import os

#: Beside the other feed state. Relative, like every feedstate path —
#: builds run from the repo root.
STATE_PATH = os.path.join("data", "feedstate", "cfb_teams.json")

#: A book's team string longer than this is not a team string.
MAX_NAME = 80


def load(path: str | None = None) -> dict:
    """``{book's spelling: canonical abbreviation}``, or ``{}``.

    Never raises. A missing or corrupt file means the harvest keys teams
    exactly as it did before this module existed — degraded, not broken,
    which is the only acceptable failure for a file that sits in the
    path of a nightly job.
    """
    try:
        with open(path or STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.get("teams", {}).items()
            if k and v and len(str(k)) <= MAX_NAME}


def remember(pairs: dict, path: str | None = None) -> int:
    """Merge ``{book spelling: canonical}`` into the stored map.

    Returns the number of NEW names learned (0 when the build only saw
    schools already known, which is the common case late in a season).
    Never raises into a build: telemetry that can break a betting board
    is worse than telemetry that misses a night.
    """
    path = path or STATE_PATH
    clean = {str(k).strip(): str(v).strip() for k, v in (pairs or {}).items()
             if k and v and len(str(k).strip()) <= MAX_NAME}
    if not clean:
        return 0
    try:
        current = load(path)
        fresh = {k: v for k, v in clean.items() if current.get(k) != v}
        if not fresh:
            return 0
        current.update(clean)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"teams": dict(sorted(current.items()))}, fh, indent=2)
        os.replace(tmp, path)      # atomic: a torn map is worse than none
        return len(fresh)
    except OSError:
        return 0
