"""A line to everybody on the site, written from the owner's desk.

Ethan, 2026-11-02: "add more features and tools the Qellys book owners account
should have". An owner needs to say something to every reader at once —
"Tonight's picks are late: the odds feed is down", "New: the live play-by-play
says what happened" — without a deploy. The site's own account writes it on
its desk (js/owner.js), it shows as a bar across the top of every page until
its hours run out or the desk clears it, and a reader can close it for
themselves.

ONE NOTICE, PLAIN TEXT. Posting replaces the last; at most `MAX_LEN`
characters, control characters and runs of spaces taken out, and the page
draws it as text, never as markup. It lives in data/site_notice.json and
rides on /api/billing/status, which every page already asks for when it
opens, so it costs no request of its own. Its `id` changes with its words, so
closing one notice never hides the next.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "site_notice.json"
MAX_LEN = 200
#: How long a notice may stand: a week at most, an hour at least.
MIN_HOURS, MAX_HOURS = 1, 24 * 7
TONES = ("info", "warn", "good")
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")


def clean(text) -> str:
    return " ".join(_CTRL.sub(" ", str(text or "")).split())[:MAX_LEN].strip()


def _read(path: Path | None = None) -> dict | None:
    try:
        got = json.loads((path or PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def current(now: float | None = None, path: Path | None = None) -> dict | None:
    """The notice standing now, or None (none posted, cleared, or run out)."""
    got = _read(path)
    t = time.time() if now is None else float(now)
    if not got or not got.get("text"):
        return None
    try:
        if float(got.get("until") or 0) <= t:
            return None
    except (TypeError, ValueError):
        return None
    return {k: got.get(k) for k in ("id", "text", "tone", "at", "until")}


def post(text, hours=24, tone="info", now: float | None = None, path: Path | None = None) -> tuple[int, dict]:
    """Stand a notice up for ``hours``; (200, the notice) or (400, why not)."""
    words = clean(text)
    if not words:
        return 400, {"error": "Write the notice first."}
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return 400, {"error": "How many hours should it stand?"}
    h = max(MIN_HOURS, min(MAX_HOURS, h))
    tone = tone if tone in TONES else "info"
    t = time.time() if now is None else float(now)
    note = {"id": hashlib.sha256(f"{t:.0f}|{words}".encode()).hexdigest()[:12], "text": words, "tone": tone,
            "at": round(t), "until": round(t + h * 3600)}
    p = path or PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(note), encoding="utf-8")
    os.replace(tmp, p)
    return 200, {"ok": True, "notice": note}


def clear(path: Path | None = None) -> tuple[int, dict]:
    try:
        (path or PATH).unlink()
    except FileNotFoundError:
        pass
    return 200, {"ok": True, "notice": None}
