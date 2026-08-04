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


def wind_band(wind_out, roofed=False) -> str | None:
    """Signed wind toward center field at pick time, banded.

    ``wind_out`` is +mph blowing out, −mph blowing in, 0 for cross —
    derived from the weather layer's park-relative classification (the
    CF bearings live in engine/mlb/sources/mlbstats.py). Indoors there
    is no wind dimension at all: the park band already says "roof", and
    a duplicate band would double-count the same fact."""
    if roofed or wind_out is None:
        return None
    try:
        w = float(wind_out)
    except (TypeError, ValueError):
        return None
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


def features_of(side=None, odds=None, prob=None, book=None,
                horizon_days=None, lead_min=None, park_hr=None,
                wind_out=None, roofed=False, lineup_slot=None,
                lineup_conf=False) -> dict:
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
        "wind": wind_band(wind_out, roofed),
        "slot": lineup_band(lineup_slot, bool(lineup_conf)),
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
        "lead_min, park_hr, wind_out, roofed, lineup_slot, lineup_conf "
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
            "feats": features_of(side=r["side"], odds=r["odds"], prob=p,
                                 book=r["book"], horizon_days=horizon,
                                 lead_min=r["lead_min"], park_hr=r["park_hr"],
                                 wind_out=r["wind_out"],
                                 roofed=bool(r["roofed"]),
                                 lineup_slot=r["lineup_slot"],
                                 lineup_conf=bool(r["lineup_conf"])),
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


def mine(records: list[dict], min_n: int | None = None,
         alpha: float | None = None) -> dict:
    """Slice the record two ways — within a market, and across a sport —
    test every slice big enough to mean something, and let BH decide what
    was actually found."""
    min_n = MIN_N if min_n is None else min_n
    alpha = ALPHA if alpha is None else alpha

    slices: dict[tuple, list[dict]] = {}
    for r in records:
        for dim, val in r["feats"].items():
            slices.setdefault((r["sport"], r["market"], dim, val), []).append(r)
            slices.setdefault((r["sport"], None, dim, val), []).append(r)

    tested = []
    for (sport, market, dim, val), rows in sorted(slices.items(),
                                                  key=lambda kv: str(kv[0])):
        if len(rows) < min_n:
            continue
        t = _slice_test(rows)
        if t is None:
            continue
        t.update({"sport": sport, "market": market, "dim": dim, "value": val})
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
        hot = t["gap_pts"] >= CLOSE_GAP_PTS and t["market"] is not None
        t["action"] = "close" if hot else "watch"
        t["reading"] = (
            f"said {t['said']:.0%}, hit {t['hit']:.0%} over {t['n']} bets — "
            + ("ran hot; this slice closed itself" if hot
               else "ran hot pooled across markets — the specific slice decides closures"
               if t["gap_pts"] >= CLOSE_GAP_PTS
               else "ran hot — under the closure bar, watching" if t["gap_pts"] > 0
               else "ran cold — money left on the table, not a danger"))
        findings.append(t)
    findings.sort(key=lambda f: (f["action"] != "close", f["q"]))

    return {
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "n_records": len(records), "tested": len(tested),
        "min_n": min_n, "alpha": alpha,
        "findings": findings,
        "closed": [f for f in findings if f["action"] == "close"],
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
                        lineup_slot=lineup_slot, lineup_conf=lineup_conf)
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
