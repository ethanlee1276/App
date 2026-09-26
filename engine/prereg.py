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
import re
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
         "markets", "price_band", "compare_price_band",
         "sides", "compare_sides",
         "min_n", "z_threshold", "registered", "decides"))
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


def implied(odds: int) -> float:
    """American odds as an implied probability, vig and all.

    Exported so a test's band can be written as `implied(-250)` rather
    than as a decimal somebody rounded. Written as 0.7143 the bound
    EXCLUDES -250 itself — its true implied is 0.714285… — so the band
    named "-250 or shorter" would quietly start at -251.
    """
    odds = int(odds)
    return (-odds) / ((-odds) + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def _in_band(r, band) -> bool:
    """Is this bet's price inside an implied-probability band?

    THE BAND IS IN IMPLIED PROBABILITY, NOT AMERICAN ODDS, and that is
    not a preference. American odds are not monotone in price: -163 is
    shorter than +122 and numerically smaller, so `lo <= odds <= hi`
    silently means something different on either side of the jump. A
    band written as a probability is monotone everywhere, and the
    numbers a person reasons about — "-250 needs 71.4% to break even" —
    are already in that unit.

    Half-open at the top so adjacent bands cannot both claim a bet.
    """
    o = r.get("odds")
    if o is None or not band:
        return False
    try:
        o = int(o)
    except (TypeError, ValueError):
        return False
    if not o:
        return False
    p = implied(o)
    lo, hi = band
    return lo <= p < hi or (hi >= 1.0 and p >= lo)


#: A calendar day and nothing else. Deliberately a SHAPE check before a
#: parse, because `date.fromisoformat` is not a validator here: on
#: Python 3.11+ it happily accepts the ISO WEEK form, and
#: `fromisoformat("2026-W01")` returns 2025-12-29 — a real date, in the
#: wrong year, with no error. Parsing alone would therefore turn the
#: football journal's week labels into December days and make the bug
#: below worse rather than catching it.
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_day(value) -> bool:
    """Can this journal date be placed on a calendar at all?

    THE BUG THIS EXISTS FOR, and it is the one property this whole module
    is built to guarantee. `bets.date` does not hold the same kind of
    thing for every sport: the NFL journals a SEASON-WEEK LABEL —
    "2026-W01", from `engine.sources.nflverse`'s slate key — while MLB,
    CFB and the rest journal ISO days. `engine.ledger` has already had to
    reason about this twice, in `--stranded` and in the record window,
    and both times concluded that within its own year a week label sorts
    ABOVE every ISO day, because "W" sorts above any digit.

    For a display window that is the safe direction: a current-season
    week is included rather than silently dropped. HERE IT IS EXACTLY
    BACKWARDS. `verdict`'s one non-negotiable rule is that bets which
    existed when the idea did cannot test it, enforced by `date > reg` —
    and a week label passes that comparison unconditionally. Every NFL
    bet in the journal has therefore been counted as "after" every
    registration, whenever it was actually placed. The exclusion rule
    reads healthy and does nothing, which is the failure this file's own
    header calls the one this codebase finds in itself most often.

    A row that cannot be placed in time is DROPPED, not guessed at, and
    `verdict` reports how many it dropped. Silently collecting zero is
    the other half of the same failure.
    """
    return bool(isinstance(value, str) and _ISO_DAY.match(value)
                and _safe_day(value))


def _safe_day(value: str) -> bool:
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _side_of(r) -> str:
    """The side a bet took, in one spelling.

    THE JOURNAL IS ALREADY CONSISTENT and this is not fixing it: every
    writer into `bets.side` upper-cases, and `engine.ledger` folds the
    YES/NO vocabulary onto OVER/UNDER at the moment it writes. Case is
    normalised here anyway because a test's population is a hand-typed
    list, and a registration that reads `["over"]` must not collect
    nothing forever while looking healthy — the failure mode `TD_EDGE_NFL`
    nearly died of, recorded in `verdict` twenty lines down.

    Deliberately does NOT map YES/NO itself. That translation belongs to
    the one writer that owns it; a second copy here is two rules that can
    drift, and the drift would be invisible because both sides would
    still return a plausible word.
    """
    return str(r.get("side") or "").strip().upper()


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
    mine = [r for r in rows
            if r.get("sport") == test["sport"]
            and r.get("status") in ("won", "lost")]
    # A ROW THAT CANNOT BE PLACED IN TIME IS DROPPED. See `_is_day`: the
    # NFL journals a season-week label rather than a calendar day, and a
    # week label sorts ABOVE every ISO date inside its own year — so
    # `date > reg` waved every football bet through as "after the
    # registration" no matter when it was taken. Counting them is the one
    # thing this module exists to prevent, so they are excluded, and the
    # number is carried on the result and said out loud in the reading.
    # A silent zero is the same failure with the sign flipped.
    undated = [r for r in mine if not _is_day(r.get("date"))]
    fresh = [r for r in mine if _is_day(r.get("date")) and r["date"] > reg]
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
    # PRICE, when the test names one. Optional and absent from every
    # test registered before 2026-09-06, so `_terms_hash` keying on it
    # only when a test carries it leaves their fingerprints untouched —
    # the same rule `markets` is added under, for the same reason.
    #
    # A test that splits on price puts the FULL grade ladder in both
    # `population` and `compare_to`; the bands are what separate them.
    if test.get("price_band"):
        pop = [r for r in pop if _in_band(r, test["price_band"])]
    if test.get("compare_price_band"):
        ref = [r for r in ref if _in_band(r, test["compare_price_band"])]
    # THE SIDE TAKEN, when the test names one. Optional and absent from
    # every test registered before 2026-09-09, added under the same rule
    # as `markets` and `price_band` before it: `_terms_hash` keys on it
    # only when a test carries it, so no existing registration's
    # fingerprint moves and none of them are voided by this line
    # existing.
    #
    # A test that splits on side puts the FULL grade ladder in both
    # `population` and `compare_to`, exactly as a price split does; the
    # sides are what separate the two arms.
    if test.get("sides"):
        want = {str(x).strip().upper() for x in test["sides"]}
        pop = [r for r in pop if _side_of(r) in want]
    if test.get("compare_sides"):
        want = {str(x).strip().upper() for x in test["compare_sides"]}
        ref = [r for r in ref if _side_of(r) in want]
    out["n"] = len(pop)
    out["n_reference"] = len(ref)
    out["undated"] = len(undated)
    # THE SENTENCE THAT STOPS THIS BEING A SILENT ZERO. Without it a test
    # blocked entirely by the journal's date format is indistinguishable
    # from a quiet week, and the reader has no way to tell "nothing has
    # happened yet" from "this can never collect anything".
    unplaced = ("" if not undated else
                f" {len(undated)} settled bet(s) were left out because "
                f"their journal date is a season-week label rather than a "
                f"day, so there is no way to tell whether they predate the "
                f"registration; until that is fixed this test cannot "
                f"collect them.")

    if len(pop) < test["min_n"]:
        out["status"] = "collecting"
        out["reading"] = (
            f"{len(pop)} of {test['min_n']} bets since {reg}. Nothing is "
            f"reported until the sample the terms named has arrived — "
            f"peeking early and calling it is how noise becomes a finding."
            + unplaced)
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
           "changes and the bucket stays.")
        + unplaced)
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
    # BOTH LADDERS since 2026-09-02, when the long-shot board moved to the
    # §10 0–100 letter (Ethan: "1. 0-100"): the 51 bets already collected
    # graded on the old words and must stay counted.
    "population": ["A+", "A", "B+", "Strong Play", "Play", "Lean"],
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


#: SUPERSEDES `td-edge-nfl-2026-08`, which was registered against a
#: touchdown model that no longer exists. `engine.touchdowns` now pulls
#: its share toward the player's slice of his offence's expected fantasy
#: points (XFP_SHARE_WEIGHT), measured worth +0.037 AUC on held-out
#: seasons over the historical rate it leaned on before. A test asks
#: whether a specific model's disagreement with the book is edge, so a
#: different model needs a different registration — the alternative is a
#: verdict about a thing that stopped being true halfway through
#: collection.
#:
#: The original is not edited. Its terms stay frozen and `supersede`
#: records the replacement beside them, which is the whole point of
#: having written them down.
TD_EDGE_NFL_XFP = {
    "id": "td-edge-nfl-xfp-2026-08",
    "claim": ("NFL anytime-TD picks lose at the model's own claimed rate: "
              "the board's disagreement with the book is not edge"),
    "sport": "nfl",
    # THE LONG-SHOT BOARD'S OWN VOCABULARY. `quality.letter` returns
    # A+/A/B+/Pass and `longshots._grade` returns Strong Play/Play/Lean/
    # Pass — different ladders entirely, and a test populated with the
    # wrong one collects nothing forever while looking healthy. All 51
    # bets behind this graded "Lean"; the other two are named so the
    # test does not go blind the day one clears a higher bar.
    # BOTH LADDERS since 2026-09-02, when the long-shot board moved to the
    # §10 0–100 letter (Ethan: "1. 0-100"): the 51 bets already collected
    # graded on the old words and must stay counted.
    "population": ["A+", "A", "B+", "Strong Play", "Play", "Lean"],
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
#: DRAFTED AND THEN DECLINED, 2026-09-06, and kept rather than deleted
#: because what we asked and why we did not run it is the record.
#:
#: `stakecheck --prices` came back with 26 settled bets at -250 or
#: shorter — 2.8% of the whole book. `min_n` 80 in a band that thin is
#: the TD_EDGE_NFL failure exactly: a test that sits at "0 of 80"
#: forever while looking perfectly healthy. The counts check was built
#: to catch this and caught it.
#:
#: It is also an answer rather than a dead end. The Edge board barely
#: bets chalk, so a price bar at -250 was never going to decide much.
#: The price question that DOES have a sample is LONG_PRICE_MLB below.
#:
#: DRAFTED 2026-09-06, NOT YET REGISTERED. `ensure_registered` does not
#: call this, deliberately — that call is what freezes the terms, and
#: Ethan reads them first. One line there activates it.
#:
#: WHERE IT CAME FROM. `stakecheck --select` compared three orderings of
#: the same 931 settled bets. Backed out of that table, the three arms
#: are not three ideas — they are three PRICES:
#:
#:     ordering   avg winner pays   hit     ROI
#:     edge            +122        44.6%   -0.9%
#:     prob            -163        56.2%   -9.3%
#:     market          -166        54.1%  -13.4%
#:     the lot         -102        48.1%   -4.5%
#:
#: The short-price arms lost most. That is the observation, and it is
#: NOT evidence, because it is the same 931 rows that produced it.
#:
#: WHY THE THRESHOLD IS BORROWED RATHER THAN FITTED. The obvious move is
#: to read a cut point off that table, and it is exactly the move this
#: module exists to refuse. So the bar is -250 for one reason only: it
#: is already `likely.HEAVIEST_PRICE`, chosen by Ethan on 2026-09-01
#: from the MOST LIKELY board's own settled night — a different board,
#: a different sample, a different question — with the arithmetic that
#: at -250 a bet needs 71.4% to break even. A number set on other
#: evidence is not fitted to this one.
#:
#: WHAT IT WOULD CHANGE. `engine.betting`'s gate has no price bar at
#: all: `favourite_surcharge` adjusts break-even, it does not refuse.
#: The Most Likely board has had one since 09-01; the Edge board never
#: got it.
#:
#: THE HONEST LIMIT, stated before it collects rather than after. ROI
#: tests are blunt. At the per-bet spread these prices carry, 80 bets
#: can only convict a deficit of roughly fifteen points; a real
#: five-point leak would sit inside the noise and report "not
#: supported". This can catch a board being eaten by chalk. It cannot
#: certify that chalk is fine.
HEAVY_PRICE_EDGE = {
    "id": "heavy-price-edge-2026-09",
    "claim": ("Edge-board bets priced at -250 or shorter lose more than "
              "the rest of the board at the same stake"),
    "sport": "mlb",
    "population": ["A+", "A", "B+"],
    "compare_to": ["A+", "A", "B+"],
    "price_band": [implied(-250), 1.01],
    "compare_price_band": [0.0, implied(-250)],
    "metric": "ROI at a flat 1u, split on the price taken",
    "min_n": 80,
    "decides": ("the Edge board gets the price bar the Most Likely board "
                "has had since 2026-09-01 — engine.betting's gate refuses "
                "a pick priced shorter than likely.HEAVIEST_PRICE"),
    "why_now": ("stakecheck --select put the short-price arm at -9.3% "
                "against -0.9% for the long-price arm over 931 settled "
                "bets, and the model's probability ordering was 94% the "
                "same bets as the book's own price ordering. Reading a "
                "cut point off that table would fit the test to the "
                "sample that suggested it, so the bar is borrowed from "
                "likely.HEAVIEST_PRICE, set on a different board's "
                "evidence, and the question is asked forward."),
}


#: DRAFTED 2026-09-06, NOT YET REGISTERED — one line in
#: `ensure_registered` starts it collecting.
#:
#: WHERE IT CAME FROM, AND WHY THAT SOURCE IS NOT THE OUTCOME DATA.
#: `stakecheck --clv` on 303 settled bets with a rebuilt close:
#:
#:     price band          bets      mean CLV    SE from 0
#:     shorter than +100    153        1.17%          5.5
#:     +100 to +119          74        2.14%          3.9
#:     +120 to +199          72        3.05%          5.0
#:
#: Monotone, and every band decisive. We get better prices the longer
#: the bet is. CLV is computed from the price we took against the price
#: at close — it does not look at whether the bet WON — so choosing a
#: band by CLV and then testing ROI is not the same sample answering
#: twice. `stakecheck --select` pointed the same way on ROI (the long
#: arm at -0.9% against the short arm's -9.3%), and that one IS outcome
#: data on these rows, so it is named as corroboration and not as the
#: reason.
#:
#: THE BOUNDARY IS NOT FITTED. +100 is even money — the point where a
#: dog becomes a favourite. It is where the CLV table already splits and
#: it is not a number anybody searched over.
#:
#: FRAMED AS THE SHORT BAND LOSING, because `verdict` reports
#: `supported` when the POPULATION is worse than its reference. The
#: claim is the same claim either way round; this is the direction the
#: module's arithmetic reads.
#:
#: WHAT IT WOULD CHANGE. `engine.betting.favourite_surcharge` already
#: sits in the gate — `net > favourite_surcharge(best.odds)` — and
#: already scales with price. If short prices really do lose more, that
#: surcharge widens. A live lever the gate reads every time it prices a
#: card, which is the test A_BAND_NFL failed: its remedy named a
#: constant that had stopped deciding anything.
#:
#: THE HONEST LIMIT. 80 bets convicts a deficit of roughly fifteen
#: points at the spread these prices carry. It can catch a board being
#: eaten by the short end. It cannot certify that the short end is fine.
LONG_PRICE_MLB = {
    "id": "long-price-mlb-2026-09",
    "claim": ("MLB bets priced +100 or shorter lose more than bets priced "
              "longer than +100, at the same stake"),
    "sport": "mlb",
    "population": ["A+", "A", "B+"],
    "compare_to": ["A+", "A", "B+"],
    "price_band": [implied(100), 1.01],
    "compare_price_band": [0.0, implied(100)],
    "metric": "ROI at a flat 1u, split on the price taken",
    "min_n": 80,
    "decides": ("the favourite surcharge widens — "
                "engine.betting.favourite_surcharge, which the gate already "
                "reads on every card it prices"),
    "why_now": ("closing-line value rises monotonically with price length "
                "across three bands at 3.9 to 5.5 standard errors, and CLV "
                "is measured on prices rather than outcomes, so the band it "
                "picks can be tested on ROI without asking one sample twice. "
                "The boundary is even money, not a searched number. 534 of "
                "931 settled bets sit in the short band, so min_n arrives in "
                "about nine days rather than never."),
}


#: DRAFTED 2026-09-09, NOT YET REGISTERED — one line in
#: `ensure_registered` starts it collecting, and one number has to be
#: checked on the droplet before that line is worth writing. See the
#: last paragraph.
#:
#: WHERE IT CAME FROM. The refusal audit, run on the droplet the day
#: before Week 1: `backtest.py --gate --real-lines` over 6,339 replayed
#: NFL props, 3,339 of which had a real harvested close. Of the 83 bets
#: the gate ADMITTED on a real book price, split by the side taken:
#:
#:     side     bets     ROI at a flat unit
#:     OVER       61          -24.7%
#:     UNDER      22          +20.8%
#:
#: A 45.5-point gap on roughly 1.9 standard errors.
#:
#: WHY THAT IS NOT A RESULT. Nobody asked that question in advance. The
#: same run printed a grade split (A +12.4% over 19, B+ -19.7% over 64)
#: and a basis split, and the side split is simply the one that read
#: worst. Picking the ugliest cell of a table nobody preregistered and
#: reporting its z is the move `gradecheck` refused to make on the B+
#: bucket at 2.1, and this is weaker than that was. It is a lead.
#:
#: WHY THE CLAIM IS PLAUSIBLE ANYWAY, which is what makes it worth a
#: registration rather than a shrug. The prop model projects a level and
#: bets the side of the posted number it lands on; anything that biases
#: the projection UP — a recency shade, a usage estimate fitted on
#: healthy weeks, a missing snap-count haircut — produces OVERs, not a
#: symmetric spread of overs and unders. A one-sided error therefore has
#: a mechanism, unlike a grade bucket, which does not.
#:
#: MARKETS ARE MANDATORY HERE, and not for tidiness. `engine.ledger`
#: journals a moneyline, a spread and a total ALL with `side='OVER'` —
#: the word is a placeholder on a game bet, not a direction. Left
#: unscoped this test would fill its OVER arm with team bets and answer
#: a question about game lines while claiming to answer one about props.
#: The four markets named are the edge board's player-prop menu
#: (engine.quality.MARKET_TIER tiers 1 and 2). `anytime_td` and
#: `pass_td` are deliberately out: they are the long-shot board, they
#: journal in the `longshot` bucket rather than this one, and they have
#: no UNDER to compare against at all.
#:
#: WHAT IT WOULD CHANGE. `engine.betting.temper_edge` already takes the
#: haircut as a parameter and callers already vary it by market tier
#: (engine.quality.TIER_SHRINK). A supported claim makes it vary by side
#: as well: an OVER keeps less of its raw disagreement with the book
#: than an UNDER does. That is a live lever on the number the gate
#: prices, not a constant that stopped deciding anything — the failure
#: `supersede` was written for when `A_BAND_NFL`'s remedy went inert.
#:
#: THE HONEST LIMIT, stated before it collects rather than after. At the
#: per-bet spread a -110 prop carries, 80 OVERs against the ~29 UNDERs
#: that ratio implies can only convict a gap of about 41 points — near
#: enough to the 45.5 observed that a real but smaller bias would report
#: "not supported". If the sides arrive nearer parity it reaches about
#: 30. This can catch a board that is badly one-sided. It cannot certify
#: that a ten-point tilt is not there.
#:
#: THE NUMBER TO CHECK BEFORE REGISTERING, which is the whole reason
#: this is drafted rather than live. `HEAVY_PRICE_EDGE` sits unregistered
#: two blocks up because its band holds 26 bets in the entire book: a
#: test that cannot finish is worse than no test, because it looks like
#: one. Nobody here knows how many NFL player-prop bets the edge board
#: journals in a week, and 18 weeks is the whole runway. One query on
#: the droplet settles it:
#:
#:     SELECT side, COUNT(*) FROM bets WHERE sport='nfl'
#:       AND market IN ('receptions','pass_yds','rush_yds','rec_yds')
#:       AND category IN ('main','paper') AND stake_units > 0
#:       AND date >= '2025-09-01' GROUP BY side;
#:
#: If last season's rate puts 80 OVERs inside the season, register it as
#: written. If it does not, the honest move is to lower `min_n` to what
#: the runway actually reaches and say in `metric` what that costs, or
#: to leave it drafted — not to register a clock that never rings.
#:
#: MEASURED 2026-09-09, AND STILL NOT REGISTERED — but for a different
#: reason than the first reading of the count suggested. Ethan ran it on
#: the droplet:
#:
#:     OVER    11
#:     UNDER   12
#:
#: THE FIRST READING WAS WRONG AND IT IS WORTH SAYING WHY, because the
#: mistake is the same one `_is_day` was written for an hour later. The
#: query carried `AND date >= '2025-09-01'`, and that clause filtered
#: NOTHING: the NFL journals a season-week label, and a week label sorts
#: above every ISO day in its own year, so every football row passed the
#: window unconditionally. So 23 is not "a season's worth". It is EVERY
#: NFL player-prop bet this journal has ever held, and all of them sit
#: under one season-week prefix, on the day the season opens. The NFL
#: prop book starts at Week 1; there is no history behind it at all.
#:
#: Which flips the sizing. Twenty-three bets in the first week is about
#: eleven OVERs a week, and `min_n: 80` then arrives around week seven —
#: comfortably inside an 18-week season. The population is NOT too thin.
#:
#: WHAT BLOCKS IT NOW IS THE JOURNAL, NOT THE RATE. Until `bets.date`
#: carries a calendar day for the NFL, `verdict` drops every football row
#: it cannot place in time (see `_is_day`), so this test would sit at "0
#: of 80" forever and say so out loud. That is the correct behaviour and
#: it is still a blocker: registering now would start a clock against a
#: population the reader cannot see. Register it when the NFL journal
#: writes a day.
#:
#: The terms below are LEFT EXACTLY AS DRAFTED rather than trimmed,
#: because a record of what was originally asked is the thing this module
#: exists to keep. Nothing was frozen — `register()` is the call that
#: freezes, and it was never made — so no goalpost has moved.
#:
#: AND THE COUNT SAYS SOMETHING THE LEAD DID NOT — more sharply now that
#: the rows are known to be a single week's selection rather than a
#: year's. Week 1 went out 11 overs to 12 unders. The replay's admitted
#: arm was 61 to 22, three quarters overs. Those are different populations — the replay prices
#: historical seasons through today's model, the journal is what the
#: board actually took — but the production board is plainly not
#: currently selecting three-to-one overs, which is the premise the
#: whole lead rests on. That does not refute a one-sided error in the
#: PROJECTION; it does say the SELECTION is not visibly lopsided, and
#: those are two different claims that the segment table conflated.
#:
#: THE TWO LIVE OPTIONS, neither of them taken yet:
#:
#:   1. POOL THE FOOTBALL. The claim is about a projection model that
#:      both leagues share, and college runs far more games. `verdict`
#:      filters on ONE `sport`, so this needs a `sports` field added the
#:      same optional, only-hashed-when-carried way `sides` was — and it
#:      needs the CFB count first, because if college is thin too the
#:      pooled test is just as dead and the field would be machinery
#:      built for nothing.
#:
#:   2. STOP ASKING IT WITH ROI. Twenty-three settled bets can never
#:      answer a 40-point ROI question, but the same 23 carry a
#:      projection and an outcome, and calibration needs far fewer rows
#:      than profit does. "Does the projection sit above the realised
#:      number more often than chance" is a different, cheaper question
#:      about the same suspected fault — and it is the hypothesis lab's
#:      machine next door, not this one's.
#:
#: THE OTHER FINDING, from the gate census the same evening: 286 props
#: analysed, 8 recommended. 113 never got a real price, 108 died at
#: calibration, 56 graded Pass, 1 was held on an injury. No market's bar
#: was unreachable, which rules out the worst case — the board is
#: refusing props, not being refused by its own thresholds. The 108 is
#: task #164's actual question.
OVER_BIAS_NFL = {
    "id": "over-bias-nfl-2026-09",
    "claim": ("NFL player props the edge board recommends on the OVER lose "
              "more than the ones it recommends on the UNDER, at the same "
              "stake: the model's disagreement with the book is one-sided"),
    "sport": "nfl",
    # THE FULL LADDER IN BOTH ARMS. The sides are what separate them, the
    # same way the price bands separate the two price tests. A grade
    # filter here would be a second cut on a sample already too small for
    # one.
    "population": ["A+", "A", "B+"],
    "compare_to": ["A+", "A", "B+"],
    "sides": ["OVER"],
    "compare_sides": ["UNDER"],
    "markets": ["receptions", "pass_yds", "rush_yds", "rec_yds"],
    "metric": "ROI at a flat 1u, split on the side taken",
    "min_n": 80,
    "decides": ("the market haircut varies by side as well as by market "
                "tier — the `shrink` argument engine.betting.temper_edge "
                "already takes, fed a smaller number for an OVER than for "
                "an UNDER"),
    "why_now": ("the refusal audit's own segment table put the 61 admitted "
                "OVERs at -24.7% against +20.8% for the 22 UNDERs, on real "
                "harvested closes. That is a table read after the fact, so "
                "it is a lead and not a finding — but a projection model "
                "biased high produces exactly this asymmetry and nothing "
                "else in the run has a mechanism behind it. Week 1 opens "
                "tomorrow, so the forward sample starts from an empty "
                "season rather than from rows the lead already saw."),
}


ROW_SQL = ("SELECT date, sport, grade, market, side, odds, status, category "
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
    store = register(TD_EDGE_NFL_XFP, path)
    # REGISTERED 2026-09-06 ON ETHAN'S WORD, after he read the terms:
    # "register it and keep going". The clock starts today and only bets
    # dated strictly after it count — the CLV table that suggested the
    # band is 303 rows that can never be part of the answer, which is the
    # point.
    #
    # HEAVY_PRICE_EDGE IS DELIBERATELY NOT HERE. Its band holds 26 bets in
    # the whole book; registering it would be writing a test that cannot
    # finish. See its own note.
    store = register(LONG_PRICE_MLB, path)
    # A_BAND_NFL asked "does A beat B+". Slicing by grade AND market
    # answered it — the deficit is one cell, A-graded receptions — and
    # RECEPTIONS_A_NFL asks that sharper question with a remedy that
    # moves something. The original's did not: see `supersede`.
    # The touchdown model changed underneath the original test.
    # engine.touchdowns now pulls its share toward the player's slice of
    # his offence's expected fantasy points, worth +0.037 AUC on held-out
    # seasons over the historical rate it had been leaning on. A
    # preregistration asks whether ONE model's disagreement with the book
    # is edge; carrying it across a model change would deliver a verdict
    # about something that stopped being true mid-collection. The
    # successor registers today, so rows priced by the old model fall
    # outside its window rather than being quietly counted.
    try:
        store = supersede(
            TD_EDGE_NFL["id"], TD_EDGE_NFL_XFP["id"],
            "the touchdown model it was registered against was replaced: "
            "engine.touchdowns now blends the share toward the player's "
            "xFP share of his offence (XFP_SHARE_WEIGHT), measured at "
            "+0.037 AUC on 8,442 held-out player-weeks. The claim is "
            "unchanged and re-asked of the model that will actually take "
            "the bets.", path)
    except KeyError:                                          # pragma: no cover
        pass
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
