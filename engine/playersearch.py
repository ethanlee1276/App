"""One search box, every source.

Ethan, 2026-08-23: "i want the search bar to be to search any player in
every leauge" — and, an hour later, "im not able to search ufc players."

The second is not the first with one more league added to a list. Four
leagues live in ``player_game_logs`` (engine/statlogs.py) and are found by
a SQL LIKE; fighters live in ``data/ufc_dossiers.json`` (engine/ufc/
fighters.py) and are found by reading a file. Different stores, different
readers, one answer — and this is where the answer gets assembled, so
neither reader has to know the other exists.

RANKED BY ROUND-ROBIN, NOT BY ONE BIG SORT. Every source ranks its own
hits by whatever means something to it — the log search uses
``season || '-' || period``, which is a zero-padded NFL week ('005') in
one league and an ISO date in another, and neither of those means
anything against a fighter's UFC-fight count. There is no honest way to
sort them against each other, so nothing tries: one hit is taken from
each source in turn. That needs no cross-source comparison at all, and it
guarantees every league a place in a short list rather than letting
whichever format sorts highest take the lot.

Names that START with the query go round first. ``prefer`` — the tab the
visitor is standing on — only decides who goes first within a tier. It
never removes anyone, which is the entire point of the change.
"""

from __future__ import annotations

import re

#: Every source this box covers, in the order a tie is broken. The log
#: leagues come from statlogs; ufc is its own reader.
SOURCES = ("nfl", "mlb", "nba", "wnba", "ufc")


def leads_with(name: str, q: str) -> bool:
    """Does ``q`` start the name, or start any word in it?

    "mahomes" leading Patrick Mahomes has to outrank "mahomes" merely
    appearing inside somebody else's name, or the source that happens to
    go first eats the whole result list.
    """
    n = (name or "").lower()
    ql = (q or "").lower()
    if not ql:
        return False
    return n.startswith(ql) or any(
        w.startswith(ql) for w in re.split(r"[^a-z0-9]+", n) if w)


def merge(per_source: dict, q: str, limit: int, order) -> list[dict]:
    """Round-robin over already-ranked lists, leading matches first."""
    order = [s for s in order if s in per_source]
    strong = {s: [h for h in per_source[s] if leads_with(h["player"], q)]
              for s in order}
    weak = {s: [h for h in per_source[s] if not leads_with(h["player"], q)]
            for s in order}
    out: list[dict] = []
    for tier in (strong, weak):
        depth = 0
        while len(out) < limit:
            took = False
            for s in order:
                lst = tier[s]
                if depth < len(lst):
                    out.append(lst[depth])
                    took = True
                    if len(out) >= limit:
                        break
            if not took:
                break
            depth += 1
    return out[:limit]


def source_order(prefer: str = "") -> list[str]:
    """SOURCES with the visitor's own league first."""
    return ([prefer] if prefer in SOURCES else []) + \
        [s for s in SOURCES if s != prefer]


def search(q: str, limit: int = 12, prefer: str = "",
           db_path=None, ufc_path=None) -> list[dict]:
    """Every player and fighter whose name contains ``q``."""
    from . import statlogs
    from .ufc import fighters
    q = (q or "").strip()
    if not q:
        return []
    order = source_order(prefer)
    # Every source fetches a full page: four empty ones must not cost the
    # fifth its results. The log leagues come back in ONE connection.
    per: dict = dict(statlogs.search_by_sport(
        q, limit, [s for s in order if s != "ufc"], db_path))
    # A store that is missing is not an error — see fighters.load.
    per["ufc"] = fighters.search(q, limit=limit, path=ufc_path)
    return merge(per, q, limit, order)
