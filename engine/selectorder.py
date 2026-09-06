"""Which ORDERING of the same pool should get the money?

Ethan, 2026-09-06, after `stakecheck --info` returned 931 settled bets
with the model at AUC 0.589, the market at 0.589, the claimed edge at
0.471 and a paired difference of -0.000 [-0.007, +0.007], chose:
"Rebuild what it selects on" — keep staking, stop selecting on claimed
edge, sort and gate on the model's probability rank instead.

This module is the backtest that has to run BEFORE that gate changes.
Not because the decision is in doubt — it is Ethan's to make — but
because the last time this repo changed what the board selects on it did
so on an argument, and the argument is exactly the thing the information
test says cannot be trusted. A selection rule that has never been scored
against the alternative it replaces is a second unmeasured claim
standing where the first one was.

THE QUESTION THIS CAN ANSWER
----------------------------
Take the bets we actually placed and settled. Order them three ways,
take the top slice of each, and count the money:

    edge    hit_prob - implied, the number every gate in the repo reads
    prob    hit_prob alone, the ordering Ethan chose
    market  the implied probability from the price we took

Same rows, same prices, same vig, same settling. The only difference is
which of them get the money, so the difference in ROI is a difference in
SELECTION and nothing else. That is the same construction `likely.py`
records in its own docstring for receptions and rec_yds, generalised and
made re-runnable.

THE THIRD ORDERING IS THE POINT, and it is not decoration. The
information test measured the model's AUC and the market's AUC at the
same 0.589 with a paired difference indistinguishable from zero. If
those two rank the same bets the same way, then "sort by the model's
probability" and "sort by the shortest price" are the same instruction
wearing different words — and this repo already knows, in writing, what
sorting by the shortest price does: `likely.HEAVIEST_PRICE` exists
because a board built that way spent its first settled night on -800,
-1200 and -1800 rows and lost 11.2%. So the overlap between the `prob`
slice and the `market` slice is reported beside the ROIs. A high overlap
is not a bug in the rebuild; it is the measurement telling us the
rebuild needs a price bar bolted to it, which is a design fact worth
knowing before the gate moves rather than after.

AND A FOURTH ARM THAT IS NOT AN ORDERING. "Sort and gate on the model's
probability rank" is two decisions, and they can come apart: a cut can
lose money on a pool the same sort orders perfectly, because the top
slice by probability is the shortest prices on the board and the hold
sits where the money goes. So `all` — bet every row the gate already
admitted, at flat stakes, no cut — is scored against the `prob` slice
with its own paired interval. `likely.HEAVIEST_PRICE` is that failure
already paid for once.

THE QUESTION THIS CANNOT ANSWER
-------------------------------
Whether probability-ranking would have ADMITTED better bets that the
edge gate refused. The journal holds bets we placed; it does not hold
the candidates we passed on, and a bet with no settled outcome cannot be
scored. So every number here is conditional on the current gate having
already run. It compares two ways of ordering and cutting the same
admitted pool, which is the honest half of the question, and the half
that decides whether the board's sort order and its cap should change.

The other half needs the candidate surface with outcomes attached, which
is `engine.backtest`'s replay rather than the journal, and is registered
as its own piece of work rather than smuggled in here as an assumption.

FLAT STAKES BY DEFAULT, and deliberately. Ethan's instruction keeps the
staking rule ("size on the price ladder that is already measured") and
changes the selection, so the measurement has to isolate selection. At
one unit a bet the ROI difference between two orderings is entirely the
difference in which bets they chose. `stakes="as_placed"` re-runs it at
the sizes actually recorded, which answers the different and also-useful
question of what would have happened to the real bankroll.

Standard library only.
"""

from __future__ import annotations

import math

#: Settled bets in the pool before any of this may be read. Below this
#: the top quarter is a few dozen rows and its ROI carries ten points of
#: standard error, which is wider than any selection effect worth acting
#: on.
MIN_N = 100

#: The slice each ordering gets to bet. A quarter is the cut
#: `engine.likely`'s own bake-off used, kept so the two tables can be
#: read against each other.
TOP_SHARE = 0.25

#: The orderings compared. `market` is the control described above, not
#: a proposal — nobody is suggesting the board sort itself by the book's
#: price.
ORDERINGS = ("edge", "prob", "market")

#: At or above this share of shared rows, two orderings are picking the
#: same bets and calling them different things.
PROXY_OVERLAP = 0.85


def _payout(odds: int) -> float:
    """Profit per unit staked on a winner at American odds."""
    odds = int(odds)
    return odds / 100.0 if odds > 0 else 100.0 / abs(odds)


def usable(rows) -> list[dict]:
    """The settled rows that can be ordered all three ways.

    A row missing `hit_prob` or `odds` cannot be scored by the model
    ordering OR the market one, so dropping it keeps the three
    orderings on an identical population — which is the entire basis
    for reading a difference between them as a selection effect.
    """
    out = []
    for r in rows:
        if r["status"] not in ("won", "lost"):
            continue
        if r.get("hit_prob") is None or r.get("odds") is None:
            continue
        try:
            p, o = float(r["hit_prob"]), int(r["odds"])
        except (TypeError, ValueError):
            continue
        if not o:
            continue
        try:
            stake = float(r.get("stake_units") or 0.0)
        except (TypeError, ValueError):
            stake = 0.0
        out.append({"p": p, "odds": o, "won": r["status"] == "won",
                    "stake": stake, "sport": r.get("sport") or "",
                    "market": r.get("market") or ""})
    return out


def _scores(pool: list[dict], order: str) -> list[float]:
    from .odds import american_to_prob
    if order == "all":
        # NOT an ordering. `all` is the do-not-cut arm: every row scores
        # the same, so the slice below is the whole pool whatever
        # `top_share` says. It is here so the question "should we cut at
        # all?" gets the same paired interval as "cut on what?" — Ethan's
        # instruction was to sort AND gate, and those are two decisions.
        return [0.0] * len(pool)
    if order == "prob":
        return [r["p"] for r in pool]
    if order == "market":
        return [american_to_prob(r["odds"]) for r in pool]
    if order == "edge":
        return [r["p"] - american_to_prob(r["odds"]) for r in pool]
    raise ValueError(f"unknown ordering {order!r}")


def _top(pool: list[dict], order: str, top_share: float,
         idx: list[int] | None = None) -> list[int]:
    """Indices of the slice this ordering would bet, best first.

    Ties break on position, which is the journal's own insertion order.
    An arbitrary but FIXED tiebreak matters here: three orderings of a
    pool containing repeated prices will tie constantly, and a tiebreak
    that varied between them would show up as a selection difference
    that nobody chose.
    """
    if idx is None:
        idx = list(range(len(pool)))
    sc = _scores(pool, order)
    ranked = sorted(idx, key=lambda i: (-sc[i], i))
    if order == "all":
        return ranked
    k = max(1, int(math.ceil(len(ranked) * top_share)))
    return ranked[:k]


def _score_slice(pool: list[dict], picks, stakes: str) -> dict:
    n = wins = 0
    staked = net = 0.0
    for i in picks:
        r = pool[i]
        stake = 1.0 if stakes == "flat" else r["stake"]
        if stake <= 0:
            continue
        n += 1
        staked += stake
        if r["won"]:
            wins += 1
            net += stake * _payout(r["odds"])
        else:
            net -= stake
    return {"bets": n, "wins": wins,
            "hit": (wins / n) if n else None,
            "staked": round(staked, 2), "net": round(net, 2),
            "roi": (net / staked) if staked else None}


def _boot_roi_diff(pool, a: str, b: str, top_share: float, stakes: str,
                   reps: int, seed: int):
    """Percentile CI for ROI(a) - ROI(b), resampling BETS not slices.

    The selection is inside the statistic on purpose. Each replicate
    re-orders and re-cuts the resampled pool, so the interval carries
    the uncertainty in WHICH bets each rule would have picked as well as
    the uncertainty in how they ran. Cutting once and bootstrapping the
    two fixed slices would report an interval for a decision that was
    made with hindsight.
    """
    import random
    rng = random.Random(seed)
    n = len(pool)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        rs = [pool[i] for i in idx]
        ra = _score_slice(rs, _top(rs, a, top_share), stakes)["roi"]
        rb = _score_slice(rs, _top(rs, b, top_share), stakes)["roi"]
        if ra is not None and rb is not None:
            out.append(ra - rb)
    if len(out) < reps // 2:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def compare(rows, top_share: float = TOP_SHARE, stakes: str = "flat",
            min_n: int = MIN_N, reps: int = 2000,
            seed: int = 20260906) -> dict:
    """Score every ordering on the same pool. Never raises on thin data."""
    pool = usable(rows)
    res = {"n": len(pool), "top_share": top_share, "stakes": stakes,
           "enough": len(pool) >= min_n, "min_n": min_n,
           "orderings": {}, "overlap": {}, "diff": {}, "all": None}
    if not res["enough"]:
        res["note"] = (f"{len(pool)} settled bets carry a probability and a "
                       f"price; {min_n} is the floor for reading a slice")
        return res
    picks = {o: _top(pool, o, top_share) for o in ORDERINGS}
    picks["all"] = _top(pool, "all", top_share)
    res["all"] = _score_slice(pool, picks["all"], stakes)
    for o in ORDERINGS:
        res["orderings"][o] = _score_slice(pool, picks[o], stakes)
    size = len(picks["edge"])
    for a, b in (("prob", "edge"), ("prob", "market"), ("edge", "market")):
        shared = len(set(picks[a]) & set(picks[b]))
        res["overlap"][f"{a}|{b}"] = round(shared / size, 4) if size else None
    for a, b in (("prob", "edge"), ("prob", "market"), ("prob", "all")):
        ra = res["orderings"][a]["roi"]
        rb = (res["all"] if b == "all" else res["orderings"][b])["roi"]
        lo, hi = _boot_roi_diff(pool, a, b, top_share, stakes, reps, seed)
        res["diff"][f"{a}-{b}"] = {
            "point": None if (ra is None or rb is None) else round(ra - rb, 4),
            "lo": None if lo is None else round(lo, 4),
            "hi": None if hi is None else round(hi, 4)}
    return res


def reading(res: dict) -> str:
    """One sentence a person can act on, or say why they cannot."""
    if not res.get("enough"):
        return res.get("note") or "not enough settled bets to read"
    d = res["diff"].get("prob-edge") or {}
    lo, hi, pt = d.get("lo"), d.get("hi"), d.get("point")
    ov = res["overlap"].get("prob|market")
    share = int(round(res["top_share"] * 100))
    if ov is not None and ov >= PROXY_OVERLAP:
        return (f"ordering by the model's probability IS ordering by price: "
                f"{ov:.0%} of the top {share}% is the same bets the book's "
                f"own number would have picked, so this rebuild needs a "
                f"price bar bolted to it before it selects anything")
    if lo is None or hi is None or pt is None:
        return "the orderings could not be separated on this sample"
    if lo > 0:
        return (f"probability-ranking beat edge-ranking by {pt:+.1%} ROI on "
                f"the top {share}% [{lo:+.1%}, {hi:+.1%}] — the whole "
                f"interval is above zero")
    if hi < 0:
        return (f"probability-ranking LOST to edge-ranking by {pt:+.1%} ROI "
                f"on the top {share}% [{lo:+.1%}, {hi:+.1%}] — the whole "
                f"interval is below zero")
    return (f"no measured difference between the two orderings: {pt:+.1%} "
            f"ROI on the top {share}%, interval [{lo:+.1%}, {hi:+.1%}] "
            f"straddling zero, so this sample cannot justify the change "
            f"either way")


def cut_reading(res: dict) -> str:
    """The OTHER half of the instruction, in its own sentence.

    "Sort and gate on the model's probability rank" is two decisions, and
    a cut can lose money even when the sort it cuts on is the better one.
    Betting the top slice is only worth doing if it beats betting
    everything the gate already admitted — which the table shows and
    nobody would necessarily read, since a ROI column invites comparing
    the slices to each other and not to the row underneath them.
    """
    if not res.get("enough"):
        return res.get("note") or "not enough settled bets to read"
    d = res["diff"].get("prob-all") or {}
    lo, hi, pt = d.get("lo"), d.get("hi"), d.get("point")
    share = int(round(res["top_share"] * 100))
    if lo is None or hi is None or pt is None:
        return "the cut could not be scored against betting the whole pool"
    if hi < 0:
        return (f"and the CUT itself loses money: the top {share}% by "
                f"probability runs {pt:+.1%} ROI against betting every bet "
                f"the gate already admitted [{lo:+.1%}, {hi:+.1%}], so on "
                f"this sample the sort is worth more than the gate")
    if lo > 0:
        return (f"and the cut earns its place: the top {share}% by "
                f"probability beats betting the whole pool by {pt:+.1%} ROI "
                f"[{lo:+.1%}, {hi:+.1%}]")
    return (f"and the cut is unproven: the top {share}% by probability runs "
            f"{pt:+.1%} ROI against the whole pool [{lo:+.1%}, {hi:+.1%}], "
            f"an interval that contains zero")
