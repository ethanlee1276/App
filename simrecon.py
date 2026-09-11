"""Does the game sim's joint actually beat the measured prior? — task #60.

`engine/mlb/simjoint.py` already hands the Parlay Zone a lineup-specific
correlation, dealt out of the same simulated innings as the two legs it
prices. It shipped behind two structural gates (marginals must reconcile,
the solved rho may not drift far from the prior) — but no OUTCOME has ever
graded it. "The sim knows the leadoff pair from the leadoff-and-eight
pair" is an argument; whether that knowledge prices real nights better
than +0.186-for-everyone is a measurement, and this file is it.

THE BAR, DECLARED BEFORE ANY RESULT (the same discipline as
engine/nfl/prefit.py — written above the answer so it cannot be talked
into place afterwards):

  * Scored on at least MIN_PAIRS (500) teammate pairs.
  * The sim KEEPS its seat in pricing if its mean log-loss is not worse
    than the measured prior's by more than one standard error of the
    paired per-pair difference.
  * It is called an IMPROVEMENT only when better by at least two of those
    standard errors.
  * Worse by more than one — the honest action is printed at the bottom
    of the run: set `engine/mlb/simjoint.ENABLED = False`, and every pair
    keeps the 27,613-game prior, exactly as before #60.

All three competitors are scored from IDENTICAL marginals — the sim's own
p1 and p2 — so the only thing that differs between them is the dependence:

    independence      p1 * p2
    measured prior    joint_two(p1, p2, +0.186)   (the Gaussian copula)
    the sim           its own tallied P(both)

TWO ARMS, BECAUSE THE CLEAN DATA IS THIN AND THE THICK DATA IS BLURRED.

History arm (`--history`): every completed MLB team-game in the window is
replayed — projections rebuilt from each hitter's PRIOR games only, through
the same `build_mlb_projection` the live board prices with (neutral game:
this grades the correlation structure, not the park model). One handicap,
named rather than hidden: the DB does not store historical batting orders,
so lineup spots are inferred by ranking each night's hitters on their
as-of plate-appearance rate. That blurs exactly the adjacency signal the
sim claims as its edge — so a WIN here understates the live sim, and only
a LOSS here should be read at face value.

Forward arm (`--forward`): grades `data/simrecon_log.jsonl`, which
`simjoint.build` appends — every candidate pair it actually solved on a
live slate, with the true lineup card behind it. Real lines, real orders,
zero leakage; a few pairs a night. The two arms answer the same question
from opposite ends, and the verdict prints both.

    python3 simrecon.py                    # both arms, 30-day history window
    python3 simrecon.py --days 60          # longer replay (roughly linear cost)
    python3 simrecon.py --forward-only     # just grade the live journal

Read-only against the DB; writes nothing but its own printout.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.mlb import gamesim as G                          # noqa: E402
from engine.mlb.models import (                              # noqa: E402
    HITS, HOME_RUNS, TOTAL_BASES, MLBGameLog, MLBProp,
)
from engine.models import SportsbookLine                     # noqa: E402
from engine.parlays import MEASURED, joint_two               # noqa: E402

DB_PATH = "data/history.db"
LOG_PATH = "data/simrecon_log.jsonl"

#: The verdict's floor. Below this many scored pairs the answer is "keep
#: collecting", never a pass or a fail.
MIN_PAIRS = 500

#: Verdict lines at which the two hitter markets are scored. Book-standard
#: numbers; home runs are graded too but reported OUTSIDE the verdict —
#: at 20,000 trials a 6% joint moves visibly on sampler noise alone, and a
#: verdict that noise can flip is not a verdict.
VERDICT_LINES = {HITS: 1.5, TOTAL_BASES: 1.5}
EXTRA_LINES = {HOME_RUNS: 0.5}

#: A hitter needs this many PRIOR games before his projection is evidence —
#: the same floor the walk-forward backtest uses.
MIN_HISTORY = 8

#: Prior-game cap per projection, most recent first (mirrors the backtest).
LOG_LIMIT = 40

PRIOR_RHO = MEASURED["lineup_stack"][0]
PRIOR_N = MEASURED["lineup_stack"][1]

EPS = 1e-6


# --- scoring -----------------------------------------------------------------
def _ll(p: float, hit: bool) -> float:
    p = min(1.0 - EPS, max(EPS, p))
    return -math.log(p if hit else 1.0 - p)


class Tally:
    """Paired scores for the three competitors over one set of pairs."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, p_ind: float, p_prior: float, p_sim: float,
            hit: bool, adjacent: bool | None) -> None:
        self.rows.append({
            "ind": _ll(p_ind, hit), "prior": _ll(p_prior, hit),
            "sim": _ll(p_sim, hit),
            "b_ind": (p_ind - hit) ** 2, "b_prior": (p_prior - hit) ** 2,
            "b_sim": (p_sim - hit) ** 2,
            "hit": bool(hit), "adjacent": adjacent,
        })

    @property
    def n(self) -> int:
        return len(self.rows)

    def mean(self, key: str) -> float:
        return sum(r[key] for r in self.rows) / self.n if self.rows else 0.0

    def diff_se(self, a: str = "sim", b: str = "prior") -> tuple[float, float]:
        """Mean paired difference a-b and its standard error.

        Paired, because every pair is scored by all three competitors on
        the same night — the night-to-night variance that dominates an
        unpaired comparison cancels out of the difference."""
        ds = [r[a] - r[b] for r in self.rows]
        if not ds:
            return 0.0, float("inf")
        m = sum(ds) / len(ds)
        if len(ds) < 2:
            return m, float("inf")
        var = sum((d - m) ** 2 for d in ds) / (len(ds) - 1)
        return m, math.sqrt(var / len(ds))

    def subset(self, pred) -> "Tally":
        t = Tally()
        t.rows = [r for r in self.rows if pred(r)]
        return t


# --- the history arm ---------------------------------------------------------
#: Doubleheader leg suffix on a log row's game_id ("...-G2" = second game).
_LEG_RE = re.compile(r"-G(\d+)$")


def _mlb_rows(conn, days: int) -> dict:
    """(period, team, leg) -> {player: {market: value}} for the window.

    The window is the most recent ``days`` DISTINCT slate dates with MLB
    logs, not calendar days — an All-Star break must not silently shrink
    the sample.

    The key deliberately does NOT include game_id: the ingest writes MLB
    log rows with a PER-PLAYER game_id ("{player}-{date}", plus "-G2" for
    a doubleheader's second leg — engine/ingest.py). Grouping on it hands
    every "lineup" exactly one hitter, and the six-hitter gate then fails
    on all of them — the first run against real data replayed 8,619 such
    groups and scored zero. A team's slate date IS its lineup card; the
    leg parsed off the suffix keeps a doubleheader's halves apart."""
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT period FROM player_game_logs WHERE sport='mlb' "
        "ORDER BY period DESC LIMIT ?", (days,))]
    if not dates:
        return {}
    marks = (HITS, TOTAL_BASES, HOME_RUNS, "pa")
    out: dict = defaultdict(dict)
    q = ("SELECT period, game_id, team, player, market, value "
         "FROM player_game_logs WHERE sport='mlb' AND period >= ? "
         f"AND market IN ({','.join('?' * len(marks))})")
    for period, gid, team, player, market, value in conn.execute(
            q, (min(dates), *marks)):
        m = _LEG_RE.search(gid or "")
        leg = int(m.group(1)) if m else 1
        out[(period, team, leg)].setdefault(player, {})[market] = float(value)
    return out


def _histories(conn, first_date: str) -> dict:
    """player -> chronological [(period, {market: value})] BEFORE the window
    plus inside it (each replayed date slices strictly earlier rows)."""
    marks = (HITS, TOTAL_BASES, HOME_RUNS, "pa")
    hist: dict = defaultdict(dict)
    q = ("SELECT player, period, game_id, market, value FROM player_game_logs "
         f"WHERE sport='mlb' AND market IN ({','.join('?' * len(marks))}) "
         "ORDER BY period")
    for player, period, gid, market, value in conn.execute(q, marks):
        hist[player].setdefault((period, gid), {})[market] = float(value)
    return {p: sorted(games.items()) for p, games in hist.items()}


def _as_of_means(name: str, prior_games: list, market: str) -> float | None:
    """The live board's own projection path, on prior games only.

    Neutral park and weather on purpose: the question is whether the sim's
    DEPENDENCE beats the prior's, and feeding one arm context the other
    cannot see would grade the context instead."""
    from engine.mlb.projection import build_mlb_projection
    vals = [g[1].get(market) for g in prior_games]
    vals = [v for v in vals if v is not None][-LOG_LIMIT:]
    if len(vals) < MIN_HISTORY:
        return None
    logs = [MLBGameLog(game=len(vals) - j, opponent="", value=float(v))
            for j, v in enumerate(reversed(vals))]
    prop = MLBProp(player=name, team="HOME", opponent="AWAY", position="",
                   market=market, logs=logs,
                   career_avg=sum(vals) / len(vals), vs_pitcher_avg=None,
                   lines=[SportsbookLine("proxy", 1.5, -110, -110)],
                   lineup_spot=3)
    try:
        return build_mlb_projection(
            prop, _neutral_game()).mean
    except Exception:                                        # noqa: BLE001
        return None


def _neutral_game():
    from engine.mlb.models import MLBGame
    return MLBGame(home="HOME", away="AWAY", park="generic")


def run_history(conn, days: int, trials: int, fit_trials: int,
                progress=print) -> tuple[Tally, dict]:
    """Replay the window; return the verdict tally and a notes dict."""
    from engine.mlb.projection import reconcile_triple

    team_games = _mlb_rows(conn, days)
    hist = _histories(conn, "")
    notes = {"team_games": len(team_games), "lineups_scored": 0,
             "gate_failed": 0, "too_few_hitters": 0, "hr_pairs": 0}
    tally, hr_tally = Tally(), Tally()

    for (period, team, leg), players in sorted(team_games.items()):
        # As-of projections for every hitter who actually appeared.
        means, spots_rank = {}, []
        for name, night in players.items():
            games = hist.get(name) or []
            prior = [g for g in games if g[0][0] < period]
            mk = {}
            for market in (HITS, TOTAL_BASES, HOME_RUNS):
                m = _as_of_means(name, prior, market)
                if m is not None:
                    mk[market] = m
            if len(mk) != 3:
                continue
            pa_vals = [g[1].get("pa") for g in prior[-20:]]
            pa_vals = [v for v in pa_vals if v]
            if not pa_vals:
                continue
            means[name] = mk
            spots_rank.append((-(sum(pa_vals) / len(pa_vals)), name))
        if len(means) < 6:                       # simjoint.MIN_HITTERS
            notes["too_few_hitters"] += 1
            continue

        # Spots inferred by as-of PA rate — THE NAMED BLUR (see module doc).
        spots = {name: i + 1
                 for i, (_, name) in enumerate(sorted(spots_rank)[:9])}

        rates, targets = [], {}
        for name, mk in means.items():
            if name not in spots:
                continue
            hr, tb, note = reconcile_triple(mk[HITS], mk[TOTAL_BASES],
                                            mk[HOME_RUNS])
            if note:
                mk[HOME_RUNS], mk[TOTAL_BASES] = hr, tb
            r = G.rates_from_means(mk[HITS], mk[TOTAL_BASES], mk[HOME_RUNS],
                                   G.expected_pa(spots[name]))
            r.name, r.spot = name, spots[name]
            if not r.consistent:
                continue
            rates.append(r)
            targets[name] = dict(mk)
        if len(targets) < 6:
            notes["too_few_hitters"] += 1
            continue

        rates = G.pad_to_nine(sorted(rates, key=lambda r: r.spot or 9))
        fitted = G.calibrate(rates, targets, trials=fit_trials)

        legs = [(n, m, ln) for n in targets
                for m, ln in {**VERDICT_LINES, **EXTRA_LINES}.items()]
        sim = G.simulate_lineup(fitted, legs, trials=trials)
        rec = G.reconcile(sim, targets)
        if not rec["ok"]:
            notes["gate_failed"] += 1
            continue
        notes["lineups_scored"] += 1

        names = sorted(targets)
        for i, a_name in enumerate(names):
            for b_name in names[i + 1:]:
                adjacent = abs(spots[a_name] - spots[b_name]) <= 2
                for market, line in VERDICT_LINES.items():
                    _score_pair(tally, sim, players, a_name, b_name,
                                market, line, adjacent)
                for market, line in EXTRA_LINES.items():
                    _score_pair(hr_tally, sim, players, a_name, b_name,
                                market, line, adjacent)
        if notes["lineups_scored"] % 50 == 0:
            progress(f"  … {notes['lineups_scored']} lineups scored, "
                     f"{tally.n} verdict pairs")

    notes["hr_pairs"] = hr_tally.n
    notes["hr_tally"] = hr_tally
    return tally, notes


def _score_pair(tally: Tally, sim, players: dict, a_name: str, b_name: str,
                market: str, line: float, adjacent: bool) -> None:
    a, b = (a_name, market, line), (b_name, market, line)
    p1, p2 = sim.p_over(*a), sim.p_over(*b)
    p_both = sim.p_both(a, b)
    if p1 is None or p2 is None or p_both is None:
        return
    if not (0.0 < p1 < 1.0 and 0.0 < p2 < 1.0):
        return
    va = players.get(a_name, {}).get(market)
    vb = players.get(b_name, {}).get(market)
    if va is None or vb is None:
        return
    hit = va > line and vb > line
    tally.add(p1 * p2, joint_two(p1, p2, PRIOR_RHO), p_both, hit, adjacent)


# --- the forward arm ---------------------------------------------------------
def run_forward(conn, log_path: str = LOG_PATH) -> tuple[Tally, dict]:
    """Grade the live journal simjoint.build has been writing."""
    notes = {"recorded": 0, "graded": 0, "ungraded": 0}
    if not os.path.exists(log_path):
        return Tally(), notes
    latest: dict = {}
    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            key = (row.get("date"), tuple(row.get("a") or ()),
                   tuple(row.get("b") or ()))
            latest[key] = row                    # last write per pair wins
    notes["recorded"] = len(latest)

    tally = Tally()
    for row in latest.values():
        hit = _forward_outcome(conn, row)
        if hit is None:
            notes["ungraded"] += 1
            continue
        p1, p2 = float(row["p1"]), float(row["p2"])
        if not (0.0 < p1 < 1.0 and 0.0 < p2 < 1.0):
            continue
        tally.add(p1 * p2, joint_two(p1, p2, PRIOR_RHO),
                  float(row["sim_joint"]), hit, None)
        notes["graded"] += 1
    return tally, notes


def _forward_outcome(conn, row: dict) -> bool | None:
    """Did both journaled legs clear? None while the night is unsettled."""
    gn = int(row.get("game_number") or 1)
    vals = []
    for leg in (row.get("a"), row.get("b")):
        if not leg or len(leg) != 3:
            return None
        player, market, line = leg[0], leg[1], float(leg[2])
        rows = conn.execute(
            "SELECT game_id, value FROM player_game_logs WHERE sport='mlb' "
            "AND period=? AND player=? AND market=?",
            (row.get("date"), player, market)).fetchall()
        if not rows:
            return None
        if len(rows) > 1:                        # doubleheader: match the half
            want = f"-G{gn}" if gn > 1 else ""
            rows = [r for r in rows
                    if (want and r[0].endswith(want))
                    or (not want and "-G" not in r[0])] or rows[:1]
        vals.append((float(rows[0][1]), line))
    return all(v > ln for v, ln in vals)


# --- the verdict -------------------------------------------------------------
def _report(label: str, t: Tally) -> None:
    if not t.n:
        print(f"  {label}: no pairs scored")
        return
    hits = sum(1 for r in t.rows if r["hit"])
    print(f"  {label}: {t.n} pair(s), {hits} both-hit "
          f"({100.0 * hits / t.n:.1f}%)")
    print(f"    log-loss  independence {t.mean('ind'):.4f}   "
          f"prior {t.mean('prior'):.4f}   sim {t.mean('sim'):.4f}")
    print(f"    brier     independence {t.mean('b_ind'):.4f}   "
          f"prior {t.mean('b_prior'):.4f}   sim {t.mean('b_sim'):.4f}")
    d, se = t.diff_se()
    print(f"    sim − prior log-loss: {d:+.5f} ± {se:.5f} "
          f"({'sim better' if d < 0 else 'prior better'}, "
          f"{abs(d) / se if se else 0:.1f} SE)")


def verdict(t: Tally) -> str:
    d, se = t.diff_se()
    if t.n < MIN_PAIRS:
        return (f"KEEP COLLECTING — {t.n} pairs against the {MIN_PAIRS} the "
                f"bar requires. No verdict either way.")
    if d < 0 and d <= -2 * se:
        return ("IMPROVEMENT — the sim prices real nights better than the "
                "prior by at least two standard errors. It keeps its seat, "
                "and this run is the evidence #60 was waiting for.")
    if d <= se:
        return ("KEEPS ITS SEAT — not distinguishably better, not worse. "
                "The structural argument stands and nothing here argues "
                "against it.")
    return ("WORSE THAN THE PRIOR by more than one standard error. The "
            "honest action: set engine/mlb/simjoint.ENABLED = False (every "
            "pair keeps the measured prior), and bring this printout.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--days", type=int, default=30,
                    help="distinct slate dates to replay (default 30)")
    ap.add_argument("--trials", type=int, default=6000,
                    help="scoring-sim trials per lineup")
    ap.add_argument("--fit-trials", type=int, default=4000,
                    help="calibration trials per fit round")
    ap.add_argument("--forward-only", action="store_true")
    ap.add_argument("--history-only", action="store_true")
    ap.add_argument("--journal", default=LOG_PATH)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    n_mlb = conn.execute("SELECT COUNT(*) FROM player_game_logs "
                         "WHERE sport='mlb'").fetchone()[0]
    print(f"simrecon — sim joint vs measured prior ({PRIOR_RHO:+.3f} on "
          f"{PRIOR_N:,} games) vs independence")
    print(f"  db: {args.db} ({n_mlb:,} MLB player-game rows)\n")
    if not n_mlb and not args.forward_only:
        print("  No MLB logs in this DB — the history arm needs the "
              "machine that ingests slates (the laptop). --forward-only "
              "still grades the live journal, if one exists here.")

    combined = Tally()
    if not args.forward_only and n_mlb:
        print(f"HISTORY ARM — last {args.days} slate dates, lineup spots "
              f"inferred (the named blur; see the header)")
        t, notes = run_history(conn, args.days, args.trials, args.fit_trials)
        print(f"  {notes['team_games']} team-games; "
              f"{notes['lineups_scored']} lineups scored, "
              f"{notes['gate_failed']} failed the marginal gate, "
              f"{notes['too_few_hitters']} lacked six projected hitters")
        _report("verdict pairs (H 1.5 / TB 1.5)", t)
        adj = t.subset(lambda r: r["adjacent"] is True)
        far = t.subset(lambda r: r["adjacent"] is False)
        _report("adjacent (|spot gap| <= 2)", adj)
        _report("distant  (|spot gap| > 2)", far)
        hr = notes.get("hr_tally")
        if hr is not None and hr.n:
            _report("home runs 0.5 (outside the verdict)", hr)
        combined.rows += t.rows

    if not args.history_only:
        print("\nFORWARD ARM — the live journal, true lineup cards")
        t, notes = run_forward(conn, args.journal)
        print(f"  {notes['recorded']} pair(s) recorded, "
              f"{notes['graded']} graded, {notes['ungraded']} not yet "
              f"settled or not in this DB")
        _report("journaled pairs", t)
        combined.rows += t.rows

    print("\nTHE VERDICT (bar in the header, declared before the answer):")
    print(f"  {verdict(combined)}")


if __name__ == "__main__":
    main()
