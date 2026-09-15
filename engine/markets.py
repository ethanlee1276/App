"""One place that turns an engine market id into English.

Ethan, 2026-08-24, looking at the Record page's BY MARKET split:
"spell out those works all the way". The table was showing `reb`, `ast`,
`fg3m` and `pts` beside "Total Bases" and "Outs Recorded" — half the
rows in the reader's language and half in the database's.

THE CAUSE WAS FIVE COPIES OF ONE VOCABULARY. engine/models.py,
engine/mlb/models.py, engine/nba/pipeline.py and engine/cfb/pipeline.py
each own the labels for their own board, which is right — that is where
a market is defined. web/js/app.js then kept a hand-typed sixth copy for
the Record page, and it had drifted: it spelled the basketball markets
`points`/`rebounds`/`assists`, which is what a person would guess, while
the journal stores `pts`/`reb`/`ast`, which is what the feed sends. Any
key the copy missed fell through to `k` and rendered raw.

So the copy is gone and this module is the merge. The sport modules stay
the definition; this reads them, adds the markets that belong to no
single board (game lines, UFC), and is exported into record.json so the
front end reads the engine's vocabulary instead of retyping it — the
same rule the break-even threshold already follows.

`label()` also prettifies an id it has never seen, so a market added to
a feed tomorrow reads as "First 3 Innings" rather than
`first_3_innings`. The fallback is a courtesy, not the plan: a stat that
does not survive title-casing (`fg3m`) has to be named here, and
test_market_words checks that every market the journal actually holds is
named rather than merely prettified.
"""

from engine.cfb.pipeline import MARKET_LABELS as _CFB
from engine.mlb.models import MARKET_LABELS as _MLB
from engine.models import MARKET_LABELS as _NFL
from engine.nba.pipeline import MARKET_LABELS as _NBA

#: Markets no single board owns. Game lines are priced on every sport,
#: and the UFC card's markets live in its own pipeline rather than a
#: MARKET_LABELS dict.
SHARED = {
    "moneyline": "Moneyline",
    "spread": "Spread",
    "total": "Game Total",
    "team_total": "Team Total",
    "prop": "Player Prop",
    "props": "Player Props",
    # UFC. `fighter_finish` is the fighter-to-finish market; "Finish" is
    # what the card itself calls it and what the UFC page already shows.
    "method": "Method",
    "distance": "Distance",
    "fighter_finish": "Finish",
    "round": "Round",
    "exact_round": "Exact Round",
}

#: Stats a board tracks that its MARKET_LABELS does not list, because
#: they are modelled without being priced as their own market.
EXTRA = {
    "targets": "Targets", "carries": "Carries",
    "first_3_innings": "First 3 Innings",
    "stl": "Steals", "blk": "Blocks", "min": "Minutes",
}

#: Where two boards spell one shared id differently, this is the
#: spelling the site uses. `side` is college football's name for the
#: spread; the journal's own `by_side` bucket means OVER/UNDER and never
#: reaches this map, so there is no collision to resolve.
OVERRIDES = {"side": "Spread", "total": "Game Total",
             "team_total": "Team Total"}


def _merged() -> dict[str, str]:
    out: dict[str, str] = {}
    for src in (_CFB, _NFL, _MLB, _NBA, SHARED, EXTRA, OVERRIDES):
        out.update(src)
    return out


WORDS = _merged()


def prettify(key: str) -> str:
    """`first_3_innings` -> `First 3 Innings`. Never returns empty."""
    s = str(key or "").replace("_", " ").replace("-", " ").strip()
    if not s:
        return "—"
    return " ".join(w if w.isupper() else w.capitalize() for w in s.split())


def label(key: str) -> str:
    """The reader's word for a market id, prettified if unknown."""
    return WORDS.get(key) or prettify(key)


def words() -> dict[str, str]:
    """A copy, for shipping in a payload."""
    return dict(WORDS)
