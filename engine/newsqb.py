"""An expected starting quarterback, read off the headlines we already pull.

Ethan, 2026-09-28: the site learned the Bears' quarterback from the depth
chart and the injury report; his research had Case Keenum from Rapoport
hours earlier ("Keenum expected to start"). The ESPN feed the site already
fetches (engine/sources/news) carries that headline — nothing new is
pulled, it is read.

WHAT COUNTS. A headline that names a quarterback the slate knows (this
team's starter or backup by passing volume — engine/qbchange.quarterbacks)
beside one of the phrases a beat reporter uses for a start:

    "expected to start", "to start", "will start", "named starter",
    "named the starter", "gets the start", "starting … at QB"

The team is the one whose quarterback room he is in, so a headline never
has to name the team. Newest wins; a headline older than MAX_AGE_S is
noise from another week. A headline that says he WON'T start ("not
expected to start", "ruled out", "won't start") is refused, not read
backwards.

WHERE IT GOES. engine/qbchange.changes takes it as ``news_qb``: when the
starter is out and this week's depth chart has not named someone else,
the reported man is the replacement — ahead of "second quarterback by
volume", behind the depth chart. The card says "expected to start (per
ESPN)" so the reader knows which it was.
"""

from __future__ import annotations

import re
import time

MAX_AGE_S = 4 * 24 * 3600

_START = re.compile(
    r"\b(expected to start|to start|will start|nam(?:e|es|ed|ing) [^.,;]{0,40}?\b(?:the |as (?:the )?)?starter|"
    r"gets? the start|get the (?:starting )?nod|starting (?:qb|quarterback)|"
    r"to make (?:his )?(?:first )?start)\b", re.I)
_NOT = re.compile(r"\b(not expected to start|won[’']?t start|will not start|ruled out|out for|"
                  r"is out|benched|backup)\b", re.I)


def _norm(name: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(str(name or ""))


def _rooms(qb: dict) -> dict:
    """{normalized name: (team, display name)} for every quarterback the slate ranks."""
    out = {}
    for team, slot in ((qb or {}).get("teams") or {}).items():
        for role in ("starter", "backup"):
            n = slot.get(role)
            if n:
                out[_norm(n)] = (team, n)
    return out


def _names_in(title: str, rooms: dict) -> list:
    """The room quarterbacks a headline names: the full name, or a surname
    of four letters or more that only one of them carries ("Bagent gets
    the start")."""
    low = _norm(title)
    words = set(re.findall(r"[a-z0-9']+", low))
    surnames: dict = {}
    for key, (team, name) in rooms.items():
        last = key.split()[-1] if key else ""
        if len(last) >= 4:
            surnames.setdefault(last, []).append((team, name))
    out = []
    for key, (team, name) in rooms.items():
        if key and key in low:
            out.append((team, name))
            continue
        last = key.split()[-1] if key else ""
        if len(last) >= 4 and last in words and len(surnames.get(last) or []) == 1:
            out.append((team, name))
    return out


def expected_starters(headlines, qb: dict, now: float | None = None) -> dict:
    """{team: {"name", "title", "source", "epoch"}} — the newest usable headline per team."""
    now = time.time() if now is None else now
    rooms = _rooms(qb)
    out: dict = {}
    for h in sorted(headlines or [], key=lambda r: -float(r.get("epoch") or 0)):
        title = str(h.get("title") or "")
        epoch = float(h.get("epoch") or 0)
        if not title or (epoch and now - epoch > MAX_AGE_S):
            continue
        if not _START.search(title) or _NOT.search(title):
            continue
        named = _names_in(title, rooms)
        # One quarterback named, or the phrase right after one of them.
        if not named:
            continue
        if len(named) > 1:
            named = [(t, n) for t, n in named if re.search(re.escape(n.split()[-1]) + r"\b[^.]{0,40}" + _START.pattern,
                                                           title, re.I)]
            if len(named) != 1:
                continue
        team, name = named[0]
        if team not in out:
            out[team] = {"name": name, "title": title[:200], "source": str(h.get("source") or ""), "epoch": epoch}
    return out


def load_headlines(path: str = "web/data/news.json", sport: str = "nfl") -> list:
    """The news build's rows for one league, or [] when there is no file."""
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            return list(((json.load(fh) or {}).get("sports") or {}).get(sport) or [])
    except (OSError, ValueError):
        return []
