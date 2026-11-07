"""Is the top of the touchdown board too shy? A one-knee calibration, measured.

    sudo -u qellys nice -n 19 python3 -m engine.tdtop
    sudo -u qellys nice -n 19 python3 -m engine.tdtop --dry-run

Ethan, 2026-10-04: four touchdown scans priced our favourites higher than
we did. Two records then said the same thing. The live one: 16 settled TD
picks we called 50%+ claimed 62% and scored 81%. The five-season replay
(`tdbacktest --board`, 96 slates): the top 1 / 3 / 5 per slate claimed
62.7 / 58.1 / 55.5% and landed 67.7 / 64.2 / 59.8%, while the top 20 and 40
were on the number.

WHY THE CALIBRATION LEAVES IT. The touchdown correction is a temperature,
logit(q) = logit(p) / T + intercept, with T ≈ 1.12: it lifts every chance a
little and SQUEEZES the spread, because the bulk of the board (15-40%) is
where the fit's weight is. A squeeze is right in the middle and wrong at
the top, where the replay says the spread should open up.

WHAT THIS FITS. The same correction plus one hinge above a knee fixed in
advance:

    baseline   logit(q) = a + b·z
    hinged     logit(q) = a + b·z + c·max(0, z − KNEE)       z = logit(p)

KNEE is the raw chance KNEE_P (40%), chosen before any run from the replay
table: the gap opens above the top 20, whose claims sit near 45% after
calibration, which is about 40% raw. Below the knee the two are the same
shape, so long shots are untouched.

THE BAR, WRITTEN BEFORE ANY RUN. Leave one season out; the hinged fit is
adopted only if (1) held-out log loss beats the baseline pooled AND in all
but one season, (2) c is positive with a cluster-robust t of at least MIN_T
(clusters = one slate, a season-week), (3) on the held-out seasons the
top-TOP_K-per-slate gap between claimed and landed shrinks, and (4) at
least MIN_ROWS rows, MIN_ABOVE of them above the knee. Saved to
td_top.json either way, with its verdict; NOTHING READS IT YET. Wiring it
into the board is a separate change, because every journaled bet records
the temperature it was priced under so the record can be un-corrected,
and a hinge needs its own column before it can be.

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

KNEE_P = 0.40
MIN_T = 2.0
MIN_ROWS = 2000
MIN_ABOVE = 300
TOP_K = 5
STORE_VERSION = 1


def _store() -> Path:
    return Path(modelstate.path("td_top.json"))


def knee() -> float:
    return math.log(KNEE_P / (1.0 - KNEE_P))


def points(rows: list[dict]) -> list[tuple]:
    """[(season, slate, z, max(0, z − knee), scored)] from tdbacktest rows."""
    from .tdfeatures import logit
    k = knee()
    out = []
    for r in rows:
        z = logit(float(r["prob"]))
        out.append((int(r["season"]), (int(r["season"]), str(r["week"])), z, max(0.0, z - k),
                    int(r["scored"])))
    return out


def _q(beta, d, hinged: bool) -> float:
    from .tdfeatures import sigmoid
    return sigmoid(beta[0] + beta[1] * d[2] + (beta[2] * d[3] if hinged else 0.0))


def top_gap(test: list[tuple], beta, hinged: bool, k: int = TOP_K) -> tuple:
    """(claimed, landed) over the top ``k`` of every slate by the fitted chance."""
    by = defaultdict(list)
    for d in test:
        by[d[1]].append((_q(beta, d, hinged), d[4]))
    claimed = landed = n = 0
    for rows in by.values():
        for q, y in sorted(rows, key=lambda t: -t[0])[:k]:
            claimed += q
            landed += y
            n += 1
    return (claimed / n, landed / n) if n else (None, None)


def judge(data: list[tuple]) -> dict:
    from .tdinjfit import _fit, _loss, cluster_t
    seasons = sorted({d[0] for d in data})
    per, better = {}, 0
    base_sum = hinge_sum = 0.0
    gaps = {"base": [0.0, 0.0, 0], "hinge": [0.0, 0.0, 0]}
    for s in seasons:
        train = [d for d in data if d[0] != s]
        test = [d for d in data if d[0] == s]
        b0, _ = _fit(train, False)
        b1, _ = _fit(train, True)
        if b0 is None or b1 is None or not test:
            continue
        base, hinge = _loss(b0, test, False), _loss(b1, test, True)
        per[s] = {"n": len(test), "gain": round((base - hinge) / len(test), 6)}
        better += hinge < base
        base_sum += base
        hinge_sum += hinge
        for name, beta, h in (("base", b0, False), ("hinge", b1, True)):
            c, l = top_gap(test, beta, h)
            if c is not None:
                k = len(test)                    # weight seasons by their size
                gaps[name][0] += c * k
                gaps[name][1] += l * k
                gaps[name][2] += k
    b, t = cluster_t(data) if data else (None, None)
    above = sum(1 for d in data if d[3] > 0)
    top = {name: (round(v[0] / v[2], 4), round(v[1] / v[2], 4)) if v[2] else (None, None)
           for name, v in gaps.items()}
    gap_base = abs(top["base"][1] - top["base"][0]) if top["base"][0] is not None else None
    gap_hinge = abs(top["hinge"][1] - top["hinge"][0]) if top["hinge"][0] is not None else None
    passed = bool(len(per) >= 2 and hinge_sum < base_sum and better >= len(per) - 1
                  and b is not None and b > 0 and t is not None and t >= MIN_T
                  and gap_base is not None and gap_hinge < gap_base
                  and len(data) >= MIN_ROWS and above >= MIN_ABOVE)
    full, _ = _fit(data, True) if data else (None, None)
    return {"n": len(data), "above_knee": above, "c": None if b is None else round(b, 4),
            "t": None if t is None else round(t, 2), "seasons": per, "better": better,
            "gain": round((base_sum - hinge_sum) / len(data), 6) if data else 0.0,
            "top": {"k": TOP_K, "base": top["base"], "hinge": top["hinge"]},
            "fit": None if full is None else [round(x, 5) for x in full],
            "knee_p": KNEE_P, "passed": passed}


def measure(conn) -> dict:
    from .tdbacktest import run
    rows: list = []
    run(conn, collect=rows.append)
    return judge(points(rows))


def save(res: dict, path=None) -> None:
    p = Path(path or _store())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": STORE_VERSION, **res,
                             "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                             .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")


def report(res: dict) -> str:
    per = ", ".join(f"{s} {d['gain']:+.5f}" for s, d in res["seasons"].items())
    tb, th = res["top"]["base"], res["top"]["hinge"]
    pct = lambda v: "—" if v is None else f"{v:.1%}"
    return (f"  TOP OF THE TD BOARD  one hinge above a raw {KNEE_P:.0%}\n"
            f"      {res['n']:,} player-weeks, {res['above_knee']:,} above the knee\n"
            f"      held-out top {res['top']['k']} per slate: today's calibration claims {pct(tb[0])}, "
            f"lands {pct(tb[1])}; hinged claims {pct(th[0])}, lands {pct(th[1])}\n"
            f"      c {res['c']}  clustered t {res['t']}  held-out gain {res['gain']:+.6f} "
            f"(better {res['better']}/{len(res['seasons'])}: {per})  → "
            f"{'PROVEN' if res['passed'] else 'not proven'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.tdtop")
    ap.add_argument("--dry-run", action="store_true", help="measure and report, save nothing")
    a = ap.parse_args(argv)
    from . import db
    res = measure(db.connect())
    print(report(res))
    if not a.dry_run:
        save(res)
        print("saved with its verdict; nothing reads it until it is wired in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
