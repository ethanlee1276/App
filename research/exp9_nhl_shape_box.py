#!/usr/bin/env python3
"""EXP-009 — NHL skater props: a shape built from his ice time against the board's own count shape, at one centre.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp9_nhl_shape_box.py
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp9_nhl_shape_box.py --holdout

Backlog B19. The NHL board (engine/nhl/model.py, live since 2026-10-03)
projects a skater's count as a per-60 rate times his recent ice time and
prices it with a shape whose constants are plain priors, never fitted:
shots on goal and blocked shots a negative binomial as wide as his own
game-to-game variance, shrunk toward SOG_DISPERSION (1.25); points a
Poisson. EXP-008 asks the NBA question; this asks it for hockey: at the
board's own centre, does a shape built from his ice time price better?
Registry EXP-009.

THE DATA. The box's own box scores (history.db player_game_logs, sport
'nhl': ice time, shots on goal, points and blocked shots by game date),
read-only, skaters only, each filed under his newest position. Every game
in the table can feed a projection, as it feeds the live one. A game is
SCORED when it is a regular-season game (before April 15 of the season's
second year) he played, with at least MIN_HISTORY earlier games of his (the
NHL walk's floor), the board has a projection, and his ice time has not
moved more than ROLE_SWING over his last five games (the board passes
those props).

ONE CENTRE FOR BOTH: μ = the board's own projection
(engine/nhl/model.skater_projection, called unchanged) from his earlier
games, at a neutral opponent with no power-play step, the position priors
from every skater-game before the date: the NHL walk's
(engine/nhl/backtest.settled). The test is the shape alone.

  S  THE BOARD'S SHAPE: the projection's own count, model.nbinom_pmf at its
     mean and dispersion, unchanged.
  C  THE COMPOUND SHAPE: ice time T = his projected ice time times a ratio
     from the training player-games' own pool (actual over projected ice
     time, scaled to mean one, read at Q quantiles); the stat given T is a
     count with mean (μ over projected ice time) × T and variance PHI ×
     mean (engine/fieldcurve._count_pmf; PHI per stat by moments on
     training, given his actual ice time). Its mean is μ.
  N  DESCRIBED, DECIDING NOTHING: the board's count refitted, one spread
     per stat (variance PHI_N × μ, PHI_N by moments on training given
     only the projection). C can beat S for two reasons: its ice time, or
     a spread the board set too narrow or too wide (points are a Poisson
     there). C against N says which.

THE SCORE: CRPS on whole numbers (shots 0-15, points 0-6, blocks 0-10),
clustered by player-season. Described, deciding nothing: N, with N - S
and C - N and their intervals; each shape's Brier at the half below μ;
the fitted spreads beside the board's 1.25; and the spread of the
ice-time ratio.

THE SPLITS, from the complete seasons the table holds (a season with games
from April 1 of its second year): with two or more, TRAIN = every complete
season before the last, VALIDATE = the last before January 1, HOLD OUT =
the last from January 1. With one, TRAIN = its games before December 15,
VALIDATE = December 15 to February 9, HOLD OUT = February 10 on. The
season under way is never scored. Each part needs MIN_PART player-games.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-19). Three tests, C against S in
shots on goal, points and blocked shots, each held to 0.05 / 3: a test
ADVANCES only if its validation mean CRPS is below S's AND on the holdout
it is below S's with the upper end of its clustered 98.33% interval under
zero; right direction with that end over zero is INCONCLUSIVE; wrong
direction REJECTED. The holdout is read once, with ``--holdout``. An
ADVANCE moves nothing by itself: it goes to Ethan with C - N beside it,
and a change to the board's shape is then a paper test before it is
anything else. When C - N's holdout interval holds zero, the gain is the
refitted spread, not the ice time, and the simpler N is the shape that
paper test tries.

HOW STRICT THAT IS, tried on made-up leagues of 90 skaters
(tests/test_nhl_shape_lab.py; the box has about ten times that): where a
count comes from that night's ice time, C advanced in 9 of 30 stat tests
over ten leagues (shots 5 of 10, points 1, blocks 3); where it comes from
his mean whatever his ice time, with the board's own spreads, in 1 of 30.

Prior art: compound (mixed) count models; ice time as the driver of a
skater's counts is standard in hockey analytics. A new application to the
site's own pricing shape (novelty class 4).

Read-only on the database; writes nothing.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fieldcurve as FC                                   # noqa: E402
from engine.nhl import model as M                                     # noqa: E402
from engine.nhl.backtest import MIN_HISTORY                           # noqa: E402
from research import exp1_two_stage as E1                            # noqa: E402

STATS = ("sog", "points", "blocks")
GRID = {"sog": [float(t) for t in range(16)], "points": [float(t) for t in range(7)],
        "blocks": [float(t) for t in range(11)]}
MIN_PART = 300
Q = 25
ALPHA = 0.05 / 3
PLAYOFFS = "04-15"
COMPLETE = "04-01"


class Game:
    """One skater-game, as small as the 1 GB box needs it; it reads like
    the game dicts engine/nhl/model takes."""
    __slots__ = ("date", "season", "toi", "sog", "points", "blocks")

    def __init__(self, date: str, season: int):
        self.date, self.season = date, season
        self.toi = self.sog = self.points = self.blocks = 0.0

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        return getattr(self, key)


class Row:
    """One (scored skater-game, stat): the board's projection and what he did."""
    __slots__ = ("who", "s", "date", "stat", "y", "t", "mu", "disp", "toi")

    def __init__(self, who, s, date, stat, y, t, mu, disp, toi):
        self.who, self.s, self.date, self.stat = who, s, date, stat
        self.y, self.t, self.mu, self.disp, self.toi = y, t, mu, disp, toi


def open_db(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def skaters(conn) -> dict:
    """``{player: {"position", "games": [Game, oldest first]}}``, every
    skater-game the table holds, regular season and playoffs."""
    q = ("SELECT player, position, season, period, market, value FROM player_game_logs "
         "WHERE sport='nhl' AND market IN ('toi','sog','points','blocks')")
    out: dict = {}
    days: dict = {}
    for player, pos, season, date, market, value in conn.execute(q):
        if not player or not date or season is None or pos == "G":
            continue
        p = out.get(player)
        if p is None:
            p = out[player] = {"position": pos, "last": "", "by": {}}
        d = days.setdefault(str(date), str(date))
        g = p["by"].get(d)
        if g is None:
            g = p["by"][d] = Game(d, int(season))
        setattr(g, market, float(value or 0.0))
        if d >= p["last"]:
            p["last"], p["position"] = d, pos
    for p in out.values():
        p["games"] = sorted(p.pop("by").values(), key=lambda g: g.date)
        del p["last"]
    return out


def league_by_date(players: dict) -> dict:
    """``{date: {"F"|"D": {stat: per 60}}}`` from every skater-game strictly
    before the date: engine/nhl/backtest._league_by_date for these three
    stats."""
    by_day: dict = defaultdict(list)
    for p in players.values():
        grp = "D" if p["position"] == "D" else "F"
        for g in p["games"]:
            by_day[g.date].append((grp, g))
    tot: dict = {}
    out: dict = {}
    for day in sorted(by_day):
        out[day] = {grp: {s: t[s] / max(t["toi"], 1.0) * 60.0 for s in STATS} for grp, t in tot.items()}
        for grp, g in by_day[day]:
            t = tot.setdefault(grp, {"toi": 0.0, "sog": 0.0, "points": 0.0, "blocks": 0.0})
            t["toi"] += g.toi
            for s in STATS:
                t[s] += getattr(g, s)
    return out


def complete_seasons(players: dict) -> list[int]:
    last: dict = {}
    for p in players.values():
        for g in p["games"]:
            if g.date > last.get(g.season, ""):
                last[g.season] = g.date
    return sorted(s for s, d in last.items() if d >= f"{s + 1}-{COMPLETE}")


def rows_from(players: dict, league_on: dict, seasons) -> list:
    """One Row per (scored skater-game, stat), in THE DATA's order of refusals."""
    want = set(seasons)
    out = []
    for name, p in players.items():
        games = p["games"]
        for i in range(MIN_HISTORY, len(games)):
            g = games[i]
            if g.season not in want or g.toi <= 0 or g.date >= f"{g.season + 1}-{PLAYOFFS}":
                continue
            view = {"position": p["position"], "games": games[max(0, i - M.RECENT_GAMES):i][::-1]}
            projs = [M.skater_projection(view, stat, league_on[g.date], {}, "") for stat in STATS]
            if any(pr is None or pr["mean"] <= 0 for pr in projs) or projs[0]["toi_swing"] > M.ROLE_SWING:
                continue
            who = f"{name}|{g.season}"
            for stat, pr in zip(STATS, projs):
                out.append(Row(who, g.season, g.date, stat, getattr(g, stat), g.toi, pr["mean"], pr["disp"],
                               pr["toi"]))
    return out


class Fit:
    """C's ice-time ratio quadrature and per-stat PHI, from training rows."""

    def __init__(self, rows: list):
        ratios = sorted(r.t / r.toi for r in rows if r.stat == STATS[0] and r.toi > 0)
        q = [ratios[min(len(ratios) - 1, int((k + 0.5) * len(ratios) / Q))] for k in range(Q)]
        centre = sum(q) / Q
        self.quad = [v / centre for v in q]
        self.spread = (ratios[int(0.05 * len(ratios))], ratios[len(ratios) // 2], ratios[int(0.95 * len(ratios))])
        num: dict = defaultdict(float)
        den: dict = defaultdict(float)
        for r in rows:
            m = r.mu * r.t / r.toi
            num[r.stat] += (r.y - m) ** 2
            den[r.stat] += m
        self.phi = {s: (num[s] / den[s] if den[s] else 1.0) for s in STATS}
        num_n: dict = defaultdict(float)
        den_n: dict = defaultdict(float)
        for r in rows:
            num_n[r.stat] += (r.y - r.mu) ** 2
            den_n[r.stat] += r.mu
        self.phi_n = {s: (num_n[s] / den_n[s] if den_n[s] else 1.0) for s in STATS}

    def cdf_c(self, x: Row) -> list[float]:
        top = len(GRID[x.stat]) - 1
        out = [0.0] * (top + 1)
        for v in self.quad:
            acc = 0.0
            for j, p in enumerate(FC._count_pmf(x.mu * v, self.phi[x.stat], top)):
                acc += p
                out[j] += acc / Q
        return out


    def cdf_n(self, x: Row) -> list[float]:
        acc, out = 0.0, []
        for p in FC._count_pmf(x.mu, self.phi_n[x.stat], len(GRID[x.stat]) - 1):
            acc += p
            out.append(min(1.0, acc))
        return out


def cdf_site(x: Row) -> list[float]:
    """The board's own count at its projection (model.nbinom_pmf at the
    mean and dispersion skater_projection gives; Poisson at 1)."""
    acc, out = 0.0, []
    for k in range(len(GRID[x.stat])):
        acc += M.nbinom_pmf(k, x.mu, x.disp)
        out.append(min(1.0, acc))
    return out


def score(rows: list, fit: Fit) -> list[dict]:
    out = []
    for x in rows:
        grid, y = GRID[x.stat], x.y
        fs, fc, fn = cdf_site(x), fit.cdf_c(x), fit.cdf_n(x)
        k = min(len(grid) - 1, max(0, int(math.floor(x.mu))))
        line = k - 0.5 if k > 0 else 0.5
        j = int(line)
        over = 1.0 if y > line else 0.0
        out.append({"who": x.who, "a": E1.crps(fs, grid, y), "b": E1.crps(fc, grid, y), "n": E1.crps(fn, grid, y),
                    "brier_s": (1 - fs[j] - over) ** 2, "brier_c": (1 - fc[j] - over) ** 2,
                    "brier_n": (1 - fn[j] - over) ** 2})
    return out


def splits(players: dict) -> tuple | None:
    full = complete_seasons(players)
    if not full:
        return None
    rows = rows_from(players, league_by_date(players), full)
    last = full[-1]
    if len(full) >= 2:
        cut = f"{last + 1}-01-01"
        train = [r for r in rows if r.s in full[:-1]]
        valid = [r for r in rows if r.s == last and r.date < cut]
        hold = [r for r in rows if r.s == last and r.date >= cut]
        labels = (", ".join(f"{s}-{s + 1 - 2000:02d}" for s in full[:-1]),
                  f"{last}-{last + 1 - 2000:02d} before January 1", f"{last}-{last + 1 - 2000:02d} from January 1")
    else:
        a, b = f"{last}-12-15", f"{last + 1}-02-10"
        train = [r for r in rows if r.date < a]
        valid = [r for r in rows if a <= r.date < b]
        hold = [r for r in rows if r.date >= b]
        labels = (f"{last}-{last + 1 - 2000:02d} before December 15", "December 15 - February 9",
                  "February 10 on")
    return train, valid, hold, labels


def bounded(scored: list[dict], key: str, base: str = "a") -> tuple:
    keep = E1.ALPHA
    E1.ALPHA = ALPHA
    try:
        return E1.boot_diff(scored, key_b=key, key_a=base)
    finally:
        E1.ALPHA = keep


def study(conn, holdout: bool = False) -> dict:
    got = splits(skaters(conn))
    if not got:
        return {"verdict": "NOT YET: no complete NHL season in the table"}
    train, valid, hold, labels = got
    short = [f"{n} has {len(p) // len(STATS)}" for n, p in (("training", train), ("validation", valid),
                                                            ("holdout", hold)) if len(p) < MIN_PART * len(STATS)]
    if short:
        return {"verdict": f"NOT YET: each part needs {MIN_PART} player-games; " + ", ".join(short)}
    fit = Fit(train)
    rep = {"labels": labels, "train": len(train) // len(STATS),
           "fit": {"toi_ratio": fit.spread, "phi": {s: round(v, 3) for s, v in fit.phi.items()},
                   "phi_n": {s: round(v, 3) for s, v in fit.phi_n.items()}, "prior": M.SOG_DISPERSION},
           "periods": {}}
    for name, part in [("validation", valid)] + ([("holdout", hold)] if holdout else []):
        per = {}
        for stat in STATS:
            t = score([x for x in part if x.stat == stat], fit)
            n = len(t)
            per[stat] = {"n": n, "players": len({p["who"] for p in t}),
                         "crps_s": sum(p["a"] for p in t) / n, "crps_c": sum(p["b"] for p in t) / n,
                         "crps_n": sum(p["n"] for p in t) / n,
                         "brier_s": sum(p["brier_s"] for p in t) / n, "brier_c": sum(p["brier_c"] for p in t) / n,
                         "brier_n": sum(p["brier_n"] for p in t) / n,
                         "c_minus_s": bounded(t, "b"), "n_minus_s": bounded(t, "n"), "c_minus_n": bounded(t, "b", "n")}
        rep["periods"][name] = per
    decisions = {}
    for stat in STATS:
        v = rep["periods"]["validation"][stat]
        h = rep["periods"].get("holdout", {}).get(stat)
        if v["crps_c"] >= v["crps_s"]:
            decisions[stat] = "REJECTED (validation)"
        elif not h:
            decisions[stat] = "validation passed; holdout not yet read (--holdout, once)"
        else:
            mean, _lo, hi = h["c_minus_s"]
            decisions[stat] = "REJECTED (holdout)" if mean >= 0 else ("ADVANCE" if hi < 0 else "INCONCLUSIVE")
    rep["decisions"] = decisions
    return rep


def render(rep: dict) -> str:
    out = ["EXP-009 — NHL skater props: a shape built from his ice time against the board's own count, one centre"]
    if "labels" not in rep:
        out.append(f"  {rep['verdict']}")
        return "\n".join(out)
    f = rep["fit"]
    lo, mid, hi = f["toi_ratio"]
    out.append(f"  fitted on {rep['labels'][0]} ({rep['train']:,} player-games): ice time over his projection "
               f"{lo:.2f} / {mid:.2f} / {hi:.2f} (5th / 50th / 95th); PHI given ice time "
               + ", ".join(f"{s} {v}" for s, v in f["phi"].items()) + "; PHI_N given the projection "
               + ", ".join(f"{s} {v}" for s, v in f["phi_n"].items())
               + f" (the board's shots-and-blocks prior {f['prior']}, points Poisson)")
    for name, label in (("validation", rep["labels"][1]), ("holdout", rep["labels"][2])):
        per = rep["periods"].get(name)
        if not per:
            continue
        out.append(f"  {name} {label}:")
        for stat in STATS:
            p = per[stat]
            d = p["c_minus_s"]
            ns, cn = p["n_minus_s"], p["c_minus_n"]
            out.append(f"    {stat:<6} n={p['n']:,} ({p['players']} player-seasons)  CRPS S {p['crps_s']:.4f}  "
                       f"C {p['crps_c']:.4f}  C-S {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]")
            out.append(f"           described: N {p['crps_n']:.4f}  N-S {ns[0]:+.4f} [{ns[1]:+.4f}, {ns[2]:+.4f}]  "
                       f"C-N {cn[0]:+.4f} [{cn[1]:+.4f}, {cn[2]:+.4f}]  | Brier at the half below the centre "
                       f"S {p['brier_s']:.4f} C {p['brier_c']:.4f} N {p['brier_n']:.4f}")
    out.append("  decision (98.33% intervals, bar written before the run): "
               + "; ".join(f"{k}: {v}" for k, v in rep["decisions"].items()))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "history.db"))
    ap.add_argument("--holdout", action="store_true", help="also read the holdout (once; see THE BAR)")
    a = ap.parse_args(argv)
    if not Path(a.db).exists():
        print(f"No database at {a.db}.")
        return 1
    print(render(study(open_db(a.db), a.holdout)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
