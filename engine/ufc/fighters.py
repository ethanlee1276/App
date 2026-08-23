"""Fighter search — the one thing the player box could never answer.

Ethan, 2026-08-23: "also i guess i should add im not able to search ufc
players."

He could not, and no amount of fixing the league-wide search would have
helped: that search reads ``player_game_logs``, and nothing writes a UFC
row there. A fight is not a game with a stat line per market — the
promotion's numbers are career RATES (strikes landed per minute, takedown
defence), and ours live in ``data/ufc_dossiers.json``, keyed by fighter.
A different store, so a different reader.

WHAT A FIGHTER CARD CANNOT HAVE, and must not pretend to. Every other
sport's search result draws a bar chart of the last ten games because a
per-game value exists to chart. A fighter has no such series here, so his
card shows the measured rates and says plainly that they are career
numbers. An invented chart would be the worst of both.

FACTS ONLY, because this rides the ungated search endpoint. Record, age,
division, and rates measured from public fight data are on the same free
footing as game logs and rosters — engine/statlogs.py's header carries the
argument. Our READ of a fighter is not: the archetype we assigned him and
the red flags we raised are analysis that blocks our own bets, and they
stay on the paid side of the line with the picks.
"""

from __future__ import annotations

import json
import os
import re

#: The dossier store. Written by ufc_dossiers.py, hand-edited by Ethan,
#: read by ufc_build.py — this is the fourth reader and the first that
#: only looks.
DOSSIERS = os.path.join("data", "ufc_dossiers.json")

#: What a search result may carry. An allow-list rather than a
#: block-list: a dossier gains fields over time (this one already has
#: `short_notice`, `r3_decay`, `ko_losses_last3`), and a new one must not
#: reach a public endpoint because nobody remembered to exclude it.
FACT_FIELDS = ("record", "age", "division", "slpm", "sapm", "str_def",
               "kd_per100", "td_per15", "td_acc", "tdd", "ctrl_per15",
               "sub_att_per15")


def load(path: str | None = None) -> dict:
    """{display name: dossier}, or {} when there is no store.

    The same honest degradation the log search has: a machine without the
    file (a fresh clone, CI) searches no fighters rather than failing.
    """
    p = path or DOSSIERS
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}                    # a half-written file is not a crash
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        # `_readme` and `_unfound` are bookkeeping, not fighters.
        if not isinstance(v, dict) or str(k).startswith("_"):
            continue
        out[str(v.get("name") or k)] = v
    return out


def brief(d: dict) -> dict:
    """The public half of a dossier: measured numbers and public record."""
    out = {k: d[k] for k in FACT_FIELDS if d.get(k) is not None}
    ufc = d.get("ufc_fights")
    career = d.get("career_fights", d.get("fights"))
    if ufc is not None:
        out["ufc_fights"] = ufc
    if career is not None:
        out["career_fights"] = career
    return out


def search(q: str, limit: int = 12, path: str | None = None) -> list[dict]:
    """Fighters whose name contains ``q``, shaped like a log-search hit.

    Same keys the history-DB search returns, so one result list can hold
    both and the page needs no second code path to lay them out:
    ``player``/``sport``/``team``/``position``/``games``/``headshot``,
    plus a ``fighter`` block the card reads for the rates.

    ``team`` is empty on purpose — a fighter has no club, and inventing
    one would put a team logo and a set of team colours on a man who has
    neither. ``position`` carries his division, which is the thing that
    actually belongs in that slot on the row.
    """
    q = (q or "").strip().lower()
    if not q:
        return []
    hits = []
    for name, d in load(path).items():
        if q not in name.lower():
            continue
        b = brief(d)
        hits.append({
            "player": name, "sport": "ufc", "team": "",
            "position": str(b.get("division") or "").replace("_", " "),
            # The count the row prints. UFC fights are what we have
            # STATS for; the career number rides in the brief beside it.
            "games": int(d.get("ufc_fights") or 0),
            "headshot": "", "fighter": b,
        })
    # Deepest record first among equals — a 12-fight veteran is the more
    # likely lookup than a debutant with the same surname.
    hits.sort(key=lambda h: (-h["games"], h["player"].lower()))
    return hits[:max(0, int(limit))]
