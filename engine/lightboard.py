"""The light copy of a board: what the Home page draws first.

Ethan, 2026-09-05: "faster first paint on mlb board" — from a list he
asked for in full. Caddy compresses the boards, but a phone still parses
the whole JSON file before it draws anything, and on the MLB tab that
file is the first thing a reader waits for.

WHAT GOES, measured rather than guessed, on the NFL board in data/built
(2.9 MB): the top-level `player_stats` table is 37% of the file and is
read only by the Players page and the player profile; inside each pick
row the projection `chain`, the rule `checks`, the `comps` and the
`line_series` are 18% and are drawn only by the prop page (chainHTML,
checksHTML, compsHTML, lineMoveHTML in web/js/app.js — each has one
caller, renderPropPage). Everything else stays: the card draws its
chart from `recent_values`, its shop strip from `all_lines`, its tape
from `line_tape`, its script chip from `game_script`, and the game-bet
bars from `team_recent`, so the light copy draws the SAME Home board
the full one does. `logs` stay too — the edge board's sparkline reads
them, and a first paint with fewer bars than the second is a step
backwards, not a faster one.

WHAT DOES NOT CHANGE. The light copy is cut from the payload the board
is written from, in the same build, and the page replaces it with the
full board the moment that lands (the prop page re-renders then). It is
published through `gate.publish` like the board, so the paywall strips
the same keys from it and a signed-out reader gets the same locked
markers; `/api/board/<name>` serves it by name like any board.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Top-level keys left out: read only by pages that are not the first
#: paint, and heavy. `player_stats` is the per-player history table the
#: Players page and the player profile read (both through
#: `(state.data || {}).player_stats || {}`).
DROP_TOP = ("player_stats",)

#: The row lists whose rows are trimmed.
ROW_LISTS = ("recommendations", "game_bets", "long_shots", "most_likely")

#: The halves of a row only the prop page draws: engine/chain.py's
#: projection chain and rule checks, engine/comps.py's comparables,
#: engine/linemoves.py's line series.
DROP_ROW = ("chain", "checks", "comps", "line_series")

#: The suffix that names a light copy beside its board:
#: recommendations.json → recommendations_picks.json.
SUFFIX = "_picks"


def light_path(board_path) -> str:
    """The light copy's path beside the board's."""
    p = Path(str(board_path))
    return str(p.with_name(p.stem + SUFFIX + p.suffix))


def trim_row(row: dict) -> dict:
    """A row without its prop-page halves. A new dict."""
    return {k: v for k, v in (row or {}).items() if k not in DROP_ROW}


def light(payload: dict, sport: str = "") -> dict:
    """The light copy of ``payload``. A new dict; the payload is untouched."""
    out = {k: v for k, v in (payload or {}).items() if k not in DROP_TOP}
    for k in ROW_LISTS:
        rows = out.get(k)
        if isinstance(rows, list):
            out[k] = [trim_row(r) if isinstance(r, dict) else r for r in rows]
    out["light"] = True
    if sport:
        out["sport"] = sport
    return out


def _mb(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 100_000 else f"{n / 1e3:.0f} KB"


def report(board_path, light_path_) -> str:
    """One line for the build log: the light copy's size against the
    board's, from the files themselves. Both should be the FULL copies
    (gate.board_source for the board, publish's second return for the
    light one) — the public copies are redacted and would flatter it."""
    try:
        b, l = os.path.getsize(str(board_path)), os.path.getsize(str(light_path_))
    except OSError:
        return "Light board: written (sizes unavailable)"
    pct = (100 * l / b) if b else 0
    return f"Light board: {_mb(l)} of {_mb(b)} ({pct:.0f}%) — {Path(str(light_path_)).name}"
