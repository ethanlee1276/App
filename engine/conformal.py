"""Honest ranges — conformal intervals around every pick's projection, coverage tested held out.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 11. Every pick shows
one number (the projection) and a chance. Neither says how wide the
outcomes really are around that number: a projection of 62 receiving
yards can mean 50 to 75 or 20 to 110, and which one it is decides how
much the line's distance from 62 is worth.

SPLIT CONFORMAL PREDICTION. Every graded pick in the journal (the
projection we published, and what the player did) gives a score: how far
he landed from our number, scaled by the square root of the number (a
bigger projection misses by more). The scores' own quantiles, with the
finite-sample correction, make a range around tonight's projection that
covers what happens at least as often as it says, with no assumption
about the shape of the misses. The same scores give a second chance for
the pick's side — the share of past misses that would have put him over
the line — beside the model's own.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. Graded picks in date order; the
first two thirds calibrate, the newest third is scored. A sport and
market's ranges earn the label "measured" only if, on the newest third,
the 50% range covered 50% and the 80% range covered 80% — each within
three points or two standard errors, whichever is wider — over at least
MIN_TEST picks. The range's chance for the side is scored against the
model's own by Brier score on the same picks and reported, not adopted:
nothing on the board reads either.

Standard library only.
"""

from __future__ import annotations

import json
import math

LEVELS = (0.5, 0.8)
GRID = [i / 100 for i in range(1, 100)]
MIN_FIT = 100
MIN_TEST = 150
TOLERANCE = 0.03
STORE = "conformal.json"


def scale(proj: float) -> float:
    return math.sqrt(abs(float(proj)) + 1.0)


def score(proj: float, actual: float) -> float:
    return (float(actual) - float(proj)) / scale(proj)


def _q(sorted_xs: list, p: float) -> float:
    """The conformal quantile: the ⌈(n+1)p⌉-th smallest score (the
    finite-sample correction), clamped to the sample."""
    n = len(sorted_xs)
    k = min(n, max(1, math.ceil((n + 1) * p)))
    return sorted_xs[k - 1]


def fit(scores: list) -> dict | None:
    """The calibration: the score quantiles each range reads, and a grid
    of them for the side's chance."""
    if len(scores) < MIN_FIT:
        return None
    xs = sorted(scores)
    out = {"n": len(xs), "grid": [round(_q(xs, p), 4) for p in GRID]}
    for lv in LEVELS:
        a = (1.0 - lv) / 2.0
        out[str(lv)] = [round(_q(xs, a), 4), round(_q(xs, 1.0 - a), 4)]
    return out


def interval(cal: dict, proj: float, level: float) -> tuple:
    lo, hi = cal[str(level)]
    s = scale(proj)
    return (round(proj + lo * s, 1), round(proj + hi * s, 1))


def chance_over(cal: dict, proj: float, line: float) -> float:
    """The share of past misses that would have put him over this line:
    one minus the scores' distribution at (line − projection)/scale, read
    off the quantile grid."""
    z = (float(line) - float(proj)) / scale(proj)
    g = cal["grid"]
    if z < g[0]:
        return 1.0 - GRID[0] * 0.5
    if z >= g[-1]:
        return (1.0 - GRID[-1]) * 0.5
    for i in range(len(g) - 1):
        if g[i] <= z < g[i + 1]:
            span = g[i + 1] - g[i]
            f = GRID[i] + (GRID[i + 1] - GRID[i]) * ((z - g[i]) / span if span else 0.0)
            return 1.0 - f
    return 0.5


def side_chance(cal: dict, proj: float, line: float, side: str) -> float:
    p = chance_over(cal, proj, line)
    return p if str(side).upper().startswith("O") else 1.0 - p


# ---- the journal, and the held-out test -------------------------------------------------

def journal_rows(conn) -> list:
    """Every graded pick once: (sport, market, date, side, line,
    projection, hit_prob, actual), oldest first. A pick journaled under two
    categories counts once."""
    seen, out = set(), []
    for r in conn.execute("SELECT sport, market, date, player, side, line, projection, hit_prob, actual FROM bets "
                          "WHERE status IN ('won','lost','push') AND actual IS NOT NULL AND projection IS NOT NULL "
                          "ORDER BY date, id"):
        key = (r[0], r[1], r[2], r[3])
        if key in seen:
            continue
        seen.add(key)
        out.append((r[0], r[1], str(r[2]), r[4] or "", r[5], float(r[6]), r[7], float(r[8])))
    return out


def held_out(rows: list) -> dict:
    """Per sport and market: calibrate on the oldest two thirds, score the
    newest third's coverage at each level, and the range's chance for the
    side against the model's by Brier score."""
    by: dict = {}
    for r in rows:
        by.setdefault(f"{r[0]}|{r[1]}", []).append(r)
    out = {}
    for key, rs in by.items():
        cut = (2 * len(rs)) // 3
        cal = fit([score(r[5], r[7]) for r in rs[:cut]])
        test = rs[cut:]
        if not cal or not test:
            out[key] = {"n": len(test), "holds": False, "note": "too few graded picks"}
            continue
        cov = {}
        ok = len(test) >= MIN_TEST
        for lv in LEVELS:
            inside = 0
            for r in test:
                lo, hi = interval(cal, r[5], lv)
                inside += lo <= r[7] <= hi
            c = inside / len(test)
            tol = max(TOLERANCE, 2.0 * math.sqrt(lv * (1 - lv) / len(test)))
            cov[str(lv)] = round(c, 3)
            ok = ok and abs(c - lv) <= tol
        b_range = b_model = 0.0
        nb = 0
        for _sport, _market, _date, side, line, proj, hp, actual in test:
            if line is None or hp is None or actual == line or not side:
                continue
            won = (actual > line) if str(side).upper().startswith("O") else (actual < line)
            b_range += (side_chance(cal, proj, line, side) - won) ** 2
            b_model += (float(hp) - won) ** 2
            nb += 1
        out[key] = {"n": len(test), "coverage": cov, "holds": bool(ok),
                    "brier_range": round(b_range / nb, 4) if nb else None,
                    "brier_model": round(b_model / nb, 4) if nb else None, "brier_n": nb}
    return out


# ---- storage, the box, the ideas file -----------------------------------------------------

def save(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(res, fh, indent=1)
    return p


def load() -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def measure(rows: list) -> dict:
    """The held-out verdicts, and the calibrations the pick page reads
    (fitted on every graded pick, newest included)."""
    by: dict = {}
    for r in rows:
        by.setdefault(f"{r[0]}|{r[1]}", []).append(score(r[5], r[7]))
    cals = {k: c for k, c in ((k, fit(v)) for k, v in by.items()) if c}
    return {"calibration": cals, "held_out": held_out(rows), "picks": len(rows)}


def ideas_section(props, games, board, sport):
    saved = load()
    cals = saved.get("calibration") or {}
    verdicts = saved.get("held_out") or {}
    rows = {}
    for r in (board or {}).get("recommendations") or []:
        key = f"{sport}|{r.get('market')}"
        cal = cals.get(key)
        proj = r.get("projection")
        if not cal or proj is None or r.get("line") is None:
            continue
        rows[f"{r.get('player')}|{r.get('market')}"] = {
            "projection": round(float(proj), 1), "line": r["line"], "side": r.get("side") or "",
            "ranges": {str(lv): interval(cal, float(proj), lv) for lv in LEVELS},
            "range_chance": round(side_chance(cal, float(proj), r["line"], r.get("side") or "over"), 3),
            "model_chance": r.get("hit_prob"), "model_range": [r.get("proj_low"), r.get("proj_high")],
            "n": cal["n"], "verdict": verdicts.get(key) or {}}
    return {"rows": rows}


def pick_view(sec, player, market, side="", line=None):
    return (sec.get("rows") or {}).get(f"{player}|{market}")


def game_view(sec, home, away):
    return None


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Conformal ranges around every pick's projection, coverage tested on the newest third")
    ap.add_argument("--save", action="store_true", help="keep the calibrations and verdicts for the pick page")
    a = ap.parse_args(argv)
    from . import ledger as _ledger
    conn = _ledger.connect()
    try:
        rows = journal_rows(conn)
    finally:
        conn.close()
    res = measure(rows)
    print(f"Honest ranges — {res['picks']} graded picks in the journal")
    for key, v in sorted(res["held_out"].items(), key=lambda kv: -kv[1].get("n", 0)):
        if not v.get("coverage"):
            continue
        cov = v["coverage"]
        print(f"  {key}: newest {v['n']} picks — the 50% range covered {cov['0.5']:.0%}, the 80% range {cov['0.8']:.0%}"
              f" — {'HOLDS' if v['holds'] else 'does not hold'}; side's chance, Brier: range {v['brier_range']} vs "
              f"model {v['brier_model']} (n {v['brier_n']})")
    print(f"  THE BAR: on the newest third, each range covers its share within {TOLERANCE:.0%} or two standard "
          f"errors, over ≥ {MIN_TEST} picks")
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
