"""The fitter every sport shares: learn from the bet journal itself.

The deep fitters (calibrate.py, formfit.py, playerfit.py) walk the history
DB through a sport's own engine — the strongest possible fit, and only MLB
and the generic-engine sports have that harness. The hoops and college
models price through their own machinery, and UFC has no game logs at all.
What EVERY sport has is the journal: settled bets carrying the claimed
probability, the projection, and what actually happened. This module fits
what the journal can honestly support, per sport and market:

  * **Temperature** — ``calibrate.fit`` on the journal's (claimed
    probability, outcome) pairs. Fitted ONLY for keys with no stored
    correction: once a correction ships, later journal rows are
    post-correction, and refitting on them would learn a correction for
    already-corrected claims and compound (see calibrate.set_enabled's
    docstring — the same disease, one data source over). First fits are
    clean by construction; refits belong to the deep fitters or to a
    future since-timestamp composition, and that boundary is the point.
  * **Player memory** — per-player multiplicative corrections from the
    journal's (projection, actual) pairs, with playerfit's exact
    restraints (shrinkage, clamp, store floor) and the same causal
    adoption test, scored by mean absolute projection error instead of
    Brier because the journal's probabilities already contain the market
    shrink. Marked ``basis: "journal-mae"`` in the store so the page
    labels the score honestly.

Both fits are floor-gated at :data:`MIN_SAMPLES` settled bets per key and
report "collecting: n of 200" below it — the bar does not bend because
the journal is young. Runs on every settle pass, so a sport crosses its
floor the night it happens, with no one watching.
"""

from __future__ import annotations

import json
from pathlib import Path

MIN_SAMPLES = 200
#: Relative MAE improvement the causal memory test must show. Projection
#: error is in stat units, so the bar is relative where playerfit's Brier
#: bar could be absolute.
MIN_MAE_GAIN_REL = 0.005


def _settled(lconn) -> list:
    return lconn.execute(
        "SELECT sport, market, player, side, hit_prob, projection, actual, "
        "status FROM bets WHERE status IN ('won','lost') "
        "ORDER BY ts, rowid").fetchall()


def as_over(p, side: str | None, status: str) -> tuple[float, int] | None:
    """Restate one settled bet as (P(over), did the over land).

    The fit has to run on ONE quantity. Pairing each bet's own hit_prob
    with won/lost does not: an over claiming 0.58 and an under claiming
    0.58 land in the same bucket as the same number, though one is a claim
    that the over hits and the other a claim that it does not.

    That is not cosmetic. The intercept is the only parameter in
    apply_temperature that can push a model off one side, and a model
    leaning over contributes a negative calibration gap on its overs and a
    positive one on its unders — which cancel. The fit built to catch a
    directional lean was blind to it by construction, and would report a
    leaning market as calibrated.

    engine/backtest.py's deep fit has always converted first; this is the
    journal fit being brought into line with it.
    """
    if p is None or not 0.0 < float(p) < 1.0:
        return None
    p = float(p)
    won = status == "won"
    if (side or "OVER").upper() == "OVER":
        return (p, 1 if won else 0)
    # An UNDER bet: its claim is that the over does NOT land, so P(over) is
    # the complement, and the bet winning means the over missed.
    return (1.0 - p, 0 if won else 1)


def fit_temperatures(lconn, path=None, min_samples: int = MIN_SAMPLES,
                     dry_run: bool = False) -> dict:
    """Fit per-(sport, market) temperatures from journaled claims."""
    from . import calibrate as cal
    path = Path(path if path is not None else cal.DEFAULT_PATH)
    try:
        stored = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(stored, dict):
            stored = {}
    except (ValueError, OSError):
        stored = {}

    groups: dict[tuple, list] = {}
    for r in _settled(lconn):
        # Restated as P(over) so the fit runs on one quantity — see
        # as_over. A won UNDER is an over that did NOT land, and pairing
        # it as a win made a directional lean invisible to the intercept.
        pair = as_over(r["hit_prob"], r["side"], r["status"])
        if pair is None:
            continue
        groups.setdefault((r["sport"], r["market"]), []).append(pair)

    out = {"fitted": [], "owned": [], "collecting": []}
    wrote = False
    for (sport, market), pairs in sorted(groups.items()):
        key = f"{sport}:{market}"
        if key in stored:
            # A stored correction means this key's later journal rows are
            # post-correction — refitting on them would compound.
            out["owned"].append({"key": key})
            continue
        if len(pairs) < min_samples:
            out["collecting"].append({"key": key, "n": len(pairs),
                                      "need": min_samples})
            continue
        c = cal.fit(pairs, sport=sport, market=market,
                    min_samples=min_samples)
        stored[key] = c.to_dict()
        wrote = True
        out["fitted"].append({"key": key, "n": c.samples,
                              "temperature": c.temperature,
                              "brier_before": round(c.brier_before, 5),
                              "brier_after": round(c.brier_after, 5),
                              "at_boundary": c.at_boundary})
    if wrote and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, indent=2))
        cal.reset_cache()
    return out


def fit_memory(lconn, path=None, min_samples: int = MIN_SAMPLES,
               dry_run: bool = False) -> dict:
    """Fit per-player corrections from journaled (projection, actual)."""
    from . import playerfit as pf
    path = Path(path if path is not None else pf.DEFAULT_PATH)
    try:
        stored = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(stored, dict):
            stored = {}
    except (ValueError, OSError):
        stored = {}

    groups: dict[tuple, list] = {}
    for r in _settled(lconn):
        proj, actual = r["projection"], r["actual"]
        if not r["player"] or proj is None or actual is None:
            continue
        try:
            proj, actual = float(proj), float(actual)
        except (TypeError, ValueError):
            continue
        if proj <= 0:
            continue
        groups.setdefault((r["sport"], r["market"]), []).append(
            (r["player"], proj, actual))

    out = {"fitted": [], "owned": [], "collecting": []}
    wrote = False
    for (sport, market), rows in sorted(groups.items()):
        key = f"{sport}:{market}"
        entry = stored.get(key)
        if isinstance(entry, dict) and entry.get("basis") != "journal-mae":
            out["owned"].append({"key": key})     # deep-fitted; theirs
            continue
        if len(rows) < min_samples:
            out["collecting"].append({"key": key, "n": len(rows),
                                      "need": min_samples})
            continue
        # The causal walk, in journal order: the correction judging row i
        # was built from rows [:i] only.
        sums: dict[str, dict] = {}
        mae_base = mae_corr = 0.0
        for player, proj, actual in rows:
            s = sums.setdefault(pf._norm(player), {"a": 0.0, "p": 0.0, "n": 0})
            m = pf.shrunk_mult(s["a"], s["p"], s["n"])
            mae_base += abs(proj - actual)
            mae_corr += abs(proj * m - actual)
            s["a"] += actual
            s["p"] += proj
            s["n"] += 1
        n = len(rows)
        mae_base /= n
        mae_corr /= n
        adopted = (mae_base > 0
                   and (mae_base - mae_corr) / mae_base >= MIN_MAE_GAIN_REL)
        players = {}
        if adopted:
            for name, s in sums.items():
                if s["n"] < pf.MIN_GAMES_STORE:
                    continue
                m = pf.shrunk_mult(s["a"], s["p"], s["n"])
                if abs(m - 1.0) < pf.MIN_DELTA_STORE:
                    continue
                players[name] = {"mult": round(m, 4), "games": s["n"]}
        stored[key] = {
            "sport": sport, "market": market, "samples": n,
            "mae_baseline": round(mae_base, 4),
            "mae_corrected": round(mae_corr, 4),
            "adopted": bool(adopted and players), "players": players,
            "basis": "journal-mae", "n0": pf.N0, "clamp_pct": pf.CLAMP_PCT,
        }
        wrote = True
        out["fitted"].append({"key": key, "n": n, "adopted": stored[key]["adopted"],
                              "players": len(players),
                              "mae_baseline": round(mae_base, 4),
                              "mae_corrected": round(mae_corr, 4)})
    if wrote and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, indent=1))
        pf._cache.clear()
    return out


def refresh(lconn) -> dict:
    """Both journal fits — the nightly learning step for every sport that
    has no deep-history harness. Called from the settle pass."""
    return {"temperatures": fit_temperatures(lconn),
            "memory": fit_memory(lconn)}
