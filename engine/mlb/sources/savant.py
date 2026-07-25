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
SAVANT_BARRELS = (
    "https://baseballsavant.mlb.com/leaderboard/exit_velocity_barrels"
    "?type={type}&year={year}&position=&team=&min=50&csv=true"
)


def _norm(name: str) -> str:
    # One normalizer everywhere (accents folded): Savant prints "Acuña" while
    # other feeds don't, and a private variant here would silently drop them.
    from ...sources.oddsapi import normalize_name
    return normalize_name(name)


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


def _pct(row: dict, *keys):
    """A percent column (7.5 means 7.5%) as a 0..1 fraction."""
    v = _f(row, *keys)
    return None if v is None else (v / 100.0 if v > 1.5 else v)


def parse_barrels(rows: list[dict]) -> dict[str, dict]:
    """Map an exit-velocity/barrels CSV to {normalized name: fields}.

    ``brl_percent`` is barrels per batted-ball event (league ~7.5%, elite
    12%+) — the scale the HR model's thresholds are tuned to. Hard-hit % is
    ``ev95percent`` (share of batted balls at 95+ mph)."""
    out: dict[str, dict] = {}
    for r in rows:
        first = (r.get("first_name") or "").strip()
        last = (r.get("last_name") or "").strip()
        if not first and last and "," in last:
            last, first = [s.strip() for s in last.split(",", 1)]
        if not (first or last):
            joined = (r.get("last_name, first_name") or "").strip()
            if "," in joined:
                last, first = [s.strip() for s in joined.split(",", 1)]
        name = _norm(f"{first} {last}") if (first or last) else ""
        if not name:
            continue
        out[name] = {
            "barrel_pct": _pct(r, "brl_percent", "barrel_batted_rate"),
            "hard_hit_pct": _pct(r, "ev95percent", "hard_hit_percent"),
        }
    return out


def load_barrels(year: int, kind: str = "batter") -> dict[str, dict]:
    """Fetch (or read a cached) barrels board for a season."""
    local = CACHE_DIR / f"savant_barrels_{kind}_{year}.csv"
    if local.exists():
        return parse_barrels(load_local_csv(local))
    url = SAVANT_BARRELS.format(type=kind, year=year)
    text = fetch_text(url, f"savant_barrels_{kind}_{year}.csv", ttl=6 * 3600)
    return parse_barrels(_read_csv_text(text))


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
    """Attach Savant profiles (expected stats + barrels) to hitter props by
    name. Returns the number matched. Pitcher boards (CSW%) are a later
    slice."""
    try:
        board = load_expected_stats(year, "batter")
    except DataUnavailable:
        board = {}
    try:
        barrels = load_barrels(year, "batter")
    except DataUnavailable:
        barrels = {}
    if not board and not barrels:
        return 0
    for name, b in barrels.items():
        prof = board.setdefault(name, StatcastProfile())
        prof.barrel_pct = b.get("barrel_pct")
        prof.hard_hit_pct = b.get("hard_hit_pct")
    n = 0
    for prop in props:
        if prop.position == "SP":
            continue
        prof = board.get(_norm(prop.player))
        if prof and (prof.xslg is not None or prof.xwoba is not None
                     or prof.barrel_pct is not None):
            prop.statcast = prof
            n += 1
    return n
