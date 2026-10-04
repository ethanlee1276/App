"""How hard a scorer's chance should follow his team's expected points.

    sudo -u qellys python3 -m engine.tdscale            # replay 2021+, save what holds
    sudo -u qellys python3 -m engine.tdscale --dry-run

Ethan, 2026-10-04: "can we do that same work for the most likely td
models. we want the tds better too."

WHAT THE RECORD SAID. The model scales a team's touchdowns straight with
its implied total (touchdowns.expected_team_tds — 27 expected points is
27/21.5 of an average team's touchdowns) and a game-script step by the
spread. The graded NFL touchdown picks say that is not steep enough:
teams the books expected to score 18-22 went 1-for-12 at a claimed 43%,
and teams at 26+ went 13-for-21 at a claimed 49%. And five seasons of
history (engine/scouthist): a scorer on a team implied under 18 scored
15% of the time against 21% for everyone, in both halves. Twelve and
twenty-one picks are a hint; the replay below is the measurement.

WHAT THIS MEASURES. The production touchdown model, replayed week by week
over every stored season (engine/tdbacktest, which runs td_probability
itself on the inputs it would have had). For each position, one exponent
g: the chance a scorer is given becomes

    1 − (1 − p) ^ ((implied ÷ league average) ^ g)

g = 0 is today's model; g > 0 makes a high-scoring team's scorers likelier
and a low-scoring team's less likely, on top of what the model already
does. Each g is judged AFTER a logistic recalibration fitted on the same
training seasons — the temperature the board already applies
(tdbacktest.fit_calibration) — so a g can only win by ordering scorers
better across team totals, never by redoing the calibration's job.

THE BAR, WRITTEN BEFORE ANY BOX RUN (the posspread/scouthist bar): leave
one season out; g fitted on the others; adopted only if held-out log loss
beats g = 0 pooled and in at least MIN_SEASONS_BETTER seasons, on MIN_ROWS
player-weeks or more. Otherwise 0.

ORDER. Weekly, inside engine/deepfit and BEFORE the touchdown temperature
is refitted, so the temperature is always fitted on top of this. The
replay this fitter reads runs with the correction switched off (`raw`),
so a refit never learns from its own adjustment.

Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from . import modelstate

POSITIONS = ("RB", "WR", "TE", "QB")
GAMMA_GRID = tuple(round(-0.5 + 0.1 * i, 1) for i in range(26))       # -0.5 .. 2.0
MIN_ROWS = 1500
MIN_SEASONS_BETTER = 4
STORE_VERSION = 1

_STATE = {"enabled": True}
_CACHE: dict = {}


def _store() -> Path:
    return Path(modelstate.path("td_implied.json"))


def load(path=None) -> dict:
    try:
        store = json.loads(Path(path or _store()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return store if store.get("version") == STORE_VERSION else {}


def gamma_for(position: str) -> float:
    """The adopted exponent for this position, 0.0 where none passed or
    while `raw()` is in force. Re-read when the store changes."""
    if not _STATE["enabled"]:
        return 0.0
    p = _store()
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        stamp = (str(p), None)
    if _CACHE.get("stamp") != stamp:
        _CACHE["stamp"], _CACHE["g"] = stamp, (load(p).get("gamma") or {})
    return float((_CACHE["g"].get(str(position or "").upper()) or {}).get("g", 0.0))


@contextlib.contextmanager
def raw():
    """The model as it was before this correction — what the fitter reads."""
    was = _STATE["enabled"]
    _STATE["enabled"] = False
    try:
        yield
    finally:
        _STATE["enabled"] = was


def adjust(p: float, implied, gamma: float) -> float:
    """1 − (1 − p) ^ ((implied ÷ league average) ^ gamma)."""
    from .longshots import NFL_AVG_TEAM_POINTS
    if not gamma or not implied or implied <= 0:
        return p
    p = min(0.999, max(0.001, float(p)))
    return 1.0 - (1.0 - p) ** ((float(implied) / NFL_AVG_TEAM_POINTS) ** gamma)


# --- the fit -----------------------------------------------------------------
def _logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1.0 - p))


def _ll(p: float, y: int) -> float:
    p = min(0.999, max(0.001, p))
    return -math.log(p if y else 1.0 - p)


def fit_logistic(xs, ys) -> tuple[float, float]:
    """(a, b) of P = 1/(1+e^-(a + b·x)) by Newton's method — the recalibration
    every candidate is judged after."""
    a, b = 0.0, 1.0
    for _ in range(12):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            p = 1.0 / (1.0 + math.exp(-(a + b * x)))
            w = p * (1.0 - p)
            ga += y - p
            gb += (y - p) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a + da, b + db
        if abs(da) < 1e-7 and abs(db) < 1e-7:
            break
    return a, b


def _scored(train, test, gamma):
    """(fitted calibration on train) → (train loss, test loss) at this gamma."""
    xtr = [_logit(adjust(p, imp, gamma)) for _s, p, imp, _y in train]
    ytr = [y for *_r, y in train]
    a, b = fit_logistic(xtr, ytr)
    cal = lambda x: 1.0 / (1.0 + math.exp(-(a + b * x)))
    tr = sum(_ll(cal(x), y) for x, y in zip(xtr, ytr))
    te = sum(_ll(cal(_logit(adjust(p, imp, gamma))), y) for _s, p, imp, y in test)
    return tr, te


def best_gamma(data) -> float:
    return min(GAMMA_GRID, key=lambda g: _scored(data, [], g)[0])


def judge(data: list) -> dict:
    """data = [(season, p, implied, scored)] for one position."""
    seasons = sorted({d[0] for d in data})
    per, better, raw_sum, fit_sum = {}, 0, 0.0, 0.0
    for s in seasons:
        train = [d for d in data if d[0] != s]
        test = [d for d in data if d[0] == s]
        if not train or not test:
            continue
        g = best_gamma(train)
        base = _scored(train, test, 0.0)[1]
        fit = _scored(train, test, g)[1]
        per[s] = {"g": g, "n": len(test), "gain": round((base - fit) / len(test), 5)}
        better += fit < base
        raw_sum += base
        fit_sum += fit
    n = len(data)
    g_all = best_gamma(data) if data else 0.0
    passed = bool(n >= MIN_ROWS and fit_sum < raw_sum and better >= MIN_SEASONS_BETTER and g_all != 0.0)
    return {"g": g_all, "n": n, "seasons": per, "better": better,
            "gain": round((raw_sum - fit_sum) / n, 5) if n else 0.0, "passed": passed}


def replay_rows(conn) -> dict:
    """{position: [(season, p, implied, scored)]} from the production model,
    replayed with this correction switched off."""
    from .tdbacktest import run
    rows: list = []
    with raw():
        run(conn, collect=rows.append)
    by = defaultdict(list)
    for r in rows:
        pos = str(r.get("position") or "").upper()
        if pos in POSITIONS and r.get("implied"):
            by[pos].append((r["season"], float(r["prob"]), float(r["implied"]), int(r["scored"])))
    return by


def measure(conn) -> dict:
    return {pos: judge(data) for pos, data in replay_rows(conn).items()}


def save(res: dict, path=None) -> None:
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    gamma = {k: {"g": v["g"], "n": v["n"], "gain": v["gain"]} for k, v in res.items() if v["passed"]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"version": STORE_VERSION, "gamma": gamma,
                               "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                               .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")
    tmp.replace(p)
    _CACHE.clear()


def report_lines(res: dict) -> list[str]:
    out = []
    for k in POSITIONS:
        v = res.get(k)
        if not v:
            continue
        verdict = f"ADOPT g {v['g']:+.1f}" if v["passed"] else "keep g +0.0"
        out.append(f"  touchdowns {k:3} n {v['n']:6}  fitted g {v['g']:+.1f}  held-out gain {v['gain']:+.5f}  "
                   f"better in {v['better']}/{len(v['seasons'])} seasons  → {verdict}")
    return out


def refit(conn, dry_run: bool = False) -> list[str]:
    res = measure(conn)
    if not dry_run:
        save(res)
    return report_lines(res) or ["  touchdowns: no replayable seasons yet"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.tdscale")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    from . import db
    for line in refit(db.connect(), a.dry_run):
        print(line)
    print("dry run: nothing saved" if a.dry_run else "saved; the next build reads it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
