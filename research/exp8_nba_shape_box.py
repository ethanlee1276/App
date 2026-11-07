#!/usr/bin/env python3
"""EXP-008 — NBA props: a shape built from his minutes against the site's fixed spread, at one centre.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp8_nba_shape_box.py
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp8_nba_shape_box.py --holdout

Backlog B9. The NBA board's centre is already two-stage: his per-minute
rate times his minutes (engine/nba/pipeline.project). Its SHAPE is not: a
points prop is a normal and a rebounds or assists prop a negative binomial,
each as wide as a fixed share of the centre (the coefficient of variation
engine/hoops_fit measures from the box's own logs). A game of 38 minutes
and a game of 24 are the same width to it. EXP-001's lesson (the
two-stage gain was the shape, not the centre) asks whether a shape built
from his minutes prices better. Registry EXP-008.

THE DATA. The box's own box scores (history.db player_game_logs, sport
'nba': minutes, points, rebounds, assists by game date), read-only;
regular season only (games before April 15 of a season's second year).
A player-game is scored when he played, with the board's own refusals
applied first: at least MIN_PRIOR earlier games played that season (its
rate and its base both need three), its volatile-role gate
(engine/nba/quality.stability_blocks: off for the NBA, on for the WNBA),
and a base of at least MIN_BASE minutes (the players books hang props on).

ONE CENTRE FOR BOTH: μ = his rate per minute this season (points, rebounds
or assists over minutes, every game he played) × his role's base minutes
(engine/nba/minutes.base_minutes of role_minutes, the site's own
arithmetic, before tonight's spread, rest, vacancy and defence dials,
which neither shape has). The test is the shape alone.

  S  THE SITE'S SHAPE: points normal with SD = cv × μ; rebounds and assists
     negative binomial with SD = cv × μ (engine/nba/prob, unchanged). cv is
     the live build's own rule (engine/hoops_fit.fit_stat_cvs: each
     player's SD over mean, the median across players), measured on the
     training window only.
  C  THE COMPOUND SHAPE: minutes M = base + a residual from the training
     player-games' own pool (actual minus base minutes, centred so that
     E[M] = base; read at Q quantiles; at least one minute); then the stat
     given M is a count with mean rate × M and variance PHI × mean
     (engine/fieldcurve._count_pmf; PHI per stat by moments on training).

THE SCORE: CRPS on whole numbers (points 0-60, rebounds 0-25, assists
0-20), clustered by player-season. Described, deciding nothing: S0, the
site's shape at the inherited cv (engine/hoops.NBA), and each shape's
chance of the over at the half below μ.

THE SPLITS, from the complete seasons the table holds (a season with games
from April 1 of its second year): with two or more, TRAIN = every complete
season before the last, VALIDATE = the last before January 1, HOLD OUT =
the last from January 1. With one, TRAIN = its games before December 15,
VALIDATE = December 15 to February 9, HOLD OUT = February 10 on. The
season under way is never used. Each part needs MIN_PART player-games.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-19). Three tests, C against S in
points, rebounds and assists, each held to 0.05 / 3: a test ADVANCES only
if its validation mean CRPS is below S's AND on the holdout it is below
S's with the upper end of its clustered 98.33% interval under zero; right
direction with that end over zero is INCONCLUSIVE; wrong direction
REJECTED. The holdout is read once, with ``--holdout``. An ADVANCE moves
nothing by itself: it goes to Ethan, and a change to the board's shape is
then a paper test before it is anything else.

HOW STRICT THAT IS, tried on made-up leagues of only 30 players
(tests/test_nba_shape_lab.py; the box has fifteen times that): where a
stat is his minutes times a rate, C advanced in 19 of 30 stat tests over
ten leagues (points 10 of 10, rebounds 4, assists 5); where a stat comes
straight from his mean whatever his minutes, in none of 30.

Prior art: compound (mixed) count models for player stats, minutes-based
NBA projection; a new application to the site's own pricing shape
(novelty class 4).

Read-only on the database; writes nothing.
"""
from __future__ import annotations

import argparse
import bisect
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fieldcurve as FC                                   # noqa: E402
from engine import hoops_fit as HF                                    # noqa: E402
from engine.hoops import NBA                                          # noqa: E402
from engine.nba import prob as P                                      # noqa: E402
from engine.nba.minutes import base_minutes, role_minutes             # noqa: E402
from engine.nba.quality import stability_blocks                       # noqa: E402
from research import exp1_two_stage as E1                            # noqa: E402

STATS = ("pts", "reb", "ast")
GRID = {"pts": [float(t) for t in range(61)], "reb": [float(t) for t in range(26)],
        "ast": [float(t) for t in range(21)]}
MIN_PRIOR = 3
MIN_BASE = 15.0
MIN_PART = 300
Q = 25
ALPHA = 0.05 / 3
PLAYOFFS = "04-15"
COMPLETE = "04-01"
CV_MIN_GAMES = 12


def open_db(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def logs(conn) -> dict:
    """``{(player, season): [(date, {market: value})...]}`` oldest first, the
    regular season's games, every game he is in a box score for."""
    q = ("SELECT player, season, period, market, value FROM player_game_logs "
         "WHERE sport='nba' AND market IN ('min','pts','reb','ast')")
    by: dict = defaultdict(dict)
    for player, season, date, market, value in conn.execute(q):
        if not player or season is None or not date or str(date) >= f"{int(season) + 1}-{PLAYOFFS}":
            continue
        by[(player, int(season), str(date))][market] = float(value or 0.0)
    out: dict = defaultdict(list)
    for (player, season, date), st in by.items():
        if "min" in st:
            out[(player, season)].append((date, st))
    for games in out.values():
        games.sort(key=lambda g: g[0])
    return dict(out)


def complete_seasons(lg: dict) -> list[int]:
    last: dict = {}
    for (_p, season), games in lg.items():
        last[season] = max(last.get(season, ""), games[-1][0])
    return sorted(s for s, d in last.items() if d >= f"{s + 1}-{COMPLETE}")


def rows_from(lg: dict, seasons) -> list[dict]:
    """One row per (player-game he played, stat) the board would price."""
    want = set(seasons)
    out = []
    for (player, season), games in lg.items():
        if season not in want:
            continue
        played = [(d, st) for d, st in games if st.get("min", 0.0) > 0]
        for i, (date, st) in enumerate(played):
            if i < MIN_PRIOR:
                continue
            hist = played[:i]
            mins = [h["min"] for _d, h in hist][::-1]
            role, _left = role_minutes(mins)
            base = base_minutes(role, NBA)
            if base is None or base < MIN_BASE or stability_blocks(role, NBA):
                continue
            tot_m = sum(mins)
            for stat in STATS:
                rate = sum(h.get(stat, 0.0) for _d, h in hist) / tot_m
                if rate <= 0:
                    continue
                out.append({"who": f"{player}|{season}", "player": player, "s": season, "date": date,
                            "stat": stat, "y": st.get(stat, 0.0), "m": st["min"], "base": base,
                            "rate": rate, "mu": rate * base})
    return out


def site_cvs(lg: dict, keep) -> dict:
    """The live build's cv rule (engine/hoops_fit.fit_stat_cvs) on the
    games ``keep(season, date)`` admits: each player's SD over mean across
    his box-score rows, the median across players."""
    vals: dict = defaultdict(list)
    for (player, season), games in lg.items():
        for date, st in games:
            if keep(season, date):
                for stat in STATS:
                    vals[(player, stat)].append(st.get(stat, 0.0))
    out = {}
    for stat in STATS:
        per, rows = [], 0
        for (_p, s), v in vals.items():
            if s != stat or len(v) < CV_MIN_GAMES:
                continue
            rows += len(v)
            mean, sd = sum(v) / len(v), HF._sd(v)
            if sd is not None and mean > 0.5:
                per.append(sd / mean)
        if len(per) >= 10 and rows >= HF.MIN_STAT_ROWS:
            per.sort()
            mid = len(per) // 2
            out[stat] = round(per[mid] if len(per) % 2 else (per[mid - 1] + per[mid]) / 2, 3)
    return out


class Fit:
    """C's minutes quadrature and per-stat PHI; S's cv."""

    def __init__(self, rows: list[dict], cvs: dict):
        resid = sorted(r["m"] - r["base"] for r in rows if r["stat"] == STATS[0])
        q = [resid[min(len(resid) - 1, int((k + 0.5) * len(resid) / Q))] for k in range(Q)]
        centre = sum(q) / Q
        self.quad = [e - centre for e in q]
        self.spread = (resid[int(0.05 * len(resid))], resid[len(resid) // 2], resid[int(0.95 * len(resid))])
        self.phi = {}
        for stat in STATS:
            t = [r for r in rows if r["stat"] == stat]
            den = sum(r["rate"] * r["m"] for r in t)
            self.phi[stat] = sum((r["y"] - r["rate"] * r["m"]) ** 2 for r in t) / den if den else 1.0
        self.cv = {s: cvs.get(s, NBA.sd_cv.get(s, 0.35)) for s in STATS}

    def cdf_c(self, x: dict) -> list[float]:
        grid = GRID[x["stat"]]
        out = [0.0] * len(grid)
        for e in self.quad:
            pmf = FC._count_pmf(x["rate"] * max(1.0, x["base"] + e), self.phi[x["stat"]], len(grid) - 1)
            acc = 0.0
            for j, p in enumerate(pmf):
                acc += p
                out[j] += acc / Q
        return out


def cdf_site(stat: str, mu: float, cv: float) -> list[float]:
    """The board's own shape at centre ``mu`` (engine/nba/prob)."""
    grid = GRID[stat]
    if stat not in P.DISCRETE:
        sd = max(0.1, cv * mu)
        return [P._phi((t + 0.5 - mu) / sd) for t in grid]
    var = max((cv * mu) ** 2, mu * 1.0001)
    r = mu * mu / (var - mu)
    p = r / (r + mu)
    out, acc = [], 0.0
    for k in range(len(grid)):
        acc += P._negbin_pmf(k, r, p)
        out.append(min(1.0, acc))
    return out


def score(rows: list[dict], fit: Fit) -> list[dict]:
    out = []
    for x in rows:
        grid, y = GRID[x["stat"]], x["y"]
        fs = cdf_site(x["stat"], x["mu"], fit.cv[x["stat"]])
        f0 = cdf_site(x["stat"], x["mu"], NBA.sd_cv.get(x["stat"], 0.35))
        fc = fit.cdf_c(x)
        k = min(len(grid) - 1, max(0, int(math.floor(x["mu"]))))
        line = k - 0.5 if k > 0 else 0.5
        j = int(line)
        over = 1.0 if y > line else 0.0
        out.append({"who": x["who"], "stat": x["stat"], "s": x["s"], "a": E1.crps(fs, grid, y),
                    "b": E1.crps(fc, grid, y), "s0": E1.crps(f0, grid, y),
                    "brier_s": (1 - fs[j] - over) ** 2, "brier_c": (1 - fc[j] - over) ** 2})
    return out


def splits(lg: dict) -> tuple | None:
    full = complete_seasons(lg)
    if not full:
        return None
    last = full[-1]
    if len(full) >= 2:
        cut = f"{last + 1}-01-01"
        keep_train = lambda s, d: s in full[:-1]                                  # noqa: E731
        rows = rows_from(lg, full)
        train = [r for r in rows if r["s"] in full[:-1]]
        valid = [r for r in rows if r["s"] == last and r["date"] < cut]
        hold = [r for r in rows if r["s"] == last and r["date"] >= cut]
        labels = (", ".join(map(str, full[:-1])), f"{last}-{last + 1 - 2000:02d} before January 1",
                  f"{last}-{last + 1 - 2000:02d} from January 1")
    else:
        a, b = f"{last}-12-15", f"{last + 1}-02-10"
        keep_train = lambda s, d: s == last and d < a                            # noqa: E731
        rows = rows_from(lg, full)
        train = [r for r in rows if r["date"] < a]
        valid = [r for r in rows if a <= r["date"] < b]
        hold = [r for r in rows if r["date"] >= b]
        labels = (f"{last}-{last + 1 - 2000:02d} before December 15", "December 15 - February 9",
                  "February 10 on")
    return train, valid, hold, labels, keep_train


def bounded(scored: list[dict], key: str) -> tuple:
    keep = E1.ALPHA
    E1.ALPHA = ALPHA
    try:
        return E1.boot_diff(scored, key_b=key)
    finally:
        E1.ALPHA = keep


def study(conn, holdout: bool = False) -> dict:
    lg = logs(conn)
    got = splits(lg)
    if not got:
        return {"verdict": "NOT YET: no complete NBA season in the table"}
    train, valid, hold, labels, keep_train = got
    short = [f"{n} has {len(p) // len(STATS)}" for n, p in (("training", train), ("validation", valid),
                                                            ("holdout", hold)) if len(p) < MIN_PART * len(STATS)]
    if short:
        return {"verdict": f"NOT YET: each part needs {MIN_PART} player-games; " + ", ".join(short)}
    fit = Fit(train, site_cvs(lg, keep_train))
    rep = {"labels": labels, "train": len(train) // len(STATS), "fit": {
        "minutes_spread": fit.spread, "phi": {s: round(v, 3) for s, v in fit.phi.items()},
        "cv": fit.cv, "cv_inherited": {s: NBA.sd_cv.get(s) for s in STATS}}, "periods": {}}
    for name, part in [("validation", valid)] + ([("holdout", hold)] if holdout else []):
        sc = score(part, fit)
        per = {}
        for stat in STATS:
            t = [p for p in sc if p["stat"] == stat]
            n = len(t)
            per[stat] = {"n": n, "players": len({p["who"] for p in t}),
                         "crps_s": sum(p["a"] for p in t) / n, "crps_c": sum(p["b"] for p in t) / n,
                         "crps_s0": sum(p["s0"] for p in t) / n,
                         "brier_s": sum(p["brier_s"] for p in t) / n, "brier_c": sum(p["brier_c"] for p in t) / n,
                         "c_minus_s": bounded(t, "b")}
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
    out = ["EXP-008 — NBA props: the compound shape (minutes × rate) against the board's fixed spread, one centre"]
    if "labels" not in rep:
        out.append(f"  {rep['verdict']}")
        return "\n".join(out)
    f = rep["fit"]
    lo, mid, hi = f["minutes_spread"]
    out.append(f"  fitted on {rep['labels'][0]} ({rep['train']:,} player-games): minutes against his base "
               f"{lo:+.1f} / {mid:+.1f} / {hi:+.1f} (5th / 50th / 95th); PHI "
               + ", ".join(f"{s} {v}" for s, v in f["phi"].items()) + "; the board's cv "
               + ", ".join(f"{s} {f['cv'][s]} (inherited {f['cv_inherited'][s]})" for s in STATS))
    for name, label in (("validation", rep["labels"][1]), ("holdout", rep["labels"][2])):
        per = rep["periods"].get(name)
        if not per:
            continue
        out.append(f"  {name} {label}:")
        for stat in STATS:
            p = per[stat]
            d = p["c_minus_s"]
            out.append(f"    {stat:<4} n={p['n']:,} ({p['players']} player-seasons)  CRPS S {p['crps_s']:.4f}  "
                       f"C {p['crps_c']:.4f}  (S0 {p['crps_s0']:.4f})  C-S {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]  "
                       f"| Brier at the half below the centre S {p['brier_s']:.4f} C {p['brier_c']:.4f}")
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
