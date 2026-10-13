"""One door for every player chart: ``/api/players/chart?kind=&sport=&player=&season=``.

Ethan, 2026-10-13, on the list of charts the data could carry next: "Yes
do all of them and don't stop till they are all done, then make sure they
are all routed correctly like nfl." The carry and route charts each got an
endpoint of their own (/api/players/carries, /api/players/routes), and
they keep them. Every chart since is a KIND here: the leagues it draws,
the function that builds it from the database, and the table whose rows
say whether the league's charts are still being filled — so a new chart
is a line in this table, not another endpoint, and the page asks every
chart the same way (js/carrychart.js `ask`).

What every answer carries, whatever the kind: the builder's own dict
(``{}`` for a player with nothing on file), his face where the site has
one (`statlogs.face`), or ``{"filling": true}`` when no one in the league
has a row yet — the charts being filled is not the same as none for him.
"""

from __future__ import annotations


def _carries(conn, sport, player, season):
    from . import carries
    return carries.chart(conn, sport, player, season)


def _routes(conn, sport, player, season):
    from . import targets
    return targets.chart(conn, player, season)


def _passes(conn, sport, player, season):
    from . import passes
    return passes.chart(conn, player, season)


def _rows_in(table):
    def stored(conn, sport):
        from .carries import stored as _stored
        return _stored(conn, sport, table=table)
    return stored


#: kind -> (the leagues it draws, builder(conn, sport, player, season),
#: stored(conn, sport): has the league any rows at all).
KINDS = {
    "carries": (("nfl", "cfb"), _carries, _rows_in("carries")),
    "routes": (("nfl",), _routes, _rows_in("targets")),
    "passes": (("nfl",), _passes, _rows_in("passes")),
}


def known(kind: str, sport: str) -> bool:
    spec = KINDS.get(kind)
    return bool(spec) and sport in spec[0]


def answer(conn, kind: str, sport: str, player: str, season: int | None = None) -> dict:
    """The chart a page draws, as every chart's endpoint answers it."""
    from . import statlogs
    _leagues, build, stored = KINDS[kind]
    out = build(conn, sport, player, season) or {}
    if out:
        out["kind"] = kind
        out["face"] = statlogs.face(conn, sport, out["player"])
    elif not stored(conn, sport):
        out = {"filling": True}
    return out
