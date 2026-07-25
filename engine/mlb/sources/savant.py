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
# The Exit Velocity & Barrels board lives at the /statcast slug (the
# /exit_velocity_barrels guess 404s — confirmed live).
SAVANT_BARRELS = (
    "https://baseballsavant.mlb.com/leaderboard/statcast"
    "?type={type}&year={year}&position=&team=&min=50&csv=true"
)


def _norm(name: str) -> str:
    # One normalizer everywhere (accents folded): Savant prints "Acuña" while
    # other feeds don't, and a private variant here would silently drop them.
    from ...sources.oddsapi import normalize_name
    return normalize_name(name)


def _row_name(row: dict) -> str:
    """Player name from a Savant CSV row, whatever shape the header took.

    Real exports use a SINGLE quoted column literally headed
    ``last_name, first_name`` (usually with a BOM in front) containing
    "Judge, Aaron"; older/other boards use separate columns or
    ``player_name``. Returns "First Last" or ""."""
    first = last = joined = ""
    for k, v in row.items():
        if k is None or v in (None, ""):
            continue
        key = str(k).replace("\ufeff", "").strip().strip('"').lower()
        val = str(v).strip()
        if key in ("last_name, first_name", "last_name,first_name"):
            joined = joined or val
        elif key == "first_name":
            first = val
        elif key == "last_name":
            last = val
        elif key in ("player_name", "name"):
            joined = joined or val
    if not first and last and "," in last:      # joined value under last_name
        joined, last = last, ""
    if joined:
        if "," in joined:
            l, f = [s.strip() for s in joined.split(",", 1)]
            return f"{f} {l}"
        return joined
    return f"{first} {last}".strip()


def _f(row: dict, *keys):
    cleaned = {str(k).replace("\ufeff", "").strip().lower(): v
               for k, v in row.items() if k is not None}
    for k in keys:
        v = cleaned.get(k)
        if v not in (None, "", "NA", "--", "null"):
            try:
                return float(str(v).strip())
            except ValueError:
                pass
    return None


def parse_expected_stats(rows: list[dict]) -> dict[str, StatcastProfile]:
    """Map an expected-statistics CSV to {normalized name: StatcastProfile}.

    Savant rows carry ``last_name, first_name`` separately plus ``slg`` /
    ``est_slg`` and ``woba`` / ``est_woba``."""
    out: dict[str, StatcastProfile] = {}
    for r in rows:
        raw = _row_name(r)
        name = _norm(raw) if raw else ""
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
        raw = _row_name(r)
        name = _norm(raw) if raw else ""
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
    # Savant's BOM precedes the first cell's opening quote; unless stripped,
    # csv splits the quoted "last_name, first_name" header into two broken
    # columns and shifts EVERY data column left by one.
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))


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


if __name__ == "__main__":
    # Ground-truth diagnostic:  python3 -m engine.mlb.sources.savant 2026
    import sys
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    for board, loader in (("expected_statistics", load_expected_stats),
                          ("exit_velocity_barrels", load_barrels)):
        try:
            data = loader(year)
            print(f"{board}: parsed {len(data)} player profile(s)")
            for name in list(data)[:3]:
                print(f"   e.g. {name!r} -> {data[name]}")
        except DataUnavailable as exc:
            print(f"{board}: FETCH FAILED — {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"{board}: PARSE FAILED — {type(exc).__name__}: {exc}")
    for f in sorted(CACHE_DIR.glob(f"savant_*_{year}.csv")):
        head = f.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        print(f"header of {f.name}: {head[0][:160] if head else '(empty)'}")
