"""Measure the correlation priors against our own history.

The parlay instruction set's Appendix is unusually honest about its own
numbers: the rho magnitudes "are professional estimates, not measured
constants," and it lists the order to go and measure them in. Everything in
engine/parlays.py currently runs on those estimates, read at the midpoint of
each published band and then shrunk by the humility clamp. That is a
defensible way to price a guess. It is not a measurement, and the difference
matters more here than almost anywhere else in this engine — a correlation
prior is the ONLY thing standing between a same-game ticket and being priced
as if its legs were independent.

So this measures them. For each pairing the doc names, it pulls every game
where both legs existed, computes the Pearson correlation of the two
underlying CONTINUOUS stats, and reports it against the published band with
a sample size and a standard error.

Why Pearson on the raw stats rather than on win/lose outcomes: the copula in
parlays.py treats each prior as a LATENT correlation between the underlying
quantities and derives the binary joint from it. Measuring the same quantity
the model consumes is the whole point; measuring the phi coefficient of two
over/unders would produce a systematically smaller number that could not be
fed back in without double-shrinking it.

    python3 -m engine.corrfit                # every pairing the DB supports
    python3 -m engine.corrfit --sport nfl
    python3 -m engine.corrfit --min-games 200

What it cannot do is invent data. A pairing whose markets are not in the
history reports "no sample" and says which market was missing, rather than
quietly measuring a subset and calling it the answer.

AND IT NOW FEEDS ITSELF BACK (2026-08-26). For its first three weeks this
module was the only fitter on the site that a human had to remember to
run: you typed the command, read the table, and hand-copied five numbers
into `engine/parlays.MEASURED` — translating between two naming schemes
and flipping one sign on the way. Every other loop here refits on the
nightly settle. This one was frozen at the day somebody last did the
copying, and nothing could tell you it had drifted.

So `refresh()` fits and PERSISTS, the parlay pricer reads the persisted
fit first, and the hand-taken table stays as the floor underneath it.
The adoption rule is the conservative one: a fresh fit replaces a
standing number only when it is measured on **at least as many games**.
That matters because these estimators are sample-shaped — the
possession-pie partial reads -0.560 on five NFL seasons and -0.045 on
one, which is not noise but a different question being answered by a
different data depth — so a thin box must never overwrite a rich fit
with a worse one.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field

from . import feedstate as _feedstate


# --- the claims under test ---------------------------------------------------
@dataclass(frozen=True)
class Prior:
    """One row of a §4-§8 correlation table, as a testable claim."""

    key: str
    sport: str
    band: tuple[float, float]
    section: str
    note: str
    # How to pull the two series. `kind` selects a join strategy below.
    kind: str
    a: str = ""
    b: str = ""


PRIORS: tuple[Prior, ...] = (
    Prior("qb_pass_yds__wr_rec_yds", "nfl", (0.35, 0.50), "§4.1",
          "the strongest usable NFL correlation, and the anchor of §4.2's "
          "passing-game stack", "teammates", "pass_yds", "rec_yds"),
    Prior("qb_pass_yds__wr_receptions", "nfl", (0.35, 0.50), "§4.1",
          "same mechanism on the Tier 1 volume market §4 wants as the anchor",
          "teammates", "pass_yds", "receptions"),
    Prior("wr_rec_yds__wr2_rec_yds", "nfl", (-0.10, 0.10), "§4.1",
          "Type 3 possession pie — two teammates splitting one set of targets",
          "same_market_teammates", "rec_yds", "rec_yds"),
    Prior("qb_pass_yds__own_points", "nfl", (0.30, 0.45), "§4.1",
          "a quarterback's yardage against his own team's total", "team_points",
          "pass_yds"),
    Prior("rb_carries__own_margin", "nfl", (0.35, 0.50), "§4.1",
          "leading teams run — carries against the team's own result",
          "team_margin", "carries"),
    Prior("rb_rush_yds__own_margin", "nfl", (0.35, 0.50), "§4.1",
          "the same claim on yards rather than volume", "team_margin",
          "rush_yds"),
    Prior("wr_receptions__own_margin", "nfl", (-0.35, -0.20), "§4.1",
          "the trailing-dog mechanism, signed: falling behind means throwing. "
          "§4.1 states it as dog-covers against dog-receptions (+0.20 to "
          "+0.35), so measured against MARGIN the sign inverts",
          "team_margin", "receptions"),
    Prior("both_teams_overs__pace", "nfl", (0.15, 0.30), "§4.1",
          "the pace link across the two sides of one game", "cross_team",
          "rec_yds", "rec_yds"),
    # MLB — measurable the moment the history carries the markets.
    Prior("sp_strikeouts__opp_runs", "mlb", (-0.35, -0.20), "§5.1",
          "§5.2's pitcher stack: strikeouts against the runs the lineup he is "
          "facing scores. §5.1 states it as K-over against opposing-total "
          "UNDER (+0.20 to +0.35), so against RUNS the sign inverts",
          "opp_points", "strikeouts"),
    Prior("sp_outs__own_margin", "mlb", (0.20, 0.35), "§5.1",
          "managers leave winners in", "team_margin", "outs"),
    Prior("two_hitters_total_bases", "mlb", (0.20, 0.35), "§5.1",
          "two bats in one lineup against one starter", "same_market_teammates",
          "total_bases", "total_bases"),
)


# --- statistics --------------------------------------------------------------
def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def partial(xs: list[float], ys: list[float], zs: list[float]) -> float:
    """Correlation of x and y with z held fixed.

    r_xy.z = (r_xy - r_xz*r_yz) / sqrt((1-r_xz^2)(1-r_yz^2))
    """
    rxy, rxz, ryz = pearson(xs, ys), pearson(xs, zs), pearson(ys, zs)
    den = math.sqrt(max(0.0, (1 - rxz ** 2) * (1 - ryz ** 2)))
    if den <= 1e-12:
        return float("nan")
    return (rxy - rxz * ryz) / den


def stderr(r: float, n: int) -> float:
    """Fisher-z standard error, back-transformed to the r scale.

    A correlation's sampling distribution is skewed, so the naive
    sqrt((1-r^2)/(n-2)) understates the interval at the ends. Fisher's z is
    approximately normal with SE 1/sqrt(n-3), which is the honest one to
    print next to a number this small.
    """
    if n < 5 or abs(r) >= 1:
        return float("nan")
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    lo, hi = math.tanh(z - se), math.tanh(z + se)
    return (hi - lo) / 2


@dataclass
class Fit:
    prior: Prior
    n: int = 0
    r: float = float("nan")
    se: float = float("nan")
    missing: str = ""
    pairs: list = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.missing:
            return f"no sample — {self.missing}"
        if self.n < 30:
            return f"too thin to read ({self.n} games)"
        lo, hi = self.prior.band
        if lo <= self.r <= hi:
            return "inside the published band"
        if self.r < lo:
            gap = lo - self.r
            return (f"{gap:+.2f} BELOW the band — the model is claiming more "
                    f"correlation than the history shows")
        return (f"{self.r - hi:+.2f} above the band — the model is leaving "
                f"correlation on the table")


# --- pulling the series ------------------------------------------------------
# The two tables do not share a game id. player_game_logs writes "TEN-001";
# games writes "DAL@TB". Nothing can be joined on it, which silently made
# every game-context measurement below return zero rows — the tool reported
# "too thin to read (0 games)" for six priors on a database holding five
# full seasons. Season + period + team is the key both tables really share.
def _logs(conn, sport: str, market: str) -> dict:
    """{(season, period, team): [(player, value), ...]} for one market."""
    out: dict = {}
    for row in conn.execute(
            "SELECT season, period, team, player, value FROM player_game_logs "
            "WHERE sport=? AND market=? AND value IS NOT NULL", (sport, market)):
        out.setdefault((row[0], row[1], row[2]), []).append(
            (row[3], float(row[4])))
    return out


def _scores(conn, sport: str) -> dict:
    """{(season, period, team): (points_for, points_against)}."""
    out: dict = {}
    for season, period, home, away, hs, aws in conn.execute(
            "SELECT season, period, home, away, home_score, away_score "
            "FROM games WHERE sport=? AND home_score IS NOT NULL "
            "AND away_score IS NOT NULL", (sport,)):
        out[(season, period, home)] = (float(hs), float(aws))
        out[(season, period, away)] = (float(aws), float(hs))
    return out


def _top(rows: list) -> tuple:
    """The busiest player on a team in a game — the one a prop would be on.

    Taking every teammate instead would measure "any receiver against any
    quarterback", which is a different and much noisier claim than the one
    §4.1 makes about WR1.
    """
    return max(rows, key=lambda t: t[1])


def fit_one(conn, prior: Prior, min_games: int = 30) -> Fit:
    f = Fit(prior)
    kind = prior.kind

    if kind in ("teammates", "same_market_teammates", "cross_team"):
        A, B = _logs(conn, prior.sport, prior.a), _logs(conn, prior.sport, prior.b)
        if not A:
            f.missing = f"no {prior.a} logs for {prior.sport}"
            return f
        if not B:
            f.missing = f"no {prior.b} logs for {prior.sport}"
            return f
        xs, ys = [], []
        if kind == "teammates":
            for key, arows in A.items():
                brows = B.get(key)
                if not brows:
                    continue
                xs.append(_top(arows)[1])
                ys.append(_top(brows)[1])
        elif kind == "same_market_teammates":
            # §3 Type 3's claim is that two teammates COMPETE for a finite
            # pool. Raw correlation cannot see that, because both are driven
            # by how big the pool was: WR1 and WR2 both go up in a 400-yard
            # passing game, and measured raw this pairing came out at +0.70
            # against a published band of -0.10 to +0.10. That is not the
            # doc being wrong — it is the wrong measurement. Cannibalisation
            # is what is left AFTER the shared volume is accounted for, so
            # this is a partial correlation holding the team's total in the
            # market fixed.
            zs = []
            for key, rows in A.items():
                if len(rows) < 2:
                    continue
                top2 = sorted(rows, key=lambda t: -t[1])[:2]
                xs.append(top2[0][1])
                ys.append(top2[1][1])
                zs.append(sum(v for _, v in rows))
            f.n = len(xs)
            if f.n >= 3:
                f.r = partial(xs, ys, zs)
                f.se = stderr(f.r, f.n - 1)
            return f
        else:                                    # cross_team: the pace link
            by_game: dict = {}
            for (season, period, _team), rows in A.items():
                by_game.setdefault((season, period), []).append(_top(rows)[1])
            for vals in by_game.values():
                if len(vals) >= 2:
                    xs.append(vals[0])
                    ys.append(vals[1])
    else:
        A = _logs(conn, prior.sport, prior.a)
        if not A:
            f.missing = f"no {prior.a} logs for {prior.sport}"
            return f
        scores = _scores(conn, prior.sport)
        if not scores:
            f.missing = f"no finished {prior.sport} games with scores"
            return f
        xs, ys = [], []
        for key, rows in A.items():
            sc = scores.get(key)
            if sc is None:
                continue
            pf, pa = sc
            xs.append(_top(rows)[1])
            ys.append(pf if kind == "team_points"
                      else pa if kind == "opp_points" else pf - pa)

    f.n = len(xs)
    if f.n >= 3:
        f.r = pearson(xs, ys)
        f.se = stderr(f.r, f.n)
    return f


def fit_all(db: str = "data/history.db", sport: str | None = None,
            min_games: int = 30) -> list[Fit]:
    conn = sqlite3.connect(db)
    try:
        return [fit_one(conn, p, min_games) for p in PRIORS
                if sport is None or p.sport == sport]
    finally:
        conn.close()


def report(fits: list[Fit]) -> None:
    print("\nCORRELATION PRIORS vs OUR OWN HISTORY")
    print("The Appendix calls these \"professional estimates, not measured")
    print("constants\". This is the measurement.\n")
    for f in fits:
        p = f.prior
        lo, hi = p.band
        print(f"  {p.sport.upper():5s} {p.key}")
        print(f"        {p.section}  band {lo:+.2f} to {hi:+.2f}  ·  {p.note}")
        if f.missing:
            print(f"        → {f.verdict}\n")
            continue
        se = "" if f.se != f.se else f"  ±{f.se:.3f}"
        print(f"        measured {f.r:+.3f}{se}  over {f.n:,} game(s)")
        print(f"        → {f.verdict}\n")
    usable = [f for f in fits if not f.missing and f.n >= 30]
    inside = [f for f in usable if f.prior.band[0] <= f.r <= f.prior.band[1]]
    print(f"  {len(inside)} of {len(usable)} measurable prior(s) landed inside "
          f"their published band.")
    if len(usable) < len(fits):
        print(f"  {len(fits) - len(usable)} could not be measured from this "
              f"database — the markets are not ingested here.")


# --- feeding it back --------------------------------------------------------
#: Which fitted pairing feeds which `engine.parlays.MEASURED` entry, and
#: whether the sign flips on the way. The flip is not a detail: §5.1
#: states the pitcher pairing as strikeouts-over against the opposing
#: total UNDER, and this module measures strikeouts against the RUNS that
#: lineup scores, which is the same claim with the opposite sign. It was
#: done by hand, in a comment, once. Now it is a table a test can read.
ADOPT: dict[str, tuple[str, int]] = {
    "qb_pass_yds__wr_rec_yds": ("qb_passing_game", +1),
    "wr_rec_yds__wr2_rec_yds": ("possession_pie", +1),
    "rb_rush_yds__own_margin": ("run_game_script", +1),
    "sp_strikeouts__opp_runs": ("pitcher_vs_lineup", -1),
    "two_hitters_total_bases": ("lineup_stack", +1),
}

#: Below this a correlation is a rumour. The standing hand-taken numbers
#: were fitted on 2,844 to 27,613 games; this is the floor under the
#: floor, for a pairing that has no standing number at all.
MIN_N = 500

# --- when a bigger sample is not better evidence -----------------------------
#
# THE CASE THIS EXISTS FOR, found 2026-08-27 by ingesting four NFL
# seasons and refitting. The standing `possession_pie` is -0.560 on
# 2,848 games. Today's code, on 2,278 games of the same league with a
# stable shape across all four seasons, measures -0.098 ± 0.021. That is
# a twenty-two sigma disagreement, which no amount of extra season
# explains — and the "never displace a better-sampled number" rule was
# dutifully protecting the older one.
#
# THE DATES SAY WHY. The hand-taken table was written on 2026-08-02. The
# ingest that widened `rec_yds` from WIDE RECEIVERS ONLY to every
# position landed on 2026-08-15. "The team's total receiving yards" —
# the quantity this pairing's partial correlation holds fixed — is a
# different number before and after that, and with only wide receivers
# in the pool the top two ARE most of the total, which forces the
# partial hard negative. The measurement was correct on the day. What
# changed was the data underneath it, and a sample count cannot see
# that: it compares how MANY, never of what.
#
# So the rule gains a second door. A standing number the current code
# cannot reproduce is not evidence, it is a record of an older schema,
# and a well-sampled precise fit supersedes it however many games it
# claims. Both halves are needed: without the sample floor one thin
# season could overturn a real measurement, and without the sigma test a
# stale constant outlives every ingest change forever.

#: A fit may supersede a better-sampled standing number only on a sample
#: this size. One NFL season is 570 team-games, so a single season can
#: never do it; four can.
REPRO_MIN_N = 1000

#: ...and only when the fit is precise enough for the disagreement to
#: mean something.
REPRO_MAX_SE = 0.05

#: Standard errors of disagreement before the standing number is treated
#: as unreproducible. Season-to-season drift lands inside this; a schema
#: change does not.
REPRO_SIGMA = 4.0

#: A fitted |r| this close to 1 is a broken join, not a discovery — two
#: series that are the same column, or a partial whose covariate has
#: collapsed onto its own inputs.
MAX_ABS_R = 0.95

#: Beside the other feed state, on the relative path every feedstate file
#: uses (builds and the settle both run from the repo root).
STATE_PATH = _feedstate.path("corr.json")

_cache: dict = {}


def _standing_r(parlay_key: str) -> float | None:
    """The rho currently in use from the hand-taken table, or None."""
    try:
        from .parlays import MEASURED
        hit = MEASURED.get(parlay_key)
        return float(hit[0]) if hit else None
    except Exception:                                        # noqa: BLE001
        return None


def _standing_n(parlay_key: str) -> int:
    """How well sampled the number currently in use is.

    Read from `engine.parlays` rather than duplicated here, so the two
    cannot disagree about what is standing. An import failure means no
    floor to clear, which is the safe direction: MIN_N still applies.
    """
    try:
        from .parlays import MEASURED
        hit = MEASURED.get(parlay_key)
        return int(hit[1]) if hit else 0
    except Exception:                                        # noqa: BLE001
        return 0


def refresh(db="data/history.db", sport: str | None = None) -> dict:
    """Fit every adoptable pairing and persist the ones that earned it.

    Returns ``{"adopted": [...], "held": [...]}`` — held entries carry
    the reason, because a fit that quietly declines to adopt is the same
    invisibility this whole change exists to remove.
    """
    conn = db if hasattr(db, "execute") else sqlite3.connect(db)
    own = conn is not db
    try:
        fits = [fit_one(conn, p) for p in PRIORS
                if p.key in ADOPT and (sport is None or p.sport == sport)]
    finally:
        if own:
            conn.close()
    state = _read_state()
    adopted, held = [], []
    for f in fits:
        parlay_key, sign = ADOPT[f.prior.key]
        floor = max(MIN_N, _standing_n(parlay_key))
        if f.missing:
            held.append({"key": parlay_key, "why": f.missing})
            continue
        if f.r != f.r or abs(f.r) > MAX_ABS_R:
            held.append({"key": parlay_key, "why": f"unusable r={f.r}"})
            continue
        fitted = sign * f.r
        standing = _standing_r(parlay_key)
        sigma = None
        if (standing is not None and f.se == f.se and f.se
                and f.n >= REPRO_MIN_N and f.se <= REPRO_MAX_SE):
            sigma = abs(fitted - standing) / f.se
        unreproducible = sigma is not None and sigma >= REPRO_SIGMA
        if f.n < floor and not unreproducible:
            held.append({"key": parlay_key,
                         "why": f"{f.n} games, needs {floor}"})
            continue
        entry = {"r": round(fitted, 4), "n": int(f.n),
                 "se": None if f.se != f.se else round(f.se, 4),
                 "from": f.prior.key, "sport": f.prior.sport,
                 "fit_at": time.time()}
        if unreproducible:
            # Kept in the state file, because a number that quietly
            # replaced another one is the thing this module exists to
            # stop happening.
            entry["superseded"] = {"was": standing, "sigma": round(sigma, 1)}
        state[parlay_key] = entry
        adopted.append({"key": parlay_key, **entry})
    if adopted:
        _write_state(state)
        _cache.clear()
    return {"adopted": adopted, "held": held}


def _read_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


def measured(name: str) -> dict | None:
    """The persisted fit for one parlay pairing, or None.

    Never raises: this is read on the pricing path for every same-game
    ticket, and a half-written state file must cost the refinement, not
    the board.
    """
    if name in _cache:
        return _cache[name]
    entry = _read_state().get(name)
    if entry is not None:
        try:
            ok = (abs(float(entry["r"])) <= MAX_ABS_R
                  and int(entry["n"]) >= MIN_N)
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            entry = None
    _cache[name] = entry
    return entry


if __name__ == "__main__":                       # pragma: no cover
    import sys
    argv = sys.argv[1:]
    sport = argv[argv.index("--sport") + 1] if "--sport" in argv else None
    db = argv[argv.index("--db") + 1] if "--db" in argv else "data/history.db"
    report(fit_all(db=db, sport=sport))
