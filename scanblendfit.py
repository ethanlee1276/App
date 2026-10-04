#!/usr/bin/env python3
"""How much of a team's rating should be this season? — measured.

    python3 scanblendfit.py                  # 2022-2025, the box's database
    python3 scanblendfit.py 2023 2024 --db path/to/history.db

Ethan, 2026-09-27: "Idk if anything should be at 75/25. Write the check
and do the check then change anything that's hurting."

Walk-forward over the stored unit table (engine/gamescan's `team_units`,
opponent-adjusted EPA, success rate): for every season, every week 3-9
and every team, blend the weeks played so far with last season at a
share w of this season, and score that blend against what the team did
over the REST of the season. The best w is solved in closed form (least
squares), per group:

  same    a side with no change
  hc      a new head coach (both sides), no new QB on that side
  qb      the offence under a new starting QB

and by how many games are in (2-3, 4-5, 6-8). Errors are standardised by
each week's league spread of the target so the four units pool. The
groups come from the nflverse schedule (engine/teamchange); coordinators
have no history there, so they are not measured separately.

A cluster bootstrap (team-season) gives each best share a ±. Reads only;
writes nothing.
"""
from __future__ import annotations

import random
import sys

from engine import gamescan as G
from engine import teamchange as T

UNITS = ("overall", "passing", "rushing", "success")
WEEKS = range(3, 10)
BUCKETS = ((2, 3), (4, 5), (6, 8))
BOOT = 300


def _rows(conn, season):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM team_units WHERE sport='nfl' AND season=?", (season,))]


def _week(r):
    try:
        return int(float(r["period"]))
    except (TypeError, ValueError):
        return 99


def collect(conn, seasons, schedules) -> list:
    """[(group, games, cluster, a (this season), b (last), y (rest), scale)]"""
    pts = []
    for S in seasons:
        now, last = _rows(conn, S), _rows(conn, S - 1)
        if not now or not last:
            print(f"  {S}: no unit rows for {S} or {S - 1} — skipped")
            continue
        pri, _ = G._adjusted(last)
        for k in WEEKS:
            cur, games = G._adjusted([r for r in now if _week(r) < k])
            fut, _ = G._adjusted([r for r in now if k <= _week(r) <= 18])
            ch = T.detect(schedules, S, before_week=k, staff={})
            for side in ("off", "def"):
                for u in UNITS:
                    ys = [fut[(t, s)][u] for (t, s) in fut if s == side and fut[(t, s)].get(u) is not None]
                    if len(ys) < 10:
                        continue
                    m = sum(ys) / len(ys)
                    sd = (sum((y - m) ** 2 for y in ys) / (len(ys) - 1)) ** 0.5 or 1.0
                    for (t, s), cell in cur.items():
                        if s != side:
                            continue
                        a, b = cell.get(u), (pri.get((t, s)) or {}).get(u)
                        y = (fut.get((t, s)) or {}).get(u)
                        if a is None or b is None or y is None:
                            continue
                        why = " ".join((ch.get(t) or {}).get(side) or [])
                        group = ("qb" if "new starting QB" in why
                                 else "hc" if "new head coach" in why else "same")
                        pts.append((group, games.get(t, 0), f"{S}{t}", a, b, y, sd))
    return pts


def best_share(pts) -> float | None:
    """Least-squares w for y ~ w*a + (1-w)*b, errors in league-sd units."""
    num = sum((a - b) * (y - b) / sd ** 2 for _g, _n, _c, a, b, y, sd in pts)
    den = sum((a - b) ** 2 / sd ** 2 for _g, _n, _c, a, b, y, sd in pts)
    return num / den if den else None


def mse(pts, w) -> float:
    return sum(((w * a + (1 - w) * b - y) / sd) ** 2 for _g, _n, _c, a, b, y, sd in pts) / len(pts)


def boot(pts, reps=BOOT, seed=7) -> float:
    """The best share's spread over team-season clusters."""
    by: dict = {}
    for p in pts:
        by.setdefault(p[2], []).append(p)
    keys = list(by)
    rnd = random.Random(seed)
    got = []
    for _ in range(reps):
        sample = [p for k in (rnd.choice(keys) for _ in keys) for p in by[k]]
        w = best_share(sample)
        if w is not None:
            got.append(w)
    if len(got) < 2:
        return 0.0
    m = sum(got) / len(got)
    return (sum((g - m) ** 2 for g in got) / (len(got) - 1)) ** 0.5


def ramp_mse(pts, k: float) -> float:
    """Error when this season's share is games / (games + k) — a share
    that grows as the season's own evidence does."""
    tot = 0.0
    for _g, n, _c, a, b, y, sd in pts:
        w = n / (n + k) if n + k > 0 else 0.0
        tot += ((w * a + (1 - w) * b - y) / sd) ** 2
    return tot / len(pts)


def best_ramp(pts) -> tuple:
    """(k, error) minimising ramp_mse over k = 0.5 … 20."""
    grid = [x / 2 for x in range(1, 41)]
    errs = [(ramp_mse(pts, k), k) for k in grid]
    e, k = min(errs)
    return k, e


def hand_share(n: float, group: str) -> float:
    """The split set by hand on 2026-09-27 before this check: 55% from
    two games on, 65% for new staff, 75% for a new QB — kept here as the
    baseline the measured split had to beat."""
    top = {"qb": 0.75, "hc": 0.65}.get(group, 0.55)
    if n >= 2:
        return top
    k = 1.0 if group in ("qb", "hc") else 4.0
    return min(top, n / (n + k)) if n > 0 else 0.0


def split_mse(pts, share) -> float:
    tot = 0.0
    for g, n, _c, a, b, y, sd in pts:
        w = share(n, g)
        tot += ((w * a + (1 - w) * b - y) / sd) ** 2
    return tot / len(pts)


def live_mse(pts, group) -> float:
    """Error under what the site does now (gamescan.unit_share)."""
    return split_mse(pts, lambda n, _g: G.unit_share(n, True, new_qb=group == "qb"))


def report(pts) -> dict:
    out = {}
    for group in ("same", "hc", "qb"):
        gp = [p for p in pts if p[0] == group]
        if not gp:
            continue
        row = {"n": len(gp), "teams": len({p[2] for p in gp}),
               "best": best_share(gp), "se": boot(gp),
               "mse": {w: mse(gp, w) for w in (0.55, 0.65, 0.75)}, "by_games": {},
               "live": live_mse(gp, group), "hand": split_mse(gp, hand_share),
               "ramp": best_ramp(gp)}
        for lo, hi in BUCKETS:
            bp = [p for p in gp if lo <= p[1] <= hi]
            if len({p[2] for p in bp}) >= 5:
                row["by_games"][f"{lo}-{hi}"] = (best_share(bp), boot(bp), len({p[2] for p in bp}))
        out[group] = row
    return out


def main(argv):
    db_path = None
    if "--db" in argv:
        i = argv.index("--db")
        db_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    seasons = [int(a) for a in argv] or [2022, 2023, 2024, 2025]
    from engine.db import connect
    from engine.sources.nflverse import load_schedules
    conn = connect(db_path) if db_path else connect()
    pts = collect(conn, seasons, load_schedules())
    if not pts:
        print("No unit rows to measure — run: python3 -m engine.gamescan backfill "
              + " ".join(str(s) for s in [seasons[0] - 1] + seasons))
        return 1
    print(f"\nSeason split, walk-forward {seasons[0]}-{seasons[-1]}, weeks {WEEKS.start}-{WEEKS.stop - 1}, "
          f"units {', '.join(UNITS)} (error in league-sd units; lower is better)\n")
    names = {"same": "no change", "hc": "new head coach", "qb": "new starting QB (offence)"}
    for group, r in report(pts).items():
        print(f"  {names[group]:<27} {r['teams']:>4} team-seasons  best this-season share "
              f"{r['best']:.2f} ± {r['se']:.2f}")
        print("      error at 55% {0:.4f} · 65% {1:.4f} · 75% {2:.4f}".format(*r["mse"].values()))
        k, e = r["ramp"]
        print(f"      best growing share games/(games+{k:g}): error {e:.4f} · live split "
              f"{r['live']:.4f} · the old hand split {r['hand']:.4f}")
        for b, (w, se, n) in r["by_games"].items():
            print(f"      after {b} games: best {w:.2f} ± {se:.2f}  ({n} team-seasons)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
