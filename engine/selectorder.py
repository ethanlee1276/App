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

THE QUESTION THIS COULD NOT ANSWER, AND NOW CAN
-----------------------------------------------
Everything below scores the bets we PLACED, because that is all the
journal holds — so `recommended` is True on every row of it and the one
question that decides whether the gate is worth having could not be
asked: what happened to the props it turned DOWN.

`backtest_from_stats` already knew. It walks the season forward, prices
every prop from prior weeks only, and settles all of them;
`SettledProp` carries `recommended` beside the outcome and
`BacktestReport.settled` keeps every row. The candidate surface with
outcomes had been sitting there the whole time and nothing read the
refused half — the report's own betting numbers are documented
"recommended bets only". `from_settled` and `gate_split` at the bottom
of this file read it.

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
                    "market": r.get("market") or "",
                    # CARRIED FOR `gate_split`, ignored by everything
                    # above it. A journal row has neither — the journal
                    # only holds bets we PLACED, so `recommended` is True
                    # on every one of them and `basis` is not recorded.
                    # They arrive on rows built by `from_settled`.
                    "recommended": bool(r.get("recommended", True)),
                    "basis": r.get("basis") or ""})
    return out


def from_settled(settled) -> list[dict]:
    """`engine.backtest.SettledProp` rows in the shape `usable` reads.

    THE POOL THIS MODULE COULD NOT SEE. Every function above scores the
    bets we PLACED, because that is all the journal holds — and this
    module's own docstring says so. The one question it therefore cannot
    ask is the one that decides whether the gate is any good: what
    happened to the props the gate turned DOWN.

    `backtest_from_stats` already knows. It walks the season forward,
    prices every prop from prior weeks only, and settles all of them
    against the box score — `SettledProp` carries `recommended` beside
    the outcome, and `BacktestReport.settled` keeps every row. The
    candidate surface with outcomes has been sitting there; nothing ever
    read the refused half of it.

    PUSHES ARE DROPPED, not counted as losses. `SettledProp.outcome` is
    None when the stat landed exactly on the line, and a push returns the
    stake — scoring it either way would bias whichever arm holds more of
    them.
    """
    rows = []
    for sp in settled or []:
        won = getattr(sp, "outcome", None)
        if won is None:
            continue
        rows.append({
            "status": "won" if won else "lost",
            "hit_prob": getattr(sp, "hit_prob", None),
            "odds": getattr(sp, "odds", None),
            "stake_units": getattr(sp, "stake_units", 1.0),
            "market": getattr(sp, "market", "") or "",
            "recommended": bool(getattr(sp, "recommended", False)),
            "basis": getattr(sp, "basis", "") or "",
        })
    return rows


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


#: Settled candidates in EACH arm before `gate_split` will read. Lower
#: than MIN_N because the split does not cut a top slice — both arms are
#: whole populations, so the same precision needs fewer rows than the
#: quarter-slice comparisons above.
GATE_MIN_N = 60


def _boot_two_sample(a: list[dict], b: list[dict], stakes: str,
                     reps: int, seed: int):
    """Percentile CI for ROI(a) - ROI(b) across TWO populations.

    NOT `_boot_roi_diff`, and the difference matters. That one resamples
    a single pool and re-cuts it, because the arms it compares are two
    orderings of the SAME rows — the uncertainty it has to carry is
    which rows each rule would have picked. Here the arms are different
    rows: the props the gate admitted and the props it refused. Nothing
    re-selects, so each arm is resampled within itself and the pairing
    that `_boot_roi_diff` relies on does not exist.

    Reusing that function here would have quietly reported a paired
    interval for an unpaired comparison, which is narrower than the
    truth — the failure mode that flatters exactly the kind of result
    somebody wants to act on.
    """
    import random
    rng = random.Random(seed)
    if not a or not b:
        return None, None
    out = []
    na, nb = len(a), len(b)
    for _ in range(reps):
        ra = _score_slice(a, [rng.randrange(na) for _ in range(na)],
                          stakes)["roi"]
        rb = _score_slice(b, [rng.randrange(nb) for _ in range(nb)],
                          stakes)["roi"]
        if ra is not None and rb is not None:
            out.append(ra - rb)
    if len(out) < reps // 2:
        return None, None
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def gate_split(rows, stakes: str = "flat", min_n: int = GATE_MIN_N,
               reps: int = 2000, seed: int = 20260909,
               basis: str = "book") -> dict:
    """What happened to the props the gate REFUSED.

    The question `engine/backtest.py` had the data for and nobody asked,
    and the one the journal can never answer: it holds the bets we
    placed, so every row in it was admitted. Feed this
    `from_settled(report.settled)` from a walk-forward and it scores both
    halves of the candidate surface at a flat 1u.

    WHAT A RESULT WOULD MEAN, and what it would not. If the refused arm
    made money, the gate is leaving money on the table and the next
    question is which refusal did it — this function does not know, and
    saying which would need the refusal REASON on the row, which
    `SettledProp` does not carry. If the refused arm lost, the gate is
    earning its place. If the interval straddles zero, this sample says
    nothing, which on a first season it very likely will.

    ONLY BOOK-PRICED ROWS BY DEFAULT. `basis="naive"` rows were priced
    against `build_slate`'s recent-form proxy at a synthetic -110, so
    their "ROI" is the model scored against itself and beating it means
    nothing about beating a market. `backtest.BacktestReport` segments
    for the same reason. Pass basis="" to pool them anyway and the
    reading will say the number is not market-relative.

    THIS IS A COUNTERFACTUAL, and it rests on one assumption worth
    stating: that we could have had those prices. For player props at
    this size that is fair — we do not move a book's number — and it is
    the same assumption every backtest in this repo already makes. It
    would NOT be fair for a market where our own action is the price.
    """
    pool = [r for r in usable(rows)
            if not basis or r.get("basis") == basis]
    took = [r for r in pool if r["recommended"]]
    left = [r for r in pool if not r["recommended"]]
    res = {"n": len(pool), "basis": basis or "all", "stakes": stakes,
           "min_n": min_n, "n_admitted": len(took), "n_refused": len(left),
           "enough": len(took) >= min_n and len(left) >= min_n,
           "admitted": None, "refused": None, "diff": {}}
    if not res["enough"]:
        res["note"] = (
            f"{len(took)} admitted and {len(left)} refused candidates priced "
            f"against a real book line; {min_n} in each arm is the floor for "
            f"reading a difference")
        return res
    res["admitted"] = _score_slice(took, range(len(took)), stakes)
    res["refused"] = _score_slice(left, range(len(left)), stakes)
    ra, rb = res["admitted"]["roi"], res["refused"]["roi"]
    lo, hi = _boot_two_sample(took, left, stakes, reps, seed)
    res["diff"]["admitted-refused"] = {
        "point": None if (ra is None or rb is None) else round(ra - rb, 4),
        "lo": None if lo is None else round(lo, 4),
        "hi": None if hi is None else round(hi, 4)}
    return res


def gate_reading(res: dict) -> str:
    """One sentence about whether the gate is worth having."""
    if not res.get("enough"):
        return res.get("note") or "not enough settled candidates to read"
    d = res["diff"].get("admitted-refused") or {}
    lo, hi, pt = d.get("lo"), d.get("hi"), d.get("point")
    na, nr = res["n_admitted"], res["n_refused"]
    tail = ("" if res["basis"] == "book" else
            " — and these are proxy-priced rows, so the number is not a "
            "claim about beating a market")
    if lo is None or hi is None or pt is None:
        return "the two arms could not be scored against each other"
    if lo > 0:
        return (f"the gate earns its place: the {na} props it admitted beat "
                f"the {nr} it refused by {pt:+.1%} ROI [{lo:+.1%}, {hi:+.1%}], "
                f"the whole interval above zero{tail}")
    if hi < 0:
        return (f"the gate is COSTING money: the {nr} props it refused beat "
                f"the {na} it admitted by {-pt:+.1%} ROI "
                f"[{lo:+.1%}, {hi:+.1%}], the whole interval below zero — "
                f"what it turns down is worth more than what it takes{tail}")
    return (f"the gate is unproven either way: admitted minus refused is "
            f"{pt:+.1%} ROI over {na} and {nr} candidates, interval "
            f"[{lo:+.1%}, {hi:+.1%}] straddling zero{tail}")


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
