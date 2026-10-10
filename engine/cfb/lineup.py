"""College's teammate-out and new-quarterback steps: measured on college games, applied like the NFL's.

    sudo -u qellys python3 -m engine.cfb.lineup              # measure every stored season, save what passes
    sudo -u qellys python3 -m engine.cfb.lineup --dry-run    # measure and print, save nothing

Ethan, 2026-10-10: "do the teammate-out and new QB stuff for college now
... we want the same methods and tools and models as we use for nfl."

The NFL's projection has a lineup step (engine/projection): a teammate out
at his position (engine/teammates, measured by engine/matefit) and his
starting quarterback out (engine/qbchange, measured by engine/qbfit). Both
ran on college at x1.00 — the college build never set a depth order or a
priced QB change on its games — because both were measured on NFL games,
with NFL targets and snap counts, and college logs neither.

WHAT COLLEGE HAS, AND HOW EACH PIECE READS IT:

  * THE DEPTH ORDER at WR, TE and RB: the top three by volume per game over
    the team's earlier games this season — CATCHES for a receiver or tight
    end, carries plus catches for a back. Never called targets: college
    logs catches, and a catch-ranked order is said as one.
  * A TEAMMATE OUT: in history, a ranked teammate with no row in a game his
    team played; on the board, one ESPN's college injury board rules out or
    every book stopped pricing (engine/pricedplayers). The case is the
    NFL's (matefit.case_for): ranked above or below him, just out ("new")
    or already out ("cont").
  * THE STARTER and his REPLACEMENT: qbfit's reading on college passing —
    the team's leading passer in attempts over earlier games with two or
    more starts; out when he threw no pass. The replacement's TIER is read
    from passes he threw before that game (this season and last): similar
    at 50+ attempts and 90%+ of the starter's yards an attempt, else a
    downgrade.

THE RULE IS THE NFL'S, UNCHANGED (engine/qbfit.shipped): a multiplier is
applied only where it sits two standard errors from 1.0 and at least three
seasons point the same way; anything else is shown on the card and moves
nothing. The fit saves what passes (cfb_lineup.json) and the build reads
it; with no store, college runs at x1.00 exactly as before, and its card
says college has not been measured. Runs weekly with the deep fitters.

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import defaultdict
from pathlib import Path

from .. import modelstate
from ..matefit import case_for
from ..qbfit import MIN_ATTEMPTS, SIMILAR_RATIO, measure, shipped

GROUPS = ("WR", "TE", "RB")
#: The markets each group is measured on: (market, form floor). The NFL's
#: (matefit.MARKETS), plus a back's carries — a college board market.
MARKETS = {
    "WR": [("rec_yds", 15.0), ("receptions", 1.5), ("anytime_td", 0.0)],
    "TE": [("rec_yds", 15.0), ("receptions", 1.5), ("anytime_td", 0.0)],
    "RB": [("rush_yds", 15.0), ("rush_att", 5.0), ("receptions", 1.5), ("rec_yds", 12.0),
           ("anytime_td", 0.0)],
}
READ = ("receptions", "rec_yds", "rush_yds", "rush_att", "anytime_td", "pass_att", "pass_yds")
#: The team's fourth game on: three earlier games behind every order.
FIRST_GAME = 4
MIN_GAMES = 3
TOP = 3
#: The roster's positions, as college's touchdown board reads them.
ROLES = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}
FIRST_SEASON = 2022
STORE_VERSION = 1
#: The depth order's own word on the card: college ranks on catches.
BASIS = "cfb"


# --- reading college's logs -------------------------------------------------------
def _role(pos: str, totals: dict) -> str:
    """The roster's position where it names one, else the usage mix (three
    or more passes a game is a QB; a heavy runner a back; anyone else who
    catches a WR) — engine/cfb/tds.role_of's reading, with passers named."""
    seen = ROLES.get(str(pos or "").strip().upper())
    if seen:
        return seen
    if totals.get("pass_att", 0.0) >= 3.0 * max(1, totals.get("_games", 1)):
        return "QB"
    if totals.get("rush_att", 0.0) >= 2.0 and totals.get("rush_att", 0.0) >= totals.get("receptions", 0.0) * 1.5:
        return "RB"
    return "WR"


def season_games(conn, season: int, teams=None) -> tuple[dict, dict]:
    """(players, team_days) for one college season.

    ``players``: {team: {name: {"role", "games": {day: {market: value}}}}}
    ``team_days``: {team: [day, ...]} in order — the days the team has a
    logged game. A college game's ``period`` IS its date (engine/sources/
    cfbfastr), so days sort as dates."""
    q = ("SELECT period, team, player, position, market, value FROM player_game_logs "
         f"WHERE sport='cfb' AND season=? AND market IN ({','.join('?' * len(READ))})")
    args: list = [int(season), *READ]
    if teams:
        teams = sorted({t for t in teams if t})
        q += f" AND team IN ({','.join('?' * len(teams))})"
        args += teams
    raw: dict = defaultdict(lambda: {"pos": "", "games": defaultdict(dict)})
    days: dict = defaultdict(set)
    for r in conn.execute(q, args):
        period, team, player, pos, market, value = (r[0], r[1], r[2], r[3], r[4], r[5])
        day = str(period or "")
        if not day or not team or not player:
            continue
        cell = raw[(team, player)]
        cell["pos"] = cell["pos"] or str(pos or "")
        cell["games"][day][market] = float(value or 0.0)
        days[team].add(day)
    players: dict = defaultdict(dict)
    for (team, name), cell in raw.items():
        totals: dict = defaultdict(float)
        for g in cell["games"].values():
            for m, v in g.items():
                totals[m] += v
        totals["_games"] = len(cell["games"])
        players[team][name] = {"role": _role(cell["pos"], totals), "games": dict(cell["games"])}
    return dict(players), {t: sorted(d) for t, d in days.items()}


def volume(game: dict, pos: str) -> float:
    """What the depth order ranks on: catches, plus carries for a back."""
    return game.get("receptions", 0.0) + (game.get("rush_att", 0.0) if pos == "RB" else 0.0)


def ranked(roster: dict, pos: str, prior_days: list, min_games: int = MIN_GAMES) -> list:
    """[(name, per-game volume, games, last game index)] best first — one
    team's players (``roster``: {name: player}) at this position with
    ``min_games`` among ``prior_days``, top TOP. The index is 1-based in
    ``prior_days``, the shape matefit.case_for reads."""
    idx = {d: i + 1 for i, d in enumerate(prior_days)}
    out = []
    for name, p in roster.items():
        if p["role"] != pos:
            continue
        played = [d for d in p["games"] if d in idx]
        if len(played) < min_games:
            continue
        out.append((name, sum(volume(p["games"][d], pos) for d in played) / len(played), len(played),
                    max(idx[d] for d in played)))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out[:TOP]


def _expected(values: list) -> float:
    """His own form over his earlier games — the projection's starting point
    (engine/form.compute_form), as engine/matefit measures it."""
    from ..form import compute_form
    from ..models import GameLog
    logs = [GameLog(week=len(values) - j, opponent="", value=v) for j, v in enumerate(reversed(values))]
    return compute_form(logs, sum(values) / len(values), None).mean


# --- the measurement --------------------------------------------------------------
def mate_samples(conn, seasons) -> list[dict]:
    """[{"season", "m", "g", "e", "y", "tier"}] — tier is the matefit case
    (above/below, new/cont), None with every ranked teammate playing."""
    out = []
    for season in seasons:
        players, team_days = season_games(conn, season)
        for team, days in team_days.items():
            roster = players.get(team) or {}
            for i in range(FIRST_GAME - 1, len(days)):
                day, prior = days[i], days[:i]
                for pos in GROUPS:
                    order = ranked(roster, pos, prior)
                    playing = {o[0] for o in order if day in roster[o[0]]["games"]}
                    for name, _v, _n, _l in order:
                        games = roster[name]["games"]
                        if day not in games:
                            continue
                        case = case_for(order, name, playing, i)
                        before = [d for d in prior if d in games]
                        for m, floor in MARKETS[pos]:
                            vals = [games[d].get(m, 0.0) for d in before]
                            e = _expected(vals)
                            if e < floor or e <= 0:
                                continue
                            out.append({"season": season, "m": m, "g": pos, "e": e,
                                        "y": games[day].get(m, 0.0), "tier": case})
    return out


def passing(players: dict) -> dict:
    """{name: [(day, attempts, yards)]} for every passer in a season."""
    out: dict = defaultdict(list)
    for name, p in ((n, p) for roster in players.values() for n, p in roster.items()):
        for day, g in p["games"].items():
            if g.get("pass_att", 0.0) > 0:
                out[name].append((day, g["pass_att"], g.get("pass_yds", 0.0)))
    return out


def tier_of(before: dict, starter: str, replacement: str) -> tuple:
    """(tier, starter ypa, replacement ypa or None) — engine/qbfit.tier_of on
    college passing: similar at MIN_ATTEMPTS+ earlier attempts and
    SIMILAR_RATIO+ of the starter's yards an attempt, else a downgrade."""
    sa, sy = before.get(starter, (0.0, 0.0))
    ra, ry = before.get(replacement, (0.0, 0.0))
    s_ypa = sy / sa if sa else None
    r_ypa = ry / ra if ra >= MIN_ATTEMPTS else None
    if s_ypa and r_ypa and r_ypa >= SIMILAR_RATIO * s_ypa:
        return "similar", s_ypa, r_ypa
    return "downgrade", s_ypa, r_ypa


def passing_before(this: dict, last: dict, day: str) -> dict:
    """{name: (attempts, yards)} over last season and this one before ``day``."""
    out: dict = defaultdict(lambda: [0.0, 0.0])
    for name, rows in (last or {}).items():
        for _d, a, y in rows:
            out[name][0] += a
            out[name][1] += y
    for name, rows in (this or {}).items():
        for d, a, y in rows:
            if d < day:
                out[name][0] += a
                out[name][1] += y
    return {k: tuple(v) for k, v in out.items()}


def passers_on(roster: dict, day: str) -> dict:
    """{name: attempts} for one team's passers on ``day``."""
    return {name: p["games"][day].get("pass_att", 0.0) for name, p in roster.items()
            if day in p["games"] and p["games"][day].get("pass_att", 0.0) > 0}


def starter_before(roster: dict, prior: list) -> str | None:
    """The established starter going into a game: the team's leading passer
    in attempts over ``prior``, with two or more starts (games he led the
    team's attempts in); None without one."""
    att, starts = defaultdict(float), defaultdict(int)
    for d in prior:
        qbs = passers_on(roster, d)
        for name, a in qbs.items():
            att[name] += a
        if qbs:
            starts[max(qbs, key=qbs.get)] += 1
    if not att:
        return None
    s = max(att, key=att.get)
    return s if starts[s] >= 2 else None


def qb_samples(conn, seasons) -> list[dict]:
    """[{"season", "m", "g", "e", "y", "tier"}] — tier None in a game with
    the usual starter, else the replacement's tier (engine/qbfit.samples on
    college games)."""
    out = []
    last_passing: dict = {}
    for season in sorted(seasons):
        players, team_days = season_games(conn, season)
        this_passing = passing(players)
        for team, days in team_days.items():
            roster = players.get(team) or {}
            for i in range(FIRST_GAME - 1, len(days)):
                day, prior = days[i], days[:i]
                starter = starter_before(roster, prior)
                if not starter:
                    continue
                now = passers_on(roster, day)
                if not now:
                    continue                # no passer logged: a hole in the feed, not a change
                tier = None
                if starter not in now:
                    rep = max(now, key=now.get)
                    tier = tier_of(passing_before(this_passing, last_passing, day), starter, rep)[0]
                for pos in GROUPS:
                    for name, _v, _n, _l in ranked(roster, pos, prior):
                        games = roster[name]["games"]
                        if day not in games:
                            continue
                        before = [d for d in prior if d in games]
                        for m, floor in MARKETS[pos]:
                            e = sum(games[d].get(m, 0.0) for d in before) / len(before)
                            if e < floor or (m == "anytime_td" and e <= 0):
                                continue
                            out.append({"season": season, "m": m, "g": pos, "e": e,
                                        "y": games[day].get(m, 0.0), "tier": tier})
        last_passing = this_passing
    return out


def stored_seasons(conn) -> list:
    return [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT season FROM player_game_logs WHERE sport='cfb' AND season>=? ORDER BY season",
        (FIRST_SEASON,))]


def fit(conn, seasons=None) -> dict:
    """{"mates": measure(...), "qb": measure(...), "seasons"} — and what
    passes the NFL's rule in each (``adopt_mates``, ``adopt_qb``)."""
    seasons = list(seasons or stored_seasons(conn))
    mates = measure(mate_samples(conn, seasons))
    qb = measure(qb_samples(conn, seasons))
    return {"seasons": seasons, "mates": mates, "qb": qb,
            "adopt_mates": shipped(mates), "adopt_qb": shipped(qb)}


# --- the store ------------------------------------------------------------------
def _store() -> Path:
    return Path(modelstate.path("cfb_lineup.json"))


def save(res: dict, path=None) -> None:
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    key = lambda k: "|".join(str(x) for x in k)                     # noqa: E731
    blob = {"version": STORE_VERSION, "seasons": res.get("seasons") or [],
            "mates": {key(k): v for k, v in (res.get("adopt_mates") or {}).items()},
            "qb": {key(k): v for k, v in (res.get("adopt_qb") or {}).items()},
            "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    tmp.replace(p)
    _CACHE.clear()


_CACHE: dict = {}


def _load() -> dict:
    """The store, re-read when it changes (the launcher is long-lived and
    the weekly refit writes from a child); {} without a usable one."""
    p = _store()
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        stamp = (str(p), None)
    if _CACHE.get("stamp") != stamp:
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            blob = {}
        _CACHE["stamp"] = stamp
        _CACHE["blob"] = blob if blob.get("version") == STORE_VERSION else {}
    return _CACHE["blob"]


def measured() -> bool:
    """Has college been measured (a store exists, whatever it adopted)?"""
    return bool(_load())


def mate_table() -> dict:
    """{(market, group, case): multiplier} — the shape engine/teammates reads."""
    return {tuple(k.split("|")): float(v) for k, v in (_load().get("mates") or {}).items()}


def qb_mult(market: str, position: str, tier) -> float:
    if not tier:
        return 1.0
    return float((_load().get("qb") or {}).get(f"{market}|{str(position or '').upper()}|{tier}", 1.0))


# --- the board: stamp tonight's games -------------------------------------------
def _norm(name: str) -> str:
    from ..sources.oddsapi import normalize_name
    return normalize_name(str(name or ""))


def depth(conn, season: int, teams, before_day: str) -> dict:
    """{"order": {"TEAM|POS": [[name, volume, games, last]]}, "last": {team: n}}
    over each team's games before ``before_day`` this season — the order
    the multipliers were measured on. From a team's second game, on the
    games so far (the NFL's early_min_games)."""
    players, team_days = season_games(conn, season, teams)
    order, last = {}, {}
    for team, days in team_days.items():
        prior = [d for d in days if d < str(before_day)[:10]]
        if not prior:
            continue
        last[team] = len(prior)
        need = max(1, min(MIN_GAMES, len(prior)))
        for pos in GROUPS:
            got = ranked(players.get(team) or {}, pos, prior, need)
            if got:
                order[f"{team}|{pos}"] = [[n, round(v, 2), g, lw] for n, v, g, lw in got]
    return {"order": order, "last": last, "players": players, "team_days": team_days}


def priced_qbs(slate) -> dict:
    """{team: [passers the books priced]} off the slate's real lines — the
    market's own statement of who starts, read BEFORE pricing so the change
    can move the number."""
    out: dict = {}
    for p in getattr(slate, "props", None) or []:
        if getattr(p, "market", "") != "pass_yds":
            continue
        if not any(str(getattr(l, "book", "") or "").lower() not in ("", "proxy") for l in p.lines or []):
            continue
        names = out.setdefault(p.team, [])
        if p.player not in names:
            names.append(p.player)
    return out


def attach(conn, slate, games: list, injuries: list, season: int, date: str) -> dict:
    """Stamp each slate game with ``lineup`` (engine/teammates.effect reads
    it) and ``qb_changes`` (engine/qbchange.effect reads it), both marked as
    college's so the projection applies college's own multipliers.
    Returns {"qb_changes": {team: change}, "outs": n, "orders": n}."""
    from ..injuries import RULED_OUT
    from ..teammates import MAYBE
    from . import qbchange as cq
    teams = {t for g in getattr(slate, "games", None) or [] for t in (g.home, g.away)}
    d = depth(conn, int(season), teams, date)
    out_by: dict = defaultdict(set)
    maybe_by: dict = defaultdict(set)
    for i in injuries or []:
        st = str(getattr(i, "status", "") or "").upper()
        if st in RULED_OUT:
            out_by[getattr(i, "team", "")].add(_norm(getattr(i, "player", "")))
        elif st in MAYBE:
            maybe_by[getattr(i, "team", "")].add(_norm(getattr(i, "player", "")))
    for g in games or []:
        for name in g.get("pulled_players") or []:
            for t in (g.get("home"), g.get("away")):
                out_by[t].add(_norm(name))       # matched only where he is on that team's order
    # The QB change, from the passers the books priced and ESPN's board.
    chs = cq.changes(cq.passers(conn, int(season), teams), injuries, priced_qbs(slate))
    this = passing(d["players"])
    last_players, _ = season_games(conn, int(season) - 1, teams) if chs else ({}, {})
    before = passing_before(this, passing(last_players), str(date)[:10]) if chs else {}
    for ch in chs.values():
        ch["league"] = "cfb"
        if ch.get("status") != "RETURNS" and ch.get("replacement"):
            tier, s_ypa, r_ypa = tier_of(before, ch["starter"], ch["replacement"])
            ch["tier"] = tier
            ch["starter_ypa"] = round(s_ypa, 1) if s_ypa else None
            ch["replacement_ypa"] = round(r_ypa, 1) if r_ypa else None
            ch["replacement_attempts"] = int((before.get(ch["replacement"]) or (0, 0))[0])
        else:
            ch["tier"] = None
    n_out = 0
    for g in getattr(slate, "games", None) or []:
        g.lineup = {}
        for t in (g.home, g.away):
            order = {pos: d["order"].get(f"{t}|{pos}") or [] for pos in GROUPS}
            names = {_norm(o[0]) for rows in order.values() for o in rows}
            outs = sorted(n for n in out_by.get(t, ()) if n in names)
            n_out += len(outs)
            g.lineup[t] = {"order": order, "out": outs,
                           "maybe": sorted(n for n in maybe_by.get(t, ()) if n in names),
                           "last": d["last"].get(t, 0), "basis": BASIS}
        g.qb_changes = {t: chs[t] for t in (g.home, g.away) if t in chs}
    return {"qb_changes": chs, "outs": n_out, "orders": len(d["order"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.cfb.lineup")
    ap.add_argument("--dry-run", action="store_true", help="measure and print, save nothing")
    ap.add_argument("--seasons", default="", help="e.g. 2022-2025 (default: every stored season from 2022)")
    a = ap.parse_args(argv)
    from .. import db
    conn = db.connect()
    seasons = None
    if a.seasons:
        lo, _, hi = a.seasons.partition("-")
        seasons = list(range(int(lo), int(hi or lo) + 1))
    res = fit(conn, seasons)
    print(f"=== CFB lineup steps, seasons {res['seasons']} (the NFL's rule: 2 SE from 1.0, 3+ seasons agree)")
    for title, cells, adopt in (("TEAMMATE OUT (catch-ranked depth)", res["mates"], res["adopt_mates"]),
                                ("STARTING QB OUT", res["qb"], res["adopt_qb"])):
        print(f"  {title}")
        for (m, g, t), r in sorted(cells.items()):
            per = " ".join(f"{s}:{x:.3f}" for s, x in r["per"].items())
            verdict = f"ADOPT ×{adopt[(m, g, t)]:.3f}" if (m, g, t) in adopt else "shown, not applied"
            print(f"    {m:<11}{g:<3}{t:<11} ×{r['mult']:.3f} ± {r['se']:.3f}  n {r['n']:<5} {per}   → {verdict}")
        if not cells:
            print("    nothing to measure")
    if not a.dry_run:
        save(res)
        print("saved; the next college build reads it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
