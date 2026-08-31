"""Cached HTTP fetching for CSV data sources.

Downloads are cached under ``data/cache/`` so repeated engine runs don't re-hit
the network. Uses only the standard library (``urllib``), which honours the
environment's ``HTTPS_PROXY`` and system CA bundle automatically. Transparently
decompresses ``.gz`` payloads.
"""

from __future__ import annotations

import csv
import gzip
import io
import time
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
USER_AGENT = "qellys-book/0.1 (+nflverse loader)"

#: Some hosts reject an unfamiliar User-Agent outright. Passing this as
#: ``user_agent`` sends NO header, so urllib supplies its own default —
#: which is what every ESPN endpoint here accepts.
#:
#: Measured 2026-08-08 from Ethan's machine, same URL, same second:
#:     User-Agent: qellys-book/0.1   ->  HTTP 403 Forbidden
#:     urllib's default              ->  200, 1 game
#:
#: This is not a disguise. It identifies the client honestly as a Python
#: script; the custom string was simply unfamiliar enough to trip a rule.
DEFAULT_AGENT = object()
DEFAULT_TTL = 12 * 3600  # re-download at most twice a day


class DataUnavailable(RuntimeError):
    """Raised when a required feed cannot be fetched and has no local cache.

    Carries ``status`` — the HTTP status when the failure was an HTTP error,
    and None when it was a timeout, a DNS failure, a refused CONNECT or
    anything else that never got a response.

    WHY A CALLER NEEDS THIS. "The server said no such file" and "I could not
    reach the server" need opposite responses, and a message that guesses
    between them sends the reader the wrong way. `load_weekly_stats` told
    Ethan that GitHub release access was "blocked by this environment's
    egress policy" and to export the file locally — on a machine with a
    working connection, whose own last-error line in the same message read
    `HTTP Error 404: Not Found`. The file was not blocked, it does not exist:
    nflverse publishes a season's player stats once games have been played,
    and the 2026 season had not started. The suggested export reads the same
    release and would have failed identically.
    """

    def __init__(self, *args, status: int | None = None):
        super().__init__(*args)
        self.status = status


def _status_of(exc: BaseException) -> int | None:
    """The HTTP status behind a fetch failure, if there was a response."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) else None


def release_unavailable(what: str, season: int, local: Path | str,
                        exporter: str, urls, last_err) -> DataUnavailable:
    """The right error for a missing nflverse release, chosen by what the
    server actually said.

    Three loaders — weekly stats, depth charts, injuries — each carried the
    same hardcoded sentence: "unavailable here (GitHub release access is
    blocked by this environment's egress policy), export it with
    nfl_data_py". That is one of the two possible causes stated as though it
    were known, and when it is the wrong one the advice is worse than
    nothing: the export reads the very same release, so it fails the same
    way. It reached Ethan's Mac, on a working connection, directly above its
    own `HTTP Error 404: Not Found`.

    404 means the file is not there. For a season whose games have not been
    played that is the expected answer and nothing to act on. Anything else
    — a refused CONNECT, a timeout, a 403 from a proxy — means we never got
    an answer, and exporting elsewhere is exactly the right move.
    """
    status = getattr(last_err, "status", None)
    tried = ", ".join(urls)
    if status == 404:
        return DataUnavailable(
            f"nflverse has not published {what} for {season} (HTTP 404). "
            f"These appear once games have been played, so before a season's "
            f"Week 1 this is the expected answer rather than something to "
            f"fix. If {season} is already under way, check whether nflverse "
            f"renamed the release.\n(tried: {tried})",
            status=404)
    return DataUnavailable(
        f"{what.capitalize()} for {season} could not be fetched — the request "
        f"never got an answer, so this is a reachability problem and not a "
        f"missing file. If that is this container's egress policy, export "
        f"them once where GitHub is reachable and save to {local}:\n"
        f"    import nfl_data_py as nfl\n"
        f"    {exporter}\n"
        f"(last error: {last_err})",
        status=status)


def _cache_path(name: str) -> Path:
    return CACHE_DIR / name


def fetch_text(url: str, cache_name: str, ttl: int = DEFAULT_TTL,
               timeout: int = 45, user_agent=USER_AGENT) -> str:
    """Return the text body of ``url``, caching it under ``cache_name``.

    If a fresh cache exists it is used. On a network failure a stale cache is
    used if present; otherwise :class:`DataUnavailable` is raised.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_name)

    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_text(encoding="utf-8", errors="replace")

    try:
        headers = ({} if user_agent is DEFAULT_AGENT
                   else {"User-Agent": user_agent})
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        if url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8", errors="replace")
        path.write_text(text, encoding="utf-8")
        return text
    except Exception as exc:  # network blocked / offline
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        raise DataUnavailable(f"Could not fetch {url}: {exc}",
                              status=_status_of(exc)) from exc


def fetch_json(url: str, cache_name: str, ttl: int = DEFAULT_TTL,
               timeout: int = 45, user_agent=USER_AGENT):
    """Fetch JSON, and refuse to cache anything that isn't.

    ``fetch_text`` writes whatever the server returned straight to disk. If
    a host answers a wrong path with an HTML error page or an empty body —
    which is what a guessed CDN path does — that garbage becomes the cached
    answer for the whole TTL, and every caller after it fails with a
    JSONDecodeError pointing at column 1 rather than at the real problem.

    So: parse first, cache second, and delete a cache entry that no longer
    parses. A poisoned cache should cost one request to recover from, not
    six hours.
    """
    import json as _json
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_name)

    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        try:
            return _json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            path.unlink(missing_ok=True)          # poisoned — go to the wire

    try:
        headers = ({} if user_agent is DEFAULT_AGENT
                   else {"User-Agent": user_agent})
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        if path.exists():
            try:
                return _json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                path.unlink(missing_ok=True)
        raise DataUnavailable(f"Could not fetch {url}: {exc}",
                              status=_status_of(exc)) from exc

    try:
        data = _json.loads(text)
    except ValueError as exc:
        head = text.strip()[:70].replace("\n", " ")
        raise DataUnavailable(
            f"{url} did not return JSON — got {len(text)} byte(s) starting "
            f"{head!r}. Nothing was cached.") from exc
    path.write_text(text, encoding="utf-8")
    return data


def fetch_csv(url: str, cache_name: str, **kw) -> list[dict]:
    """Fetch a CSV and return it as a list of row dicts.

    BOM-stripped, same as `load_local_csv` and for the same reason: a
    hand-exported file lands on this cache path and is served by the
    stale-fallback, and a leading BOM before a quoted first header cell
    breaks the quoting and shifts every column by one.
    """
    text = fetch_text(url, cache_name, **kw)
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))


def load_local_csv(path: str | Path) -> list[dict]:
    """Read a CSV the user has supplied locally (e.g. a stats export)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # utf-8-sig semantics: a leading BOM before a quoted first header cell
    # otherwise breaks the quoting and shifts every column by one.
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
