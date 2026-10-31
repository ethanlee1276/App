"""Expected batting average and slugging, fitted on our own batted balls.

Ethan, 2026-10-13, on the list he said yes to ("Yes do all of them"):
"MLB expected stats: once batted balls are stored, we could build our own
expected batting average and slugging from exit velocity and launch angle,
as we did for NHL expected goals. I'd test it before it touches a pick."

WHY OUR OWN when the board already reads Baseball Savant's season xSLG
(engine/mlb/sources/savant, mlb/statcast): Savant's leaderboard is a
season total, read when Savant answers. This is every batted ball the box
stores (engine/mlb/charts, the hit tracker's table), so it is there per
ball and per stretch of games, and when Savant is not.

THE MODEL IS A SHRUNK LOOKUP TABLE, as the hockey xG model is (engine/nhl/
xg): a ball in play falls into a cell by exit velocity band, then by
launch angle band within it; each cell's hit rate and total bases a ball
are shrunk toward its exit-velocity band's by ``PRIOR`` balls, and the
band's toward the league's. No numpy on the droplet, and a table says
exactly why a ball was worth what it was.

WHAT IT ANSWERS: one ball's chance of being a hit and its expected total
bases (`xvals`); a batter's expected average and slugging over a set of
plate appearances (`line`): the expected hits and bases of his balls in
play over his at bats, a strikeout counting nothing and a ball with no
speed or angle on file counting as what it was.

NOTHING HERE MOVES A PRICE. It is drawn on the hit tracker; whether it
predicts a hitter's next game better than his actual average and slugging
is measured, on games the model never saw, by engine/mlb/xstatsfit with a
bar written down before it was run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Exit velocity band edges (mph) and launch angle band edges (degrees).
EV = (60, 70, 75, 80, 85, 88, 91, 94, 97, 100, 103, 106, 109, 112)
LA = (-20, -10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 50)
#: Balls a cell borrows from its exit-velocity band, and a band from the league.
PRIOR = 40.0
MODEL_FILE = "mlb_xstats.json"
#: The fewest balls in play worth fitting on.
MIN_BALLS = 1000


def _band(v: float, edges) -> int:
    for i, e in enumerate(edges):
        if v < e:
            return i
    return len(edges)


def keys(ev: float, la: float) -> list[str]:
    """A ball's cell chain, coarsest first."""
    e = _band(float(ev), EV)
    return [f"e{e}", f"e{e}l{_band(float(la), LA)}"]


def _models_dir() -> Path:
    return Path(os.environ.get("QB_MODELS_DIR") or Path(__file__).resolve().parents[2] / "data" / "models")


def _bases(event_type: str) -> int:
    from .charts import HIT_BASES
    return HIT_BASES.get(event_type or "", 0)


def fit(rows) -> dict:
    """``{"league": [hit rate, bases a ball], "cells": {key: [hit rate,
    bases a ball]}, "n": balls}`` from rows ``(launch_speed, launch_angle,
    event_type)`` — balls in play with both numbers on file."""
    counts: dict = {}
    hits = bases = n = 0
    for ev, la, et in rows:
        if ev is None or la is None:
            continue
        b = _bases(et)
        hits += 1 if b else 0
        bases += b
        n += 1
        for k in keys(ev, la):
            c = counts.setdefault(k, [0, 0, 0])
            c[0] += 1 if b else 0
            c[1] += b
            c[2] += 1
    league = [hits / n, bases / n] if n else [0.3, 0.5]
    cells: dict = {}
    for k in sorted(counts, key=len):
        parent = cells.get(k.split("l")[0], league) if "l" in k else league
        h, tb, m = counts[k]
        cells[k] = [round((h + PRIOR * parent[0]) / (m + PRIOR), 4), round((tb + PRIOR * parent[1]) / (m + PRIOR), 4)]
    return {"league": [round(league[0], 4), round(league[1], 4)], "cells": cells, "n": n,
            "ev": list(EV), "la": list(LA), "prior": PRIOR}


def xvals(model: dict, ev, la) -> tuple[float, float] | None:
    """One ball's (chance of a hit, expected total bases), or None without
    its speed and angle."""
    if ev is None or la is None or not model:
        return None
    best = model.get("league") or [0.3, 0.5]
    cells = model.get("cells") or {}
    for k in keys(ev, la):
        if k in cells:
            best = cells[k]
    return float(best[0]), float(best[1])


def line(model: dict, pas) -> dict:
    """``{"ab", "xh", "xtb", "xba", "xslg"}`` over plate appearances
    ``(event_type, launch_speed, launch_angle)``: a ball in play counts
    its expected hit and bases, a strikeout nothing, a ball with no speed
    or angle what it was; walks and the like are no at bat."""
    from .charts import NOT_AB
    ab = 0
    xh = xtb = 0.0
    for et, ev, la in pas:
        if et in NOT_AB:
            continue
        ab += 1
        v = xvals(model, ev, la)
        if v is not None:
            xh += v[0]
            xtb += v[1]
        else:
            b = _bases(et)
            xh += 1 if b else 0
            xtb += b
    return {"ab": ab, "xh": round(xh, 2), "xtb": round(xtb, 2),
            "xba": round(xh / ab, 3) if ab else None, "xslg": round(xtb / ab, 3) if ab else None}


def save(model: dict, path=None) -> Path:
    p = Path(path) if path else _models_dir() / MODEL_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(model))
    os.replace(tmp, p)
    return p


def load(path=None) -> dict | None:
    p = Path(path) if path else _models_dir() / MODEL_FILE
    try:
        m = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return m if m.get("cells") else None


def fit_from_db(conn, before: str | None = None) -> dict:
    """The model on every stored ball in play (or those before a date)."""
    q = ("SELECT launch_speed, launch_angle, event_type FROM mlb_pa "
         "WHERE launch_speed IS NOT NULL AND launch_angle IS NOT NULL")
    args: list = []
    if before:
        q += " AND date < ?"
        args.append(before)
    return fit(conn.execute(q, args))
