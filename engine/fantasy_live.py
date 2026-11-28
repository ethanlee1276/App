"""Your matchup, live: points so far, the rest projected, the win chance moving.

Ethan, 2026-10-27: after round one of the Fantasy room, the next on the list
was "your matchup live (points as games happen)". The desk's head-to-head
scored both lineups on this week's projections before kickoff and stopped
there; on a Sunday afternoon the question is "am I winning?", and the
answer moved with every snap.

WHAT IS COUNTED. The points: Sleeper's own, each starter's `players_points`
on the league's matchup board (league/{id}/matchups/{week}), so the
league's scoring, kickers and defenses included, for every game of the
week (Thursday's too: our own game files are pruned after 36 hours). The
lineup: the one actually set (the board's `starters`), not the best one,
because the set one is what scores. The clock: each starter's game from
our live scoreboard (live_nfl.json: state, quarter and clock), and from the
week's kickoff times when the scoreboard does not carry it.

WHAT IS PROJECTED: what is left. A starter whose game has not kicked off
counts at his projection (this week's, under the league's scoring); one in
a game in progress at his points so far plus his projection times the share
of the game left; one whose game is over at what he scored. The spread
shrinks the same way (a finished game has none), and the win chance is the
head-to-head's (engine/fantasy_h2h): the expected final margin against its
spread.

Sleeper leagues only: their boards carry the live points. Standard library
only; pure apart from `scoreboard`, which reads one file.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOREBOARD = ROOT / "web" / "data" / "live_nfl.json"
#: Regulation, in minutes.
GAME_MIN = 60.0
#: A game's length on the clock on the wall, kickoff to final, for a game
#: the scoreboard does not carry.
WALL_MIN = 195.0


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def frac_left(period: str, clock: str) -> float:
    """The share of regulation still to play, from "Q3" and "4:12". Overtime
    is all but over; a quarter with no clock (a break) is its end."""
    p = str(period or "").strip().upper()
    if not p.startswith("Q"):
        return 0.5 if "HALF" in p else 0.0
    try:
        q = int(p[1:])
    except ValueError:
        return 0.0
    if q > 4:
        return 0.01
    secs = 0.0
    try:
        mm, ss = str(clock or "").split(":")[:2]
        secs = int(mm) * 60 + int(ss)
    except ValueError:
        secs = 0.0
    return max(0.0, min(1.0, ((4 - q) * 15 * 60 + secs) / (GAME_MIN * 60)))


def scoreboard(path: Path = SCOREBOARD) -> dict:
    """{team: {state, frac_left, clock}} off the live scoreboard file, for
    the games it carries."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for g in (doc or {}).get("games") or []:
        live = g.get("live") or {}
        st = str(live.get("state") or "").lower()
        state = "live" if st in ("in", "live") else "final" if st in ("post", "final") else "pre"
        info = {"state": state,
                "frac_left": frac_left(live.get("period"), live.get("clock")) if state == "live"
                else 0.0 if state == "final" else 1.0,
                "clock": " ".join(x for x in (live.get("period"), live.get("clock")) if x)
                if state == "live" else ("Final" if state == "final" else "")}
        for side in ("home", "away"):
            if g.get(side):
                out[str(g[side])] = info
    return out


def states(week_doc: dict | None, board: dict | None, now: _dt.datetime | None = None) -> dict:
    """{team: {state, frac_left, clock}} for every team playing this week:
    the scoreboard's word where it has one, else the kickoff time's (not
    yet, under way for a game's length on the wall clock, then over).
    ``now`` is Eastern, naive."""
    from .fantasy_compare import clock as _clock, kickoff
    if now is None:
        from .fantasy_compare import _eastern
        now = _eastern(_dt.datetime.now(_dt.timezone.utc))
    out = {}
    for team, t in ((week_doc or {}).get("teams") or {}).items():
        ko = kickoff({"date": (t or {}).get("date"), "kickoff": (t or {}).get("kickoff")})
        if ko is None:
            continue
        mins = (now - ko).total_seconds() / 60.0
        if mins < 0:
            out[team] = {"state": "pre", "frac_left": 1.0, "clock": _clock(ko)}
        elif mins >= WALL_MIN:
            out[team] = {"state": "final", "frac_left": 0.0, "clock": "Final"}
        else:
            out[team] = {"state": "live", "frac_left": max(0.0, 1.0 - mins / WALL_MIN), "clock": "Under way"}
    from .divisions import canonical
    for team, info in (board or {}).items():
        out[canonical("nfl", team)] = info
    return out


def projections(names, means: dict, scoring: dict) -> tuple[dict, dict]:
    """({name: this week's points}, {name: spread}) under the league's
    scoring, scaled the way the head-to-head scales a PPR spread
    (fantasy_h2h.team_total)."""
    from .fantasy_lineup import league_points
    proj, sds = {}, {}
    for name in names or []:
        m = (means or {}).get(name)
        if not m:
            continue
        got = league_points(m, scoring)
        proj[name] = float(got["points"])
        sd = m.get("_sd")
        base = float(got.get("base_ppr") or 0.0)
        if sd is not None:
            sds[name] = float(sd) * (float(got["points"]) / base) if base > 0 else float(sd)
    return proj, sds


def side(row: dict | None, players: dict, slots: list, proj: dict, sds: dict, game: dict) -> dict:
    """One team's starters as they stand: [{slot, player, position, team,
    points, projected, state, clock}] and the totals. ``row`` is the team's
    row on Sleeper's board; ``proj``/``sds`` {name: this week's points,
    spread} under the league's scoring; ``game`` the `states`."""
    from .divisions import canonical
    pts = {str(k): float(v or 0.0) for k, v in ((row or {}).get("players_points") or {}).items()}
    out, live, exp, var = [], 0.0, 0.0, 0.0
    for i, pid in enumerate((row or {}).get("starters") or []):
        pid = str(pid)
        p = (players or {}).get(pid) or {}
        name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        slot = slots[i] if i < len(slots) else ""
        if not name or pid == "0":
            out.append({"slot": slot, "player": None, "points": 0.0, "projected": 0.0, "state": "empty", "clock": ""})
            continue
        team = canonical("nfl", str(p.get("team") or "").upper()) if p.get("team") else ""
        g = (game or {}).get(team) or {"state": "pre", "frac_left": 1.0, "clock": ""}
        so_far = pts.get(pid, 0.0)
        mean, sd = float(proj.get(name) or 0.0), float(sds.get(name) or 0.0)
        if g["state"] == "final":
            final, v = so_far, 0.0
        elif g["state"] == "live":
            final, v = so_far + mean * g["frac_left"], sd * sd * g["frac_left"]
        else:
            final, v = mean, sd * sd
        live += so_far
        exp += final
        var += v
        out.append({"slot": slot, "player": name, "position": str(p.get("position") or "").upper(),
                    "team": team or None, "points": round(so_far, 2), "projected": round(final, 1),
                    "state": g["state"], "clock": g.get("clock") or ""})
    return {"players": out, "points": round(live, 2), "projected": round(exp, 1), "variance": var}


def matchup(board_rows: list, my_rid, players: dict, slots: list, proj: dict, sds: dict, game: dict) -> dict | None:
    """The live head-to-head off Sleeper's board, or None before a game of
    either lineup has kicked off (the projection card says it then)."""
    rows = {int(r["roster_id"]): r for r in board_rows or [] if r.get("roster_id") is not None}
    try:
        mine = rows.get(int(my_rid))
    except (TypeError, ValueError):
        mine = None
    if not mine or mine.get("matchup_id") is None:
        return None
    theirs = next((r for rid, r in rows.items() if rid != int(my_rid)
                   and r.get("matchup_id") == mine.get("matchup_id")), None)
    me = side(mine, players, slots, proj, sds, game)
    them = side(theirs, players, slots, proj, sds, game) if theirs else None
    every = me["players"] + ((them or {}).get("players") or [])
    started = [p for p in every if p.get("state") in ("live", "final")]
    if not started:
        return None
    sd = math.sqrt(me["variance"] + ((them or {}).get("variance") or 0.0))
    margin = me["projected"] - ((them or {}).get("projected") or 0.0)
    if them is None:
        wp = None
    elif sd < 1.0:
        wp = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
    else:
        wp = round(_phi(margin / sd), 4)
    for s in (me, them):
        if s:
            s.pop("variance", None)
    return {"me": me, "them": them, "win_prob": wp,
            "in_progress": any(p.get("state") == "live" for p in every),
            "done": all(p.get("state") in ("final", "empty") for p in every),
            "opponent_roster_id": int(theirs["roster_id"]) if theirs else None}
