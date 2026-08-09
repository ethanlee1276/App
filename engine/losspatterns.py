"""Mine the journal for the patterns behind the losses.

The temperature refit (engine/calibrate.py) learns one dial per market —
it can say "total_bases ran hot" but never WHERE. This module is the next
rung of the same ladder: slice every settled bet along conditions we
already record (side, price band, stated-probability band, horizon, book)
and hunt for pockets where the model's claims systematically miss.

Two disciplines keep it from becoming a pattern-hallucination machine,
which is the fate of every "trends" tab in this industry:

  * **A calibration test, not a win-rate test.** A slice is a finding when
    the model's own stated probabilities miss reality (said 64%, hit 51%),
    measured by the standard calibration z — (wins − Σp) / √Σp(1−p). Win
    rate alone would flag every honest longshot bucket as "bad".
  * **False-discovery control.** Slicing one record forty ways hands you
    two "significant" patterns by luck alone. Every slice tested enters a
    Benjamini–Hochberg correction, and only survivors are findings. BH
    assumes tests are independent or positively dependent — overlapping
    slices of one journal are the latter, so the correction is valid,
    just not free: the docstring says this so nobody "fixes" it into
    per-slice p-values later.

What a finding does mirrors what a boundary temperature already does: a
surviving slice that ran HOT by :data:`CLOSE_GAP_PTS` or more closes
itself, and :func:`veto` blocks any new pick that lands in it — same
journal-in, same verdict-out reproducibility as the rest of the loop.
Cold slices (model undersells itself) are reported as "watch", never
enforced: leaving money on the table is a finding, not a danger.

The banding functions are the single definition used by BOTH the miner
and the pick-time veto. Two copies would drift, and a veto that bands
odds differently from the miner enforces patterns nobody found.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

DEFAULT_PATH = Path("data/models/losspatterns.json")

#: A slice below this many settled bets is not tested at all. Small slices
#: are where every fake trend lives, and FDR can only correct the tests
#: it is told about.
MIN_N = 40
#: The false-discovery rate: of the slices flagged, at most this share is
#: expected to be luck.
ALPHA = 0.05
#: A surviving slice must run at least this many probability points HOT
#: (said − hit, in points) before it closes itself and vetoes picks.
#: Below it, a real miss is still a "watch" — worth showing, not worth
#: refusing bets over.
CLOSE_GAP_PTS = 5.0
#: …or this share of the claim itself. A market claiming 15% cannot miss by
#: five points without being catastrophically wrong, so an absolute-only bar
#: is unreachable for every low-probability book and merely lenient for
#: every high-probability one. A fifth of the claim is the same severity
#: wherever it lands: 15% -> 12% closes, and so does 60% -> 48%.
CLOSE_GAP_REL = 0.20


# --- the bands: one definition, used by miner and veto alike -----------------
def odds_band(odds) -> str | None:
    if odds is None:
        return None
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o <= -150:
        return "heavy favorites (-150 and shorter)"
    if o < -105:
        return "modest favorites (-149 to -106)"
    if o <= 105:
        return "near even money"
    if o < 200:
        return "underdogs (+106 to +199)"
    return "long shots (+200 and longer)"


def prob_band(prob) -> str | None:
    if prob is None:
        return None
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return None
    if not 0.0 < p < 1.0:
        return None
    if p < 0.5:
        return "stated under 50%"
    if p < 0.6:
        return "stated 50s"
    if p < 0.7:
        return "stated 60s"
    return "stated 70%+"


def horizon_band(days) -> str | None:
    if days is None:
        return None
    try:
        d = int(days)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return "same-day"
    if d <= 3:
        return "1-3 days out"
    return "4+ days out"


def lead_band(minutes) -> str | None:
    """How far ahead of the game's start the bet was logged.

    The capture_lag dimension, drafted by the triage bench and built for
    every sport: the whole intraday information cascade — weather,
    lineups, scratches, and the books' hardest repricing window (the last
    ninety minutes) — lands between an early log and first pitch, and a
    single 'same-day' horizon value could not see any of it.
    """
    if minutes is None:
        return None
    try:
        m = float(minutes)
    except (TypeError, ValueError):
        return None
    if m <= 0:
        return "after start"
    if m < 30:
        return "<30m out"
    if m < 90:
        return "30-90m out"
    if m < 180:
        return "90m-3h out"
    if m < 360:
        return "3-6h out"
    return "6h+ out"


def minutes_until(start_iso, now=None) -> float | None:
    """Minutes from ``now`` (UTC) to a kickoff/first-pitch stamp.

    Tolerates the two shapes the boards actually carry: full ISO with a Z
    or offset (usable) and a bare local clock like "13:00" (not — a clock
    with no date is no lead time, and guessing one would band bets into
    the wrong pocket)."""
    if not start_iso:
        return None
    try:
        start = _dt.datetime.fromisoformat(
            str(start_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is not None:
        start = start.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    now = now or _dt.datetime.utcnow()
    return round((start - now).total_seconds() / 60.0, 1)


def park_band(hr_index, roofed=False) -> str | None:
    """The park's home-run environment, banded per the triage spec.

    A closed roof (or a fixed dome) is its own band — indoor baseball is
    a different physics, and folding it into "neutral" would dilute both
    pockets."""
    if roofed:
        return "roof closed/dome"
    if hr_index is None:
        return None
    try:
        idx = float(hr_index)
    except (TypeError, ValueError):
        return None
    if idx < 0.90:
        return "suppressing park"
    if idx > 1.10:
        return "boosting park"
    return "neutral park"


def wind_band(wind_out, roofed=False, sport=None) -> str | None:
    """Wind at pick time, banded — with the sport deciding what wind MEANS.

    Baseball's wind is SIGNED against the park's real center-field
    bearing (+mph out, −mph in, 0 cross — the bearings live in
    engine/mlb/sources/mlbstats.py): direction is the physics of a fly
    ball. Football has no "out" — wind hurts the passing and kicking
    game by MAGNITUDE — so nfl/cfb band on speed alone. Slices are keyed
    by sport, so the two vocabularies can never pool. Indoors there is
    no wind dimension at all: the park band already says "roof", and a
    duplicate band would double-count the same fact."""
    if roofed or wind_out is None:
        return None
    try:
        w = float(wind_out)
    except (TypeError, ValueError):
        return None
    if sport in ("nfl", "cfb"):
        m = abs(w)
        if m < 8:
            return "calm (<8mph)"
        if m < 15:
            return "windy (8-15mph)"
        return "howling (15mph+)"
    if w <= -8:
        return "wind in hard"
    if w <= -3:
        return "wind in"
    if w < 3:
        return "calm/cross"
    if w < 8:
        return "wind out"
    return "wind out hard"


def lineup_band(slot, confirmed) -> str | None:
    """Batting slot and its certainty at pick time, banded per the triage
    spec. Every batter-prop over is plate appearances times per-PA
    production, and the slot is the PA half: a leadoff hitter gets about
    one more trip than the nine-hole. "Projected" bets carry silent
    scratch and demotion risk the price already reflects — if the gap
    lives in the projected bands, the blind spot is timing, not the
    hitting model."""
    if slot is None:
        return None
    try:
        s = int(slot)
    except (TypeError, ValueError):
        return None
    if s <= 0:
        return "not in lineup"
    tier = "1-3" if s <= 3 else "4-6" if s <= 6 else "7-9"
    return f"{'confirmed' if confirmed else 'projected'} {tier}"


def rest_band(days) -> str | None:
    """Days of rest at kickoff, banded. Football's schedule dimension:
    a four-day Thursday turnaround and a fortnight off a bye are
    different teams wearing the same logo. Delegates to engine.fatigue
    so the board and the miner can never drift apart on where a band
    starts."""
    from .fatigue import rest_band as _band
    return _band(days)


def clock_band(hour) -> str | None:
    """Kickoff on the team's OWN clock. A Pacific team in the 13:00 ET
    window starts at 10:00 by its body clock; a London kickoff is earlier
    still. Banded rather than continuous so a slice has a denominator."""
    try:
        h = float(hour)
    except (TypeError, ValueError):
        return None
    if h <= 10:
        return "body clock 10am or earlier"
    if h <= 11:
        return "body clock 11am"
    if h >= 20:
        return "body clock 8pm or later"
    return None          # the ordinary middle of the day discriminates nothing


def pen_band(score) -> str | None:
    """Bullpen workload behind a pick, banded — weighted relief innings
    over the two prior days (engine.mlb.bullpen). The multiplier this
    dimension drives has shipped for a long time without anything able to
    check it; banding it is what lets the record answer whether a tired
    pen is worth what the model pays for it."""
    try:
        v = float(score)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    from .mlb.bullpen import TIRED_MIN
    if v < 3.0:
        return "pen fresh"
    if v < TIRED_MIN:
        return "pen normal"
    if v < TIRED_MIN + 4:
        return "pen taxed"
    return "pen gassed"


def velo_band(delta) -> str | None:
    """A pitcher's velocity change against his own recent baseline, banded.

    MLB_MODEL §5: "A drop of 1+ mph is a red flag — check injury and
    mechanics reporting before trusting any projection of him." That
    threshold gets its own band so the miner can convict on exactly the
    thing the spec names, rather than on a bucket that blurs it.

    None when unmeasured, which is most rows: it is computed for pitcher
    markets only, and only when he has a comparable baseline. An
    unmeasured pitcher is not a steady one, and banding him "steady"
    would bury the signal under every hitter prop ever journaled.
    """
    if delta is None:
        return None
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return None
    if d <= -1.0:
        return "down 1+"
    if d <= -0.4:
        return "down"
    if d < 0.4:
        return "steady"
    return "up"


def tto_band(depth) -> str | None:
    """How deep a starter has been going, banded.

    §5 treats the third time through the order as a real penalty, so the
    bands split around it: a pitcher who reliably reaches a third pass is
    in a different spot from one pulled after two.

    It is a PROJECTION from his recent starts, never tonight's actual
    depth — that is not known when the bet is placed, and banding it
    would let the miner convict on information the pick never had.
    """
    if depth is None:
        return None
    try:
        d = float(depth)
    except (TypeError, ValueError):
        return None
    if d < 2.0:
        return "under 2x"
    if d < 2.6:
        return "about 2x"
    if d < 3.2:
        return "reaches 3x"
    return "past 3x"


def features_of(side=None, odds=None, prob=None, book=None,
                horizon_days=None, lead_min=None, park_hr=None,
                wind_out=None, roofed=False, lineup_slot=None,
                lineup_conf=False, sport=None, rest_days=None,
                body_clock=None, pen_own=None, pen_opp=None,
                velo_delta=None, tto_proj=None) -> dict:
    """The feature dict for one bet — mining and veto both come through
    here, so a pick is judged by exactly the dimensions it was mined on."""
    feats = {
        "side": (str(side).upper() or None) if side else None,
        "odds": odds_band(odds),
        "prob": prob_band(prob),
        "horizon": horizon_band(horizon_days),
        "book": (str(book) or None) if book else None,
        "lead": lead_band(lead_min),
        "park": park_band(park_hr, roofed),
        "wind": wind_band(wind_out, roofed, sport),
        "slot": lineup_band(lineup_slot, bool(lineup_conf)),
        "rest": rest_band(rest_days),
        "clock": clock_band(body_clock),
        # Two separate dimensions on purpose: the opposing pen is what
        # lifts a hitter's number, the own pen is what lengthens a
        # starter's. Pooling them would average two opposite effects.
        "pen_opp": pen_band(pen_opp),
        "pen_own": pen_band(pen_own),
        # §5's injury tell, as a dimension the miner can convict on.
        "velo": velo_band(velo_delta),
        # How deep he has been going. §5's third-time-through penalty.
        "tto": tto_band(tto_proj),
    }
    return {k: v for k, v in feats.items() if v is not None}


def records_from_ledger(conn) -> list[dict]:
    """Every graded single, with its stated probability and its features.

    Pushes are excluded — a push says nothing about whether the stated
    probability was honest. Bets journaled without a probability (imported
    rows, some game markets) cannot be calibration-tested and are skipped.
    """
    rows = conn.execute(
        "SELECT sport, market, side, odds, hit_prob, book, date, ts, status, "
        "category, "
        "lead_min, park_hr, wind_out, roofed, lineup_slot, lineup_conf, "
        "rest_days, body_clock, pen_own, pen_opp, velo_delta, tto_proj "
        "FROM bets WHERE status IN ('won','lost')").fetchall()
    out = []
    for r in rows:
        p = r["hit_prob"]
        if p is None or not 0.0 < float(p) < 1.0:
            continue
        try:
            horizon = (_dt.date.fromisoformat(r["date"])
                       - _dt.date.fromisoformat(str(r["ts"])[:10])).days
        except (TypeError, ValueError):
            horizon = None
        out.append({
            "sport": r["sport"], "market": r["market"], "prob": float(p),
            "won": 1 if r["status"] == "won" else 0,
            # Not a slicing dimension — a provenance field. The veto's
            # consequences land almost entirely on picks that would have
            # been `main`, and this journal is 227 main against 3,134
            # pooled, so a finding needs to say which book convicted it.
            "category": r["category"] or "?",
            "feats": features_of(side=r["side"], odds=r["odds"], prob=p,
                                 book=r["book"], horizon_days=horizon,
                                 lead_min=r["lead_min"], park_hr=r["park_hr"],
                                 wind_out=r["wind_out"],
                                 roofed=bool(r["roofed"]),
                                 lineup_slot=r["lineup_slot"],
                                 lineup_conf=bool(r["lineup_conf"]),
                                 velo_delta=r["velo_delta"],
                                 tto_proj=r["tto_proj"],
                                 rest_days=r["rest_days"],
                                 body_clock=r["body_clock"],
                                 pen_own=r["pen_own"], pen_opp=r["pen_opp"],
                                 sport=r["sport"]),
        })
    return out


# --- the statistics ----------------------------------------------------------
def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _slice_test(rows: list[dict]) -> dict | None:
    """Calibration z for one slice: did the stated probabilities, summed,
    predict the wins that actually arrived?"""
    n = len(rows)
    wins = sum(r["won"] for r in rows)
    said = sum(r["prob"] for r in rows)
    var = sum(r["prob"] * (1.0 - r["prob"]) for r in rows)
    if var <= 0:
        return None
    z = (wins - said) / math.sqrt(var)
    return {
        "n": n, "said": round(said / n, 4), "hit": round(wins / n, 4),
        "gap_pts": round((said - wins) / n * 100.0, 1),   # + = ran hot
        "z": round(z, 3),
        "p": min(1.0, 2.0 * (1.0 - _phi(abs(z)))),
    }


def _bh(findings: list[dict], alpha: float) -> list[dict]:
    """Benjamini–Hochberg: q-values in, survivors flagged. The number of
    tests m is EVERY slice tested, not every slice that looked odd —
    shrinking m after peeking is how false discovery control dies."""
    m = len(findings)
    if not m:
        return findings
    by_p = sorted(findings, key=lambda f: f["p"])
    threshold_rank = 0
    for i, f in enumerate(by_p, start=1):
        if f["p"] <= i / m * alpha:
            threshold_rank = i
    running_min = 1.0
    for i in range(m - 1, -1, -1):
        running_min = min(running_min, by_p[i]["p"] * m / (i + 1))
        by_p[i]["q"] = round(min(1.0, running_min), 4)
    for i, f in enumerate(by_p, start=1):
        f["survives"] = i <= threshold_rank
    return findings


#: A finding whose rows are at least this heavily one category is reported
#: as a measurement of that book rather than of the board. Not a veto and
#: not a filter — a label, because the pooled journal is 227 `main` bets
#: against 3,134 of everything, so "the model misses here" can be a
#: statement about the paper buckets while the block it produces lands on
#: real recommendations.
CATEGORY_DOMINANT = 0.80

#: A main-only re-test needs its own floor. Below this the honest
#: answer is "the book we gate has not seen this slice enough to
#: say", which is a different statement from "it disagrees".
MAIN_MIN_N = 25


def main_only_check(rows: list[dict]) -> dict | None:
    """The same calibration test, restricted to the bets we stood behind.

    THE DEFECT THIS EXISTS TO MEASURE. `records_from_ledger` pools every
    graded single across every journal category — roughly 300 `main`
    against 3,100 in the measurement buckets. A closure is then enforced
    by `veto()` against RECOMMENDATIONS, which are `main` and only `main`.
    So the evidence and the enforcement are drawn from different
    populations, and the module's own comment says so: "Labelled, never
    filtered".

    That is calibrate.py's blind spot with the sign flipped.
    `docs/SELECTION_CORRECTION.md` §2 shows the claim runs hot on selected
    bets while staying honest on the population — E[epsilon | selected] >
    0, the winner's curse — and concludes that a fit on unselected history
    can never see it. The miner has the opposite exposure: it pools the
    selected book in with ten times as much unselected material, so a real
    selection effect in `main` gets diluted toward nothing, while a slice
    that happens to be `main`-heavy inherits the curse and reads as a
    property of the slice.

    The doc also predicted the magnitude: "if the edge signal is mostly
    noise, the shrink needed is large." On 2026-08-09 the edge signal was
    measured at AUC 0.479 — noise. So the effect this cannot see is the
    large one.

    Returns the main-only test, or None when `main` is too thin to say
    anything, which is itself the finding for most slices.
    """
    # A record with no category IS a main record. `bets.category` is
    # declared `TEXT DEFAULT 'main'` and the pre-category migration
    # backfilled every old row to 'main', so absence means the headline
    # book — never "unknown, treat as paper". Reading it the other way
    # would demote every closure the moment a caller passed rows that
    # predate the column.
    m = [r for r in rows if (r.get("category") or "main") == "main"]
    if len(m) < MAIN_MIN_N:
        return {"n": len(m), "verdict": "too thin to check"}
    t = _slice_test(m)
    if t is None:
        return {"n": len(m), "verdict": "too thin to check"}
    t["verdict"] = ("agrees" if t["gap_pts"] > 0 and t["z"] < -1.0
                    else "not supported")
    return t


def _category_mix(rows: list[dict]) -> dict:
    """Share of a slice by journal category, biggest first."""
    counts: dict = {}
    for r in rows:
        counts[r.get("category") or "?"] = counts.get(r.get("category") or "?", 0) + 1
    n = len(rows) or 1
    return {k: round(v / n, 3)
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}


def _dedupe(findings: list[dict]) -> tuple[list, list]:
    """Split findings into distinct ones and restatements of those.

    The same fault bleed.py's `_dedupe` was written for, in the module next
    door. Ten "patterns" came out of one real journal and they are not ten
    facts: home_runs is 1,863 of the 2,434 rows in the "all markets OVER"
    slice, so the two are very nearly the same bets seen through two
    labels. Every market-level slice is also contained in its sport-level
    twin by construction. Printing them all as separate findings, each
    "surviving false-discovery control", makes one fact look like a pile of
    independent evidence.

    Kept: the smallest slice of each nested chain, which is the tightest
    true statement. Anything that contains a kept slice is a restatement
    and is labelled as one.

    This does NOT touch the BH correction. Overlapping slices are
    positively dependent, which is a case BH is valid for, so every one of
    these was correctly tested. The fault was only ever in the counting.
    """
    kept: list[dict] = []
    echoes: list[dict] = []
    for f in sorted(findings, key=lambda f: len(f.get("_rows") or ())):
        rows = f.get("_rows")
        cover = None
        if rows is not None:
            cover = next((k for k in kept
                          if (k.get("_rows") or set()) <= rows), None)
        if cover is None:
            kept.append(f)
        else:
            f["restates"] = (f"{cover['sport']}:{cover.get('market') or '*'}:"
                             f"{cover['dim']}={cover['value']}")
            echoes.append(f)
    return kept, echoes


def mine(records: list[dict], min_n: int | None = None,
         alpha: float | None = None) -> dict:
    """Slice the record two ways — within a market, and across a sport —
    test every slice big enough to mean something, and let BH decide what
    was actually found."""
    min_n = MIN_N if min_n is None else min_n
    alpha = ALPHA if alpha is None else alpha

    slices: dict[tuple, list[dict]] = {}
    #: Which rows landed in each slice, by position. Needed to tell a
    #: genuinely separate finding from the same bets wearing a second
    #: label — see _dedupe.
    members: dict[tuple, set] = {}
    for i, r in enumerate(records):
        for dim, val in r["feats"].items():
            for key in ((r["sport"], r["market"], dim, val),
                        (r["sport"], None, dim, val)):
                slices.setdefault(key, []).append(r)
                members.setdefault(key, set()).add(i)

    tested = []
    for (sport, market, dim, val), rows in sorted(slices.items(),
                                                  key=lambda kv: str(kv[0])):
        if len(rows) < min_n:
            continue
        t = _slice_test(rows)
        if t is None:
            continue
        t.update({"sport": sport, "market": market, "dim": dim, "value": val,
                  "_rows": members[(sport, market, dim, val)],
                  "categories": _category_mix(rows),
                  # What the slice looks like in the book the block will
                  # actually land on. Carried on every finding, so the
                  # question "does this transfer?" is answerable without
                  # re-running anything.
                  "main_only": main_only_check(rows)})
        tested.append(t)

    _bh(tested, alpha)
    findings = []
    for t in tested:
        if not t.pop("survives", False):
            continue
        # Only market-level slices may close. A sport-level slice pools
        # every market, so one bad pocket drags the aggregate under —
        # closing it would veto clean picks in markets that did nothing
        # wrong. Pooled slices point; specific slices convict.
        # Absolute OR relative, and the second one is why anything closes.
        #
        # A five-point bar cannot work across markets whose base rates run
        # from 12% to 60%. Home runs said 15% and hit 12% over 1,863 bets:
        # three points, so it never reached the bar — but that is a FIFTH
        # of the claim, on a sample big enough to put it near z 3.6, and it
        # survived false-discovery control. Measured on the real journal,
        # ten slices were found and none could close, every one of them a
        # low-probability market missing by less than five points because
        # its claims are barely above five points to begin with.
        #
        # The same absolute-vs-relative fault sits in selcheck's by-market
        # table: +2.9 points on a 14.7% claim is a fifth of it, +3.3 on a
        # 58.9% claim is a twentieth, and ranking them together compares
        # nothing.
        rel = (t["gap_pts"] / 100.0) / t["said"] if t.get("said") else 0.0
        t["gap_rel"] = round(rel, 4)
        hot = (t["gap_pts"] >= CLOSE_GAP_PTS or rel >= CLOSE_GAP_REL) \
            and t["market"] is not None
        t["action"] = "close" if hot else "watch"
        t["reading"] = (
            f"said {t['said']:.0%}, hit {t['hit']:.0%} over {t['n']} bets — "
            + (("ran hot; this slice closed itself"
                + (f" ({rel:.0%} of the claim)" if t["gap_pts"] < CLOSE_GAP_PTS
                   else "")) if hot
               else "ran hot pooled across markets — the specific slice decides closures"
               if t["gap_pts"] >= CLOSE_GAP_PTS
               else (f"ran hot — {t['gap_pts']:.0f}pts and {rel:.0%} of the "
                     f"claim, both under the bar, watching")
               if t["gap_pts"] > 0
               else "ran cold — money left on the table, not a danger"))
        findings.append(t)

    # One fault seen through several labels is one fault. Restatements are
    # kept and reported as such rather than dropped — a reader who does not
    # know a slice is contained in another cannot judge either.
    findings, echoes = _dedupe(findings)
    findings.sort(key=lambda f: (f["action"] != "close", f["q"]))
    echoes.sort(key=lambda f: f["q"])

    # A finding that is nearly all one journal category is a statement
    # about that book. The block it produces is not: it lands on whatever
    # the gate prices next, and this journal is 227 `main` against 3,134
    # pooled. Labelled, never filtered — see the module docstring.
    for f in findings + echoes:
        mix = f.get("categories") or {}
        top = next(iter(mix), None)
        if top and mix[top] >= CATEGORY_DOMINANT:
            f["measured_on"] = top
            if f["action"] == "close" and top != "main":
                f["reading"] += (f" — but {mix[top]:.0%} of these are "
                                 f"`{top}` bets, and the block lands on "
                                 f"recommendations")
    # THE CLOSURE IS DOWNGRADED WHEN THE BOOK IT GATES DOES NOT SUPPORT IT.
    #
    # The 80% label above catches only the extreme case. A slice that is
    # 55% `loose` and 45% `main` gets no label at all, and its gap is a
    # weighted average of two populations with different selection — which
    # is not a property of the slice in either of them.
    #
    # `veto()` blocks RECOMMENDATIONS. So the question that decides whether
    # a closure should fire is not "is this slice hot in the pool", it is
    # "is this slice hot in `main`". Where main cannot answer, the closure
    # is demoted to a watch: it keeps appearing, keeps accruing evidence,
    # and stops blocking picks on the strength of a different book.
    for f in findings + echoes:
        mo = f.get("main_only") or {}
        if f.get("action") != "close":
            continue
        if mo.get("verdict") == "agrees":
            continue
        f["action"] = "watch"
        f["demoted"] = mo.get("verdict") or "no main evidence"
        f["reading"] += (
            f" — NOT ENFORCED: on the {mo.get('n', 0)} `main` bets in this "
            f"slice the pattern "
            + ("has too little evidence to confirm"
               if mo.get("verdict") == "too thin to check"
               else "does not hold")
            + ", and a block would land on `main` alone")
    for f in findings + echoes:
        f.pop("_rows", None)

    return {
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "n_records": len(records), "tested": len(tested),
        "min_n": min_n, "alpha": alpha,
        "findings": findings,
        "restatements": echoes,
        # ENFORCEMENT IS DELIBERATELY UNCHANGED BY THE DEDUPE, and the
        # first cut of this got it wrong by taking `closed` from the
        # deduped list alone.
        #
        # Two slices can cover the identical rows and still enforce
        # differently: closing `prob_band=10-20%` refuses future props in
        # that band, closing `side=over` refuses every over. Identical
        # evidence, different forward scope. Dropping one because it
        # restates the other silently narrows the veto — a pricing change,
        # made as a side effect of a counting fix, which is exactly the
        # kind of thing that is supposed to need a human.
        #
        # So the dedupe is for READING. Every convicted slice still
        # enforces.
        "closed": [f for f in findings + echoes if f["action"] == "close"],
    }


# --- persistence and the pick-time veto --------------------------------------
def save(result: dict, path=None) -> Path:
    p = Path(path if path is not None else DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=1))
    return p


#: (path, mtime) → parsed store. veto() runs once per candidate prop —
#: thousands per build — and the store only changes when a settle pass
#: re-mines, so the mtime is the cache key that can never serve stale.
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
    """Mine the journal and persist the result — the nightly learning
    step, called from the settle pass right after grades land."""
    result = mine(records_from_ledger(lconn))
    save(result, path)
    return result


def veto(sport: str, market: str, side=None, odds=None, prob=None,
         book=None, horizon_days=None, lead_min=None, park_hr=None,
         wind_out=None, roofed=False, lineup_slot=None, lineup_conf=False,
         rest_days=None, body_clock=None, pen_own=None, pen_opp=None,
         velo_delta=None, tto_proj=None,
         path=None) -> str | None:
    """The reason this pick is blocked, or None.

    Consulted where is_reliable() is: a pick whose features land in a slice
    the miner closed gets refused, with the pattern spelled out — the same
    self-closure contract markets already live under, one level finer.
    ``lead_min`` is minutes to the game's start at pick time; a gate that
    does not know its clock passes None, and an unknown band never
    matches a closure — honest ignorance, never a false block."""
    store = load(path)
    feats = features_of(side=side, odds=odds, prob=prob, book=book,
                        horizon_days=horizon_days, lead_min=lead_min,
                        park_hr=park_hr, wind_out=wind_out, roofed=roofed,
                        lineup_slot=lineup_slot, lineup_conf=lineup_conf,
                        rest_days=rest_days, body_clock=body_clock,
                        velo_delta=velo_delta, tto_proj=tto_proj,
                        pen_own=pen_own, pen_opp=pen_opp,
                        sport=sport)
    for f in store.get("closed") or []:
        if f.get("sport") != sport:
            continue
        if f.get("market") is not None and f.get("market") != market:
            continue
        if feats.get(f.get("dim", "")) == f.get("value"):
            scope = f"{sport} {f['market']}" if f.get("market") else sport
            return (f"The record shows a blind spot here: {scope}, "
                    f"{f['value']} — {f.get('reading', 'ran hot')}")
    # The hypothesis lab's confirmed closures enforce through this same
    # gate — multi-dimension slices the single-dim miner never tests,
    # proposed by the LLM and convicted by the same statistics. One door,
    # so no engine needs to know the lab exists.
    try:
        from . import hypotheses as hyp
        return hyp.blocked(sport, market, feats)
    except Exception:                              # noqa: BLE001
        return None


# --- looking at it before it bites -------------------------------------------
def _format(result: dict) -> str:
    """The miner's own findings, in the order they would act.

    This exists because a closure is a PRICING change: a slice that closes
    starts refusing bets on the next build, and the house rule is that you
    see which slices close before the veto goes live. Reading the JSON is
    not the same as reading it — the numbers that decide are `said`, `hit`,
    the two bars, and which one crossed.
    """
    fs = result.get("findings") or []
    out = [
        "=" * 78,
        "WHAT THE JOURNAL SAYS ABOUT ITS OWN LOSSES",
        "=" * 78,
        f"  {result.get('n_records', 0):,} graded bets   "
        f"{result.get('tested', 0):,} slices big enough to test (n >= "
        f"{result.get('min_n')})   FDR {result.get('alpha')}",
        f"  bars: {CLOSE_GAP_PTS:.0f} points absolute  OR  "
        f"{CLOSE_GAP_REL:.0%} of the claim",
        "",
    ]
    if not fs:
        # An empty journal and a clean one print the same table unless the
        # two are told apart, and they mean opposite things: one is "no
        # slice missed by more than luck explains", the other is "this
        # machine has no record to mine".
        if not result.get("tested"):
            out += ["  Nothing was TESTED. Either the journal is empty on",
                    "  this machine, or no slice reached the minimum sample —",
                    "  this is not a verdict about the model.", ""]
        else:
            out += ["  Nothing survived false-discovery control. That is a",
                    "  result, not an error: no slice missed by more than luck",
                    "  explains.", ""]
        return "\n".join(out)

    out += ["  act    sport market            slice                       "
            "  n   said    hit   gap   rel",
            "  " + "-" * 74]
    for f in fs:
        mk = f.get("market") or "(all markets)"
        sl = f"{f.get('dim')}={f.get('value')}"
        out.append(
            f"  {f['action']:5}  {f['sport']:5} {mk:16.16}  {sl:26.26} "
            f"{f['n']:5}  {f['said']:5.1%}  {f['hit']:5.1%}  "
            f"{f['gap_pts']:+5.1f}  {f.get('gap_rel', 0):+5.0%}")

    echoes = result.get("restatements") or []
    if echoes:
        out += ["", f"  {len(echoes)} further slice(s) survived and are "
                    f"RESTATEMENTS of the above —", "  the same bets under a "
                    "wider label, not separate evidence:"]
        for f in echoes:
            mk = f.get("market") or "(all markets)"
            out.append(f"    {f['sport']} {mk} {f['dim']}={f['value']} "
                       f"({f['n']}) restates {f['restates']}")

    closed = [f for f in fs if f["action"] == "close"]
    out += ["", "=" * 78,
            f"WOULD CLOSE: {len(closed)} of {len(fs)}", "=" * 78]
    if not closed:
        out += ["  No slice reaches either bar. The veto stays empty and no",
                "  pick is refused.", ""]
    for f in closed:
        scope = f"{f['sport']} {f['market']}" if f.get("market") else f["sport"]
        which = ("both bars" if f["gap_pts"] >= CLOSE_GAP_PTS
                 and f.get("gap_rel", 0) >= CLOSE_GAP_REL
                 else "the absolute bar" if f["gap_pts"] >= CLOSE_GAP_PTS
                 else "the relative bar")
        out += [f"  * {scope}, {f['dim']}={f['value']}  (crossed {which})",
                f"      {f.get('reading', '')}",
                f"      every new pick landing here is refused"]
    out += ["", "  Nothing above has been written. Re-run with --apply to",
            "  persist, or let the nightly settle pass do it.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse
    import sys as _sys

    p = argparse.ArgumentParser(
        description="Mine the journal for the patterns behind the losses.")
    p.add_argument("--sport", default=None,
                   help="show only this sport's findings")
    p.add_argument("--min-n", type=int, default=None,
                   help=f"smallest slice to test (default {MIN_N})")
    p.add_argument("--alpha", type=float, default=None,
                   help=f"false-discovery rate (default {ALPHA})")
    p.add_argument("--apply", action="store_true",
                   help="write the result to the store the veto reads")
    a = p.parse_args(argv if argv is not None else _sys.argv[1:])

    from . import ledger
    result = mine(records_from_ledger(ledger.connect()),
                  min_n=a.min_n, alpha=a.alpha)
    shown = dict(result)
    if a.sport:
        shown["findings"] = [f for f in result["findings"]
                             if f["sport"] == a.sport]
    print(_format(shown))
    if a.apply:
        # Always the FULL result — filtering is a reading convenience and
        # must never narrow what the veto enforces.
        print(f"  wrote {save(result)}")
    return 0


if __name__ == "__main__":
    import sys as _s
    _s.exit(main())
