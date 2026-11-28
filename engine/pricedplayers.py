"""Who the books priced, pull by pull — and who they stopped pricing.

Ethan, 2026-09-26, on Zay Flowers: "i dont see zay flowers on any sports
book. ik he was out for hamstring." The official report still read
Questionable (ESPN, Thursday 4:14 PM ET) while every book had already taken
his props down. The books move first; the report catches up.

The board never invents a price: a player's rows exist only while the
latest paid pull still lists him, so the next pull removes his prices on
its own. What it does not remove is his matchup read — "could shine" is
built from usage, not from books — and nothing says WHY he vanished.

This module remembers, per event, the players the latest pull priced and
the ones the pull before it priced. A player in the earlier pull and absent
from every book in the newer one — for a game that has not started — was
PULLED. The build marks him on the game (`Game.pulled_players`), the
matchup scan gives him no read, and the scan says who was pulled and why.

HE STAYS PULLED UNTIL A PULL PRICES HIM AGAIN (``gone``). Kyle Monangai,
2026-10-22, ruled out for a third straight game: one pull priced him, the
next did not, and the one after that did not either — and since only the
last two pulls were compared, the third read as nobody pulled, and the
report's change log wrote "Kyle Monangai's props are back up" beside the
line that said he was out.

A pull is recognised by its payload's write time, so a cached rebuild
serving the same file is not a new pull and changes nothing. Standard
library only; the store lives beside the other model state.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata

#: A player must have been priced within this long before the newer pull
#: for his absence to mean anything: a menu from last week is a different
#: game week.
MAX_GAP_S = 4 * 86400


def store_path() -> str:
    from . import modelstate as _ms
    return _ms.path("priced_players.json")


def _load(path: str) -> dict:
    try:
        with open(path) as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def record(event_id: str, players: list, pulled_at: float, data: dict) -> None:
    """Fold one served payload into ``data`` (in place). A payload written
    after the latest recorded pull becomes the latest; the previous latest
    becomes the earlier one. The same pull served again changes nothing."""
    if not event_id or pulled_at is None:
        return
    names = sorted({str(p) for p in players if p})
    cur = data.get(event_id) or {}
    latest_at = float(cur.get("latest_at") or 0.0)
    if pulled_at <= latest_at + 1.0:
        return
    if cur.get("latest") is not None:
        rec = {"latest_at": pulled_at, "latest": names,
               "earlier_at": latest_at, "earlier": cur.get("latest") or []}
    else:
        rec = {"latest_at": pulled_at, "latest": names}
    # Who is down stays down until a pull prices him; a pull that priced
    # nobody says nothing about anyone, so it clears no one either.
    gone = set(cur.get("gone") or []) | set(_dropped(rec))
    if names:
        now = {_same(p) for p in names}
        gone = {p for p in gone if _same(p) not in now}
    if gone:
        rec["gone"] = sorted(gone)
    data[event_id] = rec


#: Name endings a book may or may not print.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _same(name: str) -> str:
    """One key for a man however a pull spells him — "D.J. Moore" and "DJ
    Moore", "Carlton Davis III" and "Carlton Davis", "Luka Dončić" and
    "Luka Doncic" — so a spelling that changes between pulls is neither a
    pull nor, once he is down, a man who never comes back."""
    plain = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z ]", "", plain.lower().replace("-", " ")).split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return "".join(words)


def _dropped(cur: dict) -> list:
    """Players priced in the earlier pull and in none of the books in the
    latest one — [] when there is no earlier pull, the gap is too long, or
    the latest pull priced nobody (a payload with no player markets says
    nothing about any one player)."""
    latest, earlier = cur.get("latest"), cur.get("earlier")
    if not latest or not earlier:
        return []
    if float(cur.get("latest_at") or 0) - float(cur.get("earlier_at") or 0) > MAX_GAP_S:
        return []
    now = {_same(p) for p in latest}
    return sorted(p for p in earlier if _same(p) not in now)


def pulled(event_id: str, data: dict) -> list:
    """Every player the books have taken down for this event and no pull
    has priced since: the one the latest pull dropped, and anyone dropped
    before it who has not come back."""
    cur = data.get(event_id) or {}
    return sorted(set(cur.get("gone") or []) | set(_dropped(cur)))


class Tracker:
    """One build's view: record each served payload, then ask who was pulled."""

    def __init__(self, path: str | None = None):
        self.path = path or store_path()
        self.data = _load(self.path)
        self.dirty = False

    def see(self, event_id: str, players: list, age_s: float | None, now: float | None = None) -> list:
        if age_s is None:
            return pulled(event_id, self.data)
        at = (now if now is not None else time.time()) - float(age_s)
        before = json.dumps(self.data.get(event_id), sort_keys=True)
        record(event_id, players, at, self.data)
        if json.dumps(self.data.get(event_id), sort_keys=True) != before:
            self.dirty = True
        return pulled(event_id, self.data)

    def save(self) -> None:
        if self.dirty:
            try:
                _save(self.path, self.data)
            except OSError:
                pass
            self.dirty = False
