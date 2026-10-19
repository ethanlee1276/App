#!/usr/bin/env python3
"""EXP-001 — does modelling opportunities first make a prop's whole distribution better?

    python3 research/exp1_two_stage.py              (fit 2017-2021, validate 2022-2023)
    python3 research/exp1_two_stage.py --holdout    (adds 2024-2025; run ONCE, result recorded)

Research spec Part 8, Experiment 1 (Ethan, 2026-10-17). Registry entry
EXP-001 in research/registry.json.

THE QUESTION. Is P(Y | X) = Σ_o P(Y | O = o, X) · P(O = o | X) a better
forecast of a player's stat than a direct model of Y, on games neither saw?

THE TWO MODELS, built from the same pre-game information (his games before
this one, this season, for this team; last season's games for the prior):

  A  DIRECT. The mean is the board's own form blend (engine/form, pulled
     toward last season where engine/carry does that). The shape is the
     training seasons' pool of y / mean ratios for that market and position
     group, so A's shape is learned, not assumed: A forecasts
     P(Y <= t) = share of the pool with ratio <= t / mean.

  B  TWO-STAGE. Opportunities O ~ NegBin(mean mu_O, size r): mu_O is his
     games weighted by age (engine/nflusage.ewma_opps, the half-lives
     rolewindowfit.py chose), r fitted on the training seasons per market
     and position. Then, given o:
       receptions  catches ~ Binomial(o, p), p = his catch rate this season
                   shrunk toward his position's by k targets;
       rec_yds     zero with chance (1 - p)^o, otherwise a normal with the
                   compound's moments given at least one catch (yards per
                   catch shrunk the same way, its spread from training);
       rush_yds    Normal(o * m, o * s^2), m his yards per carry shrunk.
     Every k, r and s^2 is fitted on the training seasons only.

  B@A  DIAGNOSTIC, not a candidate: B's shape rescaled to A's mean, which
     says whether B's gain (if any) is its shape or its mean.

THE SCORE. CRPS — the area between the forecast CDF and the step at what
happened — on a fixed threshold grid (receptions 0..15 = the ranked
probability score; yards every 5 from -10 to 250). Proper, and needs no
book line, which is the point: this measures the forecast, not a proxy for
a price. Secondary: Brier on "over" at A's median rounded to the half
(where a book's line would sit; a PROXY, labelled as one), and the
calibration of B's over-probabilities by decile.

THE BAR, WRITTEN BEFORE ANY RUN (2026-10-17). Per market, B advances only
if (1) on 2022-2023 its mean CRPS is below A's, and (2) on 2024-2025 it is
below A's with the paired, player-season-clustered bootstrap's upper bound
on CRPS(B) - CRPS(A) under zero at 98.33% (0.05 / 3 markets, Bonferroni).
Right direction with a bound over zero is INCONCLUSIVE; wrong direction is
REJECTED. Nothing is tuned after the holdout is read.

AMENDMENT 1 (2026-10-17, after the first validation read, BEFORE any
holdout read): the shrink grid stopped at k = 160 and four of five training
fits sat on that edge, so it now runs to 1280. Widened, those four stay at
160 (a true optimum) and rush yards moves to 320; validation moved by under
0.01. The bar is unchanged.

THE RESULT (2026-10-17, holdout read once, code frozen first):

  holdout 2024-25  CRPS A      B       B@A     B-A [98.33% clustered]   decision
  receptions       1.1746  1.1476  1.1795  -0.0270 [-0.0436, -0.0102]  ADVANCE
  rec_yds         16.1170 16.1454 15.9846  +0.0284 [-0.1491, +0.2252]  REJECTED (validation +0.0865)
  rush_yds        18.2176 18.0023 17.9104  -0.2153 [-0.4567, +0.0474]  INCONCLUSIVE

Two cautions read off the same run. Receptions' gain is over the whole
distribution: at a line-like threshold (the proxy Brier) B is slightly
WORSE (0.2198 v 0.2165), and B's over-chances are too extreme at both ends
(its top decile says 0.49, 0.36 happened). So it advances to calibration
and to a test at real book prices, not to the board. And in both yardage
markets B's SHAPE at A's mean (B@A) beat both, in validation and holdout:
an observation made after looking, so it is not a result. It is EXP-001b,
preregistered below and scored only on games played after this was frozen.

EXP-001b, PREREGISTERED 2026-10-17. Hybrid H = the direct model's mean with
the two-stage model's shape (B@A above), against A, on rec_yds and
rush_yds. Fit on 2017-2025 by the same procedure; scored on every 2026
regular-season game played after 2026-10-17 (`--prospective`). H advances
if its mean CRPS beats A's in both markets with the clustered bound under
zero at 97.5% (0.05 / 2). Nothing in the procedure changes before it reads.

EXP-001b AMENDMENT 1 (2026-10-19, before any game after the freeze was
read): "every 2026 regular-season game played after 2026-10-17" is read
ONCE, when the last of those games is final in the schedule and in
nflverse's weekly file. Until then `--prospective` prints how many rows
have arrived and nothing else — no score, no difference — so no interim
look can steer anything.

KNOWN LIMITS. nflverse's weekly file has a row only when a player recorded
a stat, so a receiver who played and saw no target is missing for both
models alike; the defence step is left out of both (the same in each, so it
cannot favour either); weekly totals have no per-target yards, so B's
yardage given o is a moment-matched approximation, not the true compound.

Reads data/cache (nflverse weekly player stats); writes nothing but a
season file the cache lacks, fetched once through the site's own loader.
"""
from __future__ import annotations

import argparse
import bisect
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import carry as C                                    # noqa: E402
from engine.form import compute_form                             # noqa: E402
from engine.models import GameLog                                # noqa: E402
from engine.nflusage import MIN_EFF_OPPS, ROLE_HALF_LIFE, ewma_opps   # noqa: E402
from engine.sources.nflverse import quarterbacked, stat_value    # noqa: E402

FREEZE = "2026-10-17"
TRAIN = range(2017, 2022)
VALID = range(2022, 2024)
HOLD = range(2024, 2026)
#: market -> (opportunity column, opportunity key, production column, positions)
MARKETS = {"receptions": ("targets", "targets", "receptions", ("WR", "TE", "RB")),
           "rec_yds": ("targets", "targets", "receiving_yards", ("WR", "TE", "RB")),
           "rush_yds": ("carries", "carries", "rushing_yards", ("RB",))}
GRID = {"receptions": [float(t) for t in range(0, 16)],
        "rec_yds": [float(t) for t in range(-10, 255, 5)],
        "rush_yds": [float(t) for t in range(-10, 255, 5)]}
R_GRID = (1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 40.0, 100.0)
K_GRID = (5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0, 640.0, 1280.0)
ALPHA = 0.05 / 3
BOOT = 1000


def _num(row: dict, col: str) -> float:
    try:
        return float(row.get(col) or 0)
    except (TypeError, ValueError):
        return 0.0


#: The columns the lab reads. Keeping only these holds a season in a tenth
#: of the memory, which is what lets the same code run on the 1 GB box.
KEEP = ("player_display_name", "player_name", "position", "position_group", "team", "opponent_team",
        "season", "week", "season_type", "game_id", "targets", "receptions", "receiving_yards",
        "receiving_air_yards", "receiving_yards_after_catch", "carries", "rushing_yards", "attempts")


def load(season: int) -> list[dict]:
    """A season's regular-season weekly rows, from data/cache, fetched once
    through the site's own loader when the cache does not have it."""
    import csv
    path = ROOT / "data" / "cache" / f"player_stats_{season}.csv"
    if not path.exists():
        from engine.sources.nflverse import load_weekly_stats
        load_weekly_stats(season)
    with open(path, newline="") as fh:
        return [{k: r.get(k) for k in KEEP} for r in csv.DictReader(fh)
                if str(r.get("season_type") or "REG") == "REG"]


# --- the rows: one per player-game and market, with what was known before it ---
def _after_freeze() -> set:
    """game_ids of games played after FREEZE (the prospective set)."""
    import csv
    with open(ROOT / "data" / "cache" / "games.csv", newline="") as fh:
        return {g["game_id"] for g in csv.DictReader(fh)
                if (g.get("gameday") or "") > FREEZE and g.get("home_score")}


def rows_for(season: int, only: set | None = None) -> list[dict]:
    """Every row of the season; with ``only``, just the games in it (the
    history before each still comes from every game)."""
    now, before = load(season), load(season - 1)
    prev: dict = defaultdict(list)
    for r in before:
        prev[r["player_display_name"]].append(r)
    mine: dict = defaultdict(list)
    for r in now:
        mine[(r["player_display_name"], r.get("team"))].append(r)
    out = []
    for (name, team), games in mine.items():
        games.sort(key=lambda r: int(float(r["week"])))
        pos = str(games[0].get("position") or "").upper()
        for m, (ocol, okey, pcol, poss) in MARKETS.items():
            if pos not in poss:
                continue
            last = [stat_value(r, m) for r in prev.get(name, ()) if quarterbacked(r, m)]
            gs = [r for r in games if quarterbacked(r, m)]
            k = C.SEASON_PRIOR_GAMES.get(m)
            for i, r in enumerate(gs):
                if int(float(r["week"])) < 4 or i < 3:
                    continue
                hist = gs[:i]
                vals = [stat_value(x, m) for x in hist]
                opps = [_num(x, ocol) for x in hist]
                prods = [_num(x, pcol) for x in hist]
                if sum(opps) < MIN_EFF_OPPS[okey]:
                    continue
                logs = [GameLog(week=int(float(x["week"])), opponent="", value=v)
                        for x, v in zip(hist, vals)][::-1]
                career = sum(vals) / len(vals)
                if compute_form(logs, career, None).mean < C.SEASON_PRIOR_FLOOR[m]:
                    continue
                anchored = bool(k) and len(last) >= C.MIN_PRIOR_GAMES
                form = (compute_form(logs, career, None, prior=sum(last) / len(last), prior_n=len(last),
                                     prior_games=k) if anchored else compute_form(logs, career, None))
                if form.mean <= 0:
                    continue
                if only is not None and r.get("game_id") not in only:
                    continue
                row = {"m": m, "s": season, "pos": "RB" if pos == "RB" else "REC",
                       "who": f"{name}|{season}", "name": name, "team": team, "gid": r.get("game_id"),
                       "week": int(float(r["week"])), "y": stat_value(r, m), "o": _num(r, ocol),
                       "mu_a": form.mean, "mu_o": ewma_opps(opps, ROLE_HALF_LIFE.get(okey)),
                       "opps": sum(opps), "prod": sum(prods)}
                if m == "rec_yds":
                    row["catches"] = sum(_num(x, "receptions") for x in hist)
                out.append(row)
    return out


# --- distributions ----------------------------------------------------------
def nb_pmf(mu: float, r: float, top: int) -> list[float]:
    """NegBin(mean mu, size r) for 0..top, the tail folded into top."""
    p = r / (r + mu)
    out = [p ** r]
    for k in range(1, top + 1):
        out.append(out[-1] * (k - 1 + r) / k * (1 - p))
    out[-1] += max(0.0, 1.0 - sum(out))
    return out


def binom_cdf(t: float, n: int, p: float) -> float:
    if t < 0:
        return 0.0
    if t >= n:
        return 1.0
    acc, term = 0.0, (1 - p) ** n
    for c in range(0, int(math.floor(t)) + 1):
        if c > 0:
            term *= (n - c + 1) / c * (p / (1 - p)) if p < 1 else 0.0
        acc += term
    return min(1.0, acc)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def shrunk(num: float, den: float, prior: float, k: float) -> float:
    return (num + k * prior) / (den + k)


class Fit:
    """Everything B and A take from the training seasons, per market and position."""

    def __init__(self, rows: list[dict]):
        self.pool: dict = defaultdict(list)
        self.r: dict = {}
        self.k: dict = {}
        self.prior: dict = {}
        self.ypc: dict = {}
        self.s2: dict = {}
        by = defaultdict(list)
        for x in rows:
            by[(x["m"], x["pos"])].append(x)
            self.pool[(x["m"], x["pos"])].append(x["y"] / x["mu_a"])
        for key in self.pool:
            self.pool[key].sort()
        for key, xs in by.items():
            m = key[0]
            self.r[key] = max(R_GRID, key=lambda r: sum(_nb_ll(x["o"], x["mu_o"], r) for x in xs))
            self.prior[key] = sum(x["prod"] for x in xs) / max(1e-9, sum(x["opps"] for x in xs))
            if m == "receptions":
                self.k[key] = max(K_GRID, key=lambda k: sum(
                    _bin_ll(x["y"], x["o"], shrunk(x["prod"], x["opps"], self.prior[key], k)) for x in xs))
            elif m == "rec_yds":
                # catch rate from targets, yards per catch, both shrunk by k.
                cr = sum(x["catches"] for x in xs) / max(1e-9, sum(x["opps"] for x in xs))
                yc = sum(x["prod"] for x in xs) / max(1e-9, sum(x["catches"] for x in xs))
                self.prior[key] = (cr, yc)
                self.k[key] = max(K_GRID, key=lambda k: -sum(
                    (x["y"] - x["o"] * shrunk(x["prod"], x["opps"], cr * yc, k)) ** 2 for x in xs))
                # a catch's yards spread, method of moments on games with a catch
                num = den = 0.0
                for x in xs:
                    if x["o"] > 0 and x["y"] != 0:
                        num += (x["y"] - x["o"] * cr * yc) ** 2 - yc * yc * x["o"] * cr * (1 - cr)
                        den += x["o"] * cr
                self.s2[key] = max(25.0, num / max(1e-9, den))
            else:
                self.k[key] = max(K_GRID, key=lambda k: -sum(
                    (x["y"] - x["o"] * shrunk(x["prod"], x["opps"], self.prior[key], k)) ** 2 for x in xs))
                num = sum((x["y"] - x["o"] * self.prior[key]) ** 2 for x in xs if x["o"] > 0)
                den = sum(x["o"] for x in xs if x["o"] > 0)
                self.s2[key] = max(1.0, num / max(1e-9, den))

    def cdf_a(self, x: dict, t: float, mean: float | None = None) -> float:
        pool = self.pool[(x["m"], x["pos"])]
        mu = x["mu_a"] if mean is None else mean
        return bisect.bisect_right(pool, t / mu) / len(pool) if mu > 0 else float(t >= 0)

    def cdf_b(self, x: dict, grid: list[float], scale: float = 1.0) -> list[float]:
        key = (x["m"], x["pos"])
        r = self.r[key]
        top = int(x["mu_o"] + 6 * math.sqrt(x["mu_o"] + x["mu_o"] ** 2 / r) + 3)
        pmf = nb_pmf(max(0.05, x["mu_o"]), r, top)
        k = self.k[key]
        out = [0.0] * len(grid)
        if x["m"] == "receptions":
            p = min(0.98, shrunk(x["prod"], x["opps"], self.prior[key], k))
            for o, po in enumerate(pmf):
                if po < 1e-7:
                    continue
                for j, t in enumerate(grid):
                    out[j] += po * binom_cdf(t / scale, o, p)
            return out
        if x["m"] == "rec_yds":
            cr0, yc0 = self.prior[key]
            p = min(0.98, shrunk(x["catches"], x["opps"], cr0, k))
            ypc = shrunk(x["prod"], max(1e-9, x["catches"]), yc0, k)
            s2 = self.s2[key]
            for o, po in enumerate(pmf):
                if po < 1e-7:
                    continue
                if o == 0:
                    for j, t in enumerate(grid):
                        out[j] += po * float(t >= 0)
                    continue
                p0 = (1 - p) ** o
                ey = o * p * ypc
                vy = o * p * s2 + ypc * ypc * o * p * (1 - p)
                m1 = ey / (1 - p0)
                sd = math.sqrt(max(1.0, (vy + ey * ey) / (1 - p0) - m1 * m1))
                for j, t in enumerate(grid):
                    tt = t / scale
                    out[j] += po * ((p0 if tt >= 0 else 0.0) + (1 - p0) * _phi((tt - m1) / sd))
            return out
        m_ = shrunk(x["prod"], x["opps"], self.prior[key], k)
        s2 = self.s2[key]
        for o, po in enumerate(pmf):
            if po < 1e-7:
                continue
            for j, t in enumerate(grid):
                tt = t / scale
                out[j] += po * (float(tt >= 0) if o == 0 else _phi((tt - o * m_) / math.sqrt(o * s2)))
        return out

    def mean_b(self, x: dict) -> float:
        key = (x["m"], x["pos"])
        k = self.k[key]
        if x["m"] == "receptions":
            return x["mu_o"] * shrunk(x["prod"], x["opps"], self.prior[key], k)
        if x["m"] == "rec_yds":
            cr0, yc0 = self.prior[key]
            return x["mu_o"] * shrunk(x["catches"], x["opps"], cr0, k) * shrunk(x["prod"], max(1e-9, x["catches"]), yc0, k)
        return x["mu_o"] * shrunk(x["prod"], x["opps"], self.prior[key], k)


def _nb_ll(y: float, mu: float, r: float) -> float:
    mu = max(0.05, mu)
    y = int(round(y))
    return (math.lgamma(y + r) - math.lgamma(r) - math.lgamma(y + 1)
            + r * math.log(r / (r + mu)) + y * math.log(mu / (r + mu)))


def _bin_ll(y: float, n: float, p: float) -> float:
    n, y = int(round(n)), int(round(y))
    if y > n:
        return -50.0
    p = min(max(p, 1e-4), 1 - 1e-4)
    return (math.lgamma(n + 1) - math.lgamma(y + 1) - math.lgamma(n - y + 1)
            + y * math.log(p) + (n - y) * math.log(1 - p))


# --- scoring ----------------------------------------------------------------
def crps(cdf: list[float], grid: list[float], y: float) -> float:
    """Σ (F(t) - 1{y <= t})^2 · Δt on the grid (Δt = 1 for the count grid: the RPS)."""
    step = grid[1] - grid[0]
    return sum((f - (1.0 if y <= t else 0.0)) ** 2 for f, t in zip(cdf, grid)) * step


def score(rows: list[dict], fit: Fit) -> list[dict]:
    out = []
    for x in rows:
        grid = GRID[x["m"]]
        fa = [fit.cdf_a(x, t) for t in grid]
        fb = fit.cdf_b(x, grid)
        mb = fit.mean_b(x)
        fba = fit.cdf_b(x, grid, scale=x["mu_a"] / mb) if mb > 0 else fb
        # the proxy line: A's median, to the half below it
        med = next((t for t, f in zip(grid, fa) if f >= 0.5), grid[-1])
        line = math.floor(med) + 0.5 if x["m"] == "receptions" else math.floor(med) + 0.5
        over = 1.0 if x["y"] > line else 0.0
        pa = 1.0 - _cdf_at(fit, x, line, "a")
        pb = 1.0 - _cdf_at(fit, x, line, "b")
        out.append({"m": x["m"], "s": x["s"], "who": x["who"], "y": x["y"],
                    "a": crps(fa, grid, x["y"]), "b": crps(fb, grid, x["y"]), "ba": crps(fba, grid, x["y"]),
                    "brier_a": (pa - over) ** 2, "brier_b": (pb - over) ** 2, "pb": pb, "over": over,
                    "mae_a": abs(x["y"] - x["mu_a"]), "mae_b": abs(x["y"] - mb)})
    return out


def _cdf_at(fit: Fit, x: dict, t: float, which: str) -> float:
    return fit.cdf_a(x, t) if which == "a" else fit.cdf_b(x, [t])[0]


def boot_diff(scored: list[dict], key_b: str = "b", key_a: str = "a", seed: int = 7) -> tuple:
    """Mean of CRPS(B) - CRPS(A) and its two-sided (1 - ALPHA) interval,
    resampling whole player-seasons (a player's games are not independent)."""
    by = defaultdict(list)
    for p in scored:
        by[p["who"]].append(p[key_b] - p[key_a])
    groups = list(by.values())
    n = sum(len(g) for g in groups)
    mean = sum(sum(g) for g in groups) / n
    rng = random.Random(seed)
    sums = [(sum(g), len(g)) for g in groups]
    stats = []
    for _ in range(BOOT):
        tot = cnt = 0.0
        for _ in range(len(sums)):
            s, c = sums[rng.randrange(len(sums))]
            tot += s
            cnt += c
        stats.append(tot / cnt)
    stats.sort()
    lo = stats[int(BOOT * ALPHA / 2)]
    hi = stats[min(BOOT - 1, int(BOOT * (1 - ALPHA / 2)))]
    return mean, lo, hi


def decide(valid_diff: float, hold: tuple | None) -> str:
    if valid_diff >= 0:
        return "REJECTED (validation)"
    if hold is None:
        return "validation passed; holdout not yet read"
    mean, _lo, hi = hold
    if mean >= 0:
        return "REJECTED (holdout)"
    return "ADVANCE" if hi < 0 else "INCONCLUSIVE"


def calibration(scored: list[dict]) -> list[tuple]:
    pts = sorted(scored, key=lambda p: p["pb"])
    n = len(pts)
    out = []
    for d in range(10):
        part = pts[d * n // 10:(d + 1) * n // 10]
        if part:
            out.append((round(sum(p["pb"] for p in part) / len(part), 3),
                        round(sum(p["over"] for p in part) / len(part), 3), len(part)))
    return out


def summarise(scored: list[dict], m: str) -> dict:
    t = [p for p in scored if p["m"] == m]
    n = len(t)
    return {"n": n, "players": len({p["who"] for p in t}),
            "crps_a": sum(p["a"] for p in t) / n, "crps_b": sum(p["b"] for p in t) / n,
            "crps_ba": sum(p["ba"] for p in t) / n,
            "brier_a": sum(p["brier_a"] for p in t) / n, "brier_b": sum(p["brier_b"] for p in t) / n,
            "mae_a": sum(p["mae_a"] for p in t) / n, "mae_b": sum(p["mae_b"] for p in t) / n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="also score 2024-2025 (run once)")
    ap.add_argument("--prospective", action="store_true",
                    help=f"EXP-001b: fit 2017-2025, score 2026 games played after {FREEZE}")
    a = ap.parse_args(argv)
    if a.prospective:
        return prospective()
    train = [x for s in TRAIN for x in rows_for(s)]
    fit = Fit(train)
    print(f"EXP-001 two-stage vs direct — fitted on {TRAIN.start}-{TRAIN.stop - 1}, {len(train):,} rows")
    for key in sorted(fit.r):
        print(f"  fit {key[0]:<10} {key[1]:<3} NB size {fit.r[key]:g}  shrink k {fit.k[key]:g}"
              + (f"  spread² {fit.s2[key]:.1f}" if key in fit.s2 else ""))
    periods = [("validation", VALID)] + ([("holdout", HOLD)] if a.holdout else [])
    results: dict = {}
    for label, seasons in periods:
        scored = score([x for s in seasons for x in rows_for(s)], fit)
        results[label] = scored
        print(f"\n{label} {seasons.start}-{seasons.stop - 1}")
        for m in MARKETS:
            sm = summarise(scored, m)
            diff = boot_diff([p for p in scored if p["m"] == m])
            print(f"  {m:<10} n={sm['n']:,} ({sm['players']:,} player-seasons)  CRPS A {sm['crps_a']:.4f}  "
                  f"B {sm['crps_b']:.4f}  B@A-mean {sm['crps_ba']:.4f}  | B-A {diff[0]:+.4f} "
                  f"[{diff[1]:+.4f}, {diff[2]:+.4f}]  | Brier@proxy A {sm['brier_a']:.4f} B {sm['brier_b']:.4f}"
                  f"  | MAE A {sm['mae_a']:.2f} B {sm['mae_b']:.2f}")
    print("\nDecision (bar written before the run):")
    for m in MARKETS:
        v = summarise(results["validation"], m)
        hold = boot_diff([p for p in results["holdout"] if p["m"] == m]) if "holdout" in results else None
        print(f"  {m:<10} {decide(v['crps_b'] - v['crps_a'], hold)}")
    if "holdout" in results:
        print("\nB's over-probability calibration on the holdout (forecast, observed, n) by decile:")
        for m in MARKETS:
            print(f"  {m:<10} " + "  ".join(f"{f:.2f}/{o:.2f}" for f, o, _n in
                                           calibration([p for p in results["holdout"] if p["m"] == m])))
    return 0


def season_done(season: int = 2026, after: str = FREEZE, games=None, with_stats=None) -> tuple[int, int]:
    """(games after ``after`` final and in nflverse's weekly file, all
    regular-season games after it) — EXP-001b reads when the two match.
    ``games`` and ``with_stats`` default to the cache's files."""
    import csv
    if games is None:
        with open(ROOT / "data" / "cache" / "games.csv", newline="") as fh:
            games = list(csv.DictReader(fh))
    games = [g for g in games if str(g.get("season")) == str(season)
             and (g.get("game_type") or "REG") == "REG" and (g.get("gameday") or "") > after]
    if with_stats is None:
        try:
            with_stats = {r.get("game_id") for r in load(season)}
        except Exception:                                     # noqa: BLE001 — no weekly file yet
            with_stats = set()
    done = sum(1 for g in games if str(g.get("home_score") or "").strip() != "" and g["game_id"] in with_stats)
    return done, len(games)


def prospective() -> int:
    """EXP-001b as preregistered: hybrid (A's mean, B's shape) against A,
    read once when the regular season after the freeze is complete."""
    global ALPHA
    done, total = season_done()
    games = _after_freeze()
    if not total or done < total:
        n = sum(1 for x in rows_for(2026, only=games) if x["m"] in ("rec_yds", "rush_yds")) if games else 0
        print(f"EXP-001b prospective — {done} of {total} regular-season games after {FREEZE} final with stats; "
              f"{n:,} rows so far. Read once when all are in (AMENDMENT 1); nothing scored until then.")
        return 0
    fit = Fit([x for s in range(2017, 2026) for x in rows_for(s)])
    scored = [p for p in score(rows_for(2026, only=games), fit) if p["m"] in ("rec_yds", "rush_yds")]
    print(f"EXP-001b prospective — 2026 games after {FREEZE}: {len(games)} games, {len(scored)} rows")
    if not scored:
        print("  nothing played since the freeze yet")
        return 0
    ALPHA, keep = 0.05 / 2, ALPHA
    try:
        ok = True
        for m in ("rec_yds", "rush_yds"):
            t = [p for p in scored if p["m"] == m]
            if not t:
                ok = False
                print(f"  {m:<10} no rows yet")
                continue
            mean, lo, hi = boot_diff(t, key_b="ba")
            ok = ok and hi < 0
            print(f"  {m:<10} n={len(t):,}  CRPS A {sum(p['a'] for p in t) / len(t):.4f}  "
                  f"H {sum(p['ba'] for p in t) / len(t):.4f}  H-A {mean:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        print(f"  decision: {'ADVANCE' if ok else 'not yet / does not hold'} (needs both bounds under zero)")
    finally:
        ALPHA = keep
    return 0


if __name__ == "__main__":
    sys.exit(main())
