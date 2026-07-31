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
USER_AGENT = "qelly/0.1 (+nflverse loader)"
DEFAULT_TTL = 12 * 3600  # re-download at most twice a day


class DataUnavailable(RuntimeError):
    """Raised when a required feed cannot be fetched and has no local cache."""


def _cache_path(name: str) -> Path:
    return CACHE_DIR / name


def fetch_text(url: str, cache_name: str, ttl: int = DEFAULT_TTL,
               timeout: int = 45) -> str:
    """Return the text body of ``url``, caching it under ``cache_name``.

    If a fresh cache exists it is used. On a network failure a stale cache is
    used if present; otherwise :class:`DataUnavailable` is raised.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_name)

    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_text(encoding="utf-8", errors="replace")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
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
        raise DataUnavailable(f"Could not fetch {url}: {exc}") from exc


def fetch_csv(url: str, cache_name: str, **kw) -> list[dict]:
    """Fetch a CSV and return it as a list of row dicts."""
    text = fetch_text(url, cache_name, **kw)
    return list(csv.DictReader(io.StringIO(text)))


def load_local_csv(path: str | Path) -> list[dict]:
    """Read a CSV the user has supplied locally (e.g. a stats export)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    # utf-8-sig semantics: a leading BOM before a quoted first header cell
    # otherwise breaks the quoting and shifts every column by one.
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
