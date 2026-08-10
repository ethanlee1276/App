"""Rocket Radar — which Solana meme coins are igniting, and which are dying.

THE HONEST FRAME COMES BEFORE THE SIGNALS, because the spec's own base
rates are the most important thing on the page:

  ~1.4% of pump.fun tokens ever graduate. 60% of traders lose money and
  only 3% clear $1,000. Of high-return tokens, 82.8% show evidence of
  artificial growth (arXiv:2507.01963). ~41% of Solana meme volume is
  wash trading (VanEck). Rug pulls die with median lifecycles under an
  hour; median holding time is ~62 seconds.

So this page's genuine value is FILTERING, not prophecy — the spec says
it plainly: "a tracker's genuine value is filtering scams and enforcing
disciplined exits, not predicting moonshots." Nothing here is a buy
signal, nothing is journaled as a bet, and nothing touches the sports
model. It is a radar screen with the danger channel drawn as loudly as
the momentum channel.

WHAT THE SPEC ASKS FOR vs WHAT THE FREE TIER CARRIES, stated exactly
because the difference is the design (docs/MEMECOIN_MODEL.md carries the
full map):

  built here     volume acceleration (2nd derivative, across our own
                 snapshots), unique-buyer growth (GeckoTerminal carries
                 buyers/sellers per window), buy/sell pressure trend,
                 price acceleration, liq/MC, vol/MC, pair age, wash-trade
                 flag, paid-boost flag, LP-drop proxy, divergence
  parked (paid)  smart-money wallet scoring, holder velocity, bundle and
                 sniper detection, dev-sell alerts, bonding-curve stages
                 — each needs the firehose tier the spec prices out

The spec's two hard rules are enforced structurally:

  MOMENTUM AND RISK STAY SEPARATE. "Never blend them into one number
  that hides danger." Two scores, and risk is a GATE — a coin over the
  risk line never reaches the rocket list however hard it accelerates.
  COHORT-RELATIVE, NOT ABSOLUTE. "A raw $50k volume means nothing
  without context." Every momentum component is a percentile against the
  live board, and velocity is measured against the coin's OWN history.

And the spec's verdict on classic TA is adopted wholesale: no RSI, no
MACD, no Bollinger — "on sub-minute meme charts they are mostly noise."
Order flow is the model.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

HISTORY_PATH = Path("data/cache/memecoin_history.jsonl")
#: Snapshots older than this are pruned on write. Meme lifecycles are
#: minutes; six hours of history is generous, and the disk is shared.
HISTORY_KEEP_S = 6 * 3600

# --- risk: the GATE ----------------------------------------------------------
#: Liquidity below this is exit-impossible for anyone but the dev.
MIN_LIQ_USD = 5_000
#: Liq/MC under 3% — the spec's own threshold: one sell craters it.
MIN_LIQ_MC = 0.03
#: The wash-trade rule, verbatim from the arXiv study the spec cites:
#: volume spiking >500% while price moves <5% is volume with no one in it.
WASH_VOL_SPIKE = 5.0
WASH_PRICE_BAND = 5.0
#: Risk at or above this never reaches the rocket list.
RISK_GATE = 60

#: MomentumScore weights. The spec's table assigns smart-money 25%,
#: holder velocity 10% and social 5% — all firehose-tier inputs this
#: build does not have. Their 40 points are redistributed across the
#: order-flow signals we DO measure, keeping the spec's ordering
#: (acceleration and unique buyers stay on top). Stated here so nobody
#: mistakes the reweighting for the spec's own numbers.
WEIGHTS = {
    "vol_accel": 0.30,        # spec 25 — volume 2nd derivative
    "buyer_growth": 0.30,     # spec 20 — unique buyers, the anti-wash core
    "pressure": 0.25,         # spec 15 — buy/sell trend
    "price_accel": 0.15,      # convex onset
}


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def age_minutes(row, now_ms=None) -> float | None:
    """Pair age in minutes from either provider's creation stamp."""
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    ts = row.get("pair_created_at")
    if ts is None and row.get("created_at"):
        try:
            import datetime as _dt
            d = _dt.datetime.fromisoformat(
                str(row["created_at"]).replace("Z", "+00:00"))
            ts = d.timestamp() * 1000
        except (TypeError, ValueError):
            return None
    if ts is None:
        return None
    try:
        return max(0.0, (now_ms - float(ts)) / 60000.0)
    except (TypeError, ValueError):
        return None


# --- the snapshot store: our own tape ----------------------------------------
def record_snapshots(rows: list[dict], ts: float | None = None,
                     path: Path | None = None) -> int:
    """Append one compact row per coin per refresh, pruning as it goes.

    The linemoves pattern, deliberately: velocity and ACCELERATION — the
    spec's core "igniting" signal is a second derivative — need at least
    three sightings of the same coin, and no free endpoint hands out
    per-minute history. Our own polling builds the tape.
    """
    ts = ts if ts is not None else time.time()
    path = Path(path) if path else HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    keep: list[str] = []
    if path.exists():
        cutoff = ts - HISTORY_KEEP_S
        for line in path.read_text().splitlines():
            try:
                if float(json.loads(line).get("ts", 0)) >= cutoff:
                    keep.append(line)
            except (ValueError, TypeError):
                continue
    n = 0
    for r in rows:
        if not r.get("mint"):
            continue
        keep.append(json.dumps({
            "ts": ts, "mint": r["mint"],
            "price": r.get("price_usd"),
            "vol_m5": (r.get("volume") or {}).get("m5"),
            "liq": r.get("liquidity"),
            "buyers_m5": ((r.get("tx_m5") or {}).get("buyers")),
        }))
        n += 1
    path.write_text("\n".join(keep) + ("\n" if keep else ""))
    return n


def load_history(path: Path | None = None) -> dict:
    """{mint: [snapshot, ...] oldest-first}."""
    path = Path(path) if path else HISTORY_PATH
    out: dict = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
            out.setdefault(r["mint"], []).append(r)
        except (ValueError, TypeError, KeyError):
            continue
    for v in out.values():
        v.sort(key=lambda r: r.get("ts", 0))
    return out


def accel(series: list, per_s: list) -> float | None:
    """Second derivative from the last three sightings, per minute².

    None below three points — the honest answer, and common for a coin
    seen for the first time. Zero would claim "steady" about a coin
    nobody has watched long enough to say.
    """
    if len(series) < 3:
        return None
    (v0, t0), (v1, t1), (v2, t2) = [
        (s, t) for s, t in zip(series[-3:], per_s[-3:])]
    if None in (v0, v1, v2) or t2 <= t1 or t1 <= t0:
        return None
    r1 = (v1 - v0) / ((t1 - t0) / 60.0)
    r2 = (v2 - v1) / ((t2 - t1) / 60.0)
    return (r2 - r1) / (((t2 - t0) / 2) / 60.0)


# --- indicators --------------------------------------------------------------
def indicators(row: dict, hist: list[dict] | None = None) -> dict:
    """Every per-coin signal the free tier can honestly compute."""
    vol = row.get("volume") or {}
    # GT's block WINS when both exist, and the order is load-bearing: a
    # merged row carries DexScreener's `txns` (buys/sells only, summed
    # across pools) AND GeckoTerminal's `tx_*` (buys/sells AND unique
    # buyers/sellers). Preferring DexScreener silently threw away the
    # unique-buyer data on every merged row — the one field this page
    # exists to watch — and the fading-buyers exit signal could never
    # fire. Found because a test coin built to be dying was not flagged.
    tx1 = row.get("tx_h1") or row.get("txns", {}).get("h1") or {}
    tx5 = row.get("tx_m5") or row.get("txns", {}).get("m5") or {}
    pc = row.get("price_change") or {}
    liq, mc = _f(row.get("liquidity")), _f(row.get("market_cap")) \
        or _f(row.get("fdv"))
    v1, v5 = _f(vol.get("h1")), _f(vol.get("m5"))

    buys1, sells1 = _f(tx1.get("buys"), 0.0), _f(tx1.get("sells"), 0.0)
    ratio1 = buys1 / sells1 if sells1 else (None if not buys1 else 99.0)
    buys5, sells5 = _f(tx5.get("buys"), 0.0), _f(tx5.get("sells"), 0.0)
    ratio5 = buys5 / sells5 if sells5 else (None if not buys5 else 99.0)

    out = {
        "age_min": age_minutes(row),
        "liq_mc": (liq / mc) if (liq and mc) else None,
        "vol_mc_h1": (v1 / mc) if (v1 and mc) else None,
        "ratio_h1": round(ratio1, 3) if ratio1 is not None else None,
        "ratio_m5": round(ratio5, 3) if ratio5 is not None else None,
        # Rising m5 ratio against h1 = pressure building NOW.
        "pressure_trend": (round(ratio5 - ratio1, 3)
                           if None not in (ratio5, ratio1) else None),
        # Convexity proxy from the provider windows: m5 pace vs h1 pace.
        # Positive = the last five minutes outrun the hour — parabolic
        # onset. (h1 % / 12) is the hour restated per five minutes.
        "price_accel_w": (round(_f(pc.get("m5"), 0.0)
                                - _f(pc.get("h1"), 0.0) / 12.0, 3)
                          if pc.get("m5") is not None
                          and pc.get("h1") is not None else None),
        # m5 volume against its share of the hour, same construction.
        "vol_spike": (round(v5 / (v1 / 12.0), 2)
                      if v5 and v1 else None),
        "buyers_m5": tx5.get("buyers"),
        "sellers_m5": tx5.get("sellers"),
    }
    # The wash rule, arXiv thresholds: big volume, no price.
    out["wash_flag"] = bool(
        out["vol_spike"] is not None and out["vol_spike"] >= WASH_VOL_SPIKE
        and abs(_f(pc.get("m5"), 0.0)) < WASH_PRICE_BAND)
    # Our own tape: true second derivatives once three sightings exist.
    if hist:
        ts = [h.get("ts") for h in hist]
        out["vol_accel"] = accel([_f(h.get("vol_m5")) for h in hist], ts)
        out["price_accel"] = accel([_f(h.get("price")) for h in hist], ts)
        out["buyer_accel"] = accel([_f(h.get("buyers_m5")) for h in hist], ts)
        liqs = [_f(h.get("liq")) for h in hist if _f(h.get("liq"))]
        if liqs and liq:
            # The LP-pull proxy: our last sighting vs now. A 20% drop in
            # one poll interval is either a pull or the start of one —
            # the spec ranks liquidity removal as the single most
            # destructive event, and this is the free tier's only eye
            # on it.
            out["liq_drop"] = round(1.0 - liq / liqs[-1], 4) \
                if liqs[-1] else None
    return out


# --- scoring: two numbers, never one -----------------------------------------
def _pct(value, cohort: list) -> float:
    """Percentile of `value` within the live cohort, 0..1."""
    xs = sorted(x for x in cohort if x is not None)
    if value is None or not xs:
        return 0.5
    below = sum(1 for x in xs if x < value)
    return below / len(xs)


def momentum_score(ind: dict, cohort: list[dict]) -> int:
    """0-100, cohort-relative. Components missing on a coin score at the
    cohort median rather than at zero — a coin seen once must not be
    punished for our tape being short."""
    comps = {
        "vol_accel": _pct(ind.get("vol_accel"),
                          [c.get("vol_accel") for c in cohort]),
        "buyer_growth": _pct(ind.get("buyer_accel"),
                             [c.get("buyer_accel") for c in cohort]),
        "pressure": _pct(ind.get("pressure_trend"),
                         [c.get("pressure_trend") for c in cohort]),
        "price_accel": _pct(ind.get("price_accel")
                            if ind.get("price_accel") is not None
                            else ind.get("price_accel_w"),
                            [c.get("price_accel")
                             if c.get("price_accel") is not None
                             else c.get("price_accel_w") for c in cohort]),
    }
    return round(100 * sum(WEIGHTS[k] * v for k, v in comps.items()))


def risk_score(row: dict, ind: dict) -> tuple[int, list[str]]:
    """0-100, higher = more dangerous, with the reasons. A GATE.

    The spec's critical flags that are OBSERVABLE free-tier are hard
    points; the firehose-tier ones (mint authority, honeypot, dev wallet)
    are in the doc's parked list and their absence is stated on the page
    rather than silently scored as safe.
    """
    score, why = 0, []
    liq = _f(row.get("liquidity"))
    if liq is not None and liq < MIN_LIQ_USD:
        score += 40
        why.append(f"liquidity ${liq:,.0f} — exit-impossible thin")
    lm = ind.get("liq_mc")
    if lm is not None and lm < MIN_LIQ_MC:
        score += 25
        why.append(f"liq/MC {lm:.1%} — one sell craters it (spec flags <3%)")
    if ind.get("wash_flag"):
        score += 30
        why.append("volume spike with flat price — the wash-trade signature")
    if ind.get("liq_drop") is not None and ind["liq_drop"] > 0.2:
        score += 40
        why.append(f"liquidity down {ind['liq_drop']:.0%} since last look — "
                   f"LP pull pattern")
    a = ind.get("age_min")
    if a is not None and a < 30:
        score += 15
        why.append("under 30 minutes old — median rug dies inside an hour")
    if row.get("boosted"):
        score += 10
        why.append("someone is PAYING DexScreener to promote this")
    if row.get("has_socials") is False:
        score += 10
        why.append("no socials at all")
    return min(100, score), why


def exit_signals(ind: dict) -> list[str]:
    """The 'about to crash' channel, in the spec's priority order —
    restricted to what the free tier can see."""
    out = []
    if ind.get("liq_drop") is not None and ind["liq_drop"] > 0.2:
        out.append("LIQUIDITY LEAVING — the most destructive event there is")
    r5, r1 = ind.get("ratio_m5"), ind.get("ratio_h1")
    if r5 is not None and r1 is not None and r1 >= 1.0 > r5:
        out.append("buy/sell ratio flipped under 1 — distribution has begun")
    b, s = ind.get("buyers_m5"), ind.get("sellers_m5")
    if (b is not None and s is not None and s > b
            and (ind.get("vol_spike") or 0) > 1.5):
        out.append("volume rising while unique buyers fade — a few wallets "
                   "selling into thinning demand")
    pa = ind.get("price_accel") if ind.get("price_accel") is not None \
        else ind.get("price_accel_w")
    if (pa is not None and pa < 0
            and ind.get("buyer_accel") is not None
            and ind["buyer_accel"] < 0):
        out.append("momentum divergence — price and buyers both rolling over")
    return out


def build_board(rows: list[dict], history: dict | None = None,
                now_ms=None) -> dict:
    """The whole page: every coin scored, the two channels split.

    ROCKET requires clearing the risk gate; EXIT ignores the gate
    entirely — a dangerous coin crashing is exactly what the danger
    channel is for.
    """
    history = history or {}
    scored = []
    for r in rows:
        ind = indicators(r, history.get(r.get("mint")))
        if now_ms is not None:
            ind["age_min"] = age_minutes(r, now_ms)
        scored.append({**r, "ind": ind})
    cohort = [s["ind"] for s in scored]
    for s in scored:
        s["momentum"] = momentum_score(s["ind"], cohort)
        s["risk"], s["risk_why"] = risk_score(s, s["ind"])
        s["exit_why"] = exit_signals(s["ind"])
    rocket = sorted([s for s in scored if s["risk"] < RISK_GATE],
                    key=lambda s: -s["momentum"])
    exits = sorted([s for s in scored if s["exit_why"]],
                   key=lambda s: -len(s["exit_why"]))
    return {
        "coins": scored,
        "rocket": [s["mint"] for s in rocket[:10]],
        "exits": [s["mint"] for s in exits[:10]],
        "gated": sum(1 for s in scored if s["risk"] >= RISK_GATE),
        "n": len(scored),
    }
