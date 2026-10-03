"""Expected goals for hockey, fitted on our own shots.

Ethan's Edge Hunter brief (2026-10-03) leans on "5v5 expected goals, shot
quality, high-danger opportunities, goalie performance". MoneyPuck and NHL
EDGE are not wired; the league's play-by-play is (engine/sources/nhlpbp),
and every shot in it carries where it was taken from and what kind it was.
That is enough for the model every public xG starts from.

THE MODEL IS A SHRUNK LOOKUP TABLE, not a regression — the droplet has no
numpy, and a table says exactly why a shot was worth what it was. An
unblocked attempt (goal, shot on goal, miss; a block's location is the
blocker's) falls into a cell by distance band, angle band, shot type,
rebound/rush and strength. Each cell's rate is shrunk toward its parent's
(the same shot without the last split) by ``PRIOR`` attempts, all the way
up to the league rate — so a rare combination borrows from what it is a
special case of instead of reading 1-for-1 as a sure goal. Empty-net
attempts are left out of the fit (no goalie to beat).

WHAT IT ANSWERS, per player and team over their newest games: individual
xG (ixG) and unblocked attempts; a team's xG for and against, all
strengths and at even strength; a goalie's goals saved above expected
(xG faced on shots he saw minus goals he allowed). The model is refitted
nightly by the maintenance job (``fit``) and saved beside the rank fits.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: Distance bands (feet) and angle bands (degrees).
DIST = (10, 20, 30, 40, 55)
ANGLE = (15, 30, 45)
#: Shot types grouped the way they behave.
TYPE_GROUP = {"wrist": "wrist", "snap": "wrist", "slap": "slap", "backhand": "backhand",
              "tip-in": "tip", "deflected": "tip", "bat": "tip", "between-legs": "tip",
              "wrap-around": "wrap", "poke": "wrap", "cradle": "wrap"}
#: Attempts a cell borrows from its parent.
PRIOR = 60.0
MODEL_FILE = "nhl_xg.json"
UNBLOCKED = ("goal", "sog", "miss")


def _band(v: float, edges) -> int:
    for i, e in enumerate(edges):
        if v < e:
            return i
    return len(edges)


def keys(shot: dict) -> list[str]:
    """The cell chain for one attempt, coarsest first."""
    d = _band(float(shot.get("dist") or 0), DIST)
    a = _band(float(shot.get("angle") or 0), ANGLE)
    t = TYPE_GROUP.get(str(shot.get("shot_type") or "").lower(), "wrist")
    rr = "reb" if shot.get("rebound") else "rush" if shot.get("rush") else "-"
    st = str(shot.get("strength") or "EV")
    return [f"d{d}", f"d{d}a{a}", f"d{d}a{a}{t}", f"d{d}a{a}{t}{rr}", f"d{d}a{a}{t}{rr}{st}"]


def _models_dir() -> Path:
    return Path(os.environ.get("QB_MODELS_DIR") or Path(__file__).resolve().parents[2] / "data" / "models")


def fit(rows) -> dict:
    """{"league": rate, "cells": {key: rate}, "n": attempts} from shot rows
    (dicts or sqlite rows with dist, angle, shot_type, rebound, rush,
    strength, kind, empty_net, is_goal)."""
    counts: dict = {}
    goals = n = 0
    for r in rows:
        r = dict(r)
        if r.get("kind") not in UNBLOCKED or r.get("empty_net"):
            continue
        g = int(r.get("is_goal") or 0)
        goals += g
        n += 1
        for k in keys(r):
            c = counts.setdefault(k, [0, 0])
            c[0] += g
            c[1] += 1
    league = goals / n if n else 0.07
    cells: dict = {}
    for k in sorted(counts, key=len):
        parent = league
        for cut in range(len(k) - 1, 0, -1):
            if k[:cut] in cells:
                parent = cells[k[:cut]]
                break
        g, m = counts[k]
        cells[k] = round((g + PRIOR * parent) / (m + PRIOR), 5)
    return {"league": round(league, 5), "cells": cells, "n": n}


def xg(model: dict, shot: dict) -> float:
    """One attempt's expected goals: 0 for a block, the empty-net rate for
    an open net, else the deepest cell the model has."""
    if shot.get("kind") not in UNBLOCKED:
        return 0.0
    if shot.get("empty_net"):
        return 0.6
    cells = model.get("cells") or {}
    best = model.get("league", 0.07)
    for k in keys(shot):
        if k in cells:
            best = cells[k]
    return best


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


def fit_from_db(conn, seasons=None) -> dict:
    q = ("SELECT kind, empty_net, is_goal, dist, angle, shot_type, rebound, rush, strength "
         "FROM nhl_shots")
    args: list = []
    if seasons:
        q += " WHERE season IN (%s)" % ",".join("?" * len(seasons))
        args = list(seasons)
    return fit(conn.execute(q, args))


def game_rows(conn, model: dict, seasons=None) -> list[dict]:
    """Every stored attempt with its xG, newest game first."""
    q = ("SELECT game_id, date, season, team, opponent, shooter, goalie, kind, empty_net, is_goal, "
         "dist, angle, shot_type, rebound, rush, strength FROM nhl_shots")
    args: list = []
    if seasons:
        q += " WHERE season IN (%s)" % ",".join("?" * len(seasons))
        args = list(seasons)
    out = []
    for r in conn.execute(q + " ORDER BY date DESC", args):
        d = dict(r)
        d["xg"] = xg(model, d)
        out.append(d)
    return out


def summaries(rows: list[dict], window: int = 20) -> dict:
    """Per player, team and goalie, over each one's newest ``window`` games:

    players  {name: {"ixg", "iff", "sog", "goals", "games"}}   (iff = unblocked
             attempts, sog = on goal, goals included — ixg / sog is the
             shooting percentage his shots were worth)
    teams    {abbr: {"xgf", "xga", "xgf_ev", "xga_ev", "gf", "ga", "games"}}
    goalies  {name: {"xga", "ga", "shots", "gsax", "games"}}  (no empty nets)
    """
    by_player: dict = {}
    by_team: dict = {}
    by_goalie: dict = {}
    for r in rows:
        if r["kind"] in UNBLOCKED and r.get("shooter"):
            g = by_player.setdefault(r["shooter"], {})
            if r["game_id"] in g or len(g) < window:
                acc = g.setdefault(r["game_id"], [0.0, 0, 0, 0])
                acc[0] += r["xg"]
                acc[1] += 1
                acc[2] += r["is_goal"]
                acc[3] += r["kind"] in ("goal", "sog")
        for team, side in ((r["team"], "f"), (r["opponent"], "a")):
            t = by_team.setdefault(team, {})
            if r["game_id"] in t or len(t) < window:
                acc = t.setdefault(r["game_id"], {"xgf": 0.0, "xga": 0.0, "xgf_ev": 0.0, "xga_ev": 0.0,
                                                  "gf": 0, "ga": 0})
                acc[f"xg{side}"] += r["xg"]
                if r["strength"] == "EV" and not r["empty_net"]:
                    acc[f"xg{side}_ev"] += r["xg"]
                acc[f"g{side}"] += r["is_goal"]
        if r.get("goalie") and not r["empty_net"] and r["kind"] in ("goal", "sog"):
            gk = by_goalie.setdefault(r["goalie"], {})
            if r["game_id"] in gk or len(gk) < window:
                acc = gk.setdefault(r["game_id"], [0.0, 0, 0])
                acc[0] += r["xg"]
                acc[1] += r["is_goal"]
                acc[2] += 1
    players = {n: {"ixg": round(sum(v[0] for v in g.values()), 3), "iff": sum(v[1] for v in g.values()),
                   "sog": sum(v[3] for v in g.values()), "goals": sum(v[2] for v in g.values()), "games": len(g)}
               for n, g in by_player.items()}
    teams = {}
    for team, g in by_team.items():
        tot = {k: sum(v[k] for v in g.values()) for k in ("xgf", "xga", "xgf_ev", "xga_ev", "gf", "ga")}
        tot["games"] = len(g)
        teams[team] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in tot.items()}
    goalies = {}
    for name, g in by_goalie.items():
        xga = sum(v[0] for v in g.values())
        ga = sum(v[1] for v in g.values())
        goalies[name] = {"xga": round(xga, 3), "ga": ga, "shots": sum(v[2] for v in g.values()),
                         "gsax": round(xga - ga, 2), "games": len(g)}
    return {"players": players, "teams": teams, "goalies": goalies}


#: The board's summaries, kept beside the model: reading every stored shot
#: takes seconds and they only change when the nightly job adds shots or
#: refits, so a build reuses them while that key holds.
BOARD_FILE = "nhl_xg_board.json"


def board_summaries(conn, seasons=None, window: int = 40) -> dict | None:
    """The summaries a board build reads, over each one's newest ``window``
    games — None until a model is fitted and shots are stored, and then the
    board reads exactly as it did before shot quality."""
    model = load()
    if not model:
        return None
    q, args = "SELECT COUNT(*), MAX(game_id) FROM nhl_shots", []
    if seasons:
        q += " WHERE season IN (%s)" % ",".join("?" * len(seasons))
        args = list(seasons)
    count, newest = conn.execute(q, args).fetchone()
    if not count:
        return None
    key = [model.get("n"), model.get("league"), count, newest, sorted(seasons or []), window]
    path = _models_dir() / BOARD_FILE
    try:
        kept = json.loads(path.read_text())
        if kept.get("key") == key:
            return kept["summaries"]
    except (OSError, ValueError, AttributeError):
        pass
    out = summaries(game_rows(conn, model, seasons), window)
    try:
        save({"key": key, "summaries": out}, path)
    except OSError:
        pass
    return out


def team_goalie_pool(goalies: dict, players: dict, team: str) -> dict | None:
    """Every goalie of ``team`` pooled ({"xga", "ga"}) — what the team's
    goals against already carries, so tonight's starter is measured
    against it (the save-rate twin is model.team_sv)."""
    pool = [goalies[n] for n, p in players.items()
            if p.get("position") == "G" and p.get("team") == team and n in goalies]
    if not pool:
        return None
    return {"xga": sum(g["xga"] for g in pool), "ga": sum(g["ga"] for g in pool)}


def main(argv=None) -> int:
    """`python3 -m engine.nhl.xg fit` — refit on every stored shot and save."""
    import argparse
    from .. import db
    ap = argparse.ArgumentParser(description="Fit the NHL expected-goals model on stored shots.")
    ap.add_argument("cmd", choices=["fit"])
    a = ap.parse_args(argv)
    if a.cmd == "fit":
        conn = db.connect()
        m = fit_from_db(conn)
        if not m["n"]:
            print("No stored NHL shots yet — run: python3 ingest.py nhl --shots")
            return 1
        p = save(m)
        print(f"NHL xG: fitted on {m['n']:,} unblocked attempts, league rate {m['league']:.3f}, "
              f"{len(m['cells'])} cells -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
