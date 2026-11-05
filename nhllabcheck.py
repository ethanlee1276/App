#!/usr/bin/env python3
"""The NHL lab's changes, re-measured on the box's own stored games.
Read-only: it opens the history file read-only and writes nothing.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 nhllabcheck.py

You, 2026-11-05: "Go through nfl and CFB and nba and mlb and wnba and nhl
... make sure we have all the tools and data we can be using like how we
just added for nba". The lab (docs/NHL_LAB.md) replayed three seasons of
every NHL box score through engine/nhl/model, fitted on one season and
judged on the other, and changed what measured:

* the memories: a skater's rate reads a 30-game half-life (was 12), his
  ice time 3 (was 6), from up to 60 games (was 40); a team's strength a
  40-game half-life (was 25), shrunk by 100 games of average (was 15);
* back-to-backs: the tired side's goals 0.93 of the model's (was 0.97),
  its rested opponent's 1.04 (was nothing), and every skater's number by
  the measured factor (model.B2B_SKATER, B2B_SKATER_OPP);
* the goalie: a probable starter who started last night is not the
  probable starter — his team's backup starts 78% of those nights.

This replays the box's stored NHL games the same way, this season's
included (the lab's files stopped at last April), three ways:

1. SKATERS: every skater-game on every other date, priced walk-forward from
   his games before it (neutral opponent, the league's rates before that
   date, as engine/nhl/backtest walks), with the constants BEFORE the lab
   and as shipped, at the lab's ladder of lines; log loss by market.
2. BACK-TO-BACKS on the box's games: actual ÷ projected for a skater whose
   team is on its second night, one whose opponent is, and both, each
   against the rested games' ratio — the factors the model ships, read
   again on data the lab never had.
3. THE GAME LINES: moneyline, puck line and a totals ladder, the team
   constants before against after, and the goalie rule's two rates.

The last lines say whether the box's games agree with the lab. Under a
few hundred games a part says it has too few rather than guess.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.nhl import model as M          # noqa: E402

#: The constants as they stood before the lab, for the side-by-side.
BEFORE = {"RATE_HALF_LIFE": 12.0, "TOI_HALF_LIFE": 6.0, "RECENT_GAMES": 40, "TEAM_HALF_LIFE": 25.0,
          "TEAM_PRIOR_GAMES": 15.0, "B2B_FACTOR": 0.97, "B2B_OPP_FACTOR": 1.0,
          "B2B_SKATER": {}, "B2B_SKATER_OPP": {}}
SHIPPED = {k: getattr(M, k) for k in BEFORE}
MARKETS = ("sog", "points", "goals", "assists", "blocks")
LADDER = {"sog": (0.5, 1.5, 2.5, 3.5, 4.5), "blocks": (0.5, 1.5, 2.5), "points": (0.5, 1.5),
          "assists": (0.5,), "goals": (0.5,)}
TOTALS = (4.5, 5.5, 6.5, 7.5)
MIN_HISTORY = 5
MIN_GAMES = 300


def _ro(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _day_before(d: str) -> str:
    return (dt.date.fromisoformat(d[:10]) - dt.timedelta(days=1)).isoformat()


def _logs(conn) -> dict:
    """{player: {"position", "games": [oldest first]}} with team, opponent
    and every stored stat per game."""
    out: dict = {}
    q = ("SELECT player, team, opponent, position, period, market, value, season FROM player_game_logs "
         "WHERE sport='nhl'")
    for player, team, opp, pos, day, market, value, season in conn.execute(q):
        p = out.setdefault(player, {"position": pos, "games": {}})
        g = p["games"].setdefault(day, {"date": str(day)[:10], "team": team, "opponent": opp,
                                        "season": season})
        g[market] = float(value or 0)
    for p in out.values():
        p["games"] = sorted(p["games"].values(), key=lambda g: g["date"])
    return out


def _schedule(conn) -> tuple[list, dict]:
    games, played = [], defaultdict(set)
    q = ("SELECT home, away, home_score, away_score, extra, period, season FROM games WHERE sport='nhl' "
         "AND home_score IS NOT NULL ORDER BY period")
    for home, away, hs, as_, extra, day, season in conn.execute(q):
        try:
            ex = json.loads(extra or "{}")
        except ValueError:
            ex = {}
        d = str(day)[:10]
        games.append({"date": d, "home": home, "away": away, "hs": float(hs), "as": float(as_ or 0),
                      "hsog": ex.get("home_sog"), "asog": ex.get("away_sog"), "season": int(season or 0)})
        played[home].add(d)
        played[away].add(d)
    return games, played


def _apply(cfg: dict) -> None:
    for k, v in cfg.items():
        setattr(M, k, v)


def _ll(p: float, y: int) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def skaters(players: dict, played: dict, cfg: dict, every: int = 2) -> tuple[dict, dict]:
    """({market: [log loss sum, n]}, {(market, cat): [actual, projected-before-rest, n]})."""
    from engine.nhl.backtest import _league_by_date
    _apply(cfg)
    league_on = _league_by_date(players)
    dates = sorted({g["date"] for p in players.values() for g in p["games"]})
    keep = set(dates[::every])
    ll: dict = defaultdict(lambda: [0.0, 0])
    rest: dict = defaultdict(lambda: [0.0, 0.0, 0])
    for p in players.values():
        if p["position"] == "G":
            continue
        games = p["games"]
        for i in range(MIN_HISTORY, len(games)):
            g = games[i]
            if g["date"] not in keep or g.get("toi", 0) <= 0:
                continue
            prior = [x for x in games[:i][::-1] if x.get("toi", 0) > 0][:M.RECENT_GAMES]
            if len(prior) < 3:
                continue
            view = {"position": "D" if p["position"] == "D" else "F", "games": prior}
            me = _day_before(g["date"]) in played.get(g["team"], ())
            them = _day_before(g["date"]) in played.get(g.get("opponent"), ())
            cat = "both" if me and them else "me" if me else "opp" if them else "rested"
            label = M.rest_of(me, them)
            for mk in MARKETS:
                market = "anytime_goal" if mk == "goals" else mk
                proj = M.skater_projection(view, market, league_on[g["date"]], {}, "", rest=label)
                if not proj:
                    continue
                actual = g.get(mk, 0.0)
                for line in LADDER[mk]:
                    q = M.skater_prob(proj, market, line, "OVER")
                    acc = ll[mk]
                    acc[0] += _ll(q, 1 if actual > line else 0)
                    acc[1] += 1
                r = rest[(mk, cat)]
                r[0] += actual
                r[1] += proj["mean"] / (proj.get("rest_factor") or 1.0)
                r[2] += 1
    return ll, rest


def _profiles(games: list, date: str) -> dict:
    """model.team_profiles as of ``date``: each team's games before it,
    newest season and the older ones profiled apart and blended."""
    by: dict = defaultdict(list)
    for g in games:
        if g["date"] >= date:
            break
        by[g["home"]].append((g["season"], (g["hs"], g["as"], g["hsog"], g["asog"])))
        by[g["away"]].append((g["season"], (g["as"], g["hs"], g["asog"], g["hsog"])))
    out = {}
    for team, rows in by.items():
        newest = max(s for s, _ in rows)
        cur = [r for s, r in reversed(rows) if s == newest]
        old = [r for s, r in reversed(rows) if s != newest]
        if not old or not cur:
            prof = M._profile(cur or old)
            prof["gp_season"] = len(cur)
            out[team] = prof
            continue
        a, b, w = M._profile(cur), M._profile(old), M.season_weight(len(cur))
        prof = {k: (w * a[k] + (1 - w) * b[k]) if a[k] is not None and b[k] is not None
                else (a[k] if a[k] is not None else b[k]) for k in ("gf", "ga", "sog_for", "sog_against")}
        prof["n"], prof["gp_season"] = a["n"] + b["n"], len(cur)
        out[team] = prof
    return out


def game_lines(games: list, played: dict, cfg: dict) -> dict:
    _apply(cfg)
    acc = defaultdict(float)
    cache: dict = {}
    for g in games:
        if g["date"] not in cache:
            cache.clear()
            cache[g["date"]] = _profiles(games, g["date"])
        teams = cache[g["date"]]
        if g["home"] not in teams or g["away"] not in teams:
            continue
        rested = {g["home"]: _day_before(g["date"]) not in played[g["home"]],
                  g["away"]: _day_before(g["date"]) not in played[g["away"]]}
        lam = M.team_lambdas(teams, g["home"], g["away"], rested=rested)
        if not lam:
            continue
        pr = M.game_probs(*lam)
        acc["n"] += 1
        acc["ml"] += _ll(pr["home_ml"], 1 if g["hs"] > g["as"] else 0)
        acc["pl"] += (_ll(pr["home_-1.5"], 1 if g["hs"] - g["as"] >= 2 else 0)
                      + _ll(pr["away_-1.5"], 1 if g["as"] - g["hs"] >= 2 else 0)) / 2
        for line in TOTALS:
            acc["tot"] += _ll(M.total_over(pr, line), 1 if g["hs"] + g["as"] > line else 0) / len(TOTALS)
    n = acc["n"] or 1
    return {"n": int(acc["n"]), "ml": acc["ml"] / n, "pl": acc["pl"] / n, "tot": acc["tot"] / n,
            "all": (acc["ml"] + acc["pl"] + acc["tot"]) / (3 * n)}


def goalies(players: dict, played: dict) -> dict:
    """How often the probable starter who started last night starts again,
    and how often model.backup_goalie's choice starts instead."""
    starts: dict = defaultdict(list)
    for name, p in players.items():
        if p["position"] != "G":
            continue
        for g in p["games"]:
            if g.get("started"):
                starts[g["team"]].append((g["date"], name))
    tally = {"again": [0, 0], "backup": [0, 0]}
    for team, rows in starts.items():
        rows.sort()
        for k in range(M.STARTER_WINDOW, len(rows)):
            date, who = rows[k]
            recent = [n for _d, n in rows[k - M.STARTER_WINDOW:k]]
            prob = max(set(recent), key=recent.count)
            if rows[k - 1][0] != _day_before(date) or rows[k - 1][1] != prob:
                continue
            view = {n: {"team": team, "position": "G",
                        "games": [{"date": d, "started": True} for d, nn in rows[:k] if nn == n]}
                    for n in set(nn for _d, nn in rows[:k])}
            backup = M.backup_goalie(view, team, prob)
            tally["again"][0] += prob == who
            tally["again"][1] += 1
            tally["backup"][0] += backup == who
            tally["backup"][1] += 1
    return tally


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=None, help="the history file (default: the box's)")
    ap.add_argument("--every", type=int, default=2, help="price every Nth date (default 2)")
    args = ap.parse_args(argv)
    from engine.db import DEFAULT_DB
    conn = _ro(args.db or DEFAULT_DB)
    try:
        players = _logs(conn)
        games, played = _schedule(conn)
    finally:
        conn.close()
    seasons = sorted({g["season"] for g in games})
    print(f"NHL on the box: {len(games)} finals over seasons {seasons}, "
          f"{sum(1 for p in players.values() if p['position'] != 'G')} skaters")
    if len(games) < MIN_GAMES:
        print(f"Fewer than {MIN_GAMES} finals stored: too few to read.")
        return 1
    verdicts = []
    try:
        print("\n1. SKATERS — ladder log loss, the constants before the lab against as shipped")
        before, _ = skaters(players, played, BEFORE, args.every)
        after, rest = skaters(players, played, SHIPPED, args.every)
        better = 0
        for mk in MARKETS:
            b, a = before[mk], after[mk]
            if not b[1]:
                continue
            lb, la = b[0] / b[1], a[0] / a[1]
            better += la < lb
            print(f"   {mk:8} before {lb:.5f}  after {la:.5f}  ({la - lb:+.5f}, {a[1]} priced)")
        verdicts.append(f"skaters: the shipped constants better in {better} of {len(MARKETS)} markets")
        print("\n2. BACK-TO-BACKS — actual ÷ projected against the rested games' ratio (shipped factor)")
        agree = total = 0
        for mk in MARKETS:
            base = rest[(mk, "rested")]
            if not base[1]:
                continue
            r0 = base[0] / base[1]
            parts = []
            for cat, ship in (("me", M.B2B_SKATER.get(mk, 1.0)), ("opp", M.B2B_SKATER_OPP.get(mk, 1.0)),
                              ("both", 1.0)):
                c = rest[(mk, cat)]
                if not c[1]:
                    continue
                ratio = c[0] / c[1] / r0
                parts.append(f"{cat} {ratio:.3f} (ships {ship:.3f}, n={c[2]})")
                if cat != "both":
                    total += 1
                    agree += (ratio - 1) * (ship - 1) > 0
            print(f"   {mk:8} " + " | ".join(parts))
        verdicts.append(f"back-to-backs: the box's games lean the shipped way in {agree} of {total}")
        print("\n3. GAME LINES — log loss, the team constants before against as shipped")
        gb, ga = game_lines(games, played, BEFORE), game_lines(games, played, SHIPPED)
        for k in ("ml", "pl", "tot", "all"):
            print(f"   {k:4} before {gb[k]:.5f}  after {ga[k]:.5f}  ({ga[k] - gb[k]:+.5f})")
        print(f"   {ga['n']} games priced")
        verdicts.append(f"game lines: {'better' if ga['all'] < gb['all'] else 'worse'} after "
                        f"({ga['all'] - gb['all']:+.5f} a line)")
        gt = goalies(players, played)
        a, b = gt["again"], gt["backup"]
        if a[1]:
            print(f"\n   The probable starter who started last night started again {a[0]}/{a[1]} = "
                  f"{a[0] / a[1]:.0%} (the lab: 9%); the backup named started {b[0]}/{b[1]} = "
                  f"{b[0] / b[1]:.0%} (the lab: 78%)")
            verdicts.append(f"goalies: backup named right {b[0] / b[1]:.0%} of {b[1]} nights")
    finally:
        _apply(SHIPPED)
    print("\n" + "\n".join(verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
