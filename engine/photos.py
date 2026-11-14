"""His action photo, where his league publishes one under the id his
headshot already carries.

Ethan, 2026-10-14, beside the hit tracker's card: "why do baseball players
have cool ass photos of themselves but no one else does, fix that". Every
chart now leads with his card (js/carrychart.js `playerHero`), and the
photo on it is the best his league publishes:

  * MLB files an action shot under the Stats API person id
    (`mlb.sources.mlbstats.action_url`), and his headshot's address carries
    that id (``.../people/{id}/headshot/...``);
  * the NHL files one under its player id at
    ``assets.nhle.com/mugs/actionshots/1296x729/{id}.jpg`` — the field the
    league's own player API returns as ``actionShot`` (community reference
    of the API, every address checked answering 200 on 2026-10-03) — and
    his headshot's address carries the id
    (``assets.nhle.com/mugs/nhl/{season}/{team}/{id}.png``);
  * the NFL, college, the NBA, the WNBA and the UFC publish none: their
    action photography is licensed through agencies (Getty, via
    Sportradar's image API, for the NBA), so the card stands his cut-out
    headshot on his club's colour instead.

CONSTRUCTED, NEVER FETCHED HERE, and written to cost nothing when wrong: a
man the league has no action shot for answers 404 and the page steps to
his headshot (carrychart.js `faceStep`). `photocheck.py` asks the box to
read a few of each, the way `assets.py` checked the headshots.
"""

from __future__ import annotations

import re

#: The NHL's action shot by player id (one size published).
NHL_ACTION = "https://assets.nhle.com/mugs/actionshots/1296x729/{pid}.jpg"

_MLB_ID = re.compile(r"/people/(\d+)/")
_NHL_ID = re.compile(r"assets\.nhle\.com/mugs/nhl/(?:[^/?#]+/)*(\d{6,8})\.png", re.I)


def action_url(sport: str, face: str) -> str:
    """His league's action photo from the id in his headshot's address, or
    "" where the league publishes none (or the address carries no id)."""
    face = str(face or "")
    if sport == "mlb":
        m = _MLB_ID.search(face)
        if m:
            from .mlb.sources.mlbstats import action_url as mlb_action
            return mlb_action(m.group(1))
    elif sport == "nhl":
        m = _NHL_ID.search(face)
        if m:
            return NHL_ACTION.format(pid=m.group(1))
    return ""
