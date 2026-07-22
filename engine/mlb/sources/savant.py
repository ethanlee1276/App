"""Baseball Savant (Statcast) adapter.

Builds :class:`StatcastProfile` objects from Savant's public leaderboard CSVs —
principally the **expected statistics** board, which carries the xSLG/xwOBA vs
SLG/wOBA gaps that drive the regression signal:

    https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=batter&year=YYYY&csv=true

The CSV **parser** is pure and unit-tested; the fetch wrapper caches under
``data/cache/`` and raises :class:`DataUnavailable` when Savant is unreachable
(it is blocked in some sandboxed environments). Barrel/hard-hit and pitcher
CSW% come from other Savant boards and are the next slice; this module covers
the expected-stats layer end to end.
"""

from __future__ import annotations

import csv
import io

from ...sources.fetch import fetch_text, load_local_csv, CACHE_DIR, DataUnavailable
from ..models import StatcastProfile

SAVANT_EXPECTED = (
    "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
    "?type={type}&year={year}&position=&team=&filterType=bip&min=q&csv=true"
)


def _norm(name: str) -> str:
    import re
    s = name.lower().replace(".", " ").replace("'", "")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _f(row: dict, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "NA"):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def parse_expected_stats(rows: list[dict]) -> dict[str, StatcastProfile]:
    """Map an expected-statistics CSV to {normalized name: StatcastProfile}.

    Savant rows carry ``last_name, first_name`` separately plus ``slg`` /
    ``est_slg`` and ``woba`` / ``est_woba``."""
    out: dict[str, StatcastProfile] = {}
    for r in rows:
        first = (r.get("first_name") or r.get("﻿first_name") or "").strip()
        last = (r.get("last_name") or r.get("﻿last_name") or "").strip()
        # Some exports use "last_name, first_name" in a single column.
        if not first and last and "," in last:
            last, first = [s.strip() for s in last.split(",", 1)]
        name = _norm(f"{first} {last}") if (first or last) else ""
        if not name:
            continue
        out[name] = StatcastProfile(
            xslg=_f(r, "est_slg", "xslg"),
            slg=_f(r, "slg"),
            xwoba=_f(r, "est_woba", "xwoba"),
            woba=_f(r, "woba"),
        )
    return out


def _read_csv_text(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def load_expected_stats(year: int, kind: str = "batter") -> dict[str, StatcastProfile]:
    """Fetch (or read a cached) expected-stats board for a season."""
    local = CACHE_DIR / f"savant_expected_{kind}_{year}.csv"
    if local.exists():
        return parse_expected_stats(load_local_csv(local))
    url = SAVANT_EXPECTED.format(type=kind, year=year)
    text = fetch_text(url, f"savant_expected_{kind}_{year}.csv", ttl=6 * 3600)
    return parse_expected_stats(_read_csv_text(text))


def attach_statcast(props, year: int) -> int:
    """Attach expected-stats profiles to hitter props by name. Returns the
    number matched. Pitcher boards (CSW%) are a later slice."""
    try:
        board = load_expected_stats(year, "batter")
    except DataUnavailable:
        return 0
    n = 0
    for prop in props:
        prof = board.get(_norm(prop.player))
        if prof and (prof.xslg is not None or prof.xwoba is not None):
            prop.statcast = prof
            n += 1
    return n
