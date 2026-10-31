"""Stop staking a market shelf the record says is losing.

Ethan, 2026-09-21: *"what makes people the most money without losing the
most money alongside increasing and boosting our ROI record."*

THE ROI LEVER IS SELECTION, NOT SIZE. A flat stake cannot move ROI — see
`engine/likelysize` — so the only thing that raises the percentage is
taking fewer, better bets. This is the mechanism for the "fewer" half,
and it is the one the Edge book did not have.

WHY THE EDGE BOOK NEEDS IT MOST. It is the board staking the most real
money and carrying the least evidence: `boards.EDGE_AUC` is 0.468, below
a coin flip, and `engine/haircut` measured what the claim is worth at
settlement — CFB claimed +12.53% and landed -0.06%, NFL claimed +9.77%
and landed -1.13%, every band spanning zero at every claim size. The
likelihood board has had a breaker since it was staked (`live_verdict`
cuts a band that is not paying and leaves the rest alone). The book with
more money on it and worse evidence had none.

SAME BAR AS THAT BREAKER, PLUS ONE. A shelf is stopped at
`ledger.LIVE_STOP_Z` — two standard errors clear of zero on the losing
side — over at least `MIN_N` settled rows. The extra is false-discovery
control: the likelihood breaker tests four bands, this tests every
market of every sport, and at sixty shelves a z of -2 throws up more
than one false stop per run by chance alone. Benjamini-Hochberg over
ALL eligible shelves, the same control `losspatterns` mines under, and
the same rule about m: every shelf tested, never only the ones that
looked bad.

THE ASYMMETRY IS WHY THE BAR IS NOT STRICTER THAN THAT. A false stop
costs the edge on a shelf whose measured edge is indistinguishable from
zero — approximately nothing. Failing to stop a losing shelf costs money
every night. Bonferroni over sixty tests would need a z near -3.2 and
would never fire, which is not caution, it is a rule written to do
nothing.

WHAT THIS DOES NOT YET DO: grade the counterfactual. A stopped shelf's
picks are refused rather than journaled at zero stake, so the record
cannot say whether stopping was right the way the likelihood board's
demotion can. What it CAN say is how many picks the stop is costing,
because the refusal reason lands in the board's `why` census like every
other. Saying so here rather than implying otherwise.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

#: Settled, staked rows before a shelf can be judged at all. Above the
#: likelihood breaker's per-band floor of 60 because a shelf that is
#: stopped stops earning, and below its whole-book 100 because a shelf
#: is a smaller thing than a book.
MIN_N = 80

#: The false-discovery rate across every shelf tested.
FDR_ALPHA = 0.10

#: Where the decision is kept between the settle pass that makes it and
#: the build that reads it — the same shape `losspatterns` uses, for the
#: same reason: pick-time code has no ledger connection and must not
#: grow one.
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "models" \
    / "shelfstop.json"


def _phi(x: float) -> float:
    from .losspatterns import _phi as p
    return p(x)


def measure(conn, since: str | None = None) -> list[dict]:
    """Every (sport, market) shelf in the money book, with its z."""
    from .ledger import BOOK, _roi_z, off_record_sql
    marks = ",".join("?" * len(BOOK))
    bench, bargs = off_record_sql()
    q = ("SELECT sport, market, COUNT(*) n, SUM(status='won') w, "
         "COALESCE(SUM(pnl_units),0) u, "
         "COALESCE(SUM(CASE WHEN status='push' THEN 0 ELSE stake_units END),0) s "
         "FROM bets WHERE status IN ('won','lost') AND stake_units > 0 "
         f"AND category IN ({marks})" + bench)
    args: list = list(BOOK) + list(bargs)
    if since:
        q += " AND date >= ?"
        args.append(since)
    out = []
    for r in conn.execute(q + " GROUP BY sport, market", args):
        n = int(r["n"] or 0)
        if not n or not r["s"]:
            continue
        roi = r["u"] / r["s"]
        hit = float(r["w"] or 0) / n
        z = _roi_z(hit, roi, n)
        out.append({"sport": str(r["sport"] or ""),
                    "market": str(r["market"] or ""),
                    "n": n, "roi": round(roi, 4), "hit": round(hit, 4),
                    "z": None if z is None else round(z, 3)})
    return out


def decide(shelves: list[dict], alpha: float = FDR_ALPHA) -> dict:
    """``{"shelves": [...], "stopped": [...]}`` — the verdicts.

    THE m IS EVERY ELIGIBLE SHELF, not every shelf that looked bad.
    Shrinking it after peeking is how false-discovery control dies, and
    `losspatterns._bh` says so in its own docstring.
    """
    from .ledger import LIVE_STOP_Z
    from .losspatterns import _bh
    eligible = [s for s in shelves if s["n"] >= MIN_N and s["z"] is not None]
    for s in eligible:
        s["p"] = min(1.0, 2.0 * (1.0 - _phi(abs(s["z"]))))
    _bh(eligible, alpha)
    stopped = []
    for s in shelves:
        if s not in eligible:
            s["verdict"] = "run"
            s["why"] = (f"{s['n']} settled, {MIN_N} needed before this shelf "
                        f"can be judged")
            continue
        if s["z"] <= LIVE_STOP_Z and s.get("survives"):
            s["verdict"] = "stop"
            s["why"] = (f"{s['roi']:+.1%} over {s['n']} settled "
                        f"(z {s['z']:+.2f}, q {s.get('q')}) — clear of the "
                        f"noise band on the losing side, and it survives "
                        f"false-discovery control over every shelf tested")
            stopped.append({k: s[k] for k in
                            ("sport", "market", "n", "roi", "z", "why")})
        elif s["z"] <= LIVE_STOP_Z:
            # LOSING PAST TWO STANDARD ERRORS AND STILL NOT STOPPED. With
            # sixty shelves tested this is what one of them looks like by
            # chance, and acting on it is the error this repo has made
            # with a 2-row shelf before.
            s["verdict"] = "review"
            s["why"] = (f"{s['roi']:+.1%} over {s['n']} settled "
                        f"(z {s['z']:+.2f}) — past the noise band on its "
                        f"own, but not once every shelf tested is counted "
                        f"(q {s.get('q')})")
        else:
            s["verdict"] = "run"
            s["why"] = f"{s['roi']:+.1%} over {s['n']} settled (z {s['z']:+.2f})"
    return {"generated_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
            "min_n": MIN_N, "alpha": alpha,
            "tested": len(eligible), "shelves": shelves, "stopped": stopped}


def save(result: dict, path=None) -> Path:
    p = Path(path if path is not None else DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=1))
    return p


#: (path, mtime) → parsed store. `blocked` runs once per candidate pick,
#: thousands a build, and the store only changes when a settle pass
#: re-decides — so the mtime is a cache key that cannot serve stale.
_cache: dict = {}


def load(path=None) -> dict:
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if key in _cache:
        return _cache[key]
    try:
        raw = json.loads(p.read_text())
        out = raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        out = {}
    _cache.clear()
    _cache[key] = out
    return out


def refresh(lconn, path=None) -> dict:
    """Re-decide from the journal and persist — the settle-pass step,
    beside `losspatterns.refresh` and for the same reason."""
    result = decide(measure(lconn))
    save(result, path)
    return result


def blocked(sport: str, market: str, path=None) -> str | None:
    """The reason this shelf is not being staked, or None.

    Reached through `losspatterns.veto`, which every board already
    consults — deliberately, rather than at each board's own gate. Four
    engines call that veto today and a fifth will be written; a rule
    added at four of five call sites is the shape `game_day` took when
    eight inserts of eleven forgot it.
    """
    for s in (load(path).get("stopped") or []):
        if s.get("sport") == sport and s.get("market") == market:
            return (f"This shelf is stopped: {sport} {market} is "
                    f"{s['roi']:+.1%} over {s['n']} settled bets "
                    f"(z {s['z']:+.2f}). It keeps being priced and shown; "
                    f"it is not being staked until the record turns.")
    return None
