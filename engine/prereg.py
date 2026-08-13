"""Preregistered tests: the terms written down BEFORE the data arrives.

Ethan, 2026-08-13, after `gradecheck` came back with nothing significant:
"yeah do that, wire it into the lab."

WHAT THIS IS FOR, AND WHY THE HYPOTHESIS LAB COULD NOT DO IT. The lab
next door proposes slices with an LLM and convicts them on CALIBRATION —
said versus hit, keyed on sport/market/dims, under Benjamini-Hochberg.
That is the right machine for "which slices does the model misread". It
is the wrong machine for this, which is a claim about ROI by GRADE, made
by a human, about a bucket that was chosen precisely BECAUSE it looked
bad. Feeding a hand-picked bucket into a discovery engine and reading the
p-value would be circular.

THE THREE THINGS THAT MAKE THIS A PREREGISTRATION RATHER THAN A NOTE.

1. THE TERMS ARE FROZEN. Everything that decides the answer — the claim,
   the population, the metric, the sample size, the threshold — is
   written at registration and hashed. `verdict()` recomputes the hash
   from the stored terms and refuses to report if it has moved. Moving
   the goalposts is the failure mode preregistration exists to prevent,
   so it is made mechanically visible rather than trusted to discipline.

2. THE EVIDENCE THAT SUGGESTED IT IS EXCLUDED. The B+ bucket was picked
   because 95 already-settled bets read -24.4%. Testing on those 95 would
   be asking the same data twice and getting the same answer twice. Only
   bets dated STRICTLY AFTER the registration date count, and `n` never
   includes a row that existed when the idea did.

3. IT DECIDES ONCE, AT A FIXED N. Watching a running total and calling it
   the moment it crosses a line is sequential testing, and it finds
   "significance" in pure noise given enough looks. Before `min_n` the
   only honest output is how far along it is. Nothing is reported as a
   result until the sample the terms named has actually arrived.

The registry is data, not code, so a decision can be recorded next to the
terms it was made under and read later by somebody asking what we knew
and when.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

DEFAULT_PATH = Path("data/models/prereg.json")

#: Two-sided z for a single preregistered comparison. It can be this
#: ordinary BECAUSE the test was named in advance — the 2.6-ish bar
#: gradecheck needs is the price of picking the worst of six buckets
#: after seeing them, and a preregistration does not pay it.
Z_THRESHOLD = 1.96


def _terms_hash(t: dict) -> str:
    """A fingerprint of everything that decides the answer."""
    keyed = {k: t[k] for k in sorted(
        ("claim", "sport", "population", "compare_to", "metric",
         "min_n", "z_threshold", "registered", "decides"))
        if k in t}
    return hashlib.sha256(
        json.dumps(keyed, sort_keys=True).encode()).hexdigest()[:16]


def load(path=None) -> dict:
    p = Path(path if path is not None else DEFAULT_PATH)
    try:
        return json.loads(p.read_text())
    except Exception:                                         # noqa: BLE001
        return {"tests": []}


def save(store: dict, path=None) -> Path:
    p = Path(path if path is not None else DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2))
    return p


def register(test: dict, path=None) -> dict:
    """Freeze a test's terms. Re-registering the same id is a no-op —
    the first registration is the one that counts, and silently
    overwriting it would erase the very thing being protected."""
    store = load(path)
    if any(t["id"] == test["id"] for t in store["tests"]):
        return store
    t = dict(test)
    t.setdefault("registered", _dt.date.today().isoformat())
    t.setdefault("z_threshold", Z_THRESHOLD)
    t["hash"] = _terms_hash(t)
    t["status"] = "collecting"
    store["tests"].append(t)
    save(store, path)
    return store


def _wl(rows):
    w = sum(1 for r in rows if r["status"] == "won")
    return w, sum(1 for r in rows if r["status"] == "lost")


def _flat_profit(r) -> float:
    """Units at a FLAT 1u — the metric the terms name, so sizing cannot
    confound a question about which bucket wins."""
    if r["status"] != "won":
        return -1.0
    o = r["odds"]
    if o is None:
        return 0.0
    return (o / 100.0) if o > 0 else (100.0 / -o)


def _mean_se(vals):
    n = len(vals)
    if n < 2:
        return (vals[0] if vals else 0.0), 0.0
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return m, (var / n) ** 0.5


def verdict(test: dict, rows: list[dict]) -> dict:
    """Evaluate one frozen test against settled bets.

    ``rows`` are dicts with date, grade, sport, odds, status. Rows dated
    on or before the registration are DROPPED — see the module note.
    """
    out = {"id": test["id"], "claim": test["claim"],
           "registered": test["registered"], "min_n": test["min_n"]}
    if test.get("hash") and test["hash"] != _terms_hash(test):
        out["status"] = "void"
        out["reading"] = ("the terms changed after registration — this is "
                          "no longer a preregistered test and reports "
                          "nothing")
        return out

    reg = test["registered"]
    fresh = [r for r in rows
             if (r.get("date") or "") > reg
             and r.get("sport") == test["sport"]
             and r.get("status") in ("won", "lost")]
    pop = [r for r in fresh if r.get("grade") in test["population"]]
    ref = [r for r in fresh if r.get("grade") in test["compare_to"]]
    out["n"] = len(pop)
    out["n_reference"] = len(ref)

    if len(pop) < test["min_n"]:
        out["status"] = "collecting"
        out["reading"] = (
            f"{len(pop)} of {test['min_n']} bets since {reg}. Nothing is "
            f"reported until the sample the terms named has arrived — "
            f"peeking early and calling it is how noise becomes a finding.")
        return out

    pv = [_flat_profit(r) for r in pop]
    rv = [_flat_profit(r) for r in ref]
    pm, pse = _mean_se(pv)
    rm, rse = _mean_se(rv)
    diff = pm - rm
    se = (pse ** 2 + rse ** 2) ** 0.5
    z = (diff / se) if se else 0.0
    w, l = _wl(pop)
    out.update({"roi": pm, "roi_se": pse, "reference_roi": rm,
                "diff": diff, "z": z, "wins": w, "losses": l,
                "status": "decided",
                "supported": bool(z <= -test["z_threshold"])})
    out["reading"] = (
        f"{w}-{l} since {reg}: {pm:+.1%} at a flat unit against "
        f"{rm:+.1%} for {'/'.join(test['compare_to'])}, a gap of "
        f"{diff:+.1%} at z={z:+.2f}. "
        + (f"The claim holds at the preregistered bar — {test['decides']}"
           if out["supported"] else
           "The claim does NOT clear the preregistered bar, so nothing "
           "changes and the bucket stays."))
    return out


#: The registration Ethan asked for on 2026-08-13.
#:
#: It exists because B+ props read -24.4% over 95 settled bets while A+
#: and A were statistically identical to each other (-8.7% and -9.4%).
#: `gradecheck` would not convict it: testing six buckets and picking the
#: worst needs about |z| > 2.6 and this was 2.1. That is not evidence of
#: nothing — it is evidence that has not been earned yet, and the way to
#: earn it is to name the test before the data arrives.
B_MINUS = {
    "id": "bplus-props-2026-08",
    "claim": "B+ player props lose more than A/A+ props at the same stake",
    "sport": "mlb",
    "population": ["B+"],
    "compare_to": ["A", "A+"],
    "metric": "ROI at a flat 1u",
    "min_n": 100,
    "decides": "drop B+ from the recommended board",
    "why_now": ("B+ read -24.4% over 95 settled bets (z=2.1) while A+ and "
                "A were indistinguishable from each other. Picking the "
                "worst of six buckets after the fact needs |z|>2.6, so "
                "this is registered forward instead of acted on."),
}


def ensure_registered(path=None) -> dict:
    """Idempotent: registers the standing tests if they are not there."""
    return register(B_MINUS, path)


def report(rows: list[dict], path=None) -> list[dict]:
    store = ensure_registered(path)
    return [verdict(t, rows) for t in store["tests"]]
