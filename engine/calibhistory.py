"""Keep every calibration sweep, so "are we improving?" has an answer.

The question was unanswerable. Each sweep printed a table to a terminal and
vanished, so a model change could be judged on the forward bet record — the
MODEL_ERAS split on the Record page — but never on whether the
PROBABILITIES got better. That is the thing a re-tune is actually trying to
fix, and it is measurable in thousands of settled props today rather than
in a P&L sample that needs a season to say anything at all.

The asymmetry is the point. A calibration sweep over 295,627 props can
detect a 2-point improvement immediately. The same improvement takes years
to show up in win-loss, because betting outcomes are mostly variance.
Judging model changes on P&L alone means judging them on noise.

Each row is one market from one run, stamped with the git SHA, so a jump in
ECE ties to a commit rather than to a memory of what changed that week.

Nothing here is retroactive: runs made before this existed were not
recorded and cannot be recovered. The first stored run is a baseline, not
a verdict.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess


def code_version() -> str:
    """The commit this run measured. Without it a trend is a list of
    numbers with no causes attached."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        sha = (out.stdout or "").strip()
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               capture_output=True, text=True, timeout=10)
        code = [l for l in (dirty.stdout or "").splitlines()
                if l.strip() and not l.split()[-1].startswith(("web/data/",
                                                               "data/"))]
        return f"{sha}+dirty" if code else sha
    except Exception:
        return ""


def record(conn, sport: str, market: str, report, note: str = "",
           ts: str | None = None) -> None:
    """Store one market's result. Never raises: losing a history row must
    not take down the sweep that produced it."""
    try:
        sk = report.skill() if hasattr(report, "skill") else None
        bins = [{"lo": b.lo, "hi": b.hi, "n": b.n,
                 "said": b.mean_pred, "actual": b.hit_rate}
                for b in (getattr(report, "bins", None) or []) if b.n]
        conn.execute(
            "INSERT OR REPLACE INTO calibration_runs (ts, code, sport, market,"
            " n, brier, ece, base_rate, skill, hedged, bins, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            # Microseconds, not seconds. Two sweeps finishing inside the
            # same second collapsed into one row under the primary key —
            # a history that silently drops measurements is not a history.
            (ts or _dt.datetime.now().isoformat(timespec="microseconds"),
             code_version(), sport, market,
             getattr(report, "n", 0), getattr(report, "brier", 0.0),
             getattr(report, "ece", 0.0),
             (sk or {}).get("base_rate"), (sk or {}).get("skill"),
             (sk or {}).get("hedged"),
             json.dumps(bins), note))
        conn.commit()
    except Exception:
        pass


def history(conn, sport: str = "mlb", market: str | None = None,
            limit: int = 40) -> list[dict]:
    q = ("SELECT ts, code, market, n, brier, ece, base_rate, skill, hedged, "
         "note FROM calibration_runs WHERE sport=?")
    args: list = [sport]
    if market:
        q += " AND market=?"
        args.append(market)
    q += " ORDER BY ts DESC, market LIMIT ?"
    args.append(limit)
    try:
        return [dict(r) for r in conn.execute(q, args)]
    except Exception:
        return []


def trend(conn, sport: str = "mlb") -> dict:
    """Per market: the first stored run, the latest, and the move.

    Direction is stated rather than left to the reader, because ECE going
    DOWN is an improvement and half the numbers on this page improve by
    going up. A sign error here would be read as a result.
    """
    out: dict = {}
    try:
        markets = [r[0] for r in conn.execute(
            "SELECT DISTINCT market FROM calibration_runs WHERE sport=? "
            "ORDER BY market", (sport,))]
    except Exception:
        return out
    for m in markets:
        rows = [dict(r) for r in conn.execute(
            "SELECT ts, code, n, brier, ece, skill, hedged "
            "FROM calibration_runs WHERE sport=? AND market=? ORDER BY ts",
            (sport, m))]
        if not rows:
            continue
        first, last = rows[0], rows[-1]
        out[m] = {
            "runs": len(rows), "first": first, "last": last,
            "ece_delta": (last["ece"] or 0) - (first["ece"] or 0),
            "brier_delta": (last["brier"] or 0) - (first["brier"] or 0),
            # Improvement means ECE falling. Spelled out so nobody has to
            # remember which way is good while reading a table.
            "improved": (last["ece"] or 0) < (first["ece"] or 0),
            "same_code": first["code"] == last["code"],
        }
    return out
