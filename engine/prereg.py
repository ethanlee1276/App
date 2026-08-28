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

from . import modelstate as _modelstate

DEFAULT_PATH = Path(_modelstate.path("prereg.json"))

#: Two-sided z for a single preregistered comparison. It can be this
#: ordinary BECAUSE the test was named in advance — the 2.6-ish bar
#: gradecheck needs is the price of picking the worst of six buckets
#: after seeing them, and a preregistration does not pay it.
Z_THRESHOLD = 1.96


def _terms_hash(t: dict) -> str:
    """A fingerprint of everything that decides the answer."""
    keyed = {k: t[k] for k in sorted(
        ("claim", "sport", "population", "compare_to", "metric",
         "markets", "min_n", "z_threshold", "registered", "decides"))
        if k in t}
    return hashlib.sha256(
        json.dumps(keyed, sort_keys=True).encode()).hexdigest()[:16]


def supersede(test_id: str, by: str, why: str, path=None) -> dict:
    """Record that a registered test has been replaced, without editing it.

    THE CASE THIS EXISTS FOR. `A_BAND_NFL` was registered on 2026-08-27
    with the remedy "level A's stake cap down to B+'s —
    engine.quality.STAKE_CAP_U". That constant stopped deciding a stake
    when `engine.staking` retired Kelly-times-grade, and A and B+ already
    take the same fraction, so the test would one day report `supported`
    and change NOTHING. A preregistration whose remedy is inert is the
    same failure this module exists to prevent, wearing the uniform of
    the fix.

    It cannot simply be edited. The terms are hashed precisely so that
    nobody can move the goalposts after seeing data, and `verdict`
    rightly reports an edited test as void. So the terms stay exactly as
    frozen and the supersession is recorded BESIDE them: the successor's
    id, the reason, and the date. The old test stops collecting and says
    what replaced it; the record of what was originally asked survives,
    which is the whole point of writing it down in the first place.

    Idempotent, and refuses to supersede a test that does not exist —
    silently marking a typo would be indistinguishable from working.
    """
    store = load(path)
    for t in store["tests"]:
        if t["id"] != test_id:
            continue
        if t.get("superseded_by") == by:
            return store
        t["superseded_by"] = by
        t["superseded_why"] = why
        t["superseded_on"] = _dt.date.today().isoformat()
        save(store, path)
        return store
    raise KeyError(f"no registered test with id {test_id!r}")


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

    if test.get("superseded_by"):
        out["status"] = "superseded"
        out["superseded_by"] = test["superseded_by"]
        out["reading"] = (
            f"replaced by {test['superseded_by']} on "
            f"{test.get('superseded_on', '')} — "
            f"{test.get('superseded_why', 'no reason recorded')}. The terms "
            f"above are the ones that were frozen; they are kept rather than "
            f"edited, because a preregistration nobody can read afterwards "
            f"protects nothing.")
        return out

    reg = test["registered"]
    fresh = [r for r in rows
             if (r.get("date") or "") > reg
             and r.get("sport") == test["sport"]
             and r.get("status") in ("won", "lost")]
    # OPTIONAL, and absent from every test registered before 2026-08-27
    # — which is why `_terms_hash` only keys on the fields a test
    # actually carries. Adding a filter no existing test uses must not
    # change their fingerprints and void them.
    markets = test.get("markets")
    if markets:
        fresh = [r for r in fresh if r.get("market") in markets]
    # THE BUCKET, and this one was nearly fatal to `TD_EDGE_NFL`. The
    # journal keeps the scorer board in `category='longshot'` — a
    # measurement-only bucket, deliberately never mixed into the headline
    # record — and both feeds selected `category IN ('main','paper')`.
    # A test about the long-shot board could therefore never collect a
    # single row, and would have sat at "0 of 120" forever while looking
    # perfectly healthy. Registered, enforced nowhere: the bug this
    # codebase finds in itself more than any other, committed here an
    # hour after writing that sentence.
    #
    # Default is the headline buckets, so every test registered before
    # this reads exactly what it always did — and `_terms_hash` keys
    # only on fields a test carries, so their fingerprints are untouched.
    cats = test.get("categories") or ("main", "paper")
    fresh = [r for r in fresh
             if (r.get("category") or "main") in cats]
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
    # ZERO VARIANCE IS NOT ZERO EVIDENCE. `se` is 0 only when every bet
    # in the sample returned the same thing — every one lost, or every
    # one won at identical odds — and `z = 0.0` then reports the
    # strongest possible result as the weakest. Two populations rarely
    # reach it; a ONE-SAMPLE test against break-even (`compare_to: []`)
    # reaches it the moment a whole sample loses, which is exactly the
    # case such a test is registered to catch. With no sampling spread
    # inside the sample there is no z to compute, so the sign decides and
    # the reading says that is what happened.
    degenerate = (not se) and diff != 0.0
    w, l = _wl(pop)
    out.update({"roi": pm, "roi_se": pse, "reference_roi": rm,
                "diff": diff, "z": z, "wins": w, "losses": l,
                "status": "decided", "degenerate": degenerate,
                "supported": bool(diff < 0 if degenerate
                                  else z <= -test["z_threshold"])})
    # A test with no comparison band is a ONE-SAMPLE test against
    # break-even: `ref` is empty, `_mean_se([])` is (0, 0), and the z
    # above is therefore the population's own flat-unit ROI over its
    # standard error. Saying "against +0.0% for " with nothing after it
    # would read as a missing value rather than a deliberate baseline.
    against = ("/".join(test["compare_to"]) if test.get("compare_to")
               else "break-even")
    out["reading"] = (
        f"{w}-{l} since {reg}: {pm:+.1%} at a flat unit against "
        f"{rm:+.1%} for {against}, a gap of "
        + (f"{diff:+.1%} — every bet in the sample returned the same "
           f"thing, so there is no spread to compute a z from and the "
           f"sign decides. " if degenerate else
           f"{diff:+.1%} at z={z:+.2f}. ")
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


#: Registered 2026-08-27, and registered rather than acted on for the
#: reason this module exists.
#:
#: The NFL prop backtest was given a per-grade calibration report and it
#: came back with the elite band landing WORSE than the band below it in
#: every one of four ingested seasons:
#:
#:     season   A lands   B+ lands
#:     2022      46.4%     50.8%
#:     2023      49.1%     55.7%
#:     2024      57.6%     57.8%
#:     2025      45.9%     61.1%
#:
#: Pooled: A 123/248 = 49.6% against a claimed 54.2%; B+ 432/765 =
#: 56.5% against a claimed 53.8%. The difference is −6.9 points at
#: z = −1.89.
#:
#: WHY THIS IS NOT ACTED ON TODAY. B_MINUS above was registered forward
#: at z = 2.1 because 2.1 was not enough to convict a bucket chosen
#: after looking. This reads 1.89 — weaker than the number that was
#: already judged insufficient — and acting on it would be applying a
#: lower bar to my own finding than the one already set. Four seasons
#: agreeing is real information and it is not the same as earned.
#:
#: It matters more than the z suggests, which is why it is registered
#: rather than shrugged off: `engine.quality.STAKE_CAP_U` caps A at 1.0u
#: and B+ at 0.5u, so the board sizes DOUBLE into the band that has
#: landed worse four years running. The decision this test settles is
#: therefore about money, not about display order.
#:
#: NOTE THE DIRECTION IS OPPOSITE TO B_MINUS, which claims B+ is the bad
#: bucket in MLB. Two sports pointing opposite ways is itself a finding:
#: it argues against a universal law about grade bands and for measuring
#: each sport on its own record.
A_BAND_NFL = {
    "id": "a-band-nfl-props-2026-08",
    "claim": "A-graded NFL props land no more often than B+ ones",
    "sport": "nfl",
    "population": ["A"],
    "compare_to": ["B+"],
    "metric": "hit rate on settled recommendations",
    "min_n": 120,
    "decides": ("level A's stake cap down to B+'s until it out-lands it "
                "— engine.quality.STAKE_CAP_U"),
    "why_now": ("A landed 49.6% (123/248) against a claimed 54.2% across "
                "2022-2025, while B+ landed 56.5% (432/765). z = -1.89 on "
                "the difference, and B+ was registered forward at 2.1, so "
                "this does not clear the bar this project already set."),
}


#: Registered 2026-08-27, from the slice that answered "why does B+ beat
#: A". The answer turned out to be one cell.
#:
#: Four ingested NFL seasons, 1,016 settled recommendations, split by
#: grade AND market:
#:
#:     A   receptions    86 bets   40.7%      B+  receptions   199   60.3%
#:     A   rec_yds       84 bets   51.2%      B+  rec_yds      288   57.3%
#:     A   rush_yds      70 bets   58.6%      B+  rush_yds     222   52.7%
#:                                            B+  pass_yds      56   53.6%
#:
#: A-graded RECEPTIONS is the whole deficit. Take that one cell out and
#: the A band lands 54.7%, a shade under B+ and nowhere near a finding.
#: Left in, it drags A to 49.6% against a 54.8% pool — z = -2.63.
#:
#: THE MECHANISM IS IN THE SCORE, WHICH IS WHY THIS IS WORTH REGISTERING
#: RATHER THAN SHRUGGING AT. `engine.quality.quality_score` awards its
#: 40 edge points as `edge / (1.5 × TIER_MIN_EDGE[tier])`, and receptions
#: is the only Tier 1 market, with the lowest minimum of the three
#: (0.025 against 0.030). So a receptions prop reaches full edge credit
#: on 3.75% where a yardage prop needs 4.5% — it is the easiest market in
#: the book to grade A in, and the A band is 34.7% receptions against
#: B+'s 26.0%. The grade inherits the tier's leniency twice: once in the
#: shrink that sets the edge, and again in the scale that scores it.
#:
#: AND WHY IT IS NOT ACTED ON. Seven grade-by-market cells were examined
#: and this is the worst of them; picking the worst of seven after the
#: fact needs more than the 2.1 this project set for a named bucket, and
#: -2.63 clears 2.6 by three hundredths. That is not a margin to retune a
#: live model on. The edge signal's own anti-correlation is weaker still
#: — outcome on edge, logistic, gives z = -1.73 pooled and -2.17 inside
#: receptions — so the honest reading is one suggestive market, not a
#: broken ladder.
RECEPTIONS_A_NFL = {
    "id": "a-receptions-nfl-2026-08",
    "claim": "A-graded NFL receptions props lose to B+ ones in the same market",
    "sport": "nfl",
    "population": ["A"],
    "compare_to": ["B+"],
    "markets": ["receptions"],
    "metric": "ROI at a flat 1u, receptions only",
    "min_n": 80,
    "decides": ("the grade's edge scale stops inheriting the tier's "
                "minimum, so an A demands the same edge in every market "
                "— engine.quality.quality_score's edge_pts denominator"),
    "why_now": ("A receptions read 40.7% over 86 settled bets against a "
                "54.8% pool (z = -2.63) while B+ receptions read 60.3% "
                "over 199. It is the worst of seven cells looked at "
                "after the fact, and 2.63 is not enough of a margin over "
                "2.6 to move a live model on."),
}


#: The touchdown board bets where it disagrees with the book, and on the
#: 2025 season those disagreements were worthless.
#:
#: THE NUMBERS. 51 book-priced anytime-TD bets, 6 won (11.8%). The model
#: claimed 30.5% across them; the raw market implied 27.5%. Rejecting the
#: model's own claim is decisive — P(<= 6 wins | the model's per-bet
#: probabilities) = 0.0012. De-vigged at a 15-25% one-sided hold the
#: market expected 11-12 wins and P(<= 6) is 0.02-0.045, so the sample
#: was also poor against the book, but not damningly so.
#:
#: WHY THIS IS NOT THE CALIBRATION FAILING. Across all 22,102 ingested
#: player-weeks the same model is well calibrated: it claims 16.9% and
#: 20.0% score, and in the 28-40% band it claims 33.1% where 36.8%
#: score. On the 51 it CHOOSES it claims 30.5% and delivers 11.8%. Same
#: model, same season, opposite answer — the difference is selection.
#: Every one of the 51 has the model above the market, by 1.4 to 4.0
#: points, and the win rate falls as the price lengthens (20.0% short,
#: 14.3% middle, 5.6% long). That is adverse selection: betting the
#: largest disagreements selects the largest errors.
#:
#: WHY IT IS REGISTERED RATHER THAN FIXED. 51 bets is enough to reject a
#: claim and nowhere near enough to fit a new constant to. The obvious
#: levers — a bigger `MARKET_SHRINK` for scorer markets, a higher edge
#: bar — would be tuned to this one sample. The board already grades
#: every one of these "Lean", so it is not claiming they are elite; the
#: question is whether it should be betting them at all.
TD_EDGE_NFL = {
    "id": "td-edge-nfl-2026-08",
    "claim": ("NFL anytime-TD picks lose at the model's own claimed rate: "
              "the board's disagreement with the book is not edge"),
    "sport": "nfl",
    # THE LONG-SHOT BOARD'S OWN VOCABULARY. `quality.letter` returns
    # A+/A/B+/Pass and `longshots._grade` returns Strong Play/Play/Lean/
    # Pass — different ladders entirely, and a test populated with the
    # wrong one collects nothing forever while looking healthy. All 51
    # bets behind this graded "Lean"; the other two are named so the
    # test does not go blind the day one clears a higher bar.
    "population": ["Strong Play", "Play", "Lean"],
    # The scorer board journals here, not in the headline record.
    "categories": ["longshot"],
    # NO COMPARISON BAND, because there is no second population to
    # compare against — the claim is that these bets lose at a flat unit,
    # full stop. An empty list makes `verdict` a one-sample test against
    # break-even, which is exactly the question.
    "compare_to": [],
    "markets": ["anytime_td"],
    "metric": ("landed rate against the mean claimed probability of the "
               "same bets, book-priced only, flat 1u"),
    "min_n": 120,
    "decides": ("whether the scorer board keeps betting sub-5-point "
                "disagreements at all — engine.longshots.MARKET_SHRINK "
                "for scorer markets, or the edge bar in "
                "engine.touchdowns.build_td_longshots"),
    "why_now": ("6 of 51 landed where the model claimed 30.5%, at "
                "p = 0.0012 against its own numbers. The same model over "
                "22,102 player-weeks claims 16.9% and lands 20.0%, so "
                "this is selection rather than calibration — and 51 bets "
                "is a rejection, not a number to tune a constant to."),
}


#: Every column `verdict` reads off a journal row, and every bucket any
#: registered test draws from.
#:
#: ONE definition because there were two callers and they had drifted:
#: `ledger.prereg_status` selected `market` (added for
#: `RECEPTIONS_A_NFL`) and `launch.py`'s report did not — so on the CLI
#: path every market-scoped test filtered its entire population away and
#: reported "0 of 80" forever. A query shape that two places have to
#: agree on is a query shape that belongs in one.
ROW_SQL = ("SELECT date, sport, grade, market, odds, status, category "
           "FROM bets WHERE status IN ('won','lost') "
           "AND category IN ('main','paper','longshot') "
           "AND stake_units > 0")


def rows_for(conn) -> list:
    """Journal rows in the shape `report` expects."""
    return [dict(r) for r in conn.execute(ROW_SQL)]


def ensure_registered(path=None) -> dict:
    """Idempotent: registers the standing tests if they are not there."""
    store = register(B_MINUS, path)
    store = register(A_BAND_NFL, path)
    store = register(RECEPTIONS_A_NFL, path)
    store = register(TD_EDGE_NFL, path)
    # A_BAND_NFL asked "does A beat B+". Slicing by grade AND market
    # answered it — the deficit is one cell, A-graded receptions — and
    # RECEPTIONS_A_NFL asks that sharper question with a remedy that
    # moves something. The original's did not: see `supersede`.
    try:
        store = supersede(
            A_BAND_NFL["id"], RECEPTIONS_A_NFL["id"],
            "its remedy named engine.quality.STAKE_CAP_U, which stopped "
            "deciding a stake when Kelly-times-grade was retired — A and B+ "
            "already take the same fraction, so the test would have fired "
            "and changed nothing. The successor tests the one market the "
            "deficit is actually in, and names the 40-point edge component "
            "of the quality score, which does decide the grade",
            path)
    except KeyError:                                          # pragma: no cover
        pass
    return store


def report(rows: list[dict], path=None) -> list[dict]:
    store = ensure_registered(path)
    return [verdict(t, rows) for t in store["tests"]]
