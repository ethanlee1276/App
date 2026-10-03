"""Walk-forward for the NHL props — the measurement that opens each Most
Likely shelf (engine.rankfit).

The live model, not a copy of it: each game a player played is projected
by `model.skater_projection` (or `goalie_projection`) from ONLY the games
before it, then settled against what he did. Neutral opponent, like every
other sport's walk (engine/logwalk, engine/mlb/backtest) — this measures
the form, ice-time and count layers; the opponent tilt is judged on top by
the record. The line is a naive one off his own trailing games (the same
idea as logwalk's `_naive_line`), because a ranking AUC asks whether the
model's chance orders the outcomes, not whether it beat a book.

NOTHING FROM THE FUTURE, the league included: the position priors a
player is shrunk toward are the league's totals from games BEFORE the
date being projected (`_league_by_date`), not the whole sample's — a
pooled prior taken from all three seasons moved a first-week projection
with games played months later, and the test caught it.
"""
from __future__ import annotations

import math

from ..backtest import SettledProp, evaluate, BacktestReport
from . import model as M

#: Games of his own before a game is projected.
MIN_HISTORY = 5


def _naive_line(market: str, prior: list[float]) -> float:
    """A book-shaped number off his last eight games: the half-point under
    his average (0.5 at the least). Every goal market is hung at 0.5."""
    if market in ("anytime_goal", "goals"):
        return 0.5
    recent = prior[:8]
    return math.floor(sum(recent) / len(recent)) + 0.5


def _all_games(conn, seasons=None) -> dict:
    """{player: {"position", "games": [game dicts, OLDEST first]}} — every
    game, unsliced (player_games keeps the newest RECENT_GAMES only)."""
    q = ("SELECT player, position, period, team, market, value FROM player_game_logs "
         "WHERE sport='nhl'")
    args: list = []
    if seasons:
        q += f" AND season IN ({','.join('?' * len(seasons))})"
        args += list(seasons)
    out: dict = {}
    for player, pos, day, team, market, value in conn.execute(q, args):
        p = out.setdefault(player, {"position": pos, "games": {}})
        g = p["games"].setdefault(day, {"date": day, "team": team})
        g[market] = float(value or 0)
    for p in out.values():
        p["games"] = sorted(p["games"].values(), key=lambda g: g["date"])
    return out


_RATE_STATS = ("sog", "points", "goals", "assists", "blocks")


def _league_by_date(players: dict) -> dict:
    """{date: league rates from every game strictly before that date} —
    the same shape `model.league_rates` returns."""
    by_day: dict = {}
    for p in players.values():
        grp = "G" if p["position"] == "G" else ("D" if p["position"] == "D" else "F")
        for g in p["games"]:
            by_day.setdefault(g["date"], []).append((grp, g))
    tot: dict = {}
    out: dict = {}
    for day in sorted(by_day):
        snap = {grp: {s: t.get(s, 0.0) / max(t["toi"], 1.0) * 60.0 for s in _RATE_STATS}
                for grp, t in tot.items() if grp != "G"}
        gk = tot.get("G") or {}
        snap["sv"] = (gk["saves"] / gk["shots_against"]) if gk.get("shots_against") else M.LEAGUE_SV
        out[day] = snap
        for grp, g in by_day[day]:
            t = tot.setdefault(grp, {"toi": 0.0})
            t["toi"] += g.get("toi", 0.0)
            for s in _RATE_STATS + ("saves", "shots_against"):
                t[s] = t.get(s, 0.0) + g.get(s, 0.0)
    return out


def settled(conn, market: str, seasons=None, players: dict | None = None) -> list[SettledProp]:
    players = players if players is not None else _all_games(conn, seasons)
    league_on = _league_by_date(players)
    goalie = market in M.GOALIE_MARKETS
    stat = "saves" if goalie else M._STAT[market]
    out: list[SettledProp] = []
    for name, p in players.items():
        if (p["position"] == "G") != goalie:
            continue
        games = p["games"]
        for i in range(MIN_HISTORY, len(games)):
            g = games[i]
            if goalie:
                if not g.get("started"):
                    continue
            elif g.get("toi", 0) <= 0:
                continue
            prior = games[:i][::-1][:M.RECENT_GAMES]
            league = league_on[g["date"]]
            view = {"position": p["position"], "games": prior, "team": g.get("team")}
            if goalie:
                # Shots against from his OWN recent games (no team table in a
                # walk), save rate exactly as the live projection shrinks it.
                faced = [x.get("shots_against", 0) for x in prior if x.get("shots_against", 0) > 0][:15]
                if len(faced) < 3:
                    continue
                teams = {g.get("team"): {"sog_against": sum(faced) / len(faced), "n": len(faced)}}
                proj = M.goalie_projection(view, league, teams, g.get("team"), "")
            else:
                proj = M.skater_projection(view, market, league, {}, "")
            if proj is None:
                continue
            vals = [x.get(stat, 0.0) for x in prior]
            line = _naive_line(market, vals)
            p_over = M.goalie_prob(proj, line, "OVER") if goalie else M.skater_prob(proj, market, line, "OVER")
            actual = g.get(stat, 0.0)
            if market == "anytime_goal":
                actual = 1.0 if actual >= 1 else 0.0
            out.append(SettledProp(player=name, market=market, line=line, odds=-110,
                                   hit_prob=p_over, raw_prob=p_over, projection=proj["mean"],
                                   actual=actual, side="OVER", basis="naive"))
    return out


def walk(conn, market: str, seasons=None, players: dict | None = None) -> BacktestReport:
    s = settled(conn, market, seasons=seasons, players=players)
    report = evaluate(s)
    report.total_priced = len(s)
    return report
