"""Do our expected average and slugging see a hitter's next game better
than his actual ones?

    sudo -u qellys nice -n 19 python3 -m engine.mlb.xstatsfit [--dry-run]

Ethan, 2026-10-13: "MLB expected stats ... I'd test it before it touches a
pick." engine/mlb/xstats fits a hit chance and expected bases for every
ball in play from its exit velocity and launch angle. Drawn on the hit
tracker it is context; before it could ever move a number it has to see
something his plain average and slugging do not. This asks that.

WHAT IS MEASURED. Every stored plate appearance (engine/mlb/charts'
mlb_pa), its game dates in order and cut three ways:

  TRAIN  the first TRAIN_SHARE of the dates: the table is fitted on these
         balls and on nothing later;
  TUNE   the next TUNE_SHARE: each predictor's pull toward the league is
         picked here, from GRID, and nowhere else;
  TEST   the rest: the comparison.

For every hitter's game in TUNE and TEST with at least MIN_PRIOR_AB at
bats earlier that season, two predictors of that game, each from only his
earlier plate appearances that season:

  ACTUAL    his hits and total bases an at bat;
  EXPECTED  his expected hits and bases an at bat (the TRAIN table on each
            ball; a strikeout counts nothing, a ball with no speed or
            angle on file counts what it was);

each pulled toward the TRAIN league's rate by K at bats. They are scored
on that game:

  HITS   did he get one — 1 − (1 − rate)^(his at bats) — by log loss;
  BASES  his total bases — rate × his at bats — by mean squared error.

THE BAR, WRITTEN BEFORE ANY RUN: EXPECTED passes a target only if it beats
ACTUAL by at least BAR_LOGLOSS (hits) or by BAR_MSE of ACTUAL's error
(bases) in BOTH halves of TEST, by date, with at least MIN_GAMES hitter-
games in each half. The league's rate alone is reported beside them as
the floor either should clear.

NOTHING HERE MOVES A PRICE, and passing moves nothing either: a pass is a
line on the hit tracker and a decision for Ethan. The verdict is written
to the models directory (``MEASURED_FILE``) so the chart can say it.

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

from .. import modelstate
from . import xstats
from .charts import HIT_BASES, NOT_AB

TRAIN_SHARE = 0.60
TUNE_SHARE = 0.15
GRID = (25, 50, 100, 200, 400, 800)
MIN_PRIOR_AB = 20
BAR_LOGLOSS = 0.001
BAR_MSE = 0.005
MIN_GAMES = 2000
MEASURED_FILE = "mlb_xstats_measured.json"
_EPS = 1e-6


def _store() -> Path:
    return Path(modelstate.path(MEASURED_FILE))


def _cuts(dates: list[str]) -> tuple[str, str]:
    """The first TUNE date and the first TEST date."""
    n = len(dates)
    a = max(1, int(n * TRAIN_SHARE))
    b = max(a + 1, int(n * (TRAIN_SHARE + TUNE_SHARE)))
    return dates[min(a, n - 1)], dates[min(b, n - 1)]


def samples(rows, model=None, tune_from=None, test_from=None, min_prior_ab=MIN_PRIOR_AB):
    """Hitter-games in TUNE and TEST, each with his season-to-date line
    before it. ``rows`` are ``(date, season, game_pk, batter_id,
    event_type, launch_speed, launch_angle)``.

    Returns ``(samples, league, model, cuts)``: each sample ``{date, ab,
    h, tb, xh, xtb, g_ab, g_hit, g_tb, part}``; the league's hits and bases
    an at bat over TRAIN; the TRAIN table; the two cut dates."""
    rows = sorted(rows, key=lambda r: (r[0], r[2]))
    dates = sorted({r[0] for r in rows})
    if len(dates) < 3:
        return [], (0.0, 0.0), model or {}, ("", "")
    if not (tune_from and test_from):
        tune_from, test_from = _cuts(dates)
    train = [r for r in rows if r[0] < tune_from]
    if model is None:
        model = xstats.fit((r[5], r[6], r[4]) for r in train)
    ab = [r for r in train if r[4] not in NOT_AB]
    league = ((sum(1 for r in ab if r[4] in HIT_BASES) / len(ab)) if ab else 0.0,
              (sum(HIT_BASES.get(r[4], 0) for r in ab) / len(ab)) if ab else 0.0)
    games: dict = {}
    for d, season, gpk, bid, et, ev, la in rows:
        games.setdefault((d, gpk, bid), (season, []))[1].append((et, ev, la))
    so_far: dict = {}
    out = []
    for (d, gpk, bid), (season, pas) in sorted(games.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        acc = so_far.setdefault((bid, season), [0, 0, 0, 0.0, 0.0])
        g = [0, 0, 0, 0.0, 0.0]
        for et, ev, la in pas:
            if et in NOT_AB:
                continue
            b = HIT_BASES.get(et, 0)
            v = xstats.xvals(model, ev, la)
            g[0] += 1
            g[1] += 1 if b else 0
            g[2] += b
            g[3] += v[0] if v else (1 if b else 0)
            g[4] += v[1] if v else b
        if d >= tune_from and g[0] and acc[0] >= min_prior_ab:
            out.append({"date": d, "ab": acc[0], "h": acc[1], "tb": acc[2], "xh": acc[3], "xtb": acc[4],
                        "g_ab": g[0], "g_hit": 1 if g[1] else 0, "g_tb": g[2],
                        "part": "test" if d >= test_from else "tune"})
        for i in range(5):
            acc[i] += g[i]
    return out, league, model, (tune_from, test_from)


def _rate(s: dict, which: str, k: float, lg: float) -> float:
    return (s[which] + k * lg) / (s["ab"] + k)


def _logloss(ss, which, k, lg) -> float:
    tot = 0.0
    for s in ss:
        r = min(max(_rate(s, which, k, lg), 0.0), 1.0)
        p = min(max(1.0 - (1.0 - r) ** s["g_ab"], _EPS), 1.0 - _EPS)
        tot -= math.log(p) if s["g_hit"] else math.log(1.0 - p)
    return tot / len(ss) if ss else float("nan")


def _mse(ss, which, k, lg) -> float:
    return (sum((_rate(s, which, k, lg) * s["g_ab"] - s["g_tb"]) ** 2 for s in ss) / len(ss)) if ss else float("nan")


#: target → (scorer, actual's field, expected's field, which league rate)
TARGETS = {"hits": (_logloss, "h", "xh", 0), "bases": (_mse, "tb", "xtb", 1)}


def _scored(part, score, act, exp, k_act, k_exp, lg) -> dict:
    """Both predictors and the league's rate on a set of hitter-games;
    the gain is log loss saved, or the share of squared error saved."""
    a, e = score(part, act, k_act, lg), score(part, exp, k_exp, lg)
    gain = (a - e) if score is _logloss else ((a - e) / a if a else 0.0)
    return {"n": len(part), "actual": round(a, 5), "expected": round(e, 5),
            "league": round(score(part, act, 1e12, lg), 5), "gain": round(gain, 5)}


def measure(rows, model=None, min_games: int = MIN_GAMES, min_prior_ab: int = MIN_PRIOR_AB) -> dict:
    ss, league, model, (tune_from, test_from) = samples(rows, model, min_prior_ab=min_prior_ab)
    tune = [s for s in ss if s["part"] == "tune"]
    test = [s for s in ss if s["part"] == "test"]
    tdates = sorted({s["date"] for s in test})
    mid = tdates[len(tdates) // 2] if tdates else ""
    halves = ([s for s in test if s["date"] < mid], [s for s in test if s["date"] >= mid])
    res: dict = {"n_tune": len(tune), "n_test": len(test), "halves_n": [len(h) for h in halves],
                 "tune_from": tune_from, "test_from": test_from, "half_at": mid,
                 "league": [round(league[0], 4), round(league[1], 4)], "balls": model.get("n", 0),
                 "targets": {}}
    for name, (score, act, exp, li) in TARGETS.items():
        lg = league[li]
        k_act = min(GRID, key=lambda k: score(tune, act, k, lg)) if tune else GRID[0]
        k_exp = min(GRID, key=lambda k: score(tune, exp, k, lg)) if tune else GRID[0]
        whole = _scored(test, score, act, exp, k_act, k_exp, lg) if test else None
        parts = [_scored(h, score, act, exp, k_act, k_exp, lg) if h else {"n": 0, "gain": 0.0} for h in halves]
        bar = BAR_LOGLOSS if score is _logloss else BAR_MSE
        passed = all(p["n"] >= min_games and p["gain"] >= bar for p in parts)
        res["targets"][name] = {"k_actual": k_act, "k_expected": k_exp, "test": whole, "halves": parts,
                                "bar": bar, "passed": passed}
    res["passed"] = {k: v["passed"] for k, v in res["targets"].items()}
    return res


def read_rows(conn):
    return conn.execute("SELECT date, season, game_pk, batter_id, event_type, launch_speed, launch_angle "
                        "FROM mlb_pa WHERE batter_id IS NOT NULL AND date IS NOT NULL").fetchall()


def save(res: dict, path=None) -> Path:
    p = Path(path) if path else _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    out = dict(res, version=1,
               at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"))
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return p


def measured(path=None) -> dict | None:
    """The last saved verdict, or None before the first run."""
    try:
        m = json.loads(Path(path or _store()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m.get("passed"), dict) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.mlb.xstatsfit")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    from .. import db
    res = measure(read_rows(db.connect()))
    print(f"balls in the TRAIN table: {res['balls']:,}; TUNE from {res['tune_from']} "
          f"({res['n_tune']:,} hitter-games), TEST from {res['test_from']} ({res['n_test']:,}), "
          f"halves split at {res['half_at']}")
    for name, t in res["targets"].items():
        unit = "log loss" if name == "hits" else "squared error"
        w = t["test"]
        if not w:
            print(f"  {name.upper()}: no TEST hitter-games yet → does not pass")
            continue
        print(f"  {name.upper()} ({unit}; K actual {t['k_actual']}, expected {t['k_expected']})  "
              f"actual {w['actual']}  expected {w['expected']}  league {w['league']}  gain {w['gain']:+.5f}")
        for i, h in enumerate(t["halves"], 1):
            print(f"      half {i}: n {h['n']:,}  gain {h['gain']:+.5f}  (bar {t['bar']})")
        print(f"      → {'PASSES the bar' if t['passed'] else 'does not pass'}")
    if not a.dry_run:
        save(res)
        print("saved; a pass is a line on the hit tracker and a decision for Ethan, never a number")
    return 0


if __name__ == "__main__":
    sys.exit(main())
