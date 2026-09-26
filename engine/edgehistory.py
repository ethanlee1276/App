"""Does the model know anything the price doesn't — measured on a schedule.

On 2026-08-09 `stakecheck --info` answered that question for the first
time, and the answer was no: the model's ranking of its own bets and the
market's ranking of the same bets differ by +0.004 AUC, and the claimed
edge cannot be told apart from a coin flip. See
`docs/THE_INFORMATION_TEST.md`.

WHY THIS FILE EXISTS RATHER THAN JUST THE TOOL. That measurement took a
terminal, a human remembering to run it, and a human remembering what it
said last time. Which means in practice it gets run when something feels
wrong — exactly the times least able to distinguish a real change from
the mood that prompted the check.

The whole point of the finding is that it should MOVE if the model ever
starts working. A number that only exists in a scrollback cannot move,
because there is nothing to move against. So each run is stored, stamped
with the commit that produced it, and the site renders the series.

The same asymmetry `calibhistory` was built on applies here. The claimed
edge's AUC over a few hundred bets has an interval around +/-0.065; the
P&L over the same bets says almost nothing at all. Judging a model change
on the bet record alone means judging it on variance. This is the sharper
instrument, so it is the one worth keeping a history of.

Nothing here is retroactive. The first stored run is a baseline.
"""

from __future__ import annotations

import datetime as _dt
import json

from .calibhistory import code_version

_TABLE = """
CREATE TABLE IF NOT EXISTS edge_runs (
    ts TEXT PRIMARY KEY,
    code TEXT,
    category TEXT,
    n INTEGER, wins INTEGER,
    auc_model REAL, auc_model_lo REAL, auc_model_hi REAL,
    auc_market REAL, auc_market_lo REAL, auc_market_hi REAL,
    auc_edge REAL, auc_edge_lo REAL, auc_edge_hi REAL,
    diff REAL, diff_lo REAL, diff_hi REAL,
    clv_mean REAL, clv_se REAL, clv_n INTEGER,
    verdict TEXT,
    note TEXT
);
"""


def ensure(conn) -> None:
    conn.executescript(_TABLE)


def measure(rows: list[dict]) -> dict | None:
    """The information test, as a dict. None when the sample is too thin.

    Imports from `stakecheck` rather than duplicating the arithmetic. Two
    copies of an AUC is two things to keep in step, and the one nobody
    looks at is the one that drifts.
    """
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from stakecheck import _auc, _boot_auc, _boot_auc_diff
    from .odds import american_to_prob

    use = [r for r in rows
           if r.get("status") in ("won", "lost")
           and r.get("hit_prob") is not None and r.get("odds") is not None]
    if len(use) < 40:
        return None
    y = [1 if r["status"] == "won" else 0 for r in use]
    model = [float(r["hit_prob"]) for r in use]
    market = [american_to_prob(int(r["odds"])) for r in use]
    edge = [m - k for m, k in zip(model, market)]
    a_model, a_market, a_edge = (_auc(model, y), _auc(market, y),
                                 _auc(edge, y))
    if a_model is None or a_market is None or a_edge is None:
        return None      # all winners or all losers: AUC is undefined
    m_lo, m_hi = _boot_auc(model, y)
    k_lo, k_hi = _boot_auc(market, y)
    e_lo, e_hi = _boot_auc(edge, y)
    d_lo, d_hi = _boot_auc_diff(model, market, y)

    # THE VERDICT IS DERIVED HERE, ONCE, so the site, the nightly prose and
    # the LLM's evidence pack cannot each invent their own reading of the
    # same three numbers.
    if e_lo is not None and e_lo > 0.5:
        verdict = "edge_predicts"
    elif e_hi is not None and e_hi < 0.5:
        verdict = "edge_inverted"
    else:
        verdict = "edge_is_noise"
    return {
        "ts": _dt.datetime.utcnow().isoformat(timespec="microseconds"),
        "code": code_version(),
        "n": len(use), "wins": sum(y),
        "auc_model": a_model, "auc_model_lo": m_lo, "auc_model_hi": m_hi,
        "auc_market": a_market, "auc_market_lo": k_lo, "auc_market_hi": k_hi,
        "auc_edge": a_edge, "auc_edge_lo": e_lo, "auc_edge_hi": e_hi,
        "diff": a_model - a_market, "diff_lo": d_lo, "diff_hi": d_hi,
        "verdict": verdict,
    }


def record(conn, rows: list[dict], category: str = "main",
           clv: dict | None = None, note: str = "") -> dict | None:
    """Measure and store one run. Never raises — losing a history row must
    not take down the settle that produced it."""
    try:
        ensure(conn)
        m = measure(rows)
        if m is None:
            return None
        m["category"] = category
        m["note"] = note
        for k in ("clv_mean", "clv_se", "clv_n"):
            m[k] = (clv or {}).get(k)
        cols = ("ts, code, category, n, wins, auc_model, auc_model_lo, "
                "auc_model_hi, auc_market, auc_market_lo, auc_market_hi, "
                "auc_edge, auc_edge_lo, auc_edge_hi, diff, diff_lo, diff_hi, "
                "clv_mean, clv_se, clv_n, verdict, note")
        conn.execute(
            f"INSERT OR REPLACE INTO edge_runs ({cols}) VALUES "
            f"({','.join('?' * len(cols.split(', ')))})",
            tuple(m[k.strip()] for k in cols.split(", ")))
        conn.commit()
        return m
    except Exception:                                       # noqa: BLE001
        return None


def series(conn, category: str = "main", limit: int = 60) -> list[dict]:
    """Every stored run, oldest first, for the chart."""
    try:
        ensure(conn)
        rows = conn.execute(
            "SELECT * FROM edge_runs WHERE category=? "
            "ORDER BY ts DESC LIMIT ?", (category, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
    except Exception:                                       # noqa: BLE001
        return []


def latest(conn, category: str = "main") -> dict | None:
    s = series(conn, category, limit=1)
    return s[-1] if s else None
