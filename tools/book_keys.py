"""Which books the odds feed really answers for (runbook step JL).

The book list (engine/sources/oddsapi.DEFAULT_BOOKS) is ten since
2026-11-02 — the most one region's price buys (Ethan: "cut the books to
10"). theScore Bet was asked for under two keys, ESPN BET's old one and the
renamed book's, because the API's docs did not say which it uses; this
counts the bookmaker keys in the paid payloads cached over the last few
days, and on 3 November it showed `espnbet` answering and `thescorebet`
never, so that slot went to Fliff. It still names any book asked for that
never answers (Fliff's first days included) and which theScore key is live.

Read-only: no network, no credits. On the box:

    cd /srv/qellys && sudo -u qellys python3 tools/book_keys.py
"""
from __future__ import annotations

import collections
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import oddsapi as O                         # noqa: E402

THESCORE = ("espnbet", "thescorebet", "thescore")


def _events(payload):
    """The events in a cached payload, whatever its shape: one event, a
    board (a list of events), or a historical wrapper ({"data": ...})."""
    if isinstance(payload, dict) and "data" in payload and "bookmakers" not in payload:
        payload = payload["data"]
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    return []


def count(cache_dir=None, days: float = 3.0, now: float | None = None):
    """``(payloads read, Counter of bookmaker key -> events it priced)``
    over the cached odds payloads written in the last ``days``."""
    folder = cache_dir or O.CACHE_DIR
    t = time.time() if now is None else float(now)
    seen, files = collections.Counter(), 0
    for path in sorted(folder.glob("odds_*.json")):
        try:
            if t - path.stat().st_mtime > days * 86400:
                continue
        except OSError:
            continue
        payload = O._read_cached_json(path)
        if payload is None:
            continue
        files += 1
        for event in _events(payload):
            for bm in event.get("bookmakers") or []:
                if isinstance(bm, dict) and bm.get("key"):
                    seen[str(bm["key"])] += 1
    return files, seen


def report(files: int, seen, asked=None, days: float = 3.0) -> list[str]:
    asked = list(asked or O.DEFAULT_BOOKS)
    out = [f"Asked for ({len(asked)}): {', '.join(asked)}"]
    if not files:
        return out + [f"No odds payloads cached in the last {days:g} days to count."]
    out.append(f"Answered, events priced, in {files} payloads from the last {days:g} days:")
    for key, n in seen.most_common():
        title = O.BOOK_TITLES.get(key, key)
        out.append(f"  {key:<16} {n:>6}  {title}{'' if key in asked else '  (not asked for now)'}")
    silent = [k for k in asked if not seen.get(k)]
    out.append("Never answered: " + (", ".join(silent) if silent else "none — every book asked for priced something"))
    score = [(k, seen.get(k, 0)) for k in THESCORE if k in asked or seen.get(k)]
    if score:
        said = ", ".join(f"{k} {n}" for k, n in score)
        live = [k for k, n in score if n]
        if len(live) == 1:
            dead = [k for k, n in score if not n and k in asked]
            out.append(f"theScore Bet: {said} — it answers to {live[0]}"
                       + (f"; {', '.join(dead)} can give its slot to another book." if dead else "."))
        elif not live:
            out.append(f"theScore Bet: {said} — neither key answered; it may not quote these games.")
        else:
            out.append(f"theScore Bet: {said}.")
    return out


def main(argv=None) -> int:
    files, seen = count()
    print("\n".join(report(files, seen)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
