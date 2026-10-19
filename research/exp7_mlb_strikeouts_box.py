#!/usr/bin/env python3
"""EXP-007 — the first MLB experiment: a starter's strikeouts, batters faced first.

    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp7_mlb_strikeouts_box.py
    cd /srv/qellys && sudo -u qellys nice -n 19 python3 research/exp7_mlb_strikeouts_box.py --holdout

The research spec, Part 2: a program per sport, and no NFL finding assumed
to transfer. EXP-001's question, asked of baseball's best-known prop: is
P(K) = Σ_bf P(K | BF = bf) · P(BF = bf) — how many batters he lasts, then
how often he strikes one out — a better forecast of a starter's strikeouts
than a direct model of his strikeouts? Backlog B8. Registry EXP-007.

THE DATA. The box's own play-by-play table (history.db ``mlb_pa``: one row
per plate appearance, filled nightly for the hit and pitch charts),
read-only. A start is a pitcher's plate appearances in one game, kept only
for the pitcher who faced his opponents' first batter (engine/role.py's
rule); batters faced = those plate appearances, strikeouts = the ones that
end in a strikeout (engine/mlb/charts.STRIKEOUTS). Games ``mlb_games``
marks as postseason are left out. A start is scored only with MIN_PRIOR
earlier starts that season behind it, and everything it is scored with
comes from those earlier starts.

THE MODELS:
  A  DIRECT. The mean is the site's own MLB form blend of his strikeouts
     this season (engine.form.compute_form with MLB_WINDOW_WEIGHTS, where
     engine/mlb/projection.py starts, before its park, weather, umpire and
     matchup dials, which neither model has); the shape is the training
     starts' pool of strikeouts over that mean, as EXP-001's A.
  B  TWO-STAGE. Batters faced = his earlier starts' batters faced weighted
     by age (half-life BF_HALF_LIFE starts) plus a residual drawn from the
     training starts' own pool of them, rounded, at least one — the
     training data's spread, early exits included, not an assumed curve;
     then strikeouts | batters faced ~ Binomial(bf, p), p his strikeouts
     per batter this season shrunk toward the training league's by k
     batters, k fitted on the training starts over K_GRID.
  H  A's mean with B's shape (EXP-001b's idea; it held in college rushing).

THE SCORE: CRPS on 0..15 strikeouts (the ranked probability score),
clustered by pitcher-season.

THE SPLITS, from the seasons the table holds (a season counts with at
least MIN_SEASON_STARTS scored starts): with two or more, TRAIN = every
season before the last, VALIDATE = the last season's starts before July 1,
HOLD OUT = the last season's starts from July 1 on. With one, TRAIN = its
starts before June 1, VALIDATE = June 1 to July 14, HOLD OUT = July 15 on.
Each part needs MIN_PART starts, or the script says NOT YET.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-19). Two tests, B against A and H
against A, each held to 0.05 / 2: a test ADVANCES only if its validation
mean CRPS is below A's AND on the holdout it is below A's with the upper
end of its clustered 97.5% interval under zero. Right direction with that
end over zero is INCONCLUSIVE; wrong direction REJECTED. The holdout is
read once, with ``--holdout``, and only when (1) the table holds plays for
at least COMPLETE of every season's regular-season finals, so the rows
cannot change after the read, and (2) no fitted constant sits on the edge
of its grid, which would call for a written amendment first.

HOW STRICT THAT IS, tried on made-up leagues of only 30 starters
(tests/test_mlb_strikeouts_lab.py; the box has about five times that):
where strikeouts are batters faced times a rate, B advanced on 19 seeds of
20; where they come straight from a pitcher's mean with a spread batters
faced do not explain, on none — rejected at validation on all 20.

Prior art: strikeouts as batters faced times a strikeout rate is standard
among baseball bettors and projection systems — a new application of an
established method (novelty class 4), tested properly.

Read-only on the database; writes nothing.
"""
from __future__ import annotations

import argparse
import bisect
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.form import MLB_WINDOW_WEIGHTS, compute_form              # noqa: E402
from engine.models import GameLog                                     # noqa: E402
from engine.nflusage import ewma_opps                                 # noqa: E402
from research import exp1_two_stage as E1                            # noqa: E402

STRIKEOUTS = ("strikeout", "strikeout_double_play", "strikeout_triple_play")
GRID = [float(t) for t in range(0, 16)]
BF_HALF_LIFE = 3.0
K_GRID = (25.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0)
MIN_PRIOR = 3
MIN_SEASON_STARTS = 500
MIN_PART = 200
COMPLETE = 0.98
ALPHA = 0.05 / 2


def open_db(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)


def _not_regular(conn) -> set:
    try:
        return {pk for (pk,) in conn.execute(
            "SELECT game_pk FROM mlb_games WHERE game_type IS NOT NULL AND game_type != 'R'")}
    except sqlite3.Error:
        return set()


def starts(conn) -> list[dict]:
    """Every regular-season start, oldest first: {pid, name, game, date,
    season, bf, k}, the starter being the pitcher who faced his opponents'
    first batter."""
    marks = ",".join("?" * len(STRIKEOUTS))
    q = (f"SELECT game_pk, pitcher_id, MIN(pitcher), team, MIN(date), MIN(season), COUNT(*), "
         f"SUM(CASE WHEN event_type IN ({marks}) THEN 1 ELSE 0 END), MIN(at_bat) FROM mlb_pa "
         f"WHERE pitcher_id IS NOT NULL AND event_type IS NOT NULL AND event_type != '' "
         f"GROUP BY game_pk, pitcher_id, team")
    first: dict = {}
    for pk, pid, name, team, date, season, bf, k, ab in conn.execute(q, STRIKEOUTS):
        key = (pk, team)
        if key not in first or ab < first[key]["ab"]:
            first[key] = {"pid": pid, "name": name, "game": pk, "date": date, "season": int(season),
                          "bf": int(bf), "k": int(k or 0), "ab": ab}
    skip = _not_regular(conn)
    out = [s for s in first.values() if s["game"] not in skip]
    out.sort(key=lambda s: (s["date"], s["game"]))
    return out


def coverage(conn) -> dict:
    """``{season: (regular-season games with plays, regular-season finals
    mlb_games knows, or None)}``."""
    skip = _not_regular(conn)
    have: dict = defaultdict(set)
    for pk, season in conn.execute("SELECT DISTINCT game_pk, season FROM mlb_pa"):
        if pk not in skip and season is not None:
            have[int(season)].add(pk)
    finals: dict = {}
    try:
        for season, n in conn.execute("SELECT season, COUNT(*) FROM mlb_games WHERE game_type='R' GROUP BY season"):
            finals[int(season)] = n
    except sqlite3.Error:
        pass
    return {s: (len(have[s]), finals.get(s)) for s in sorted(have)}


def rows_from(all_starts: list[dict]) -> list[dict]:
    """One row per start with MIN_PRIOR earlier starts that season."""
    by: dict = defaultdict(list)
    for s in all_starts:
        by[(s["pid"], s["season"])].append(s)
    out = []
    for (pid, season), ss in by.items():
        for i, s in enumerate(ss):
            if i < MIN_PRIOR:
                continue
            ks = [h["k"] for h in ss[:i]]
            bfs = [float(h["bf"]) for h in ss[:i]]
            logs = [GameLog(week=j, opponent="", value=float(v)) for j, v in enumerate(ks)][::-1]
            mu_a = compute_form(logs, sum(ks) / len(ks), None, weights=MLB_WINDOW_WEIGHTS).mean
            if mu_a <= 0:
                continue
            out.append({"who": f"{pid}|{season}", "s": season, "date": s["date"], "y": float(s["k"]),
                        "o": float(s["bf"]), "mu_a": mu_a, "mu_o": ewma_opps(bfs, BF_HALF_LIFE),
                        "k_sum": float(sum(ks)), "bf_sum": sum(bfs)})
    return out


class Fit:
    """A's pool, B's batters-faced residuals, the league rate and the shrink k."""

    def __init__(self, rows: list[dict]):
        self.pool = sorted(x["y"] / x["mu_a"] for x in rows)
        self.resid = sorted(x["o"] - x["mu_o"] for x in rows)
        self.league = sum(x["y"] for x in rows) / max(1e-9, sum(x["o"] for x in rows))
        self.k = max(K_GRID, key=lambda k: sum(E1._bin_ll(x["y"], x["o"], self.rate(x, k)) for x in rows))

    def rate(self, x: dict, k: float | None = None) -> float:
        return E1.shrunk(x["k_sum"], x["bf_sum"], self.league, self.k if k is None else k)

    def bf_pmf(self, x: dict) -> list[tuple[int, float]]:
        n = len(self.resid)
        top = max(1, int(x["mu_o"] + self.resid[-1] + 1))
        out, below = [], 0.0
        for o in range(1, top + 1):
            c = 1.0 if o == top else bisect.bisect_right(self.resid, o + 0.5 - x["mu_o"]) / n
            if c > below:
                out.append((o, c - below))
                below = c
        return out

    def cdf_a(self, x: dict, t: float) -> float:
        return bisect.bisect_right(self.pool, t / x["mu_a"]) / len(self.pool)

    def cdf_b(self, x: dict, scale: float = 1.0) -> list[float]:
        p = min(0.98, self.rate(x))
        out = [0.0] * len(GRID)
        for o, po in self.bf_pmf(x):
            for j, t in enumerate(GRID):
                out[j] += po * E1.binom_cdf(t / scale, o, p)
        return out

    def mean_b(self, x: dict) -> float:
        return sum(o * po for o, po in self.bf_pmf(x)) * min(0.98, self.rate(x))


def score(rows: list[dict], fit: Fit) -> list[dict]:
    out = []
    for x in rows:
        fa = [fit.cdf_a(x, t) for t in GRID]
        fb = fit.cdf_b(x)
        mb = fit.mean_b(x)
        fh = fit.cdf_b(x, scale=x["mu_a"] / mb) if mb > 0 else fb
        out.append({"who": x["who"], "s": x["s"], "y": x["y"], "a": E1.crps(fa, GRID, x["y"]),
                    "b": E1.crps(fb, GRID, x["y"]), "ba": E1.crps(fh, GRID, x["y"]),
                    "mae_a": abs(x["y"] - x["mu_a"]), "mae_b": abs(x["y"] - mb)})
    return out


def splits(rows: list[dict]) -> tuple | None:
    """(train, validate, hold, labels, seasons) by THE SPLITS, or None with no season."""
    counts: dict = defaultdict(int)
    for x in rows:
        counts[x["s"]] += 1
    seasons = sorted(s for s, n in counts.items() if n >= MIN_SEASON_STARTS)
    if not seasons:
        return None
    last = seasons[-1]
    if len(seasons) >= 2:
        cut = f"{last}-07-01"
        train = [x for x in rows if x["s"] in seasons[:-1]]
        valid = [x for x in rows if x["s"] == last and x["date"] < cut]
        hold = [x for x in rows if x["s"] == last and x["date"] >= cut]
        labels = (f"{seasons[0]}-{seasons[-2]}", f"{last} before July 1", f"{last} from July 1")
    else:
        a, b = f"{last}-06-01", f"{last}-07-15"
        train = [x for x in rows if x["s"] == last and x["date"] < a]
        valid = [x for x in rows if x["s"] == last and a <= x["date"] < b]
        hold = [x for x in rows if x["s"] == last and x["date"] >= b]
        labels = (f"{last} before June 1", f"{last} June 1 - July 14", f"{last} from July 15")
    return train, valid, hold, labels, seasons


def bounded(scored: list[dict], key: str) -> tuple:
    keep = E1.ALPHA
    E1.ALPHA = ALPHA
    try:
        return E1.boot_diff(scored, key_b=key)
    finally:
        E1.ALPHA = keep


def on_edge(fit: Fit) -> list[str]:
    return [f"the shrink k = {fit.k:g} sits on its grid's edge"] if fit.k in (K_GRID[0], K_GRID[-1]) else []


def incomplete(cover: dict, seasons) -> list[str]:
    """Why the holdout cannot be read yet: a season the split uses whose
    plays fall short of COMPLETE of its regular-season finals, or whose
    finals mlb_games cannot count."""
    out = []
    for s in seasons:
        have, finals = cover.get(s, (0, None))
        if not finals:
            out.append(f"{s}: mlb_games has no regular-season finals to count against")
        elif have < COMPLETE * finals:
            out.append(f"{s}: plays for {have:,} of {finals:,} regular-season finals")
    return out


def study(conn, holdout: bool = False) -> dict:
    cover = coverage(conn)
    rows = rows_from(starts(conn))
    rep = {"rows": len(rows), "coverage": cover}
    got = splits(rows)
    if not got:
        rep["verdict"] = f"NOT YET: no season with {MIN_SEASON_STARTS} scored starts"
        return rep
    train, valid, hold, labels, seasons = got
    short = [f"{name} has {len(part)}" for name, part in (("training", train), ("validation", valid),
                                                          ("holdout", hold)) if len(part) < MIN_PART]
    if short:
        rep["verdict"] = f"NOT YET: each part needs {MIN_PART} starts; " + ", ".join(short)
        return rep
    fit = Fit(train)
    q = fit.resid
    rep.update({"labels": labels, "train": len(train),
                "fit": {"bf_resid": (q[int(0.05 * len(q))], q[len(q) // 2], q[int(0.95 * len(q))]),
                        "league_k_per_bf": round(fit.league, 4), "k": fit.k},
                "edge": on_edge(fit), "waiting": incomplete(cover, seasons), "periods": {}})
    blocked = rep["edge"] + rep["waiting"]
    periods = [("validation", valid)] + ([("holdout", hold)] if holdout and not blocked else [])
    for name, part in periods:
        sc = score(part, fit)
        n = len(sc)
        rep["periods"][name] = {
            "n": n, "pitcher_seasons": len({p["who"] for p in sc}),
            "crps_a": sum(p["a"] for p in sc) / n, "crps_b": sum(p["b"] for p in sc) / n,
            "crps_h": sum(p["ba"] for p in sc) / n,
            "mae_a": sum(p["mae_a"] for p in sc) / n, "mae_b": sum(p["mae_b"] for p in sc) / n,
            "b_minus_a": bounded(sc, "b"), "h_minus_a": bounded(sc, "ba")}
    v = rep["periods"]["validation"]
    h = rep["periods"].get("holdout")
    decisions = {}
    for test, key, vkey in (("B v A", "b_minus_a", "crps_b"), ("H v A", "h_minus_a", "crps_h")):
        if v[vkey] >= v["crps_a"]:
            decisions[test] = "REJECTED (validation)"
        elif h:
            mean, _lo, hi = h[key]
            decisions[test] = "REJECTED (holdout)" if mean >= 0 else ("ADVANCE" if hi < 0 else "INCONCLUSIVE")
        elif holdout:
            decisions[test] = "validation passed; holdout NOT read: " + "; ".join(blocked)
        else:
            decisions[test] = "validation passed; holdout not yet read (--holdout, once)"
    rep["decisions"] = decisions
    return rep


def render(rep: dict) -> str:
    out = ["EXP-007 — MLB starters' strikeouts: two-stage (batters faced × strikeout rate) vs direct"]
    for s, (have, finals) in rep["coverage"].items():
        out.append(f"  {s}: plays for {have:,} regular-season games"
                   + (f" of {finals:,} finals" if finals else " (mlb_games has no count)"))
    if "labels" not in rep:
        out.append(f"  {rep['rows']:,} scored starts. {rep['verdict']}")
        return "\n".join(out)
    f = rep["fit"]
    lo, mid, hi = f["bf_resid"]
    out.append(f"  {rep['rows']:,} scored starts; fitted on {rep['labels'][0]} ({rep['train']:,} starts): batters "
               f"faced against his weighted mean {lo:+.1f} / {mid:+.1f} / {hi:+.1f} (5th / 50th / 95th), "
               f"league {f['league_k_per_bf']} strikeouts a batter, shrink k {f['k']:g} batters")
    for name, label in (("validation", rep["labels"][1]), ("holdout", rep["labels"][2])):
        p = rep["periods"].get(name)
        if not p:
            continue
        b, hh = p["b_minus_a"], p["h_minus_a"]
        out.append(f"  {name} {label}: n={p['n']:,} ({p['pitcher_seasons']} pitcher-seasons)  CRPS A {p['crps_a']:.4f}  "
                   f"B {p['crps_b']:.4f}  H {p['crps_h']:.4f}  | B-A {b[0]:+.4f} [{b[1]:+.4f}, {b[2]:+.4f}]  "
                   f"H-A {hh[0]:+.4f} [{hh[1]:+.4f}, {hh[2]:+.4f}]  | MAE A {p['mae_a']:.3f} B {p['mae_b']:.3f}")
    out.append("  decision (97.5% intervals, bar written before the run): "
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
