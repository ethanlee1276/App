"""Injured-list awareness from the MLB transactions wire.

The lineup hold already stops bets on hitters without a confirmed spot —
but a MORNING board runs on projected lineups (last game's card), and a
player who hit the injured list two days ago is still in that card. He
becomes a phantom candidate, then a void. One free transactions request
covers every team's IL placements and activations; this module reduces
that wire to the two facts the board needs:

* **on the IL right now** — never a pick, said plainly on the card;
* **just activated** — biddable again, but his recent-form window is
  whatever he did BEFORE the injury, so the pick carries the caveat.

Pure functions over parsed transactions; fixture-tested.
"""

from __future__ import annotations

import datetime as _dt

from ..sources.oddsapi import normalize_name

# How long "just back from the IL" stays worth saying on a card.
RETURN_NOTE_DAYS = 5

_PLACED = ("placed", "transferred")
_BACK = ("activated", "reinstated", "returned")


def il_status(transactions: list[dict], today: str) -> dict:
    """``{normalized player: {"on_il", "date", "team", "detail"}}``.

    Only injured-list transactions count, and the LATEST one wins — a
    placement followed by an activation is a healthy player."""
    per: dict = {}
    for t in sorted(transactions or [], key=lambda t: t.get("date") or ""):
        desc = (t.get("desc") or "").lower()
        if "injured list" not in desc:
            continue
        back = any(w in desc for w in _BACK)
        placed = any(w in desc for w in _PLACED)
        if not back and not placed:
            continue
        per[normalize_name(t.get("player", ""))] = {
            "on_il": placed and not back,
            "date": t.get("date", ""),
            "team": t.get("team", ""),
            "detail": t.get("desc", ""),
        }
    return per


def just_returned(entry: dict | None, today: str,
                  days: int = RETURN_NOTE_DAYS) -> bool:
    """True when this player's latest IL move was an activation within the
    note window before ``today``."""
    if not entry or entry.get("on_il") or not entry.get("date"):
        return False
    try:
        back = _dt.date.fromisoformat(str(entry["date"])[:10])
        return 0 <= (_dt.date.fromisoformat(today) - back).days <= days
    except ValueError:
        return False
