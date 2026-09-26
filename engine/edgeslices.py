"""Is the claimed edge noise EVERYWHERE, or only on average?

`engine.edgehistory` asks whether the model knows anything the price
does not, and answers it over the whole main book: claimed-edge AUC
0.463 on 562 settled bets, verdict `edge_is_noise` (see
docs/THE_INFORMATION_TEST.md for the original measurement at n=307).

That is one number over six sports and a dozen markets, and a pooled
average can be a coin flip three different ways:

  * every slice is a coin flip — the honest reading of the pooled number,
    and the one to act on if it survives this cut;
  * one slice carries real information and the rest dilute it away;
  * two slices point in opposite directions and cancel.

Those have completely different answers. The first says stop selecting
on edge. The second says select on edge THERE and nowhere else. Nothing
in the pooled figure can tell them apart, so this cuts it — by sport, by
market — and reports every slice with its interval.

WHY THIS IS DANGEROUS WITHOUT DISCIPLINE, and what keeps it honest.
Slicing a null into twenty pieces and keeping the best one is how a
coin flip becomes a strategy. Two rules, both borrowed from
`engine.losspatterns` rather than reinvented:

  * a slice under `MIN_N` settled bets is NOT TESTED. It is reported as
    thin, and it does not enter the family — `_bh`'s own docstring is
    about exactly this, that shrinking m after peeking is how false
    discovery control dies.
  * every slice that IS tested enters one Benjamini-Hochberg family
    together, across both cuts. Twelve markets and six sports is
    eighteen chances at a 1-in-20 accident, and at alpha 0.05 unadjusted
    you would expect one.

The p-value is the standard Mann-Whitney normal approximation under the
null — AUC has a known variance when there is no signal, so this needs
no bootstrap and no assumption the bootstrap would smuggle in. The
interval beside it is still the percentile bootstrap the rest of the
repo uses, because an interval answers "how big could it be" and a
p-value does not.

WHAT THIS CANNOT SAY. Same caveat as the pooled test, and it does not
weaken with slicing: these are the bets we CHOSE to make. A slice's AUC
is how well the edge sorted the spots we liked in that slice, not
whether the model understands that market. It is the right question for
"should we keep selecting this way here", and the wrong one for "is the
projection any good".
"""

from __future__ import annotations

import math

#: Settled bets a slice needs before it is tested at all. Below this the
#: interval is wider than any effect worth acting on, and testing it only
#: enlarges the family every other slice is judged against.
MIN_N = 60

#: False-discovery rate for the family of slices. Matches
#: `losspatterns.ALPHA`.
ALPHA = 0.05

#: The cuts. Sport and market are the two the boards are actually built
#: from, so a survivor in either is directly actionable.
KEYS = ("sport", "market")


def _usable(rows):
    return [r for r in rows
            if r.get("status") in ("won", "lost")
            and r.get("hit_prob") is not None and r.get("odds") is not None]


def p_two_sided(auc: float, n_pos: int, n_neg: int) -> float | None:
    """Mann-Whitney's normal approximation under the null AUC = 0.5.

    The null variance of an AUC depends only on the two counts, which is
    what makes this exact enough to use as the family's p-value without
    a second bootstrap.
    """
    if not n_pos or not n_neg or auc is None:
        return None
    se = math.sqrt((n_pos + n_neg + 1.0) / (12.0 * n_pos * n_neg))
    if se <= 0:
        return None
    z = (auc - 0.5) / se
    return max(0.0, min(1.0, math.erfc(abs(z) / math.sqrt(2.0))))


def _measure(rs: list[dict]) -> dict | None:
    """The three AUCs for one slice, or None when it cannot be scored."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from stakecheck import _auc, _boot_auc

    from .odds import american_to_prob

    y = [1 if r["status"] == "won" else 0 for r in rs]
    if not any(y) or all(y):
        return None                       # AUC undefined
    model = [float(r["hit_prob"]) for r in rs]
    market = [american_to_prob(int(r["odds"])) for r in rs]
    edge = [m - k for m, k in zip(model, market)]
    a_edge, a_model = _auc(edge, y), _auc(model, y)
    if a_edge is None:
        return None
    lo, hi = _boot_auc(edge, y)
    wins = sum(y)
    return {"n": len(rs), "wins": wins, "losses": len(rs) - wins,
            "auc_edge": a_edge, "auc_edge_lo": lo, "auc_edge_hi": hi,
            "auc_model": a_model,
            "p": p_two_sided(a_edge, wins, len(rs) - wins)}


def by_slice(rows: list[dict], keys=KEYS, min_n: int = MIN_N,
             alpha: float = ALPHA) -> dict:
    """Every slice's claimed-edge AUC, under one FDR family.

    Returns ``{"tested": [...], "thin": [...], "survivors": [...],
    "min_n": n, "alpha": a, "n": total}`` — `tested` carries `q` and
    `survives` from Benjamini-Hochberg, `thin` is what was too small to
    ask and is deliberately NOT in the family.
    """
    from .losspatterns import _bh

    use = _usable(rows)
    tested: list[dict] = []
    thin: list[dict] = []
    for key in keys:
        groups: dict[str, list] = {}
        for r in use:
            groups.setdefault(str(r.get(key) or "?"), []).append(r)
        for name, rs in sorted(groups.items()):
            if len(rs) < min_n:
                thin.append({"key": key, "value": name, "n": len(rs)})
                continue
            m = _measure(rs)
            if m is None or m["p"] is None:
                thin.append({"key": key, "value": name, "n": len(rs),
                             "note": "all winners or all losers"})
                continue
            tested.append({"key": key, "value": name, **m})
    _bh(tested, alpha)
    return {"tested": tested, "thin": thin,
            "survivors": [t for t in tested if t.get("survives")],
            "min_n": min_n, "alpha": alpha, "n": len(use)}


def reading(result: dict) -> str:
    """One sentence a person can act on."""
    tested, surv = result.get("tested") or [], result.get("survivors") or []
    if not tested:
        return (f"No slice has {result.get('min_n')} settled bets yet — "
                f"nothing to cut. The pooled figure is all there is.")
    if not surv:
        return (f"{len(tested)} slice(s) tested, none survives false-discovery "
                f"control at {result.get('alpha')}. The claimed edge is not "
                f"noise on average and real somewhere — it is noise in every "
                f"slice big enough to ask.")
    names = ", ".join(f"{s['key']} {s['value']} (AUC {s['auc_edge']:.3f}, "
                      f"q={s.get('q')})" for s in surv)
    return (f"{len(surv)} of {len(tested)} slice(s) survive: {names}. "
            f"That is where selecting on edge is doing something; "
            f"everywhere else the pooled reading stands.")
