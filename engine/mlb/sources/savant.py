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
import os
import time
from datetime import date, datetime

from ...sources.fetch import fetch_text, CACHE_DIR, DataUnavailable
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
    """A percent column as a 0..1 fraction — ALWAYS divided by 100.

    These Savant columns are always percent units (brl_percent 0-30,
    ev95percent 15-65). The old "small values are already fractions"
    heuristic turned Luis Arraez's genuine 0.5 (= 0.5%, the lowest barrel
    rate in baseball) into 50%."""
    v = _f(row, *keys)
    return None if v is None else round(v / 100.0, 4)


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
    """Fetch (or read a cached) barrels board for a season.

    THROUGH `fetch_text`, ALWAYS (2026-10-14). This read the cached file
    whenever one existed, and `fetch_text` writes the file under the same
    name — so after the first download the board was never asked for
    again, and its `ttl` was dead: every hitter's barrel rate stayed what
    it was the day the file landed. `fetch_text` serves a copy younger than
    the ttl, asks again for an older one, and falls back to the old copy
    when Savant does not answer, which is what a supplied file needs too.
    An answer with no hitters in it never replaces a copy that has them
    (`_refresh_text`)."""
    url = SAVANT_BARRELS.format(type=kind, year=year)
    text = _refresh_text(url, f"savant_barrels_{kind}_{year}.csv", 6 * 3600,
                         lambda t: parse_barrels(_read_csv_text(t)))
    return parse_barrels(_read_csv_text(text))


def _read_csv_text(text: str) -> list[dict]:
    # Savant's BOM precedes the first cell's opening quote; unless stripped,
    # csv splits the quoted "last_name, first_name" header into two broken
    # columns and shifts EVERY data column left by one.
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))


def _held(path):
    """``(text, mtime)`` of a cached file, or None when there is none."""
    try:
        mtime = path.stat().st_mtime
        return path.read_text(encoding="utf-8", errors="replace"), mtime
    except OSError:
        return None


def _put_back(path, kept) -> None:
    """Write the last good copy back over a worse answer, beside then
    swapped in as `fetch_text` writes, WITH ITS OWN DOWNLOAD TIME: its age
    stays true, so the next read asks Savant again rather than trusting a
    copy the last request failed to replace."""
    text, mtime = kept
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        os.utime(path, (mtime, mtime))
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _refresh_text(url: str, name: str, ttl: int, players) -> str:
    """`fetch_text`, except that an answer in which ``players`` finds no
    one never replaces a cached copy in which it finds someone.

    THE REFRESH'S OWN RISK (2026-10-14). Reading through `fetch_text`
    always is what lets these boards refresh, and `fetch_text` writes
    whatever comes back over the cached file: an error page, an empty
    body, the header with no rows. Served for the whole ttl, any of them
    reads as a season with no hitters. So the copy held before the request
    is put back, with its own download time, and returned."""
    path = CACHE_DIR / name
    kept = _held(path)
    text = fetch_text(url, name, ttl=ttl)
    if kept is not None and text != kept[0] and not _finds(players, text) and _finds(players, kept[0]):
        _put_back(path, kept)
        return kept[0]
    return text


def _finds(players, text: str) -> bool:
    """Does ``players`` find anyone in ``text``? An answer the CSV reader
    cannot read at all (a line past its 128 KB field limit, as a minified
    error page can be) has no one in it."""
    try:
        return bool(players(text))
    except csv.Error:
        return False


def load_expected_stats(year: int, kind: str = "batter") -> dict[str, StatcastProfile]:
    """Fetch (or read a cached) expected-stats board for a season — through
    `fetch_text` always, and never replaced by an answer with no hitters,
    for the reasons `load_barrels` gives."""
    url = SAVANT_EXPECTED.format(type=kind, year=year)
    text = _refresh_text(url, f"savant_expected_{kind}_{year}.csv", 6 * 3600,
                         lambda t: parse_expected_stats(_read_csv_text(t)))
    return parse_expected_stats(_read_csv_text(text))


# --- the hit page's own copy: every hitter, by MLB's own id --------------------------
#
# Ethan, 2026-10-14 ("do the first 7 page items"): MLB's own expected
# average and slugging, and its barrel rate, beside ours on the hit page.
# The two boards above are the model's, and they keep only qualified
# hitters (`min=q`, `min=50`), keyed by name; a part-timer the page is
# opened for is in neither. So the page reads its own copy of each — every
# hitter with a ball in play, keyed by the player id both Savant and the
# Stats API use — fetched once a night by the chart chores
# (`fetch_page_boards`) and read from the file on a request (`page_board`),
# never from the wire. The model's boards are not changed by any of this.
SAVANT_EXPECTED_ALL = SAVANT_EXPECTED.replace("min=q", "min=1")
SAVANT_BARRELS_ALL = SAVANT_BARRELS.replace("min=50", "min=1")
#: A day, less a few hours: the nightly asks again every night.
PAGE_TTL = 20 * 3600


def page_names(year: int) -> tuple[str, str]:
    return (f"savant_expected_batter_{int(year)}_all.csv", f"savant_barrels_batter_{int(year)}_all.csv")


def fetch_page_boards(year: int) -> dict:
    """Fetch the hit page's two boards for a season (a copy under a day old
    is kept). ``{"expected": rows, "barrels": rows}``, or the error's words
    in a board's place."""
    out = {}
    for key, tmpl, name in zip(("expected", "barrels"), (SAVANT_EXPECTED_ALL, SAVANT_BARRELS_ALL),
                               page_names(year)):
        try:
            out[key] = len(_read_csv_text(_refresh_text(
                tmpl.format(type="batter", year=int(year)), name, PAGE_TTL,
                lambda t: any(_pid(r) is not None for r in _read_csv_text(t)))))
        except DataUnavailable as exc:
            out[key] = str(exc)[:160]
    return out


def _pid(row: dict):
    v = _f(row, "player_id")
    return int(v) if v is not None and v > 0 else None


def parse_page(expected: list[dict], barrels: list[dict]) -> dict:
    """``{player id: {xba, xslg, ba, slg, brl_pct, brl, bbe}}`` off the two
    boards' rows: Savant's own numbers, as it prints them (a barrel rate in
    percent becomes a share)."""
    out: dict = {}
    for r in expected or []:
        pid = _pid(r)
        if pid is None:
            continue
        out.setdefault(pid, {}).update({k: v for k, v in (("xba", _f(r, "est_ba")), ("xslg", _f(r, "est_slg")),
                                                          ("ba", _f(r, "ba")), ("slg", _f(r, "slg")))
                                        if v is not None})
    for r in barrels or []:
        pid = _pid(r)
        if pid is None:
            continue
        brl = _f(r, "barrels")
        bbe = _f(r, "attempts")
        got = {"brl_pct": _pct(r, "brl_percent"), "brl": int(brl) if brl is not None else None,
               "bbe": int(bbe) if bbe is not None else None}
        out.setdefault(pid, {}).update({k: v for k, v in got.items() if v is not None})
    return {k: v for k, v in out.items() if v}


#: ``{year: ((the two files' mtimes), board)}`` — read again only when a file changes.
_PAGE: dict = {}


def page_board(year: int) -> dict:
    """The hit page's Savant numbers for a season off the files the nightly
    fetched, each player's with ``at`` (the day the newer file was
    fetched); ``{}`` with neither file. Never the network."""
    import datetime as _dt
    paths = [CACHE_DIR / n for n in page_names(year)]
    try:
        stamps = tuple(p.stat().st_mtime if p.exists() else None for p in paths)
    except OSError:
        return {}
    if not any(stamps):
        return {}
    hit = _PAGE.get(int(year))
    if hit and hit[0] == stamps:
        return hit[1]
    rows = []
    for p in paths:
        try:
            rows.append(_read_csv_text(p.read_text(encoding="utf-8", errors="replace")) if p.exists() else [])
        except OSError:
            rows.append([])
    at = _dt.date.fromtimestamp(max(t for t in stamps if t)).isoformat()
    board = {pid: dict(v, at=at) for pid, v in parse_page(rows[0], rows[1]).items()}
    _PAGE[int(year)] = (stamps, board)
    return board


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


# --- §6's hitter half: performance BY PITCH TYPE -----------------------------
#
# MLB_MODEL §6 parked the arsenal matchup behind "needs pitch-mix +
# per-pitch-type hitter data". The pitch-mix half turned out to be free —
# `engine/mlb/arsenal.py` reads it from playByPlay payloads the board
# already caches. This is the other half, and it is one CSV a season.
#
# Header confirmed live 2026-08-10:
#
#   "last_name, first_name","player_id","team_name_alt","pitch_type",
#   "pitch_name","run_value_per_100","run_value","pitches","pitch_usage",
#   "pa","ba","slg","woba","whiff_percent","k_percent","put_away",
#   "est_ba","est_slg","est_woba","hard_hit_percent"
#
# One ROW PER PLAYER PER PITCH TYPE, which is the shape that matters: every
# other Savant board here is one row per player, so the parser below keys
# by (player, pitch_type) rather than overwriting.
SAVANT_ARSENAL = ("https://baseballsavant.mlb.com/leaderboard/"
                  "pitch-arsenal-stats?type={type}&pitchType=ALL&year={year}"
                  "&csv=true")
# THE SAME BOARD AS THE PAGE'S OWN EXPORT BUTTON WRITES IT: every pitch
# type left blank rather than "ALL", and a 10-PA floor. The box, 2026-09-26:
# "arsenal board: 0 hitter(s)", and the probe showed the cached file was
# the right header with NO ROWS — the "ALL" form answers with an empty
# table (the August check read only `head -1`, the header, so it never
# showed rows). Each form is tried in turn until one has hitters.
SAVANT_ARSENAL_ALT = ("https://baseballsavant.mlb.com/leaderboard/"
                      "pitch-arsenal-stats?type={type}&pitchType=&year={year}"
                      "&team=&min=10&csv=true")
SAVANT_ARSENAL_Q = ("https://baseballsavant.mlb.com/leaderboard/"
                    "pitch-arsenal-stats?type={type}&pitchType=&year={year}"
                    "&team=&min=q&csv=true")
#: (cache suffix, URL), in the order tried.
ARSENAL_FORMS = (("_alt", SAVANT_ARSENAL_ALT), ("_q", SAVANT_ARSENAL_Q), ("", SAVANT_ARSENAL))


def parse_arsenal(rows) -> dict[str, dict]:
    """`{normalized name: {pitch_type: {...}}}` from the arsenal board.

    Keyed by pitch type UNDER the player, because this board is the only
    one here with several rows per person — parsing it like the others
    would keep whichever pitch type happened to come last.
    """
    out: dict[str, dict] = {}
    for r in rows:
        raw = _row_name(r)
        name = _norm(raw) if raw else ""
        code = str(r.get("pitch_type") or "").strip().upper()
        if not name or not code:
            continue
        out.setdefault(name, {})[code] = {
            "pitch_name": str(r.get("pitch_name") or "").strip(),
            "pitches": _f(r, "pitches"),
            "usage": _pct(r, "pitch_usage"),
            "pa": _f(r, "pa"),
            "whiff_pct": _pct(r, "whiff_percent"),
            "k_pct": _pct(r, "k_percent"),
            "woba": _f(r, "woba"),
            "est_woba": _f(r, "est_woba"),
            "slg": _f(r, "slg"),
            "hard_hit_pct": _pct(r, "hard_hit_percent"),
        }
    return out


def _looks_like_arsenal(text: str) -> bool:
    """Is this the CSV we asked for, or something else wearing its name?

    `fetch_text` writes whatever the server returns and serves it back for
    the whole TTL — an empty body, a maintenance page, an HTML redirect.
    One bad response therefore poisons six hours, and the only symptom is
    a board with nothing in it. Checking the header is what separates "the
    season has no data" from "we cached an error page".
    """
    head = (text or "")[:400].lower()
    return "pitch_type" in head and "whiff_percent" in head


def load_arsenal(year: int, kind: str = "batter",
                 fallback: bool = True) -> dict[str, dict]:
    """Fetch (or read a cached) pitch-arsenal board for a season.

    `kind` is "batter" for how hitters fare against each pitch type, or
    "pitcher" for how each pitcher's own offerings perform. The batter
    board is the one §6 was missing.

    FALLS BACK ONE SEASON when the requested one is empty OR WILL NOT
    DOWNLOAD, and says so by returning the year it actually used. A
    hitter's profile from last season is real information; an empty dict
    is not. The fallback used to run only on an empty board, so a season
    whose fetch failed raised straight past last season's good one. The
    caller is told which year it got so it can label the reading rather
    than pass it off as current. Raises only when neither season has it.
    """
    failed = ""
    try:
        board = _arsenal_board(year, kind)
    except DataUnavailable as exc:
        if not (fallback and year > 2015):
            raise
        board, failed = {}, f"{year}: {exc}"
    if board:
        board["_season"] = year          # what the caller actually got
        return board
    if fallback and year > 2015:
        try:
            prior = load_arsenal(year - 1, kind, fallback=False)
        except DataUnavailable as exc:
            if not failed:
                raise
            raise DataUnavailable(f"{failed} | {year - 1}: {exc}") from exc
        if prior:
            return prior
    if failed:
        raise DataUnavailable(f"{failed} | {year - 1}: came back empty")
    return {}


#: How old a season's arsenal file may be before Savant is asked again:
#: the six hours the barrels and expected-stats boards use.
ARSENAL_TTL = 6 * 3600
#: A finished season's board no longer changes; it is asked again weekly.
PAST_SEASON_TTL = 7 * 24 * 3600


def _arsenal_ttl(year: int) -> int:
    return ARSENAL_TTL if int(year) >= date.today().year else PAST_SEASON_TTL


def _parsed_arsenal(text: str) -> dict:
    """`parse_arsenal` of a text, or {} when the CSV reader cannot read it."""
    try:
        return parse_arsenal(_read_csv_text(text))
    except csv.Error:
        return {}


def _good_copy(path):
    """``(text, mtime)`` of the cached file when it is the arsenal CSV,
    else None. A cached file that is not the CSV is deleted: a poisoned
    cache is worse than none, because it is served for the whole TTL and
    looks exactly like an empty season."""
    kept = _held(path)
    if kept is None or _looks_like_arsenal(kept[0]):
        return kept
    path.unlink(missing_ok=True)
    return None


def _arsenal_board(year: int, kind: str) -> dict:
    """The first URL form whose CSV has hitters in it, parsed; {} when
    every form answered with the header alone. Raises DataUnavailable only
    when no form came back as the CSV at all.

    THROUGH `fetch_text`, ALWAYS (2026-10-14), as `load_barrels` reads.
    This read the cached file whenever one existed, so after the first
    download Savant was never asked again: every hitter's line against
    each pitch type stayed what it was the day the file landed. A file
    younger than the TTL is still served without a request; an older one
    is asked for again, and served as it is when Savant does not answer.

    A REFRESH NEVER COSTS THE LAST GOOD COPY. `fetch_text` writes whatever
    comes back over the cached file, and two answers here are worse than
    the copy they replace: a page that is not the CSV (an error page, a
    maintenance notice), and the header with no rows (what the "ALL" form
    answers). Either would have dropped every hitter until a good answer
    came, or sent the board back a season. So the copy held before the
    request is put back whenever the answer has no hitters and the old
    copy has some, or the answer is not the CSV at all.
    """
    tried, got_csv = [], False
    ttl = _arsenal_ttl(year)
    for suffix, tmpl in ARSENAL_FORMS:
        name = f"savant_arsenal_{kind}_{year}{suffix}.csv"
        local = CACHE_DIR / name
        kept = _good_copy(local)
        url = tmpl.format(type=kind, year=year)
        try:
            text = fetch_text(url, name, ttl=ttl)
        except DataUnavailable as exc:
            tried.append(str(exc)[:160])
            continue
        fresh = _looks_like_arsenal(text)
        board = _parsed_arsenal(text) if fresh else {}
        if kept is not None and text != kept[0] and not board:
            old = _parsed_arsenal(kept[0])
            if old or not fresh:
                _put_back(local, kept)
                text, fresh, board = kept[0], True, old
        if not fresh:
            local.unlink(missing_ok=True)
            tried.append(f"{url} did not return the arsenal CSV — got {len(text or '')} bytes "
                         f"starting {(text or '')[:60]!r}")
            continue
        got_csv = True
        if board:
            return board
        tried.append(f"{url} came back with the header and no rows")
    if got_csv:
        return {}
    raise DataUnavailable("; ".join(tried) + ". The cache has been cleared, so a retry "
                          "will re-fetch rather than re-read this.")


def cache_report(year: int, now: float | None = None) -> list[str]:
    """One line per cached Savant file for a season: its rows, when it was
    downloaded and how long ago, and its header. What the probe prints, so
    a refresh can be seen happening on the box."""
    now = time.time() if now is None else now
    out = []
    for f in sorted(CACHE_DIR.glob(f"savant_*_{year}*.csv")):
        try:
            got = f.stat().st_mtime
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            out.append(f"{f.name}: unreadable — {exc}")
            continue
        at = datetime.fromtimestamp(got).astimezone()
        out.append(f"{f.name}: {max(len(lines) - 1, 0)} row(s), fetched "
                   f"{at:%Y-%m-%d %H:%M %Z} ({max(now - got, 0) / 3600:.1f} h ago); "
                   f"header {lines[0][:100] if lines else '(empty)'}")
    return out


if __name__ == "__main__":
    # Ground-truth diagnostic:  python3 -m engine.mlb.sources.savant 2026
    import sys
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    for board, loader in (("expected_statistics", load_expected_stats),
                          ("exit_velocity_barrels", load_barrels),
                          ("pitch_arsenal_batter", lambda y: load_arsenal(y, "batter"))):
        try:
            data = loader(year)
            print(f"{board}: parsed {len(data)} player profile(s)")
            for name in list(data)[:3]:
                print(f"   e.g. {name!r} -> {data[name]}")
        except DataUnavailable as exc:
            print(f"{board}: FETCH FAILED — {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"{board}: PARSE FAILED — {type(exc).__name__}: {exc}")
    for line in cache_report(year):
        print(line)
