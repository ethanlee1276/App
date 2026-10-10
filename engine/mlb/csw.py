"""A starter's CSW% — called strikes plus whiffs, per pitch — measured
before it moves a strikeout number.

engine/mlb/statcast.py has carried a CSW adjustment for strikeout props
since the Statcast layer was written (`LEAGUE_CSW`, "Elite CSW% …"), and
it has never run: the Savant loader only ever read the BATTER boards, so no
pitcher's profile carried a `csw_pct`. Found by the input-wiring audit,
2026-09-24 ("Pitcher strikeout props are missing their swing-and-miss
adjustment … I can load pitcher stats and test whether the adjustment helps
before it touches any numbers"); Ethan, 2026-09-25: "start working on all
of those".

NO NEW FEED. The pitch-by-pitch payloads `velocity.py` already caches for
every starter's last five starts carry the call on every pitch, so CSW is a
third read of games the board already fetched (arsenal.py is the second).

TWO HALVES, AND THE SECOND WAITS ON THE FIRST:

  * `measure` walks every cached game in date order and asks whether a
    starter's CSW over his previous five starts, put through the SHIPPED
    formula in statcast.py, predicts his strikeouts per batter better than
    his season-to-date strikeout rate alone. `python3 -m engine.mlb.csw`
    runs it on the box, where the games are.
  * `attach` puts the number on tonight's starters — on the profile the
    formula reads ONLY when `SHIPPED` is True. Until the measurement clears
    the bar (a squared-error improvement two standard errors from zero)
    it is False, and the number moves nothing.

Standard library only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

#: Flipped by hand when `measure` says SHIP on the box's games — and not
#: before. A number that has not beaten the rate it would adjust is a guess.
SHIPPED = False
#: The CALL codes that count (statsapi `details.call.code`): a called strike,
#: and the misses arsenal.WHIFF_CODES names. Foul tips are contact.
CALLED = {"C"}
#: Pitches before a starter's CSW is a number at all — about three starts.
MIN_PITCHES = 250
#: Starts behind the rolling CSW, as velocity.py reads them.
LOOKBACK = 5
#: The season-to-date strikeout rate is shrunk toward the league's with
#: this many batters' weight, so a pitcher's first start is not a 0% or 50%.
PRIOR_BF = 100
LEAGUE_K = 0.22


def _whiffs():
    from .arsenal import WHIFF_CODES
    return WHIFF_CODES


def csw_rate(rows: list[dict], pitcher_id=None) -> tuple[float | None, int]:
    """(called strikes + whiffs) / pitches for one pitcher's rows; (None, n)
    under `MIN_PITCHES`."""
    good = _whiffs() | CALLED
    n = hit = 0
    for r in rows:
        if pitcher_id is not None and r.get("pitcher_id") != pitcher_id:
            continue
        n += 1
        if r.get("called") in good:
            hit += 1
    return (round(hit / n, 4) if n >= MIN_PITCHES else None), n


def recent(person_id: int, season: int, limit: int = LOOKBACK) -> dict:
    """{"csw": rate or None, "pitches": n, "starts": k} over his last starts,
    off the cached playByPlay payloads (no request the board has not made)."""
    from .sources.pbp import fetch_playbyplay, pitches
    from .velocity import recent_start_pks
    rows: list = []
    k = 0
    for s in recent_start_pks(person_id, season, limit):
        try:
            rows += [r for r in pitches(fetch_playbyplay(s["game_pk"]))
                     if r.get("pitcher_id") == person_id]
            k += 1
        except Exception:                                    # noqa: BLE001
            continue
    rate, n = csw_rate(rows)
    return {"csw": rate, "pitches": n, "starts": k}


def attach(props, season: int) -> int:
    """Put each starter's recent CSW on his strikeout props (their
    `person_id`, as velocity.warm_starts reads them). Returns how many props
    got a number.

    The number rides on `prop.csw_recent` always (so it can be shown and
    audited) and on `prop.statcast.csw_pct` — the field statcast.py prices
    with — only when `SHIPPED`."""
    from .models import STRIKEOUTS, StatcastProfile
    got: dict = {}
    n = 0
    for p in props or []:
        if getattr(p, "market", None) != STRIKEOUTS:
            continue
        pid = getattr(p, "person_id", None)
        if pid is None:
            continue
        if pid not in got:
            got[pid] = recent(pid, season)
        r = got[pid]
        if r["csw"] is None:
            continue
        p.csw_recent = r
        n += 1
        if SHIPPED:
            if getattr(p, "statcast", None) is None:
                p.statcast = StatcastProfile()
            p.statcast.csw_pct = r["csw"]
    return n


# ── the measurement ───────────────────────────────────────────────────────


def starts_from_payload(payload: dict) -> list[dict]:
    """[{pitcher_id, date, pitches, csw_hits, bf, k}] for each game's two
    STARTERS (the first pitcher each side used), off one playByPlay payload."""
    from .sources.pbp import pitches
    plays = payload.get("allPlays") or []
    if not plays:
        return []
    date = str(((plays[0].get("about") or {}).get("startTime") or ""))[:10]
    first: dict = {}
    for pl in plays:
        half = (pl.get("about") or {}).get("halfInning")
        pid = ((pl.get("matchup") or {}).get("pitcher") or {}).get("id")
        if half and pid and half not in first:
            first[half] = pid
    rows = pitches(payload)
    good = _whiffs() | CALLED
    out = []
    for pid in set(first.values()):
        mine = [r for r in rows if r.get("pitcher_id") == pid]
        bf = k = 0
        for pl in plays:
            if ((pl.get("matchup") or {}).get("pitcher") or {}).get("id") != pid:
                continue
            ev = str((pl.get("result") or {}).get("eventType") or "")
            if not ev:
                continue
            bf += 1
            if ev.startswith("strikeout"):
                k += 1
        if bf and mine:
            out.append({"pitcher_id": pid, "date": date, "pitches": len(mine),
                        "csw_hits": sum(1 for r in mine if r.get("called") in good),
                        "bf": bf, "k": k})
    return out


def _adjusted(rate: float, csw: float) -> float:
    """statcast.py's strikeout adjustment, as shipped there, on a rate."""
    from .statcast import LEAGUE_CSW
    from ..statmath import clamp
    factor = clamp(csw / LEAGUE_CSW, 0.85, 1.20)
    mult = clamp(1.0 + (factor - 1.0) * 0.5, 0.90, 1.12)
    return rate * mult


def measure(starts: list[dict]) -> dict:
    """Walk every start in date order, per pitcher. For each with a rolling
    CSW behind it, compare two predictions of his strikeouts per batter:
    his shrunk season-to-date rate, and that rate through the CSW formula.

    {"n", "base_se", "csw_se" (mean squared error per batter, BF-weighted),
     "gain" (base − csw), "gain_se", "verdict": "SHIP" / "HOLD",
     "slope", "slope_se" (OLS of the base residual on CSW − league, for the
     record)}"""
    from .statcast import LEAGUE_CSW
    by: dict = {}
    for s in sorted(starts, key=lambda x: (x["date"], x["pitcher_id"])):
        by.setdefault(s["pitcher_id"], []).append(s)
    diffs, base_err, csw_err, xs, ys, ws = [], [], [], [], [], []
    for rows in by.values():
        for i, s in enumerate(rows):
            prior = rows[:i]
            window = prior[-LOOKBACK:]
            pitches = sum(r["pitches"] for r in window)
            if pitches < MIN_PITCHES:
                continue
            csw = sum(r["csw_hits"] for r in window) / pitches
            bf = sum(r["bf"] for r in prior)
            k = sum(r["k"] for r in prior)
            base = (k + LEAGUE_K * PRIOR_BF) / (bf + PRIOR_BF)
            adj = _adjusted(base, csw)
            actual = s["k"] / s["bf"]
            eb, ec = (actual - base) ** 2, (actual - adj) ** 2
            base_err.append(eb * s["bf"])
            csw_err.append(ec * s["bf"])
            diffs.append((eb - ec) * s["bf"])
            xs.append(csw - LEAGUE_CSW)
            ys.append(actual - base)
            ws.append(s["bf"])
    n = len(diffs)
    if n < 30:
        return {"n": n, "verdict": "HOLD", "why": "fewer than 30 starts with a CSW behind them"}
    tot_w = sum(ws)
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1))
    se = sd / math.sqrt(n)
    mx = sum(w * x for w, x in zip(ws, xs)) / tot_w
    my = sum(w * y for w, y in zip(ws, ys)) / tot_w
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    slope = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / sxx if sxx else 0.0
    resid = [y - my - slope * (x - mx) for x, y in zip(xs, ys)]
    s2 = sum(w * r * r for w, r in zip(ws, resid)) / max(1.0, tot_w - 2)
    slope_se = math.sqrt(s2 / sxx) if sxx else float("inf")
    return {"n": n, "base_se": round(sum(base_err) / tot_w, 6),
            "csw_se": round(sum(csw_err) / tot_w, 6), "gain": round(mean, 6),
            "gain_se": round(se, 6), "verdict": "SHIP" if mean > 2 * se else "HOLD",
            "slope": round(slope, 4), "slope_se": round(slope_se, 4)}


def cached_starts(cache_dir: Path | None = None) -> list[dict]:
    """Every starter's line off every cached final playByPlay payload."""
    from ..sources.fetch import CACHE_DIR
    out = []
    for f in sorted((cache_dir or CACHE_DIR).glob("mlb_pbp_*.json")):
        try:
            out += starts_from_payload(json.loads(f.read_text()))
        except Exception:                                    # noqa: BLE001
            continue
    return out


def report(res: dict) -> str:
    if res.get("n", 0) < 30 or "gain" not in res:
        return f"CSW: HOLD — {res.get('why', 'not enough starts')} (n={res.get('n', 0)})."
    return (f"CSW: {res['verdict']} — {res['n']} starts. Squared error per batter "
            f"{res['base_se']:.5f} on the strikeout rate alone, {res['csw_se']:.5f} with CSW; "
            f"gain {res['gain']:+.6f} ± {res['gain_se']:.6f} (SHIP needs two standard errors). "
            f"Slope of the miss on CSW: {res['slope']:+.3f} ± {res['slope_se']:.3f}.")


if __name__ == "__main__":
    print(report(measure(cached_starts())))
