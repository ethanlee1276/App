"""Does an injury move WHO scores, beyond what the team total already says?

    sudo -u qellys nice -n 10 python3 -m engine.tdinjfit
    sudo -u qellys nice -n 10 python3 -m engine.tdinjfit --dry-run

Ethan, 2026-10-04, with four touchdown-only scans (Broncos @ 49ers twice,
Jaguars @ Bengals twice): "figure out where we can learn more and where we
can pull more data from and what better research we can do for our
touchdown picks ... most likely bets is more important."

Most of what those scans weigh is already measured here. Goal-line work is
in the chance (tdfeatures, 2026-09-27). A defence's red-zone record adds
nothing on top of the model (tdmatchfit, 2026-10-01: both readings fail).
The team total is the whole between-game signal (scriptfit). What is left
is the move all four scans make from the INJURY REPORT:

  S1  secondary   the opponent has starting defensive backs ruled out →
                  his WRs and TEs score more ("Cook and Dugger out —
                  Washington's matchup opens up").
  S2  front       the opponent has starting defensive linemen ruled out →
                  his RBs score more ("Bosa out — boost McCaffrey").
  S3  catchers    his own team has a starting WR or TE ruled out → the
                  other WRs, TEs and RBs score more ("Evans out — Kittle,
                  Deebo and McCaffrey get his red-zone looks").

The market already moves the TEAM TOTAL for an injury, and the model reads
that total. So each claim is asked on top of the model: does the injury
change which players score, beyond the total the books already set?

WHAT IS MEASURED. Every player-week the touchdown replay grades
(engine/tdbacktest, the production chain with the closing total). The
injury flags come from the weekly injury reports and depth charts the
build reads (engine/sources/injuries, engine/sources/depthcharts): a
player ruled out (OUT, IR or DOUBTFUL) who sits first on his depth chart
counts as a starter; a backup counts for nothing, as it does on the board.
Each claim's x is how many starters in its group are out (capped at
X_CAP), and the fit is

    baseline   scored ~ logit(model prob)
    claim      scored ~ logit(model prob) + b · x

THE BAR, WRITTEN BEFORE ANY BOX RUN. A claim is PROVEN only if all of:
  - leave one season out: held-out log loss beats the baseline pooled AND
    in all but one season;
  - b is in the claimed direction (positive) with a cluster-robust t of at
    least MIN_T (clusters = one team's game: everyone facing the same
    injured defence is one result, not dozens);
  - at least MIN_FLAGGED graded player-weeks with x > 0.
Three claims, one test each. Nothing here moves a number. A proven claim
earns a "history says" line on the touchdown card first; pricing it is a
separate, later decision.

SEASONS. Only seasons whose depth chart is keyed by week (2021-2024). The
2025+ files are dated snapshots, and depthcharts answers only "this week"
and "last week" from them; reading week 9 of 2025 from them would mark
starters from a different month.

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from . import modelstate
from .tdfeatures import fit_logistic, logit, sigmoid, _solve

SEASONS = (2021, 2022, 2023, 2024)
RULED_OUT = {"OUT", "IR", "DOUBTFUL"}
X_CAP = 3
MIN_FLAGGED = 300
MIN_T = 2.0
STORE_VERSION = 1

#: Depth-chart positions by group, read after a leading L/R is dropped
#: ("LCB" → "CB", "RDE" → "DE").
SECONDARY = {"CB", "NB", "NCB", "SCB", "SLOT", "FS", "SS", "S", "DB"}
FRONT = {"DE", "DT", "NT", "DL", "EDGE"}
CATCHERS = {"WR", "SWR", "TE"}

#: claim -> (side, depth group, positions it is about, words)
CLAIMS = {
    "secondary": ("opp", SECONDARY, frozenset({"WR", "TE"}),
                  "starting defensive backs out → his receivers score more"),
    "front": ("opp", FRONT, frozenset({"RB"}),
              "starting defensive linemen out → his backs score more"),
    "catchers": ("own", CATCHERS, frozenset({"WR", "TE", "RB"}),
                 "a starting WR or TE out → his teammates score more"),
}

#: Team codes as the replay's logs spell them.
TEAM = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "OAK": "LV", "SD": "LAC", "STL": "LA"}


def _store() -> Path:
    return Path(modelstate.path("td_injury.json"))


def team_code(t: str) -> str:
    t = str(t or "").upper()
    return TEAM.get(t, t)


def group_of(depth_pos: str) -> str:
    """'secondary', 'front', 'catchers' or '' for a depth-chart position."""
    d = str(depth_pos or "").upper()
    tries = [d] + ([d[1:]] if d[:1] in ("L", "R") and len(d) > 2 else [])
    for c in tries:
        if c in SECONDARY:
            return "secondary"
        if c in FRONT:
            return "front"
        if c in CATCHERS:
            return "catchers"
    return ""


def starters_out(injuries: list, depth_index: dict) -> dict:
    """{team: {group: starters ruled out}} for one week.

    ``injuries`` are engine Injury objects for the week; ``depth_index`` is
    depthcharts.index_for_week's {(team, normalized name): (pos, rank)}."""
    from .sources.depthcharts import normalize_name
    out: dict = defaultdict(lambda: defaultdict(int))
    seen = set()
    for j in injuries:
        if j.status not in RULED_OUT:
            continue
        hit = depth_index.get((j.team, normalize_name(j.player)))
        if not hit or hit[1] != 1:
            continue
        g = group_of(hit[0])
        key = (team_code(j.team), normalize_name(j.player))
        if not g or key in seen:
            continue
        seen.add(key)
        out[team_code(j.team)][g] += 1
    return {t: dict(v) for t, v in out.items()}


def _week(v) -> int:
    try:
        return int(str(v).lstrip("0") or 0)
    except ValueError:
        return 0


def samples(rows: list[dict], out_by_week: dict) -> dict:
    """{claim: [(season, cluster, logit p, x, scored)]}.

    ``rows`` are tdbacktest collect rows; ``out_by_week`` is
    {(season, week): starters_out(...)}."""
    got: dict = {k: [] for k in CLAIMS}
    for r in rows:
        pos = str(r.get("position") or "").upper()
        season, wk = int(r["season"]), _week(r["week"])
        week_out = out_by_week.get((season, wk))
        if week_out is None:
            continue
        team, opp = team_code(r.get("team")), team_code(r.get("opponent"))
        for claim, (side, _grp, positions, _w) in CLAIMS.items():
            if pos not in positions:
                continue
            who = opp if side == "opp" else team
            if not who:
                continue
            x = min(week_out.get(who, {}).get(claim, 0), X_CAP)
            got[claim].append((season, (season, wk, who), logit(float(r["prob"])), float(x),
                               int(r["scored"])))
    return got


def _ll(p: float, y: int) -> float:
    p = min(max(p, 1e-9), 1.0 - 1e-9)
    return -math.log(p if y else 1.0 - p)


def _fit(data, with_x: bool):
    xs = [[1.0, d[2], d[3]] if with_x else [1.0, d[2]] for d in data]
    return fit_logistic(xs, [d[4] for d in data]), xs


def _loss(beta, data, with_x: bool) -> float:
    tot = 0.0
    for d in data:
        z = beta[0] + beta[1] * d[2] + (beta[2] * d[3] if with_x else 0.0)
        tot += _ll(sigmoid(z), d[4])
    return tot


def cluster_t(data) -> tuple:
    """(b, cluster-robust t of b) for the claim's term on all the data."""
    beta, xs = _fit(data, True)
    if beta is None:
        return None, None
    k = 3
    bread = [[0.0] * k for _ in range(k)]
    scores: dict = defaultdict(lambda: [0.0] * k)
    for d, x in zip(data, xs):
        p = sigmoid(sum(b * v for b, v in zip(beta, x)))
        w = p * (1.0 - p)
        for i in range(k):
            scores[d[1]][i] += x[i] * (d[4] - p)
            for j in range(k):
                bread[i][j] += w * x[i] * x[j]
    inv = []
    for c in range(k):
        col = _solve(bread, [1.0 if i == c else 0.0 for i in range(k)])
        if col is None:
            return beta[2], None
        inv.append(col)
    inv = [[inv[j][i] for j in range(k)] for i in range(k)]      # columns → rows
    meat = [[sum(s[i] * s[j] for s in scores.values()) for j in range(k)] for i in range(k)]
    row = [sum(inv[2][a] * meat[a][b] for a in range(k)) for b in range(k)]
    var = sum(row[b] * inv[b][2] for b in range(k))
    if var <= 0:
        return beta[2], None
    return beta[2], beta[2] / math.sqrt(var)


def judge(data: list) -> dict:
    """The bar, on one claim's [(season, cluster, logit p, x, scored)]."""
    seasons = sorted({d[0] for d in data})
    flagged = sum(1 for d in data if d[3] > 0)
    per, better, base_sum, fit_sum = {}, 0, 0.0, 0.0
    for s in seasons:
        train = [d for d in data if d[0] != s]
        test = [d for d in data if d[0] == s]
        b0, _ = _fit(train, False)
        b1, _ = _fit(train, True)
        if b0 is None or b1 is None or not test:
            continue
        base, fit = _loss(b0, test, False), _loss(b1, test, True)
        per[s] = {"n": len(test), "flagged": sum(1 for d in test if d[3] > 0),
                  "gain": round((base - fit) / len(test), 6)}
        better += fit < base
        base_sum += base
        fit_sum += fit
    b, t = cluster_t(data) if data else (None, None)
    # The rate behind the fit, for reading: scored / model's claim, with
    # and without the injury.
    def ratio(rows):
        exp = sum(sigmoid(d[2]) for d in rows)
        return round(sum(d[4] for d in rows) / exp, 3) if exp else None
    passed = bool(len(per) >= 2 and fit_sum < base_sum and better >= len(per) - 1
                  and b is not None and b > 0 and t is not None and t >= MIN_T
                  and flagged >= MIN_FLAGGED)
    return {"n": len(data), "flagged": flagged, "b": None if b is None else round(b, 4),
            "t": None if t is None else round(t, 2), "seasons": per, "better": better,
            "gain": round((base_sum - fit_sum) / len(data), 6) if data else 0.0,
            "scored_vs_model_flagged": ratio([d for d in data if d[3] > 0]),
            "scored_vs_model_rest": ratio([d for d in data if d[3] == 0]),
            "passed": passed}


def out_by_week(seasons=SEASONS, load_injuries=None, load_depth=None) -> dict:
    """{(season, week): starters_out} from the files the build reads."""
    from .sources import depthcharts as D
    from .sources import injuries as I
    load_injuries = load_injuries or I.load_injuries
    load_depth = load_depth or (lambda s: D.load_depth_charts(s, keep_days=None))
    out = {}
    for season in seasons:
        try:
            inj_rows, depth_rows = load_injuries(int(season)), load_depth(int(season))
        except Exception as e:                                # noqa: BLE001
            print(f"  {season}: injury or depth file unavailable ({type(e).__name__})")
            continue
        if not depth_rows or "week" not in depth_rows[0]:
            print(f"  {season}: depth chart is not keyed by week; skipped")
            continue
        weeks = sorted({_week(r.get("week")) for r in inj_rows} - {0})
        for wk in weeks:
            out[(int(season), wk)] = starters_out(I.injuries_for_week(inj_rows, wk),
                                                  D.index_for_week(depth_rows, wk))
    return out


def measure(conn, seasons=SEASONS, **loaders) -> dict:
    from .tdbacktest import run
    rows: list = []
    run(conn, seasons=list(seasons), collect=rows.append)
    flags = out_by_week(seasons, **loaders)
    return {k: judge(v) for k, v in samples(rows, flags).items()}


def save(res: dict, path=None) -> None:
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": STORE_VERSION,
                             "proven": {k: v for k, v in res.items() if v["passed"]},
                             "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                             .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")


def report_lines(res: dict) -> list:
    out = []
    for k, (_side, _g, _pos, words) in CLAIMS.items():
        v = res.get(k)
        if not v:
            continue
        per = ", ".join(f"{s} {d['gain']:+.5f}" for s, d in v["seasons"].items())
        out.append(f"  {k.upper():<10} {words}\n"
                   f"      {v['flagged']:,} of {v['n']:,} player-weeks flagged; scored ÷ model "
                   f"{v['scored_vs_model_flagged']} flagged vs {v['scored_vs_model_rest']} rest\n"
                   f"      b {v['b']}  clustered t {v['t']}  held-out gain {v['gain']:+.6f} "
                   f"(better {v['better']}/{len(v['seasons'])}: {per})  → "
                   f"{'PROVEN' if v['passed'] else 'not proven'}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.tdinjfit")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    from . import db
    res = measure(db.connect())
    for line in report_lines(res) or ["  nothing to measure: no replay rows joined an injury week"]:
        print(line)
    if not a.dry_run:
        save(res)
        print("saved; a proven claim earns a history line on the touchdown card, never a number")
    return 0


if __name__ == "__main__":
    sys.exit(main())
